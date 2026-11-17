"""casl.context_corpus — the fixtures of the context-grant contract (docs/context-grants.md), single-sourced
from the Python reference. One corpus, two consumers: tests/test_context_grants.py re-derives it and checks
it is in sync; rust/casl-broker/tests/context_differential.rs makes the Rust implementation reproduce every
expected value (parse → declared scope → grant verification → decision).

Regenerate:  PYTHONPATH=src python -m casl.context_corpus
"""
from __future__ import annotations

import json
import os
from typing import List

from casl import context as cx, core, ed25519, surface

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_RUST_CORPUS = os.path.join(_ROOT, "rust", "casl-broker", "tests", "context_corpus.json")
_EXAMPLE = os.path.join(_ROOT, "examples", "os_pilot", "seminar_review.casl")

NOW = 1_800_000_000
SK_USER, SK_HUMAN, SK_POLICY, SK_OTHER = bytes(range(32)), bytes(range(32, 64)), b"\x21" * 32, b"\x07" * 32
APPROVERS = {ed25519.public_key(SK_USER).hex(): "personal", ed25519.public_key(SK_HUMAN).hex(): "human"}
POLICY = ed25519.public_key(SK_POLICY).hex()

P, P2 = "sha256:seminar-review-v1", "sha256:grader-v1"
UNI, PRIVATE = "msgraph:uni:martin", "msgraph:private:martin"
SRC, FOLDER = "graph.microsoft.com", "/v1.0/me/mailFolders/seminar"
MODEL = "endpoint:api.anthropic.com/v1/messages#claude-sonnet-5-5"
OTHER_MODEL = "endpoint:api.openai.com/v1/chat/completions#gpt-x"


def _grant(**kw):
    g = {"v": 1, "kind": "grant", "id": "g1", "program": P, "instance": None, "op": "read", "account": UNI,
         "source": SRC, "resource": FOLDER, "exp": NOW + 3600, "uses": None}
    g.update(kw)
    return g


def _frame(**kw):
    f = {"v": 1, "kind": "frame", "id": "f1", "policy_key": POLICY, "ops": ["search", "read", "disclose"],
         "account": UNI, "source": SRC, "resource": FOLDER, "receivers": [MODEL], "program": None, "exp": NOW + 86400}
    f.update(kw)
    return f


FRAME = cx.make_frame(SK_USER, _frame())


def _user(**kw):
    return cx.make_grant(SK_USER, _grant(**kw))


def _policy(frame=FRAME, **kw):
    return cx.make_grant(SK_POLICY, _grant(**kw), frame=frame)


def _q(op="read", cap=None, resource=FOLDER + "/messages/m1", account=UNI, instance="run-1", **kw):
    q = {"program": P, "instance": instance, "cap": cap or {"search": "find", "read": "fetch"}[op], "op": op,
         "account": account, "source": SRC, "resource": resource}
    q.update(kw)
    return q


def _disclose(receiver=MODEL, origins=None, **kw):
    q = {"program": P, "instance": "run-1", "cap": "review", "op": "disclose", "receiver": receiver,
         "origins": origins if origins is not None else [{"account": UNI, "source": SRC,
                                                          "resource": FOLDER + "/messages/m1/attachments/a1"}]}
    q.update(kw)
    return q


READ, SEARCH = _user(id="g-read"), _user(id="g-search", op="search")
DISCLOSE = _user(id="g-disclose", op="disclose", receiver=MODEL)
BATCH = [SEARCH, READ, DISCLOSE]

