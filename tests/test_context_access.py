"""Runtime enforcement of context grants (casl-lang issue #7) — ONE corpus against BOTH brokers (Python
in-process, Rust binary over stdio when built). Every access is decided against the grants on record at
that moment and journaled; only a granted access is sent.

Acceptance criteria of the issue, as cases:
  · a batch continues under one matching grant; a second account, an out-of-scope item or a different model
    endpoint is stopped before any data access or dispatch;
  · expired and revoked grants in an active and in a resumed run; a delegated grant that asks for more; a
    direct tool call that bypasses the access step;
  · denied accesses reveal nothing (nothing is sent); disclosed excerpts keep their origin's restrictions;
  · exact-request write approvals still gate writes independently.
"""
import json
import os

import pytest

from casl import context as cx, context_corpus as cc, egress
from casl.broker import Broker
from casl.client import Client
from casl.journal import Journal

from test_approval_signed import PROGRAM, _RUST, _signed

NOW = cc.NOW
SRC, FOLDER, UNI, PRIVATE, MODEL = cc.SRC, cc.FOLDER, cc.UNI, cc.PRIVATE, cc.MODEL
LLM_HOST, LLM_PATH, MODEL_ID = "api.anthropic.com", "/v1/messages", "claude-sonnet-5-5"
SECRET, EXCERPT = "s3cret-bearer-value", "vertraulicher Auszug aus der Abgabe"

CONTEXTS = {
    "find": {"cap": "find", "op": "search", "source": SRC, "resource": FOLDER},
    "fetch": {"cap": "fetch", "op": "read", "source": SRC, "resource": FOLDER},
    # `review` may pass on what `fetch` read; `digest` also what `find` found (search hits carry snippets)
    "review": {"cap": "review", "op": "disclose", "receiver": MODEL,
               "from": [{"cap": "fetch", "op": "read", "source": SRC, "resource": FOLDER}]},
    "digest": {"cap": "digest", "op": "disclose", "receiver": MODEL,
               "from": [{"cap": "fetch", "op": "read", "source": SRC, "resource": FOLDER},
                        {"cap": "find", "op": "search", "source": SRC, "resource": FOLDER}]},
}
HOSTS = {"find": SRC, "fetch": SRC, "review": LLM_HOST, "digest": LLM_HOST, "tasks": "tasks.example"}


def G(**kw):
    return cx.make_grant(cc.SK_USER, cc._grant(program=PROGRAM, **kw))


READ, SEARCH = G(id="g-read"), G(id="g-search", op="search")
DISCLOSE = G(id="g-disclose", op="disclose", receiver=MODEL)
ALL = [("grant", {"grant": g}, {"added": True}) for g in (SEARCH, READ, DISCLOSE)]


def url(path):
    return f"https://{SRC}{path}"


def fetch(item="m1", **kw):
    return ("access", {"site": "Fetch", "tool": "fetch", "instance": "run-1",
                       "request": {"method": "GET", "url": url(f"{FOLDER}/messages/{item}")}, **kw})


def find(**kw):
    return ("access", {"site": "Find", "tool": "find", "instance": "run-1",
                       "request": {"method": "GET", "url": url(FOLDER + "/messages") + "?$search=seminar"}, **kw})


def disclose(origins, cap="review", model=MODEL_ID, path=LLM_PATH, **kw):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": EXCERPT}]}, ensure_ascii=False)
    return ("access", {"site": "Review", "tool": cap, "instance": "run-1", "origins": origins,
                       "request": {"method": "POST", "url": f"https://{LLM_HOST}{path}", "body": body}, **kw})


SENT = {"decision": "granted", "performed": True, "outcome": "performed", "by": "broker"}

