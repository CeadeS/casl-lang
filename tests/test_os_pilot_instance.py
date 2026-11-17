"""Durable workflow instances end to end through the Rust `casl` binary (docs/instances.md, casl-lang#1):
start, deliver one message at a time, status — every call a fresh process, the journal the only memory.
Skipped where the Rust binary is not built (`cd rust && cargo build`)."""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from casl import approval, context as cx, context_corpus as cc, ed25519
from casl.journal import Journal

from test_os_pilot_act import _CASL, _ROOT, _run

pytestmark = pytest.mark.skipif(_CASL is None, reason="rust casl binary not built/runnable on this platform")
PROGRAM = os.path.join(_ROOT, "examples", "os_pilot", "mail_digest.casl")
REVIEW = os.path.join(_ROOT, "examples", "os_pilot", "seminar_review.casl")
SRC, FOLDER, UNI = "mail.uni.example", "/INBOX/seminar", "imap:uni:martin"
LLM, MODEL_ID = "https://api.anthropic.com/v1/messages", "claude-sonnet-5-5"
RECEIVER = f"endpoint:api.anthropic.com/v1/messages#{MODEL_ID}"
EXP, TOKEN, EXCERPT = 4_000_000_000, "llm-api-key-value", "vertraulicher Auszug aus der Abgabe"
FILE_REQ = {"method": "POST", "url": "https://mail.uni.example/api/folders/digests/messages",
            "headers": {"Content-Type": "application/json"}, "body": json.dumps({"subject": "Digest"})}
NOTES = """protocol Notes {
  roles U, A, T;
  agent A caps { note(text) scope "notes" mode read ttl 5 sig "n-1"; }
  U -> A : Ask(topic: Str, count: Int);
  A -> T : Save() uses note;
  T -> A : Saved();
}
"""


class Host:
    def __init__(self, tmp, program=PROGRAM):
        self.tmp, self.journal, self.approvers = tmp, str(tmp / "journal.sqlite"), str(tmp / "approvers")
        self.program_file = program
        with open(self.approvers, "w") as f:
            f.write(f"{ed25519.public_key(cc.SK_USER).hex()}=personal\n")

    def write(self, name, obj):
        path = str(self.tmp / name)
        with open(path, "w") as f:
            json.dump(obj, f, ensure_ascii=False)
        return path

    def start(self, *extra):
        code, out = _run("instance", "start", "--program", self.program_file, "--journal", self.journal, *extra)
        if code == 0:
            self.id, self.program = out["instance"], out["program"]
        return code, out

    def status(self, program=None):
        return _run("instance", "status", "--program", program or self.program_file, "--journal", self.journal,
                    "--instance", self.id)

    def deliver(self, label, fields=None, *extra, env=None, program=None):
        args = ["instance", "deliver", "--program", program or self.program_file, "--journal", self.journal,
                "--instance", self.id, "--label", label]
        if fields is not None:
            args += ["--fields", self.write(f"fields-{label}-{threading.get_ident()}.json", fields)]
        return _run(*args, *extra, env=env)

    def grant(self, **kw):
        g = {"v": 1, "kind": "grant", "id": "g1", "program": self.program, "instance": None, "op": "search",
             "account": UNI, "source": SRC, "resource": FOLDER, "exp": EXP, "uses": None}
        g.update(kw)
        return _run("grant", "add", "--journal", self.journal, "--approvers", self.approvers,
                    "--grant", self.write(f"{g['id']}.json", cx.make_grant(cc.SK_USER, g)))

    def search(self):
        return self.deliver("Search", {"query": "Abgabe"}, "--approvers", self.approvers, "--host-performed",
                            "--account", UNI, "--source", SRC, "--resource", FOLDER)

    def summarize(self, origins, mock="200"):
        body = json.dumps({"model": MODEL_ID, "max_tokens": 200, "messages": [{"role": "user", "content": EXCERPT}]},
                          ensure_ascii=False)
        req = {"method": "POST", "url": LLM, "body": body,
               "headers": {"content-type": "application/json", "anthropic-version": "2023-06-01"}}
        return self.deliver("Summarize", {"excerpt": EXCERPT}, "--approvers", self.approvers, "--request",
                            self.write("llm.json", req), "--allow-hosts", "api.anthropic.com", "--auth-env", "LLM_KEY",
                            "--account", "anthropic:work", "--origins", origins, "--mock-egress", mock,
                            env={"LLM_KEY": TOKEN})

    def approve(self, nonce, bound=True, req=FILE_REQ, **override):
        args = ["prepare", "--program", self.program_file, "--site", "File", "--request", self.write("file.json", req)]
        if bound:
            args += ["--instance", self.id, "--journal", self.journal]
        code, out = _run(*args)
        assert code == 0, out
        payload = {**out["sign"], "nonce": nonce, "exp": EXP, **override}
        return self.write(f"approval-{nonce}.json", approval.make_signed(cc.SK_USER, payload))

    def file(self, approval_path, mock="201", req=FILE_REQ):
        return self.deliver("File", None, "--request", self.write(f"file-act-{threading.get_ident()}.json", req), "--approval", approval_path,
                            "--approvers", self.approvers, "--allow-hosts", "mail.uni.example", "--mock-egress", mock)

    def entries(self):
        j = Journal(self.journal)
        try:
            assert j.verify() == (True, None, "ok")
            return [(e[2], json.loads(e[3])) for e in j.entries()]
        finally:
            j.close()

    def to_gate(self):
        """Run the digest up to the user's decision (grants in place)."""
        assert self.start()[0] == 0
        assert self.grant(id="g-search")[0] == 0
        assert self.grant(id="g-disclose", op="disclose", receiver=RECEIVER)[0] == 0
        assert self.deliver("Ask", {"topic": "Seminar"})[0] == 0
        code, out = self.search()
        assert code == 0, out
        s = out["result"]["access"]["access"]
        assert self.deliver("Hits", {"count": 1})[0] == 0
        code, out = self.summarize(f"{s}={FOLDER}/4711")
        assert code == 0, out
        assert self.deliver("Digest", {"text": "…"})[0] == 0
        assert self.deliver("Propose", {"text": "…"})[0] == 0