# name, request, grant envelopes, state — the expected decision is computed by the reference
_DECIDE = [
    # the batch: one grant per operation covers every item in the folder
    ("batch_search", _q("search", resource=FOLDER), BATCH, {}),
    ("batch_read_item_1", _q("read"), BATCH, {}),
    ("batch_read_item_2", _q("read", resource=FOLDER + "/messages/m2/attachments/a1"), BATCH, {}),
    ("batch_disclose_to_selected_model", _disclose(), BATCH, {}),
    # each boundary on its own: a different account, resource scope, operation, receiver
    ("other_account_needs_its_own_grant", _q("read", account=PRIVATE), BATCH, {}),
    ("sibling_folder_is_outside_the_declared_scope", _q("read", resource="/v1.0/me/mailFolders/private/messages/m1"), BATCH, {}),
    ("prefix_is_segment_wise", _q("read", resource=FOLDER + "2/messages/m1"), BATCH, {}),
    ("read_grant_does_not_allow_search", _q("search", resource=FOLDER), [READ, DISCLOSE], {}),
    ("search_grant_does_not_allow_read", _q("read"), [SEARCH], {}),
    ("read_grant_does_not_allow_disclosure", _disclose(), [SEARCH, READ], {}),
    ("other_model_is_outside_the_declared_scope", _disclose(receiver=OTHER_MODEL), BATCH, {}),
    ("same_endpoint_other_model", _disclose(receiver="endpoint:api.anthropic.com/v1/messages#claude-other"), BATCH, {}),
    ("grant_for_another_receiver", _disclose(), [_user(id="g-d2", op="disclose", receiver=OTHER_MODEL)], {}),
    ("disclosure_of_two_origins_needs_both", _disclose(origins=[
        {"account": UNI, "source": SRC, "resource": FOLDER + "/messages/m1"},
        {"account": PRIVATE, "source": SRC, "resource": FOLDER + "/messages/m9"}]), BATCH, {}),
    ("grant_narrower_than_the_request", _q("read"), [_user(id="g-n", resource=FOLDER + "/messages/m2")], {}),
    ("grant_wider_than_declared_adds_nothing", _q("read", resource="/v1.0/me/mailFolders/private/messages/m1"),
     [_user(id="g-w", resource="/v1.0/me")], {}),
    # program / instance binding
    ("grant_for_another_program", _q("read"), [_user(id="g-p", program=P2)], {}),
    ("instance_bound_grant_same_instance", _q("read"), [_user(id="g-i", instance="run-1")], {}),
    ("instance_bound_grant_other_instance", _q("read", instance="run-2"), [_user(id="g-i", instance="run-1")], {}),
    ("instance_bound_grant_request_without_instance", _q("read", instance=None), [_user(id="g-i", instance="run-1")], {}),
    # bounded reuse, expiry, revocation
    ("expired", _q("read"), [_user(id="g-e", exp=NOW)], {}),
    ("revoked", _q("read"), [READ], {"revoked": ["g-read"]}),
    ("uses_left", _q("read"), [_user(id="g-u", uses=3)], {"used": {"g-u": 2}}),
    ("uses_exhausted", _q("read"), [_user(id="g-u", uses=3)], {"used": {"g-u": 3}}),
    ("a_live_grant_wins_over_a_dead_one", _q("read"), [_user(id="g-a", exp=NOW), _user(id="g-b")], {}),
    # missing, ambiguous and unsupported scopes fail closed
    ("capability_without_context", _q("read", cap="plain"), BATCH, {}),
    ("unknown_capability", _q("read", cap="nope"), BATCH, {}),
    ("operation_differs_from_declaration", _q("search", cap="fetch", resource=FOLDER), BATCH, {}),
    ("no_account", _q("read", account=""), BATCH, {}),
    ("path_with_dotdot", _q("read", resource=FOLDER + "/../private"), BATCH, {}),
    ("path_with_percent_escape", _q("read", resource=FOLDER + "/%2e%2e/private"), BATCH, {}),
    ("path_with_query", _q("read", resource=FOLDER + "/messages?$top=5"), BATCH, {}),
    ("path_with_wildcard", _q("read", resource=FOLDER + "/*"), BATCH, {}),
    ("ip_literal_source", _q("read", source="10.0.0.5"), BATCH, {}),
    ("disclosure_without_origins", _disclose(origins=[]), BATCH, {}),
    ("unsupported_receiver", _disclose(receiver="https://api.anthropic.com/v1/messages"), BATCH, {}),
    ("no_grants_at_all", _q("read"), [], {}),
    ("disclosure_request_without_a_model", _disclose(receiver="endpoint:api.anthropic.com/v1/messages"), BATCH, {}),
    # issued by the OS policy key inside a user-signed frame
    ("policy_grant_inside_frame", _q("read"), [_policy(id="pg", instance="run-1")], {}),
    ("frame_revoked_kills_its_grants", _q("read"), [_policy(id="pg")], {"revoked": ["f1"]}),
    # delegation: a derived grant narrows; revoking or exhausting the parent stops the child
    ("derived_grant", _q("read", resource=FOLDER + "/messages/m1/attachments/a1"),
     [cx.make_grant(SK_USER, _grant(id="child", resource=FOLDER + "/messages/m1"), parent=_user(id="parent"))], {}),
    ("derived_grant_outside_its_narrowed_scope", _q("read", resource=FOLDER + "/messages/m2"),
     [cx.make_grant(SK_USER, _grant(id="child", resource=FOLDER + "/messages/m1"), parent=_user(id="parent"))], {}),
    ("parent_revoked_stops_the_child", _q("read"),
     [cx.make_grant(SK_USER, _grant(id="child"), parent=_user(id="parent"))], {"revoked": ["parent"]}),
    ("parent_exhausted_stops_the_child", _q("read"),
     [cx.make_grant(SK_USER, _grant(id="child", uses=2), parent=_user(id="parent", uses=2))], {"used": {"parent": 2}}),
]