# name, [session, ...]; session = (config, [(call, expect[, save_as]), ...]); "$name" cites a saved access id
CORPUS = [
    ("batch_continues_under_one_grant", [({}, [
        ("grant", {"grant": READ}, {"added": True, "code": "ok", "id": "g-read", "issuer": "user"}),
        (fetch("m1"), dict(SENT, grants=["g-read"])), (fetch("m2"), SENT), (fetch("m3/attachments/a1"), SENT)])],
     ["run", "ctx_grant", "access", "access_result", "access", "access_result", "access", "access_result"]),
    ("declaration_alone_sends_nothing", [({}, [(fetch(), {"decision": "needs_grant", "code": "no_grant"})])],
     ["run", "access"]),
    ("second_account_is_stopped_before_data_access", [({"account": PRIVATE}, ALL + [
        (fetch(), {"decision": "needs_grant", "code": "no_grant"})])], ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access"]),
    ("out_of_scope_item_is_stopped", [({}, ALL + [
        (("access", {"site": "Fetch", "tool": "fetch", "instance": "run-1",
                     "request": {"method": "GET", "url": url("/v1.0/me/mailFolders/private/messages/m1")}}),
         {"decision": "denied", "code": "outside_declared_scope"}),
        (("access", {"site": "Find", "tool": "find", "instance": "run-1",          # a mailbox-wide search
                     "request": {"method": "GET", "url": url("/v1.0/me/messages") + "?$search=x"}}),
         {"decision": "denied", "code": "outside_declared_scope"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access", "access"]),
    ("disclosure_of_a_read_to_the_selected_model", [({}, ALL + [
        (fetch(), SENT, "r"),
        (disclose([{"access": "$r"}]), dict(SENT, grants=["g-disclose"]))])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access", "access_result", "access", "access_result"]),
    ("different_model_is_stopped_before_dispatch", [({}, ALL + [
        (fetch(), SENT, "r"),
        (disclose([{"access": "$r"}], model="claude-other"), {"decision": "denied", "code": "outside_declared_scope"}),
        (disclose([{"access": "$r"}], path="/v1/complete"), {"decision": "denied", "code": "outside_declared_scope"}),
        (disclose([{"access": "$r"}], model=None), {"decision": "denied", "code": "unsupported"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access", "access_result", "access", "access", "access"]),
    ("disclosure_needs_its_own_grant", [({}, [
        ("grant", {"grant": READ}, {"added": True}), (fetch(), SENT, "r"),
        (disclose([{"access": "$r"}]), {"decision": "needs_grant", "code": "no_grant", "missing": [0]})])],
     ["run", "ctx_grant", "access", "access_result", "access"]),
    ("search_hit_as_origin_is_bound_to_account_and_resource", [({}, ALL + [
        (find(), SENT, "s"),
        (disclose([{"access": "$s", "resource": FOLDER + "/messages/m7"}], cap="digest"), SENT),
        (disclose([{"access": "$s"}], cap="digest"), {"decision": "denied", "code": "origin_invalid"}),
        (disclose([{"access": "$s", "resource": "/v1.0/me/mailFolders/private/messages/m1"}], cap="digest"),
         {"decision": "denied", "code": "origin_invalid"}),
        (disclose([{"access": "$s", "resource": FOLDER + "/messages/m7"}]),          # `review` is `from fetch` only
         {"decision": "denied", "code": "outside_declared_scope"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access", "access_result", "access", "access_result",
      "access", "access", "access"]),
    ("origins_must_be_granted_accesses_of_this_run", [({}, ALL + [
        (fetch(), SENT, "r"),
        (disclose([]), {"decision": "denied", "code": "unsupported"}),
        (disclose([{"access": 999}]), {"decision": "denied", "code": "origin_invalid"}),
        (disclose([{"access": "$r"}], instance="run-2"), {"decision": "denied", "code": "origin_invalid"}),
        (fetch("m9", instance="run-2"), SENT, "other"),
        (disclose([{"access": "$other"}]), {"decision": "denied", "code": "origin_invalid"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access", "access_result", "access", "access", "access",
      "access", "access_result", "access"]),
    ("host_performed_search_then_disclosure", [({}, ALL + [
        # the OS searched its local index itself; the broker decided and recorded it
        (("access", {"site": "Find", "tool": "find", "instance": "run-1",
                     "host_performed": {"account": UNI, "source": SRC, "resource": FOLDER}}),
         {"decision": "granted", "by": "host", "grants": ["g-search"]}, "s"),
        (("access", {"site": "Find", "tool": "find", "instance": "run-1",
                     "host_performed": {"account": PRIVATE, "source": SRC, "resource": FOLDER}}),
         {"decision": "needs_grant", "code": "no_grant", "by": "host"}),
        (disclose([{"access": "$s", "resource": FOLDER + "/messages/m7"}], cap="digest"), SENT)])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access", "access", "access", "access_result"]),
    ("expiry_in_an_active_run", [
        ({}, [("grant", {"grant": G(id="g-short", exp=NOW + 10)}, {"added": True}), (fetch(), SENT)]),
        ({"now": NOW + 10}, [(fetch("m2"), {"decision": "needs_grant", "code": "expired"})])],
     ["run", "ctx_grant", "access", "access_result", "run", "access"]),
    ("revocation_blocks_the_next_access_and_survives_a_restart", [
        ({}, [("grant", {"grant": READ}, {"added": True}), (fetch(), SENT),
              ("revoke", {"id": "g-read"}, {"revoked": True}), ("revoke", {"id": "g-read"}, {"revoked": True}),
              (fetch("m2"), {"decision": "needs_grant", "code": "revoked"})]),
        ({}, [(fetch("m3"), {"decision": "needs_grant", "code": "revoked"})])],
     ["run", "ctx_grant", "access", "access_result", "revoke", "access", "run", "access"]),
    ("revoking_the_frame_stops_the_policy_grants", [({}, [
        ("grant", {"grant": cx.make_grant(cc.SK_POLICY, cc._grant(program=PROGRAM, id="pg"), frame=cc.FRAME)},
         {"added": True, "issuer": "policy"}),
        (fetch(), dict(SENT, grants=["pg"])), ("revoke", {"id": "f1"}, {"revoked": True}),
        (fetch("m2"), {"decision": "needs_grant", "code": "revoked"}),
        ("grant", {"grant": cx.make_grant(cc.SK_POLICY, cc._grant(program=PROGRAM, id="pg2"), frame=cc.FRAME)},
         {"added": False, "code": "frame_revoked"})])],
     ["run", "ctx_grant", "access", "access_result", "revoke", "access"]),
    ("bounded_reuse", [({}, [
        ("grant", {"grant": G(id="g-two", uses=2)}, {"added": True}),
        (fetch("m1"), SENT), (fetch("m2"), SENT), (fetch("m3"), {"decision": "needs_grant", "code": "exhausted"})])],
     ["run", "ctx_grant", "access", "access_result", "access", "access_result", "access"]),
    ("pending_request_survives_a_restart_and_is_rechecked", [
        ({}, [(fetch(), {"decision": "needs_grant", "code": "no_grant"}, "p"),
              (fetch(), {"decision": "needs_grant", "code": "no_grant", "access": "$p"})]),       # one pending record
        ({}, [(fetch(), {"decision": "needs_grant", "code": "no_grant", "access": "$p"}),
              ("grant", {"grant": G(id="g-old", exp=NOW)}, {"added": True}),                     # an expired grant
              (fetch(), {"decision": "needs_grant", "code": "expired"}),                         # …unlocks nothing
              ("grant", {"grant": READ}, {"added": True}),
              (fetch(), SENT)])],
     ["run", "access", "run", "ctx_grant", "access", "ctx_grant", "access", "access_result"]),
    ("delegated_grant_cannot_widen", [({}, [
        ("grant", {"grant": cx.make_grant(cc.SK_USER, cc._grant(program=PROGRAM, id="wide", resource="/v1.0/me"),
                                          parent=G(id="parent", resource=FOLDER + "/messages/m1"))},
         {"added": False, "code": "outside_parent"}),
        ("grant", {"grant": cx.make_grant(cc.SK_USER, cc._grant(program=PROGRAM, id="narrow", resource=FOLDER + "/messages/m1"),
                                          parent=G(id="parent"))}, {"added": True, "issuer": "derived"}),
        (fetch("m1"), dict(SENT, grants=["narrow"])),
        (fetch("m2"), {"decision": "needs_grant", "code": "no_grant"}),
        ("revoke", {"id": "parent"}, {"revoked": True}),
        (fetch("m1"), {"decision": "needs_grant", "code": "revoked"})])],
     ["run", "ctx_grant", "access", "access_result", "access", "revoke", "access"]),
    ("direct_tool_call_bypassing_the_access_step", [({}, ALL + [
        (("effect", {"site": "Fetch", "tool": "fetch", "request": {"method": "GET", "url": url(FOLDER + "/messages/m1")}}),
         {"allowed": False}),
        (("access", {"site": "X", "tool": "tasks", "instance": "run-1",
                     "request": {"method": "POST", "url": "https://tasks.example/x"}}),
         {"decision": "denied", "code": "undeclared"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access"]),
    ("write_approvals_stay_independent", [({}, ALL + [
        # every context grant is on record, and the irreversible write still needs its own signed approval
        (("effect", {"site": "Create", "tool": "tasks", "request": {"method": "POST", "url": "https://tasks.example/x"}}),
         {"allowed": False}),
        (("consent", {"site": "Create", "tool": "tasks", "approved": True}), {"granted": False, "code": "unsigned"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant"]),
    ("only_a_verifiable_grant_is_recorded", [({}, [
        ("grant", {"grant": cx.make_grant(cc.SK_OTHER, cc._grant(program=PROGRAM))}, {"added": False, "code": "unknown_key"}),
        ("grant", {"grant": {"granted": True}}, {"added": False, "code": "malformed"}),
        ("grant", {"grant": READ}, {"added": True}),
        ("grant", {"grant": READ}, {"added": False, "code": "exists"}),
        ("grant", {"grant": G(id="g-read", resource="/v1.0/me")}, {"added": False, "code": "duplicate_id"}),
        (fetch(), dict(SENT, grants=["g-read"]))])],
     ["run", "ctx_grant", "access", "access_result"]),
    ("destination_outside_the_allowlist", [({}, ALL + [
        (("access", {"site": "Fetch", "tool": "fetch", "instance": "run-1",
                     "request": {"method": "GET", "url": "https://evil.example" + FOLDER + "/messages/m1"}}),
         {"decision": "denied", "code": "destination_denied"})])],
     ["run", "ctx_grant", "ctx_grant", "ctx_grant", "access"]),
]
_IDS = [c[0] for c in CORPUS]


def _drive(client, steps, saved):
    try:
        for step in steps:
            (method, params), expect = (step[0], step[1]) if isinstance(step[0], tuple) else ((step[0], step[1]), step[2])
            save = step[-1] if isinstance(step[-1], str) else None

            def sub(v):
                if isinstance(v, str) and v.startswith("$"):
                    return saved[v[1:]]
                if isinstance(v, dict):
                    return {k: sub(x) for k, x in v.items()}
                if isinstance(v, list):
                    return [sub(x) for x in v]
                return v

            out = client._call(method, sub(params))
            for k, v in sub(expect).items():
                assert out.get(k) == v, (method, k, out, expect)
            if out.get("decision") in ("needs_grant", "denied") or out.get("allowed") is False:
                assert "body" not in out and "status" not in out          # a stopped access returns no data
            if save:
                saved[save] = out["access"]
    finally:
        client.close()


def _python(path, cfg, steps, saved):
    account, now = cfg.get("account", UNI), cfg.get("now", NOW)
    transports = {cap: egress.MediatedCapability(
        policy=egress.DestinationPolicy(allow_hosts=(host,)), transport=egress.MockTransport(status=200, body="SENSITIVE-RESPONSE"),
        inject=(("Authorization", f"Bearer {SECRET}"),), account=account) for cap, host in HOSTS.items()}
    j = Journal(path)
    try:
        b = Broker(granted_tools=set(HOSTS), irreversible_caps={"tasks"}, approvers=dict(cc.APPROVERS),
                   program_hash=PROGRAM, clock=lambda: now, transports=transports, journal=j, contexts=dict(CONTEXTS))
        _drive(Client(broker=b), steps, saved)
    finally:
        j.close()
    return transports


def _rust(path, cfg, steps, saved):
    account, now = cfg.get("account", UNI), cfg.get("now", NOW)
    env = {**os.environ, "CASL_BROKER_TOOLS": ",".join(HOSTS), "CASL_BROKER_IRREVERSIBLE": "tasks",
           "CASL_BROKER_APPROVERS": ",".join(f"{k}={v}" for k, v in cc.APPROVERS.items()),
           "CASL_BROKER_PROGRAM": PROGRAM, "CASL_BROKER_NOW": str(now), "CASL_BROKER_JOURNAL": path,
           "CASL_BROKER_EGRESS": ";".join(f"{c}={h}" for c, h in HOSTS.items()), "CASL_BROKER_MOCK_EGRESS": "200",
           "CASL_BROKER_EGRESS_AUTH": ";".join(f"{c}=PILOT_TOKEN" for c in HOSTS), "PILOT_TOKEN": SECRET,
           "CASL_BROKER_EGRESS_ACCOUNT": ";".join(f"{c}={account}" for c in HOSTS),
           "CASL_BROKER_CONTEXTS": json.dumps(CONTEXTS)}
    _drive(Client(command=[_RUST], env=env), steps, saved)


def _run_case(tmp_path, session, sessions, kinds):
    path, saved = str(tmp_path / "journal.sqlite"), {}
    for cfg, steps in sessions:
        session(path, cfg, steps, saved)
    j = Journal(path)
    try:
        assert j.verify() == (True, None, "ok")
        rows = j.entries()
    finally:
        j.close()
    assert [e[2] for e in rows] == kinds
    with open(path, "rb") as f:
        raw = f.read()
    # the audit trail carries request identity, decision and grant references — never content or secrets
    assert SECRET.encode() not in raw and EXCERPT.encode() not in raw and b"SENSITIVE-RESPONSE" not in raw
    for _seq, _ts, kind, body, _p, _h in rows:
        if kind == "access":
            b = json.loads(body)
            assert {"request", "decision", "code", "program", "site", "cap", "by"} <= set(b), b
            assert (b["decision"] == "granted") == ("grants" in b)
    return rows


@pytest.mark.parametrize("name,sessions,kinds", CORPUS, ids=_IDS)
def test_corpus_python(tmp_path, name, sessions, kinds):
    _run_case(tmp_path, _python, sessions, kinds)


@pytest.mark.skipif(_RUST is None, reason="rust casl-broker not built/runnable on this platform")
@pytest.mark.parametrize("name,sessions,kinds", CORPUS, ids=_IDS)
def test_corpus_rust(tmp_path, name, sessions, kinds):
    _run_case(tmp_path, _rust, sessions, kinds)


def test_a_stopped_access_never_reaches_the_transport(tmp_path):
    """Denied data cannot leak through result metadata: a request that is not granted is not sent at all."""
    stopped = [fetch(), find(), ("access", {"site": "Fetch", "tool": "fetch", "instance": "run-1", "request": {
        "method": "GET", "url": url("/v1.0/me/mailFolders/private/messages/m1")}})]
    transports = _python(str(tmp_path / "j.sqlite"), {}, [(s, {}) for s in stopped], {})
    assert all(t.transport.calls == [] for t in transports.values())


def test_the_same_pending_request_has_one_stable_id(tmp_path):
    path, saved = str(tmp_path / "j.sqlite"), {}
    outs = []
    for _ in range(2):                                   # two broker processes, one journal
        j = Journal(path)
        b = Broker(granted_tools=set(HOSTS), approvers=dict(cc.APPROVERS), program_hash=PROGRAM, clock=lambda: NOW,
                   journal=j, contexts=dict(CONTEXTS), transports={"fetch": egress.MediatedCapability(
                       egress.DestinationPolicy(allow_hosts=(SRC,)), egress.MockTransport(), account=UNI)})
        outs.append(Client(broker=b)._call(*fetch()))
        j.close()
    a, b2 = outs
    assert a["request"] == b2["request"] and a["access"] == b2["access"]
    assert a["pending"] == {"request": a["request"], "program": PROGRAM, "instance": "run-1", "site": "Fetch",
                            "cap": "fetch", "op": "read", "account": UNI, "source": SRC,
                            "resource": FOLDER + "/messages/m1"}
