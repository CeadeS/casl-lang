"""Signed approvals + request-bound consent — ONE corpus driven against BOTH brokers (Python reference
in-process, Rust binary over stdio when built). It pins, across implementations:
  · the pilot's acceptance criteria: an approved action runs; a changed action is blocked; an approval
    that is not signed by a trusted human key mints nothing (no agent self-approval);
  · every denial code of `casl.approval.verify_signed`;
  · the request digest (a signature made over a Python-computed digest must authorize the same request
    in Rust — including non-ASCII text), and Ed25519 itself (signed here, verified by ed25519-dalek).
"""
import json
import os
import subprocess

import pytest

from casl import approval, ed25519, egress
from casl.broker import Broker
from casl.client import BrokerError, Client

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = 1_800_000_000
PROGRAM = "sha256:3f6b0c1d-create-task-v1"
SK_PERSONAL, SK_HUMAN, SK_STRANGER = bytes(range(32)), bytes(range(32, 64)), b"\x07" * 32
APPROVERS = {ed25519.public_key(SK_PERSONAL).hex(): "personal", ed25519.public_key(SK_HUMAN).hex(): "human"}

REQ = {"method": "POST", "url": "https://tasks.example/api/lists/werkstatt/tasks",
       "headers": {"Content-Type": "application/json", "X-Account": "martin"},
       "body": json.dumps({"title": "Prüfaufgabe P-184 ✓ 😀", "due": "2026-11-20"}, ensure_ascii=False)}
REQ_CHANGED = {**REQ, "body": REQ["body"].replace("2026-11-20", "2026-12-20")}     # the frist moved
REQ_LIST_FORM = {"method": "post", "url": REQ["url"], "body": REQ["body"],         # same request, other spelling
                 "headers": [["X-Account", "martin"], ["Content-Type", "application/json"]]}


def _digest(req):
    return egress.RequestSpec.from_obj(req).digest()


def _payload(**over):
    p = {"v": 1, "kind": "action", "program": PROGRAM, "cap": "tasks", "site": "Create",
         "request": _digest(REQ), "nonce": "n-1", "exp": NOW + 600}
    p.update(over)
    return p


def _signed(sk=SK_PERSONAL, **over):
    return approval.make_signed(sk, _payload(**over))


def _signed_text(text, sk=SK_PERSONAL):
    return {"payload": text, "key": ed25519.public_key(sk).hex(),
            "sig": ed25519.sign(sk, approval.DOMAIN + text.encode("utf-8")).hex()}


def _consent(signed=None, **extra):
    return ("consent", {"site": "Create", "tool": "tasks", **({"signed": signed} if signed is not None else {}), **extra})


def _effect(req=None):
    return ("effect", {"site": "Create", "tool": "tasks", "approval": "$token", **({"request": req} if req is not None else {})})


_tampered = _signed()
_tampered = {**_tampered, "payload": _tampered["payload"].replace(str(NOW + 600), str(NOW + 999999))}