# name, envelope, revoked — the expected verification result is computed by the reference
_VERIFY = [
    ("user_grant", READ, []),
    ("human_key_grant", cx.make_grant(SK_HUMAN, _grant()), []),
    ("policy_grant_in_frame", _policy(), []),
    ("policy_grant_without_frame", cx.make_grant(SK_POLICY, _grant()), []),
    ("stranger", cx.make_grant(SK_OTHER, _grant()), []),
    ("tampered_payload", {**READ, "payload": READ["payload"].replace("seminar", "private")}, []),
    ("not_an_envelope", {"granted": True}, []),
    ("bad_hex", {**READ, "sig": "zz"}, []),
    ("user_grant_with_a_frame", cx.make_grant(SK_USER, _grant(), frame=FRAME), []),
    ("disclose_without_receiver", _user(op="disclose"), []),
    ("read_with_receiver", _user(receiver=MODEL), []),
    ("unsupported_resource", _user(resource=FOLDER + "/*"), []),
    ("uses_zero", _user(uses=0), []),
    ("disclose_grant_must_name_the_model", _user(op="disclose", receiver="endpoint:api.anthropic.com/v1/messages"), []),
    ("disclose_grant_vendor_slash_model", _user(op="disclose", receiver="endpoint:openrouter.ai/api/v1/chat/completions#anthropic/claude-sonnet"), []),
    ("disclose_grant_with_port", _user(op="disclose", receiver="endpoint:llm.example.org:8443/v1/chat#m"), []),
    ("disclose_grant_to_a_workflow", _user(op="disclose", receiver="workflow:Grader"), []),
    ("version_two", _user(v=2), []),
    # frames
    ("frame_signed_by_a_stranger", _policy(frame=cx.make_frame(SK_OTHER, _frame())), []),
    ("frame_names_another_policy_key", _policy(frame=cx.make_frame(SK_USER, _frame(policy_key=ed25519.public_key(SK_OTHER).hex()))), []),
    ("frame_tampered", _policy(frame={**FRAME, "payload": FRAME["payload"].replace("seminar", "private")}), []),
    ("frame_malformed", _policy(frame=cx.make_frame(SK_USER, _frame(ops=[]))), []),
    ("frame_revoked", _policy(), ["f1"]),
    ("frame_disclose_without_receivers", _policy(frame=cx.make_frame(SK_USER, _frame(receivers=[]))), []),
    ("grant_op_not_in_frame", _policy(frame=cx.make_frame(SK_USER, _frame(ops=["search"], receivers=[]))), []),
    ("grant_account_not_in_frame", _policy(account=PRIVATE), []),
    ("grant_resource_above_frame", _policy(resource="/v1.0/me"), []),
    ("grant_outlives_frame", _policy(exp=NOW + 86401), []),
    ("grant_receiver_not_in_frame", _policy(op="disclose", receiver=OTHER_MODEL), []),
    ("grant_receiver_in_frame", _policy(op="disclose", receiver=MODEL), []),
    ("frame_for_one_program", _policy(frame=cx.make_frame(SK_USER, _frame(program=P2))), []),
    # derivation
    ("derived_narrower", cx.make_grant(SK_USER, _grant(id="c", resource=FOLDER + "/messages/m1", program=P2), parent=READ), []),
    ("derived_wider_resource", cx.make_grant(SK_USER, _grant(id="c", resource="/v1.0/me"), parent=READ), []),
    ("derived_other_account", cx.make_grant(SK_USER, _grant(id="c", account=PRIVATE), parent=READ), []),
    ("derived_other_operation", cx.make_grant(SK_USER, _grant(id="c", op="search"), parent=READ), []),
    ("derived_later_expiry", cx.make_grant(SK_USER, _grant(id="c", exp=NOW + 7200), parent=READ), []),
    ("derived_more_uses", cx.make_grant(SK_USER, _grant(id="c", uses=5), parent=_user(id="p", uses=2)), []),
    ("derived_unbounded_from_bounded", cx.make_grant(SK_USER, _grant(id="c"), parent=_user(id="p", uses=2)), []),
    ("derived_drops_instance", cx.make_grant(SK_USER, _grant(id="c"), parent=_user(id="p", instance="run-1")), []),
    ("derived_by_policy_from_policy", cx.make_grant(SK_POLICY, _grant(id="c", resource=FOLDER + "/messages/m1"), parent=_policy(id="p")), []),
    ("derived_by_stranger", cx.make_grant(SK_OTHER, _grant(id="c"), parent=READ), []),
    ("derived_from_invalid_parent", cx.make_grant(SK_USER, _grant(id="c"), parent=cx.make_grant(SK_OTHER, _grant(id="p"))), []),
    ("derived_parent_revoked", cx.make_grant(SK_USER, _grant(id="c"), parent=_user(id="p")), ["p"]),
]

