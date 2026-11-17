"""An approval for a step of a workflow instance names the instance and the step (docs/instances.md).
The reference broker checks the binding like the Rust broker; it does not perform instance steps."""
from casl import approval, ed25519
from casl.broker import Broker

SK = bytes(range(32))
BASE = {"v": 1, "kind": "action", "program": "sha256:p", "cap": "tasks", "site": "P:Create", "request": "d" * 64,
        "exp": 2_000}


def _broker():
    b = Broker(granted_tools={"tasks"}, irreversible_caps={"tasks"}, program_hash="sha256:p",
               approvers={ed25519.public_key(SK).hex(): "personal"}, clock=lambda: 1_000)
    b.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}})
    return b


def _consent(b, nonce, extra, **params):
    env = approval.make_signed(SK, {**BASE, "nonce": nonce, **extra})
    r = b.handle({"jsonrpc": "2.0", "id": 1, "method": "consent",
                  "params": {"site": "P:Create", "tool": "tasks", "signed": env, **params}})
    return r["result"]


def test_the_binding_must_match_exactly():
    b = _broker()
    step = {"instance": "i-1", "step": 3}
    for nonce, payload, params, code in [
        ("a", {}, {}, "ok"),
        ("b", step, step, "ok"),
        ("c", step, {}, "binding_mismatch"),                          # not usable outside the instance
        ("d", {}, step, "binding_mismatch"),                          # a plain approval is not one for a step
        ("e", step, {"instance": "i-2", "step": 3}, "binding_mismatch"),
        ("f", step, {"instance": "i-1", "step": 4}, "binding_mismatch"),
        ("g", step, {"instance": "i-1"}, "binding_mismatch"),
        ("h", {"instance": "i-1"}, {"instance": "i-1"}, "malformed"),  # both or neither
        ("i", {"instance": "", "step": 0}, {}, "malformed"),
        ("j", {"instance": "i-1", "step": -1}, step, "malformed"),
        ("k", {"instance": "i-1", "step": True}, step, "malformed"),
        ("l", {"instance": 7, "step": 1}, step, "malformed"),
    ]:
        r = _consent(b, nonce, payload, **params)
        assert r["code"] == code and r["granted"] is (code == "ok"), (nonce, r)
    # a refused binding does not burn the approval
    assert _consent(b, "c", step, **step)["granted"] is True


def test_the_reference_broker_does_not_perform_instance_steps():
    b = _broker()
    token = _consent(b, "a", {"instance": "i-1", "step": 0}, instance="i-1", step=0)["token"]
    r = b.handle({"jsonrpc": "2.0", "id": 2, "method": "effect",
                  "params": {"site": "P:Create", "tool": "tasks", "approval": token, "instance": "i-1", "step": 0}})
    assert r["result"]["allowed"] is False and r["result"]["outcome"] == "stale_step", r
