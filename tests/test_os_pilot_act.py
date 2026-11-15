"""The AI-OS pilot, end to end through the Rust `casl` binary (prepare → sign → act → journal), with a mock
target. The acceptance criteria (docs/os-pilot.md):
  1. an approved action runs;
  2. an action changed after approval is blocked;
  3. a timeout produces no blind repeat;
  4. an approval not signed by a trusted human key performs nothing.
Skipped where the Rust binary is not built (`cd rust && cargo build`).
"""
import json
import os
import subprocess

import pytest

from casl import approval, ed25519
from casl.journal import Journal

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(_ROOT, "examples", "os_pilot", "create_task.casl")
SK, SK_AGENT = bytes(range(32)), b"\x09" * 32
EXP = 4_000_000_000        # far future: `act` uses the real clock
REQ = {"method": "POST", "url": "https://tasks.example/api/lists/werkstatt/tasks",
       "headers": {"Content-Type": "application/json"},
       "body": json.dumps({"id": "t-184-1", "title": "Prüfaufgabe P-184", "due": "2026-11-20"}, ensure_ascii=False)}


def _casl():
    for sub in ("debug", "release"):
        b = os.path.join(_ROOT, "rust", "target", sub, "casl")
        if os.path.exists(b) and os.access(b, os.X_OK):
            try:
                subprocess.run([b, "--version"], capture_output=True, timeout=5)
                return b
            except OSError:
                return None
    return None


_CASL = _casl()
pytestmark = pytest.mark.skipif(_CASL is None, reason="rust casl binary not built/runnable on this platform")


def _run(*args, env=None):
    p = subprocess.run([_CASL, *args], capture_output=True, text=True, env={**os.environ, **(env or {})})
    out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else p.stdout
    return p.returncode, out


class Host:
    """What the OS does around CASL: files, the prepare call, the user's signature."""

    def __init__(self, tmp):
        self.tmp = tmp
        self.journal = str(tmp / "journal.sqlite")
        self.approvers = str(tmp / "approvers")
        with open(self.approvers, "w") as f:
            f.write(f"# the user's device key\n{ed25519.public_key(SK).hex()}=personal\n")

    def write(self, name, obj):
        path = str(self.tmp / name)
        with open(path, "w") as f:
            json.dump(obj, f, ensure_ascii=False)
        return path

    def prepare(self, req, *cred, env=None):
        code, out = _run("prepare", "--program", PROGRAM, "--site", "Create", "--request", self.write("req.json", req),
                         *cred, env=env)
        assert code == 0 and out["irreversible"] is True, out
        return out["sign"]

    def approve(self, req, nonce, *cred, sk=SK, env=None):
        payload = {**self.prepare(req, *cred, env=env), "nonce": nonce, "exp": EXP}
        return self.write(f"approval-{nonce}.json", approval.make_signed(sk, payload))

    def act(self, req, approval_path, mock="201", **extra):
        args = ["act", "--program", PROGRAM, "--site", "Create", "--request", self.write("act-req.json", req),
                "--approval", approval_path, "--approvers", self.approvers, "--journal", self.journal,
                "--allow-hosts", "tasks.example", "--mock-egress", mock]
        for k, v in extra.items():
            args += [f"--{k.replace('_', '-')}", v]
        return _run(*args)

    def kinds(self):
        j = Journal(self.journal)
        try:
            assert j.verify() == (True, None, "ok")
            return [e[2] for e in j.entries()]
        finally:
            j.close()


def test_prepare_names_program_site_and_request(tmp_path):
    sign = Host(tmp_path).prepare(REQ)
    assert sign["program"].startswith("sha256:") and sign["site"] == "CreateTask:Create" and sign["cap"] == "tasks"
    assert sign["v"] == 1 and sign["kind"] == "action" and len(sign["request"]) == 64


def test_1_approved_action_runs(tmp_path):
    h = Host(tmp_path)
    code, out = h.act(REQ, h.approve(REQ, "n1"))
    assert code == 0 and out["status"] == "performed", out
    assert out["consent"]["class"] == "personal" and "token" not in out["consent"]
    assert out["effect"]["status"] == 201
    assert h.kinds() == ["run", "approval", "intent", "result"]
    assert _run("journal", "verify", h.journal)[0] == 0


def test_2_action_changed_after_approval_is_blocked(tmp_path):
    h = Host(tmp_path)
    signed = h.approve(REQ, "n1")
    changed = {**REQ, "body": REQ["body"].replace("2026-11-20", "2026-12-20")}
    code, out = h.act(changed, signed)
    assert code == 1 and out["status"] == "denied" and out["effect"]["allowed"] is False, out
    assert "intent" not in h.kinds()                      # nothing was attempted