# name, a, b — delegation: what a delegated step may use of its caller's authority
_S = {"op": "read", "source": SRC, "resource": FOLDER}
_INTERSECT = [
    ("callee_narrower", _S, {**_S, "resource": FOLDER + "/messages/m1"}),
    ("callee_wider", {**_S, "resource": FOLDER + "/messages/m1"}, {**_S, "resource": "/v1.0/me"}),
    ("identical", _S, _S),
    ("disjoint_resources", _S, {**_S, "resource": "/v1.0/me/mailFolders/private"}),
    ("other_source", _S, {**_S, "source": "mail.example.org"}),
    ("other_operation", _S, {**_S, "op": "search"}),
    ("disclose_model_narrows", {"op": "disclose", "source": SRC, "resource": FOLDER, "receiver": "endpoint:api.anthropic.com/v1/messages"},
     {"op": "disclose", "source": SRC, "resource": FOLDER + "/messages/m1", "receiver": MODEL}),
    ("disclose_other_receiver", {"op": "disclose", "source": SRC, "resource": FOLDER, "receiver": MODEL},
     {"op": "disclose", "source": SRC, "resource": FOLDER, "receiver": OTHER_MODEL}),
    ("unsupported_scope", _S, {**_S, "resource": FOLDER + "/*"}),
]

# programs whose context clause must be REJECTED at parse (deny-by-default)
_CAPS = ('  agent R caps {{\n    find(q) scope "s" mode read context search source "mail.example.org" resource "/a" ttl 1 sig "1";\n'
         '    {line}\n  }}\n')