def labels(out):
    return [e["label"] for e in out["next"]]


def test_a_workflow_runs_across_processes_and_waits_where_it_must(tmp_path):
    h = Host(tmp_path)
    code, out = h.start("--id", "digest-1")
    assert code == 0 and out["status"] == "started" and out["state"] == "running" and labels(out) == ["Ask"], out
    assert out["next"][0]["fields"] == [{"name": "topic", "sort": "Str"}]

    assert h.deliver("Ask", {"topic": "Seminar"})[0] == 0

    # the search needs a grant: the instance WAITS at that step — nothing was skipped, nothing is lost
    code, out = h.search()
    assert code == 4 and out["status"] == "needs_grant" and out["delivered"] is False, out
    rid = out["result"]["access"]["request"]
    code, out = h.status()
    assert out["state"] == "waiting_grant" and out["step"] == 1 and labels(out) == ["Search"], out
    assert [p["request"] for p in out["pending"]] == [rid] and out["pending"][0]["account"] == UNI

    # the user grants; the host delivers the same step again and it is decided afresh
    assert h.grant(id="g-search")[0] == 0
    assert h.grant(id="g-disclose", op="disclose", receiver=RECEIVER)[0] == 0
    code, out = h.search()
    assert code == 0 and out["status"] == "delivered" and out["state"]["step"] == 2, out
    s = out["result"]["access"]["access"]
    assert "pending" not in out["state"]

    assert h.deliver("Hits", {"count": 1})[0] == 0
    code, out = h.summarize(f"{s}={FOLDER}/4711")
    assert code == 0 and out["result"]["status"] == "performed", out
    assert h.deliver("Digest", {"text": "Zwei Abgaben"})[0] == 0
    code, out = h.deliver("Propose", {"text": "Zwei Abgaben"})
    assert code == 0 and labels(out["state"]) == ["Keep", "Drop"], out
    assert out["state"]["next"][0].get("consent") is True

    # the user keeps it; filing is a write and needs a signed approval for THIS instance and step
    assert h.deliver("Keep")[0] == 0
    code, out = h.status()
    assert out["next"] == [{"label": "File", "kind": "effect", "from": "A", "to": "T", "fields": [], "cap": "file",
                            "needs_approval": True}], out
    code, out = h.file(h.approve("n1"))
    assert code == 0 and out["status"] == "delivered" and out["state"]["state"] == "completed", out
    assert out["state"]["next"] == []
    assert [s["label"] for s in out["state"]["completed"]] == [
        "Ask", "Search", "Hits", "Summarize", "Digest", "Propose", "Keep", "File"]

    # a completed instance accepts nothing
    code, out = h.deliver("Ask", {"topic": "again"})
    assert code == 1 and out["code"] == "unexpected_label" and out["expected"] == [], out

    with open(h.journal, "rb") as f:
        raw = f.read()
    assert TOKEN.encode() not in raw and EXCERPT.encode() not in raw and b"Zwei Abgaben" not in raw


