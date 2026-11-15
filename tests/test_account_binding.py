"""Approvals are bound to the TARGET ACCOUNT — the identity of the credential the broker adds on the wire
(casl-lang issue #2). A request such as `POST /me/events` does not say whose account it acts on; the bearer
decides. One corpus against BOTH brokers pins:
  · the approval must name the identity of the broker-held credential; a swapped principal is denied;
  · an approval that names no account, or names one although the broker holds none, is denied;
  · a credential without an identity cannot be approved at all;
  · the identity — never the secret — lands in the journal (approval + intent).
"""
import os

import pytest

from casl import egress
from casl.broker import Broker
from casl.client import Client
from casl.journal import Journal

from test_approval_signed import APPROVERS, NOW, PROGRAM, REQ, _RUST, _digest, _signed

HOST, SECRET = "tasks.example", "s3cret-bearer-value"
ACCT_A, ACCT_B = "msgraph:tenant-1:user-a", "msgraph:tenant-1:user-b"


def _consent(**payload):
    return ("consent", {"site": "Create", "tool": "tasks", "signed": _signed(request=_digest(REQ), **payload)})


EFFECT = ("effect", {"site": "Create", "tool": "tasks", "approval": "$token", "request": REQ})

# name, broker credential config: (holds a credential?, its identity), steps
CORPUS = [
    ("named_account_runs", (True, ACCT_A), [
        (_consent(account=ACCT_A), {"granted": True, "code": "ok", "account": ACCT_A}),
        (EFFECT, {"allowed": True, "outcome": "performed"})]),
    ("swapped_principal_denied", (True, ACCT_B), [
        (_consent(account=ACCT_A), {"granted": False, "code": "account_mismatch"})]),
    ("approval_without_account_denied", (True, ACCT_A), [
        (_consent(), {"granted": False, "code": "account_mismatch"})]),
    ("account_named_but_no_credential_held", (False, None), [
        (_consent(account=ACCT_A), {"granted": False, "code": "account_mismatch"})]),
    ("credential_without_identity_cannot_be_approved", (True, None), [
        (_consent(), {"granted": False, "code": "account_unbound"}),
        (_consent(account=ACCT_A, nonce="n-2"), {"granted": False, "code": "account_unbound"})]),
    ("no_credential_no_account_still_works", (False, None), [
        (_consent(), {"granted": True}),
        (EFFECT, {"allowed": True, "outcome": "performed"})]),
    ("malformed_account", (True, ACCT_A), [
        (_consent(account=7), {"granted": False, "code": "malformed"}),
        (_consent(account="", nonce="n-2"), {"granted": False, "code": "malformed"})]),
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


def _python(path, holds, account, steps):
    mc = egress.MediatedCapability(
        policy=egress.DestinationPolicy(allow_hosts=(HOST,)), transport=egress.MockTransport(status=201, body="OK"),
        inject=(("Authorization", f"Bearer {SECRET}"),) if holds else (), account=account)
    j = Journal(path)
    try:
        _drive(Client(broker=Broker(granted_tools={"tasks"}, irreversible_caps={"tasks"}, approvers=dict(APPROVERS),
                                    program_hash=PROGRAM, clock=lambda: NOW, transports={"tasks": mc}, journal=j)), steps)
    finally:
        j.close()
    return mc


def _rust(path, holds, account, steps):
    env = {**os.environ, "CASL_BROKER_TOOLS": "tasks", "CASL_BROKER_IRREVERSIBLE": "tasks",
           "CASL_BROKER_APPROVERS": ",".join(f"{k}={v}" for k, v in APPROVERS.items()),
           "CASL_BROKER_PROGRAM": PROGRAM, "CASL_BROKER_NOW": str(NOW), "CASL_BROKER_EGRESS": f"tasks={HOST}",
           "CASL_BROKER_MOCK_EGRESS": "201", "CASL_BROKER_JOURNAL": path}
    if holds:
        env.update({"CASL_BROKER_EGRESS_AUTH": "tasks=PILOT_TOKEN", "PILOT_TOKEN": SECRET})
    if account:
        env["CASL_BROKER_EGRESS_ACCOUNT"] = f"tasks={account}"
    _drive(Client(command=[_RUST], env=env), steps)


def _check_journal(path, account, performed):
    j = Journal(path)
    try:
        assert j.verify() == (True, None, "ok")
        entries = j.entries()
    finally:
        j.close()
    import json
    by_kind = {e[2]: json.loads(e[3]) for e in entries}
    if performed:
        assert by_kind["approval"]["account"] == account and by_kind["intent"]["account"] == account
    with open(path, "rb") as f:
        assert SECRET.encode() not in f.read()              # the identity is journaled, never the secret


@pytest.mark.parametrize("name,cred,steps", CORPUS, ids=_IDS)
def test_corpus_python(tmp_path, name, cred, steps):
    path = str(tmp_path / "j.sqlite")
    _python(path, *cred, steps)
    _check_journal(path, cred[1], steps[-1][1].get("outcome") == "performed")


@pytest.mark.skipif(_RUST is None, reason="rust casl-broker not built/runnable on this platform")
@pytest.mark.parametrize("name,cred,steps", CORPUS, ids=_IDS)
def test_corpus_rust(tmp_path, name, cred, steps):
    path = str(tmp_path / "j.sqlite")
    _rust(path, *cred, steps)
    _check_journal(path, cred[1], steps[-1][1].get("outcome") == "performed")


def test_account_is_checked_again_at_execution(tmp_path):
    """Between approval and execution the broker's credential is replaced by another principal's: the
    token minted for the first principal no longer performs."""
    transport = egress.MockTransport(status=201, body="OK")
    def mc(account):
        return egress.MediatedCapability(policy=egress.DestinationPolicy(allow_hosts=(HOST,)), transport=transport,
                                         inject=(("Authorization", f"Bearer {SECRET}"),), account=account)
    b = Broker(granted_tools={"tasks"}, irreversible_caps={"tasks"}, approvers=dict(APPROVERS), program_hash=PROGRAM,
               clock=lambda: NOW, transports={"tasks": mc(ACCT_A)})
    c = Client(broker=b)
    token = c._call(*_consent(account=ACCT_A))["token"]
    b.transports["tasks"] = mc(ACCT_B)
    out = c._call("effect", {"site": "Create", "tool": "tasks", "approval": token, "request": REQ})
    assert out["allowed"] is False and "target account" in out["reason"] and transport.calls == []


def test_credential_reaches_the_wire_but_not_the_caller(tmp_path):
    mc = _python(str(tmp_path / "j.sqlite"), True, ACCT_A, CORPUS[0][2])
    sent = dict(mc.transport.calls[0].headers)
    assert sent["Authorization"] == f"Bearer {SECRET}"