_REJECT = [
    ("unknown_operation", 'x(q) scope "s" mode read context index source "mail.example.org" resource "/a" ttl 1 sig "2";'),
    ("write_mode", 'x(q) scope "s" mode write context read source "mail.example.org" resource "/a" ttl 1 sig "2";'),
    ("default_mode_is_write", 'x(q) scope "s" context read source "mail.example.org" resource "/a" ttl 1 sig "2";'),
    ("ip_source", 'x(q) scope "s" mode read context read source "10.0.0.5" resource "/a" ttl 1 sig "2";'),
    ("source_with_scheme", 'x(q) scope "s" mode read context read source "https://mail.example.org" resource "/a" ttl 1 sig "2";'),
    ("relative_resource", 'x(q) scope "s" mode read context read source "mail.example.org" resource "a/b" ttl 1 sig "2";'),
    ("wildcard_resource", 'x(q) scope "s" mode read context read source "mail.example.org" resource "/a/*" ttl 1 sig "2";'),
    ("dotdot_resource", 'x(q) scope "s" mode read context read source "mail.example.org" resource "/a/../b" ttl 1 sig "2";'),
    ("trailing_slash", 'x(q) scope "s" mode read context read source "mail.example.org" resource "/a/" ttl 1 sig "2";'),
    ("receiver_url", 'x(q) scope "s" mode read context disclose receiver "https://llm.example.org/v1" from find ttl 1 sig "2";'),
    ("receiver_without_path", 'x(q) scope "s" mode read context disclose receiver "endpoint:llm.example.org" from find ttl 1 sig "2";'),
    ("from_unknown_capability", 'x(q) scope "s" mode read context disclose receiver "workflow:Grader" from nope ttl 1 sig "2";'),
    ("from_itself", 'x(q) scope "s" mode read context disclose receiver "workflow:Grader" from x ttl 1 sig "2";'),
    ("from_twice", 'x(q) scope "s" mode read context disclose receiver "workflow:Grader" from find, find ttl 1 sig "2";'),
    ("disclose_without_from", 'x(q) scope "s" mode read context disclose receiver "workflow:Grader" ttl 1 sig "2";'),
    ("read_without_resource", 'x(q) scope "s" mode read context read source "mail.example.org" ttl 1 sig "2";'),
]


def _reject_src(line: str) -> str:
    return "protocol Bad {\n  roles U, R;\n" + _CAPS.format(line=line) + "  U -> R : Go();\n}"


def example_source() -> str:
    with open(_EXAMPLE, encoding="utf-8") as fh:
        return fh.read()


def _verified(envs: List[dict]) -> List:
    """The grants a broker holds: structurally valid, properly chained. Revocation is STATE and is applied
    by `decide` (so a revoked grant reads as `revoked`, not as absent)."""
    out = []
    for env in envs:
        ok, _code, g, chain = cx.verify_grant(env, approvers=APPROVERS)
        if ok:
            out.append((g, chain))
    return out