def test_only_the_expected_message_with_the_declared_fields_is_accepted(tmp_path):
    h = Host(tmp_path)
    assert h.start()[0] == 0
    before = h.entries()
    for label, fields, why in [
        ("Search", {"query": "x"}, "unexpected_label"),          # not yet
        ("Nope", None, "unexpected_label"),
        ("Ask", None, "bad_fields"),                             # missing
        ("Ask", {"topic": 7}, "bad_fields"),                     # wrong sort
        ("Ask", {"topic": "x", "extra": 1}, "bad_fields"),       # undeclared
        ("Ask", ["x"], "bad_fields"),
    ]:
        code, out = h.deliver(label, fields)
        assert code == 1 and out["status"] == "refused" and out["code"] == why, out
    assert h.entries() == before                                  # a refused delivery leaves no trace
    code, out = h.deliver("Nope")
    assert out["expected"] == ["Ask"]


def test_an_instance_is_bound_to_its_program_version(tmp_path):
    h = Host(tmp_path)
    assert h.start("--id", "a")[0] == 0
    code, out = h.start("--id", "a")
    assert code == 1 and out["code"] == "exists", out
    assert _run("instance", "start", "--program", PROGRAM, "--journal", h.journal, "--id", "no/slash")[0] == 2
    changed = str(tmp_path / "changed.casl")
    with open(PROGRAM) as f, open(changed, "w") as g:
        g.write(f.read() + "\n// edited\n")
    for call in (lambda: h.deliver("Ask", {"topic": "x"}, program=changed), lambda: h.status(program=changed)):
        code, out = call()
        assert code == 1 and out["code"] == "program_changed", out
    h.id = "missing"
    code, out = h.status()
    assert code == 1 and out["code"] == "unknown_instance", out


def test_an_approval_is_for_one_step_of_one_instance(tmp_path):
    h = Host(tmp_path)
    h.to_gate()
    assert h.deliver("Keep")[0] == 0
    first = h.id
    for name, path in [
        ("no instance named", h.approve("n1", bound=False)),
        ("another instance", h.approve("n2", instance="other")),
        ("another step", h.approve("n3", step=3)),
        ("half a binding", h.approve("n4", bound=False, step=7)),
    ]:
        code, out = h.file(path)
        assert code == 1 and out["delivered"] is False, (name, out)
        assert out["result"]["consent"]["code"] in ("binding_mismatch", "malformed"), (name, out)
        assert out["result"]["effect"] is None
    # … and an approval given for this instance does not perform the action outside it
    code, out = _run("act", "--program", PROGRAM, "--site", "File", "--request", h.write("f.json", FILE_REQ),
                     "--approval", h.approve("n5"), "--approvers", h.approvers, "--journal", h.journal,
                     "--allow-hosts", "mail.uni.example", "--mock-egress", "201")
    assert code == 1 and out["consent"]["code"] == "binding_mismatch", out
    assert not any(k == "intent" for k, _ in h.entries())
    assert h.id == first and h.file(h.approve("n6"))[0] == 0