def test_3_timeout_produces_no_blind_repeat(tmp_path):
    h = Host(tmp_path)
    code, out = h.act(REQ, h.approve(REQ, "n1"), mock="unknown")
    assert code == 3 and out["status"] == "unknown", out
    attempt = out["effect"]["attempt"]
    # the same request again — even with a FRESH signed approval — is blocked until clarified
    code, out = h.act(REQ, h.approve(REQ, "n2"))
    assert code == 1 and out["status"] == "unresolved" and out["effect"]["attempt"] == attempt, out
    # the host looked the task up at the target: it was not created
    code, out = _run("resolve", "--journal", h.journal, "--attempt", str(attempt), "--outcome", "not_performed",
                     "--note", "GET /tasks/t-184-1 → 404")
    assert code == 0 and out["resolved"] is True, out
    code, out = h.act(REQ, h.approve(REQ, "n3"))
    assert code == 0 and out["status"] == "performed", out
    assert h.kinds() == ["run", "approval", "intent", "result", "run", "approval", "resolve",
                         "run", "approval", "intent", "result"]


def test_4_unsigned_or_untrusted_approval_performs_nothing(tmp_path):
    h = Host(tmp_path)
    # signed by a key the broker does not trust (e.g. one the agent made up)
    code, out = h.act(REQ, h.approve(REQ, "n1", sk=SK_AGENT))
    assert code == 1 and out["consent"]["code"] == "unknown_key" and out["effect"] is None, out
    # a bare assertion instead of a signature
    code, out = h.act(REQ, h.write("fake.json", {"approved": True}))
    assert code == 1 and out["consent"]["code"] == "malformed", out
    # a replayed approval
    signed = h.approve(REQ, "n2")
    assert h.act(REQ, signed)[0] == 0
    code, out = h.act(REQ, signed)
    assert code == 1 and out["consent"]["code"] == "replayed", out
    assert h.kinds().count("intent") == 1


def test_approval_for_another_program_version_is_refused(tmp_path):
    h = Host(tmp_path)
    payload = {**h.prepare(REQ), "program": "sha256:" + "0" * 64, "nonce": "n1", "exp": EXP}
    code, out = h.act(REQ, h.write("a.json", approval.make_signed(SK, payload)))
    assert code == 1 and out["consent"]["code"] == "program_mismatch", out


def test_destination_outside_the_allowlist_is_refused(tmp_path):
    h = Host(tmp_path)
    evil = {**REQ, "url": "https://evil.example/api/tasks"}
    code, out = h.act(evil, h.approve(evil, "n1"))
    assert code == 1 and "destination denied" in out["effect"]["reason"], out


def test_caller_cannot_supply_the_broker_held_credential(tmp_path):
    h = Host(tmp_path)
    sneaky = {**REQ, "headers": {**REQ["headers"], "authorization": "Bearer stolen"}}
    code, out = _run(*["act", "--program", PROGRAM, "--site", "Create", "--request", h.write("r.json", sneaky),
                       "--approval", h.approve(sneaky, "n1", "--auth-env", "PILOT_TOKEN", "--account", "acct-a",
                                               env={"PILOT_TOKEN": "s3cret"}),
                       "--approvers", h.approvers, "--journal", h.journal,
                       "--allow-hosts", "tasks.example", "--mock-egress", "201", "--auth-env", "PILOT_TOKEN",
                       "--account", "acct-a"],
                     env={"PILOT_TOKEN": "s3cret"})
    assert code == 1 and "held by the broker" in out["effect"]["reason"], out
    assert "s3cret" not in json.dumps(out)


def test_rejected_program_is_not_executed(tmp_path):
    h = Host(tmp_path)
    bad = str(tmp_path / "bad.casl")
    with open(PROGRAM) as f:
        src = f.read().replace("Approve consent:", "Approve:")     # the effect is no longer approval-dominated
    with open(bad, "w") as f:
        f.write(src)
    code, out = _run("act", "--program", bad, "--site", "Create", "--request", h.write("r.json", REQ),
                     "--approval", h.approve(REQ, "n1"), "--approvers", h.approvers, "--journal", h.journal,
                     "--allow-hosts", "tasks.example", "--mock-egress", "201")
    assert code == 1 and "REJECTED" in out["error"], out


# -- issue #2: the approval names the target account (identity of the broker-held credential) ------------
def _jwt(**claims):
    import base64
    enc = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()   # noqa: E731
    return f"{enc({'alg': 'none'})}.{enc(claims)}.signature"


ALICE = dict(iss="https://login.example/tenant-1/v2.0", tid="tenant-1", oid="alice-oid", sub="pairwise-1")
BOB = {**ALICE, "oid": "bob-oid"}
CRED = ("--auth-env", "PILOT_TOKEN", "--account-from-token")