def build_corpus() -> dict:
    src = example_source()
    proto = surface.parse(src)
    caps = sorted({c.tool for cs in proto.caps.values() for c in cs} | {"nope"})
    decide = []
    for name, q, envs, state in _DECIDE:
        revoked, used = state.get("revoked", []), state.get("used", {})
        expect = cx.decide(cx.declared(proto, q.get("cap")), q, _verified(envs), now=NOW,
                           revoked=frozenset(revoked), used=used)
        decide.append({"name": name, "request": q, "grants": envs, "revoked": revoked, "used": used, "expect": expect})
    verify = []
    for name, env, revoked in _VERIFY:
        ok, code, g, chain = cx.verify_grant(env, approvers=APPROVERS, revoked=frozenset(revoked))
        verify.append({"name": name, "grant": env, "revoked": revoked,
                       "expect": {"ok": ok, "code": code, "issuer": chain["issuer"], "frame": chain["frame"],
                                  "ancestors": chain["ancestors"]}})
    rejected = []
    for name, line in _REJECT:
        s = _reject_src(line)
        try:
            surface.parse(s)
        except SyntaxError:
            rejected.append({"name": name, "casl": s})
        else:
            raise AssertionError(f"reject fixture {name!r} parsed — the reference must reject it")
    return {
        "now": NOW, "approvers": APPROVERS, "program": src,
        "declared": {c: cx.declared(proto, c) for c in caps},
        "decide": decide, "verify": verify,
        "intersect": [{"name": n, "a": a, "b": b, "expect": cx.intersect(a, b)} for n, a, b in _INTERSECT],
        "selectors": {
            "hosts": {h: core.valid_host(h) for h in ["graph.microsoft.com", "a", "A.example", "10.0.0.5", "localhost",
                                                       "a..b", ".a", "a-", "exa mple.org", "", "xn--bcher-kva.example", "a_b.example"]},
            "paths": {p: core.valid_path(p) for p in ["/", "/a", "/a/b", "/a/", "//a", "/a//b", "/a/./b", "/a/../b", "a",
                                                       "", "/a?b", "/a#b", "/a/*", "/a%2fb", "/a b", "/a\\b", "/A/b", "/a/b:c@d",
                                                       "/me/messages('id')", "/ä"]},
            "covers": [[s, p, core.path_covers(s, p)] for s, p in [
                ("/a/b", "/a/b"), ("/a/b", "/a/b/c"), ("/a/b", "/a/bc"), ("/a/b", "/a"), ("/", "/a"), ("/a", "/"),
                ("/a/b", "/A/b"), ("/a/*", "/a/b"), ("/a", "/a/../b")]],
            "receivers": [[s, r, core.receiver_covers(s, r)] for s, r in [
                (MODEL, MODEL), ("endpoint:api.anthropic.com/v1/messages", MODEL), (MODEL, "endpoint:api.anthropic.com/v1/messages"),
                ("endpoint:api.anthropic.com/v1", MODEL), (MODEL, OTHER_MODEL), ("workflow:Grader", "workflow:Grader"),
                ("workflow:Grader", "workflow:Other"), ("workflow:Grader", MODEL), ("endpoint:api.anthropic.com", MODEL),
                ("workflow:1x", "workflow:1x"), ("endpoint:api.anthropic.com/v1/messages#", MODEL), ("llm", "llm"),
                ("endpoint:openrouter.ai/api/v1/chat/completions#anthropic/claude-sonnet",
                 "endpoint:openrouter.ai/api/v1/chat/completions#anthropic/claude-sonnet"),
                ("endpoint:openrouter.ai/api/v1/chat/completions#anthropic/claude-sonnet",
                 "endpoint:openrouter.ai/api/v1/chat/completions#anthropic/claude-opus"),
                ("endpoint:llm.example.org:8443/v1/chat#m", "endpoint:llm.example.org:8443/v1/chat#m"),
                ("endpoint:llm.example.org/v1/chat#m", "endpoint:llm.example.org:8443/v1/chat#m"),
                ("endpoint:llm.example.org:8443/v1/chat#m", "endpoint:llm.example.org/v1/chat#m"),
                ("endpoint:llm.example.org:443/v1/chat#m", "endpoint:llm.example.org:443/v1/chat#m"),
                ("endpoint:llm.example.org:08443/v1/chat#m", "endpoint:llm.example.org:08443/v1/chat#m"),
                ("endpoint:llm.example.org:99999/v1/chat#m", "endpoint:llm.example.org:99999/v1/chat#m"),
                ("endpoint:llm.example.org/v1/chat#a//b", "endpoint:llm.example.org/v1/chat#a//b"),
                ("endpoint:llm.example.org/v1/chat#/a", "endpoint:llm.example.org/v1/chat#/a")]],
        },
        "rejected": rejected,
    }


def to_text() -> str:
    return json.dumps(build_corpus(), indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    p = write_rust_corpus()
    c = build_corpus()
    print(f"wrote {len(c['decide'])} decisions, {len(c['verify'])} verifications, {len(c['intersect'])} intersections, "
          f"{len(c['rejected'])} rejected programs → {p}")