def test_an_unknown_outcome_blocks_the_step_until_it_is_clarified(tmp_path):
    h = Host(tmp_path)
    h.to_gate()
    assert h.deliver("Keep")[0] == 0
    code, out = h.file(h.approve("n1"), mock="unknown")
    assert code == 3 and out["status"] == "not_performed" and out["state"]["state"] == "blocked", out
    attempt = out["result"]["effect"]["attempt"]
    assert out["state"]["blocked_on"] == {"attempt": attempt}

    # no second attempt of the step — not the same request, not a changed one — and no approval is burned
    other = {**FILE_REQ, "body": json.dumps({"subject": "Digest (2)"})}
    for req, nonce in ((FILE_REQ, "n2"), (other, "n3")):
        code, out = h.file(h.approve(nonce, req=req), req=req)
        assert code == 1 and out["code"] == "blocked" and out["attempt"] == attempt, out
    assert [k for k, _ in h.entries()].count("approval") == 1

    # the host looked at the target: the digest was filed. The step completes WITHOUT a second request.
    code, out = _run("resolve", "--journal", h.journal, "--attempt", str(attempt), "--outcome", "performed")
    assert code == 0 and out["resolved"] is True, out
    code, out = h.status()
    assert out["state"] == "completed" and out["completed"][-1]["label"] == "File", out
    assert [k for k, _ in h.entries()].count("intent") == 1


def test_a_failed_attempt_leaves_the_step_open_for_a_new_approval(tmp_path):
    h = Host(tmp_path)
    h.to_gate()
    assert h.deliver("Keep")[0] == 0
    signed = h.approve("n1")
    code, out = h.file(signed, mock="409")
    assert code == 3 and out["delivered"] is False and out["state"]["state"] == "running", out
    code, out = h.file(signed)                                    # one approval, one attempt
    assert code == 1 and out["result"]["consent"]["code"] == "replayed", out
    code, out = h.file(h.approve("n2"))
    assert code == 0 and out["state"]["state"] == "completed", out


def test_the_other_branch_never_reaches_the_effect(tmp_path):
    h = Host(tmp_path)
    h.to_gate()
    assert h.deliver("Drop")[0] == 0
    code, out = h.file(h.approve("n1"))
    assert code == 1 and out["code"] == "unexpected_label" and out["expected"] == ["Skip"], out
    code, out = h.deliver("Skip")
    assert code == 0 and out["state"]["state"] == "completed", out
    assert not any(k in ("intent", "approval") for k, _ in h.entries())


def test_a_denied_grant_request_ends_the_instance(tmp_path):
    h = Host(tmp_path)
    assert h.start()[0] == 0
    assert h.deliver("Ask", {"topic": "Seminar"})[0] == 0
    code, out = h.search()
    assert code == 4, out
    rid = out["result"]["access"]["request"]

    def decide(*args):
        return _run("instance", "decide", "--journal", h.journal, "--instance", h.id, *args)

    code, out = decide("--decision", "denied", "--request", "0" * 64)
    assert code == 1 and out["code"] == "stale_request", out
    assert decide("--decision", "denied")[0] == 2
    assert decide("--decision", "maybe", "--request", rid)[0] == 2
    code, out = decide("--decision", "denied", "--request", rid)
    assert code == 0 and out == {"status": "ended", "instance": h.id, "state": "denied"}, out
    code, out = decide("--decision", "denied", "--request", rid)       # the same answer twice is one answer
    assert code == 0 and out["already"] is True, out
    code, out = decide("--decision", "cancelled")                       # another answer comes too late
    assert code == 1 and out["code"] == "ended", out
    assert [k for k, _ in h.entries()].count("instance_end") == 1

    code, out = h.status()
    assert out["state"] == "denied" and out["next"] == [] and out["ended"]["request"] == rid, out
    # a grant that arrives now unlocks nothing
    assert h.grant(id="g-search")[0] == 0
    code, out = h.search()
    assert code == 1 and out["code"] == "ended", out


def test_a_revoked_or_expired_grant_does_not_unlock_a_waiting_step(tmp_path):
    h = Host(tmp_path)
    assert h.start()[0] == 0
    assert h.deliver("Ask", {"topic": "Seminar"})[0] == 0
    assert h.search()[0] == 4
    assert h.grant(id="g-old", exp=1)[0] == 0
    assert h.grant(id="g-gone")[0] == 0
    assert _run("grant", "revoke", "--journal", h.journal, "--id", "g-gone")[0] == 0
    code, out = h.search()
    assert code == 4 and out["delivered"] is False and out["state"]["step"] == 1, out
    assert h.grant(id="g-live")[0] == 0
    assert h.search()[0] == 0


