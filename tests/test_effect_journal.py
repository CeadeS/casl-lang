"""Mediated effect outcomes + the run journal — ONE corpus against BOTH brokers (Python in-process, Rust
binary over stdio when built). Pins the pilot's third acceptance criterion and its record:
  · a timeout produces NO blind repeat: the outcome is `unknown`, the same request is blocked (even with a
    fresh approval) until it is `resolve`d — and that state survives a broker restart;
  · approval replay is refused across restarts (durable nonces);
  · every run leaves approval → intent → result in a hash-chained journal that either implementation can
    verify, whichever wrote it; tampering is detected by both.
"""
import os
import sqlite3
import subprocess

import pytest

from casl import egress
from casl.broker import Broker
from casl.client import Client
from casl.journal import Journal

from test_approval_signed import APPROVERS, NOW, PROGRAM, REQ, _RUST, _digest, _signed

HOST = "tasks.example"
REQ_EVIL = {**REQ, "url": "https://evil.example/api/tasks"}
D = _digest(REQ)


def _consent(nonce, req=REQ):
    return ("consent", {"site": "Create", "tool": "tasks", "signed": _signed(nonce=nonce, request=_digest(req))})


def _effect(req=REQ):
    return ("effect", {"site": "Create", "tool": "tasks", "approval": "$token", "request": req})


def _resolve(outcome, effect=D):
    return ("resolve", {"effect": effect, "outcome": outcome, "note": "looked up at the target"})