def test_same_request_other_principal_is_denied(tmp_path):
    """The reproduction from the issue: one signed request to an implicit-account endpoint, two bearers."""
    h = Host(tmp_path)
    me = {**REQ, "url": "https://tasks.example/v1.0/me/events"}
    alice = {"PILOT_TOKEN": _jwt(**ALICE, exp=1)}
    sign = h.prepare(me, *CRED, env=alice)
    assert sign["account"] == "jwt:iss=https://login.example/tenant-1/v2.0;tid=tenant-1;sub=alice-oid"
    signed = h.approve(me, "n1", *CRED, env=alice)

    def act(env, approval_path):
        return _run("act", "--program", PROGRAM, "--site", "Create", "--request", h.write("r.json", me),
                    "--approval", approval_path, "--approvers", h.approvers, "--journal", h.journal,
                    "--allow-hosts", "tasks.example", "--mock-egress", "201", *CRED, env=env)

    code, out = act({"PILOT_TOKEN": _jwt(**BOB, exp=1)}, signed)                 # swapped principal
    assert code == 1 and out["consent"]["code"] == "account_mismatch" and out["effect"] is None, out
    code, out = act({"PILOT_TOKEN": _jwt(**ALICE, exp=2)}, h.approve(me, "n2", *CRED, env=alice))   # refreshed token
    assert code == 0 and out["status"] == "performed" and out["consent"]["account"] == sign["account"], out
    with open(h.journal, "rb") as f:
        raw = f.read()
    assert b"alice-oid" in raw and _jwt(**ALICE, exp=2).encode() not in raw       # identity yes, token no


def test_credential_needs_an_identity(tmp_path):
    h = Host(tmp_path)
    base = ["--program", PROGRAM, "--site", "Create", "--request", h.write("r.json", REQ)]
    code, out = _run("prepare", *base, "--auth-env", "PILOT_TOKEN", env={"PILOT_TOKEN": "opaque"})
    assert code == 2 and "--account" in out["error"], out
    code, out = _run("prepare", *base, "--auth-env", "PILOT_TOKEN", "--account-from-token", env={"PILOT_TOKEN": "opaque"})
    assert code == 2 and "not a JWT" in out["error"], out
    code, out = _run("prepare", *base, "--auth-env", "PILOT_TOKEN", "--account", "graph-work", env={"PILOT_TOKEN": "opaque"})
    assert code == 0 and out["sign"]["account"] == "graph-work", out
    code, out = _run("prepare", *base, "--account", "graph-work")
    assert code == 2, out


# -- issue #4: concurrent `casl act` processes on one journal ---------------------------------------------
def _race(calls):
    """Run the given act() thunks at the same moment; return their (code, out) results."""
    import threading
    start, results, lock = threading.Barrier(len(calls)), [], threading.Lock()

    def one(call):
        start.wait()
        r = call()
        with lock:
            results.append(r)

    threads = [threading.Thread(target=one, args=(c,)) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_one_signed_approval_performs_once_across_twelve_processes(tmp_path):
    h = Host(tmp_path)
    signed = h.approve(REQ, "n1")
    req_file = h.write("shared-req.json", REQ)

    def act():
        return _run("act", "--program", PROGRAM, "--site", "Create", "--request", req_file, "--approval", signed,
                    "--approvers", h.approvers, "--journal", h.journal, "--allow-hosts", "tasks.example",
                    "--mock-egress", "201")

    results = _race([act] * 12)
    performed = [out for code, out in results if code == 0]
    assert len(performed) == 1 and performed[0]["status"] == "performed", [o.get("status") for _c, o in results]
    assert all(out["consent"]["code"] == "replayed" for code, out in results if code != 0), results
    kinds = h.kinds()
    assert (kinds.count("approval"), kinds.count("intent"), kinds.count("result")) == (1, 1, 1), kinds


def test_same_action_in_flight_blocks_other_approvals_across_processes(tmp_path):
    """Twelve DIFFERENT approvals for the same request, raced, against a target that never answers: one
    attempt goes out and ends unknown; the other eleven find it in the journal and do not send."""
    h = Host(tmp_path)
    req_file = h.write("shared-req.json", REQ)
    approvals = [h.approve(REQ, f"n{i}") for i in range(12)]

    def act(a):
        return lambda: _run("act", "--program", PROGRAM, "--site", "Create", "--request", req_file, "--approval", a,
                            "--approvers", h.approvers, "--journal", h.journal, "--allow-hosts", "tasks.example",
                            "--mock-egress", "unknown")

    results = _race([act(a) for a in approvals])
    statuses = sorted(out["status"] for _code, out in results)
    assert statuses == ["unknown"] + ["unresolved"] * 11, statuses
    attempt = next(out["effect"]["attempt"] for _c, out in results if out["status"] == "unknown")
    assert all(out["effect"]["attempt"] == attempt for _c, out in results), results
    assert h.kinds().count("intent") == 1