def test_a_search_of_an_earlier_step_cannot_be_delivered_again(tmp_path):
    h = Host(tmp_path)
    h.to_gate()
    # the access path itself refuses a step the instance has left — whoever calls it
    code, out = _run("access", "--program", PROGRAM, "--site", "Search", "--journal", h.journal, "--approvers",
                     h.approvers, "--host-performed", "--account", UNI, "--source", SRC, "--resource", FOLDER,
                     "--instance", h.id)
    assert code == 0, out                                          # an untagged access is not a step (casl-lang#7)
    code, out = h.search()
    assert code == 1 and out["code"] == "unexpected_label", out


def test_concurrent_deliveries_of_one_step_complete_it_once(tmp_path):
    h = Host(tmp_path)
    assert h.start()[0] == 0
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda i: h.deliver("Ask", {"topic": f"t{i}"}), range(8)))
    assert sorted(code for code, _ in results) == [0] + [1] * 7, results
    assert {out["code"] for code, out in results if code == 1} <= {"stale_step", "unexpected_label"}
    assert [k for k, _ in h.entries()].count("step") == 1

    # an irreversible step: several processes, each with its own valid approval — one request leaves
    h2 = Host(tmp_path / "..", PROGRAM)
    h2.tmp = tmp_path
    h2.journal = str(tmp_path / "j2.sqlite")
    h2.to_gate()
    assert h2.deliver("Keep")[0] == 0
    signed = [h2.approve(f"n{i}") for i in range(6)]
    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(h2.file, signed))
    assert [code for code, _ in results].count(0) == 1, results
    rows = h2.entries()
    assert [k for k, _ in rows].count("intent") == 1
    assert h2.status()[1]["state"] == "completed"


def test_a_loop_is_walked_and_its_bound_holds(tmp_path):
    h = Host(tmp_path, REVIEW)
    assert h.start()[0] == 0
    assert h.deliver("Start", {"topic": "x"})[0] == 0
    code, out = h.status()
    assert labels(out) == ["Find"] and out["next"][0]["kind"] == "context", out


def test_a_reversible_effect_is_recorded_as_a_step(tmp_path):
    prog = str(tmp_path / "notes.casl")
    with open(prog, "w") as f:
        f.write(NOTES)
    h = Host(tmp_path, prog)
    code, out = h.start()
    assert code == 0, out
    code, out = h.deliver("Ask", {"topic": "x", "count": 2})
    assert code == 0, out
    req = h.write("note.json", {"method": "POST", "url": "https://notes.example/n", "headers": {}, "body": "x"})
    args = ("--request", req, "--allow-hosts", "notes.example")
    code, out = h.deliver("Save", None, *args, "--mock-egress", "503")
    assert code == 3 and out["delivered"] is False, out
    code, out = h.deliver("Save", None, *args, "--mock-egress", "200")
    assert code == 0 and out["delivered"] is True and labels(out["state"]) == ["Saved"], out
    code, out = h.deliver("Save", None, *args, "--mock-egress", "200")
    assert code == 1 and out["code"] == "unexpected_label", out
    assert h.deliver("Saved")[0] == 0
    assert h.status()[1]["state"] == "completed"


def test_a_program_with_an_oracle_site_is_refused(tmp_path):
    src = os.path.join(_ROOT, "examples")
    oracle = next((os.path.join(src, n) for n in sorted(os.listdir(src))
                   if n.endswith(".casl") and "oracle" in open(os.path.join(src, n)).read()
                   and _run("check", os.path.join(src, n))[0] == 0), None)
    if oracle is None:
        pytest.skip("no accepted example with an oracle site")
    code, out = _run("instance", "start", "--program", oracle, "--journal", str(tmp_path / "j.sqlite"))
    assert (code, out.get("code")) == (1, "unsupported"), out