# name, seed (journal entries written before the first session), [(mock transport, steps), ...], journal kinds
CORPUS = [
    ("performed", [], [("200", [
        (_consent("n1"), {"granted": True}),
        (_effect(), {"allowed": True, "performed": True, "outcome": "performed", "status": 200, "effect": D})])],
     ["run", "approval", "intent", "result"]),
    ("target_rejects", [], [("404", [
        (_consent("n1"), {"granted": True}),
        (_effect(), {"allowed": True, "performed": False, "outcome": "rejected", "status": 404}),
        (_consent("n2"), {"granted": True}),
        (_effect(), {"outcome": "rejected"})])],           # a definitive refusal does not block a new attempt
     ["run", "approval", "intent", "result", "approval", "intent", "result"]),
    ("timeout_no_blind_repeat", [], [("unknown", [
        (_consent("n1"), {"granted": True}),
        (_effect(), {"allowed": True, "performed": False, "outcome": "unknown"}),
        (_effect(), {"allowed": False, "outcome": "unresolved"}),        # same token: blocked
        (_consent("n2"), {"granted": True}),
        (_effect(), {"allowed": False, "outcome": "unresolved"}),        # even a FRESH approval: blocked
        (_resolve("maybe"), {"resolved": False}),
        (_resolve("not_performed"), {"resolved": True}),
        (_resolve("not_performed"), {"resolved": False}),                # nothing left to resolve
        (_effect(), {"allowed": True, "outcome": "unknown"})])],         # the block did not burn token n2
     ["run", "approval", "intent", "result", "approval", "resolve", "intent", "result"]),
    ("server_error_is_unknown", [], [("503", [
        (_consent("n1"), {"granted": True}),
        (_effect(), {"allowed": True, "performed": False, "outcome": "unknown", "status": 503})])],
     ["run", "approval", "intent", "result"]),
    ("not_sent_is_not_blocking", [], [("not_sent", [
        (_consent("n1"), {"granted": True}),
        (_effect(), {"allowed": True, "performed": False, "outcome": "not_sent"}),
        (_consent("n2"), {"granted": True}),
        (_effect(), {"outcome": "not_sent"})])],
     ["run", "approval", "intent", "result", "approval", "intent", "result"]),
    ("replay_refused_after_restart", [], [
        ("200", [(_consent("n1"), {"granted": True})]),
        ("200", [(_consent("n1"), {"granted": False, "code": "replayed"})])],
     ["run", "approval", "run"]),
    ("unknown_outcome_survives_restart", [], [
        ("unknown", [(_consent("n1"), {"granted": True}), (_effect(), {"outcome": "unknown"})]),
        ("200", [
            (_consent("n2"), {"granted": True}),
            (_effect(), {"allowed": False, "outcome": "unresolved"}),
            (_resolve("performed"), {"resolved": True}),
            (_effect(), {"allowed": True, "outcome": "performed"})])],
     ["run", "approval", "intent", "result", "run", "approval", "resolve", "intent", "result"]),
    ("crash_between_intent_and_result", [("intent", {"effect": D, "cap": "tasks", "site": "Create", "nonce": "n0"})], [
        ("200", [
            (_consent("n1"), {"granted": True}),
            (_effect(), {"allowed": False, "outcome": "unresolved"})])],
     ["intent", "run", "approval"]),
    ("denied_destination_sends_nothing", [], [("200", [
        (_consent("n1", REQ_EVIL), {"granted": True}),
        (_effect(REQ_EVIL), {"allowed": False})])],
     ["run", "approval"]),
    ("resolve_unknown_id", [], [("200", [(_resolve("performed", "no-such-effect"), {"resolved": False})])],
     ["run"]),
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


def _python_session(path, mock, steps):
    fail = mock if mock in ("not_sent", "unknown") else ""
    mc = egress.MediatedCapability(
        policy=egress.DestinationPolicy(allow_hosts=(HOST,)),
        transport=egress.MockTransport(status=int(mock) if not fail else 0, body="OK", fail=fail))
    j = Journal(path)
    try:
        b = Broker(granted_tools={"tasks"}, irreversible_caps={"tasks"}, approvers=dict(APPROVERS),
                   program_hash=PROGRAM, clock=lambda: NOW, transports={"tasks": mc}, journal=j)
        _drive(Client(broker=b), steps)
    finally:
        j.close()


def _rust_session(path, mock, steps):
    env = {**os.environ, "CASL_BROKER_TOOLS": "tasks", "CASL_BROKER_IRREVERSIBLE": "tasks",
           "CASL_BROKER_APPROVERS": ",".join(f"{k}={v}" for k, v in APPROVERS.items()),
           "CASL_BROKER_PROGRAM": PROGRAM, "CASL_BROKER_NOW": str(NOW),
           "CASL_BROKER_EGRESS": f"tasks={HOST}", "CASL_BROKER_MOCK_EGRESS": mock, "CASL_BROKER_JOURNAL": path}
    _drive(Client(command=[_RUST], env=env), steps)


def _rust_verify(path):
    return subprocess.run([_RUST, "verify-journal", path], capture_output=True).returncode


def _run_case(tmp_path, session, seed, sessions, kinds):
    path = str(tmp_path / "journal.sqlite")
    if seed:
        j = Journal(path)
        for kind, body in seed:
            j.append(kind, body, NOW)
        j.close()
    for mock, steps in sessions:
        session(path, mock, steps)
    j = Journal(path)
    try:
        assert j.verify() == (True, None, "ok")
        assert [e[2] for e in j.entries()] == kinds
    finally:
        j.close()
    if _RUST is not None:
        assert _rust_verify(path) == 0                      # whichever broker wrote it, both verify it
    return path


@pytest.mark.parametrize("name,seed,sessions,kinds", CORPUS, ids=_IDS)
def test_corpus_python(tmp_path, name, seed, sessions, kinds):
    _run_case(tmp_path, _python_session, seed, sessions, kinds)


@pytest.mark.skipif(_RUST is None, reason="rust casl-broker not built/runnable on this platform")
@pytest.mark.parametrize("name,seed,sessions,kinds", CORPUS, ids=_IDS)
def test_corpus_rust(tmp_path, name, seed, sessions, kinds):
    _run_case(tmp_path, _rust_session, seed, sessions, kinds)


def _tamper(path, sql, args=()):
    db = sqlite3.connect(path)
    db.execute(sql, args)
    db.commit()
    db.close()


@pytest.mark.parametrize("writer", ["python", "rust"])
@pytest.mark.parametrize("attack,sql", [
    ("edit_body", "UPDATE entries SET body = replace(body, '\"performed\"', '\"rejected\"') WHERE kind = 'result'"),
    ("delete_middle", "DELETE FROM entries WHERE kind = 'intent'"),
    ("backdate", "UPDATE entries SET ts = ts - 86400 WHERE kind = 'approval'"),
])
def test_tampering_is_detected_by_both(tmp_path, writer, attack, sql):
    if writer == "rust" and _RUST is None:
        pytest.skip("rust casl-broker not built/runnable on this platform")
    session = _python_session if writer == "python" else _rust_session
    path = _run_case(tmp_path, session, *CORPUS[0][1:])
    _tamper(path, sql)
    j = Journal(path)
    try:
        ok, bad, _reason = j.verify()
        assert not ok and bad is not None
    finally:
        j.close()
    if _RUST is not None:
        assert _rust_verify(path) == 1


def test_journal_cli_exit_codes(tmp_path):
    import sys
    path = _run_case(tmp_path, _python_session, *CORPUS[0][1:])
    env = {**os.environ, "PYTHONPATH": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")}
    run = lambda p: subprocess.run([sys.executable, "-m", "casl.journal", "verify", p], env=env, capture_output=True).returncode  # noqa: E731
    assert run(path) == 0
    assert run(str(tmp_path / "missing.sqlite")) == 2 and not (tmp_path / "missing.sqlite").exists()
    _tamper(path, "UPDATE entries SET kind = 'result' WHERE kind = 'intent'")
    assert run(path) == 1


def test_journal_write_failure_fails_closed(tmp_path):
    """No journaled intent ⇒ no send: if the journal cannot be written the effect is not performed."""
    class Broken(Journal):
        def append(self, kind, body, ts):
            if kind == "intent":
                raise sqlite3.OperationalError("disk full")
            return super().append(kind, body, ts)

    t = egress.MockTransport(status=200, body="OK")
    j = Broken(str(tmp_path / "j.sqlite"))
    b = Broker(granted_tools={"tasks"}, irreversible_caps={"tasks"}, approvers=dict(APPROVERS), program_hash=PROGRAM,
               clock=lambda: NOW, journal=j,
               transports={"tasks": egress.MediatedCapability(egress.DestinationPolicy(allow_hosts=(HOST,)), t)})
    c = Client(broker=b)
    token = c._call(*_consent("n1"))["token"]
    with pytest.raises(Exception):
        c._call("effect", {"site": "Create", "tool": "tasks", "approval": token, "request": REQ})
    assert t.calls == []                                   # nothing left the broker
    j.close()