# name, config, [(call, expected-subset), ...]
CORPUS = [
    ("approved_action_runs", {}, [
        (_consent(_signed()), {"granted": True, "code": "ok", "class": "personal"}),
        (_effect(REQ), {"allowed": True})]),
    ("same_request_other_spelling_runs", {}, [
        (_consent(_signed()), {"granted": True}),
        (_effect(REQ_LIST_FORM), {"allowed": True})]),
    ("unsigned_assertion_mints_nothing", {}, [
        (_consent(approved=True), {"granted": False, "code": "unsigned"}),
        (_consent(approved=True, request=REQ), {"granted": False, "code": "unsigned"})]),
    ("changed_action_is_blocked", {}, [
        (_consent(_signed()), {"granted": True}),
        (_effect(REQ_CHANGED), {"allowed": False}),
        (_effect(REQ), {"allowed": True})]),            # the mismatch did not burn the token
    ("effect_without_request_is_blocked", {}, [
        (_consent(_signed()), {"granted": True}),
        (_effect(), {"allowed": False})]),
    ("token_is_one_shot", {}, [
        (_consent(_signed()), {"granted": True}),
        (_effect(REQ), {"allowed": True}),
        (_effect(REQ), {"allowed": False})]),
    ("approval_replay_refused", {}, [
        (_consent(_signed()), {"granted": True}),
        (_consent(_signed()), {"granted": False, "code": "replayed"})]),
    ("tampered_payload", {}, [(_consent(_tampered), {"granted": False, "code": "bad_signature"})]),
    ("unknown_key", {}, [(_consent(_signed(SK_STRANGER)), {"granted": False, "code": "unknown_key"})]),
    ("expired", {}, [(_consent(_signed(exp=NOW)), {"granted": False, "code": "expired"})]),
    ("other_program_version", {}, [
        (_consent(_signed(program="sha256:other")), {"granted": False, "code": "program_mismatch"})]),
    ("other_site", {}, [(_consent(_signed(site="Delete")), {"granted": False, "code": "binding_mismatch"})]),
    ("other_cap", {}, [(_consent(_signed(cap="mail")), {"granted": False, "code": "binding_mismatch"})]),
    ("human_key_suffices_by_default", {}, [
        (_consent(_signed(SK_HUMAN)), {"granted": True, "class": "human"}),
        (_effect(REQ), {"allowed": True})]),
    ("personal_required_human_refused", {"approval_class": {"tasks": "personal"}}, [
        (_consent(_signed(SK_HUMAN)), {"granted": False, "code": "class_insufficient"}),
        (_consent(_signed(SK_PERSONAL)), {"granted": True, "class": "personal"})]),
    ("malformed_sig", {}, [(_consent({**_signed(), "sig": "zz"}), {"granted": False, "code": "malformed"})]),
    ("malformed_envelope", {}, [(_consent({"payload": 1}), {"granted": False, "code": "malformed"})]),
    ("malformed_payload_bool_version", {}, [
        (_consent(_signed_text(json.dumps({**_payload(), "v": True}))), {"granted": False, "code": "malformed"})]),
    ("malformed_payload_not_json", {}, [
        (_consent(_signed_text("approve everything")), {"granted": False, "code": "malformed"})]),
    ("no_program_identity_configured", {"program": ""}, [
        (_consent(_signed()), {"granted": False, "code": "program_mismatch"})]),
    # legacy (no trust store): the unsigned request-binding, now at Rust parity
    ("legacy_request_bound", {"approvers": {}}, [
        (_consent(approved=True, request=REQ), {"granted": True}),
        (_effect(REQ_CHANGED), {"allowed": False}),
        (_effect(REQ_LIST_FORM), {"allowed": True})]),
    ("legacy_unbound_still_works", {"approvers": {}}, [
        (_consent(approved=True), {"granted": True}),
        (_effect(), {"allowed": True})]),
]
_IDS = [c[0] for c in CORPUS]


def _drive(client, steps):
    token = None
    try:
        for (method, params), expect in steps:
            params = {k: (token if v == "$token" else v) for k, v in params.items()}
            out = client._call(method, params)
            if method == "consent" and out.get("token"):
                token = out["token"]
            for k, v in expect.items():
                assert out.get(k) == v, (method, k, out, expect)
    finally:
        client.close()


def _cfg(config):
    return (config.get("approvers", APPROVERS), config.get("program", PROGRAM), config.get("approval_class", {}))


@pytest.mark.parametrize("name,config,steps", CORPUS, ids=_IDS)
def test_corpus_python(name, config, steps):
    approvers, program, klass = _cfg(config)
    b = Broker(granted_tools={"tasks"}, irreversible_caps={"tasks"}, approvers=dict(approvers),
               program_hash=program or None, approval_class=dict(klass), clock=lambda: NOW)
    _drive(Client(broker=b), steps)


def _rust_bin():
    for sub in ("debug", "release"):
        b = os.path.join(_ROOT, "rust", "target", sub, "casl-broker")
        if not (os.path.exists(b) and os.access(b, os.X_OK)):
            continue
        try:
            p = subprocess.Popen([b], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.wait(timeout=2)
            return b
        except OSError:
            return None
        except Exception:
            return b
    return None


_RUST = _rust_bin()


@pytest.mark.skipif(_RUST is None, reason="rust casl-broker not built/runnable on this platform")
@pytest.mark.parametrize("name,config,steps", CORPUS, ids=_IDS)
def test_corpus_rust(name, config, steps):
    approvers, program, klass = _cfg(config)
    env = {**os.environ, "CASL_BROKER_TOOLS": "tasks", "CASL_BROKER_IRREVERSIBLE": "tasks",
           "CASL_BROKER_APPROVERS": ",".join(f"{k}={v}" for k, v in approvers.items()),
           "CASL_BROKER_PROGRAM": program, "CASL_BROKER_NOW": str(NOW),
           "CASL_BROKER_APPROVAL_CLASS": ",".join(f"{k}={v}" for k, v in klass.items())}
    _drive(Client(command=[_RUST], env=env), steps)


def test_parse_approvers_drops_malformed():
    k = ed25519.public_key(SK_HUMAN).hex()
    got = approval.parse_approvers(f"{k}=human, nothex=personal\n{k[:10]}=human,{k}x=robot  # comment")
    assert got == {k: "human"}
