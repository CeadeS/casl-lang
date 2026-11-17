"""Context access end to end through the Rust `casl` binary (docs/context-grants.md, casl-lang#7), with a
mock target. The first test the host asked for: an excerpt of a mail found by the host's own (local-index)
search is disclosed to ONE fixed model over HTTPS — and nothing else is.
Skipped where the Rust binary is not built (`cd rust && cargo build`)."""
import json
import os

import pytest

from casl import context as cx, context_corpus as cc, ed25519
from casl.journal import Journal

from test_os_pilot_act import _CASL, _ROOT, _run

pytestmark = pytest.mark.skipif(_CASL is None, reason="rust casl binary not built/runnable on this platform")
PROGRAM = os.path.join(_ROOT, "examples", "os_pilot", "mail_digest.casl")
SRC, FOLDER, UNI, PRIVATE = "mail.uni.example", "/INBOX/seminar", "imap:uni:martin", "imap:private:martin"
LLM, MODEL_ID = "https://api.anthropic.com/v1/messages", "claude-sonnet-5-5"
RECEIVER = f"endpoint:api.anthropic.com/v1/messages#{MODEL_ID}"
EXP, TOKEN, EXCERPT = 4_000_000_000, "llm-api-key-value", "vertraulicher Auszug aus der Abgabe"


class Host:
    def __init__(self, tmp):
        self.tmp, self.journal, self.approvers = tmp, str(tmp / "journal.sqlite"), str(tmp / "approvers")
        with open(self.approvers, "w") as f:
            f.write(f"{ed25519.public_key(cc.SK_USER).hex()}=personal\n")
        code, out = _run("prepare", "--program", PROGRAM, "--site", "File", "--request", self.write("x.json", {}))
        assert code == 0, out
        self.program = out["sign"]["program"]               # the hash a grant for this workflow must name

    def write(self, name, obj):
        path = str(self.tmp / name)
        with open(path, "w") as f:
            json.dump(obj, f, ensure_ascii=False)
        return path

    def grant(self, signer=cc.SK_USER, frame=None, **kw):
        g = {"v": 1, "kind": "grant", "id": "g1", "program": self.program, "instance": None, "op": "search",
             "account": UNI, "source": SRC, "resource": FOLDER, "exp": EXP, "uses": None}
        g.update(kw)
        return _run("grant", "add", "--journal", self.journal, "--approvers", self.approvers,
                    "--grant", self.write(f"{g['id']}.json", cx.make_grant(signer, g, frame=frame)))

    def search(self, account=UNI, resource=FOLDER, instance="run-1"):
        return _run("access", "--program", PROGRAM, "--site", "Search", "--journal", self.journal, "--approvers",
                    self.approvers, "--host-performed", "--account", account, "--source", SRC, "--resource", resource,
                    "--instance", instance)

    def summarize(self, origins, model=MODEL_ID, url=LLM, instance="run-1", mock="200"):
        body = json.dumps({"model": model, "max_tokens": 200, "messages": [{"role": "user", "content": EXCERPT}]},
                          ensure_ascii=False)
        return _run("access", "--program", PROGRAM, "--site", "Summarize", "--journal", self.journal, "--approvers",
                    self.approvers, "--request", self.write("llm.json", {"method": "POST", "url": url, "headers": {
                        "content-type": "application/json", "anthropic-version": "2023-06-01"}, "body": body}),
                    "--allow-hosts", "api.anthropic.com", "--auth-env", "LLM_KEY", "--account", "anthropic:work",
                    "--origins", origins, "--instance", instance, "--mock-egress", mock, env={"LLM_KEY": TOKEN})

    def entries(self):
        j = Journal(self.journal)
        try:
            assert j.verify() == (True, None, "ok")
            return [(e[2], json.loads(e[3])) for e in j.entries()]
        finally:
            j.close()


def test_mail_excerpt_goes_to_the_fixed_model_and_nowhere_else(tmp_path):
    h = Host(tmp_path)
    hit = FOLDER + "/4711"

    # nothing is granted yet: the search is not authorized, and the host is told what to ask for
    code, out = h.search()
    assert code == 4 and out["status"] == "needs_grant", out
    assert out["access"]["pending"]["account"] == UNI and out["access"]["pending"]["resource"] == FOLDER

    # the user grants: search in the seminar folder of the university mailbox; disclosure of it to ONE model
    assert h.grant(id="g-search")[0] == 0
    assert h.grant(id="g-disclose", op="disclose", receiver=RECEIVER)[0] == 0

    code, out = h.search()
    assert code == 0 and out["access"]["by"] == "host" and out["access"]["grants"] == ["g-search"], out
    s = out["access"]["access"]

    # the excerpt of one hit goes to the fixed model
    code, out = h.summarize(f"{s}={hit}")
    assert code == 0 and out["status"] == "performed" and out["access"]["grants"] == ["g-disclose"], out

    # … and nowhere else: another model, another endpoint, a hit outside the folder, the private mailbox
    for call, status, why in [
        (lambda: h.summarize(f"{s}={hit}", model="claude-other"), 1, "outside_declared_scope"),
        (lambda: h.summarize(f"{s}={hit}", url="https://api.anthropic.com/v1/complete"), 1, "outside_declared_scope"),
        (lambda: h.summarize(f"{s}=/INBOX/private/1"), 1, "origin_invalid"),
        (lambda: h.summarize(f"{s}"), 1, "origin_invalid"),                       # a search hit must name its resource
        (lambda: h.search(account=PRIVATE), 4, "no_grant"),
        (lambda: h.search(resource="/INBOX"), 1, "outside_declared_scope"),
    ]:
        code, out = call()
        assert (code, out["access"]["code"]) == (status, why), out
        assert "body" not in out["access"]

    rows = h.entries()
    sent = [b for k, b in rows if k == "access_result"]
    assert len(sent) == 1 and sent[0]["outcome"] == "performed"                   # exactly one request left
    with open(h.journal, "rb") as f:
        raw = f.read()
    assert TOKEN.encode() not in raw and EXCERPT.encode() not in raw
    disclosed = next(b for k, b in rows if k == "access" and b["op"] == "disclose" and b["decision"] == "granted")
    assert disclosed["receiver"] == RECEIVER
    assert disclosed["origins"] == [{"access": s, "account": UNI, "source": SRC, "resource": hit}]


def test_revocation_and_expiry_apply_at_the_next_call(tmp_path):
    h = Host(tmp_path)
    assert h.grant(id="g-search")[0] == 0
    assert h.search()[0] == 0
    assert _run("grant", "revoke", "--journal", h.journal, "--id", "g-search")[0] == 0
    code, out = h.search()
    assert code == 4 and out["access"]["code"] == "revoked", out
    assert h.grant(id="g-old", exp=1)[0] == 0                                     # an expired grant unlocks nothing
    code, out = h.search()
    assert code == 4 and out["access"]["code"] in ("revoked", "expired"), out
    assert h.grant(id="g-new")[0] == 0
    assert h.search()[0] == 0


def test_policy_key_grants_inside_a_user_signed_frame(tmp_path):
    h = Host(tmp_path)
    policy = ed25519.public_key(cc.SK_POLICY).hex()
    frame = cx.make_frame(cc.SK_USER, {"v": 1, "kind": "frame", "id": "f1", "policy_key": policy, "ops": ["search"],
                                       "account": UNI, "source": SRC, "resource": FOLDER, "program": None, "exp": EXP})
    # the OS issues an instance-bound grant on its own — inside the frame it works, outside it does not
    assert h.grant(signer=cc.SK_POLICY, frame=frame, id="pg", instance="run-1")[0] == 0
    code, out = h.grant(signer=cc.SK_POLICY, frame=frame, id="pg-wide", resource="/INBOX")
    assert code == 1 and out["code"] == "outside_frame", out
    code, out = h.grant(signer=cc.SK_POLICY, id="pg-bare")
    assert code == 1 and out["code"] == "unknown_key", out
    assert h.search(instance="run-1")[0] == 0
    assert h.search(instance="run-2")[0] == 4                                     # bound to one run
    assert _run("grant", "revoke", "--journal", h.journal, "--id", "f1")[0] == 0  # revoking the frame …
    assert h.search(instance="run-1")[0] == 4                                     # … stops what was issued under it


def test_context_capability_cannot_be_run_as_a_plain_action(tmp_path):
    h = Host(tmp_path)
    code, out = _run("act", "--program", PROGRAM, "--site", "Summarize", "--request", h.write("r.json", {
        "method": "POST", "url": LLM, "body": "{}"}), "--allow-hosts", "api.anthropic.com", "--mock-egress", "200")
    assert code == 1 and "casl access" in out["error"], out


def test_a_write_still_needs_its_own_signed_approval(tmp_path):
    h = Host(tmp_path)
    assert h.grant(id="g-search")[0] == 0 and h.grant(id="g-disclose", op="disclose", receiver=RECEIVER)[0] == 0
    code, out = _run("access", "--program", PROGRAM, "--site", "File", "--journal", h.journal, "--approvers",
                     h.approvers, "--request", h.write("w.json", {"method": "POST", "url": "https://mail.uni.example/x"}),
                     "--allow-hosts", "mail.uni.example", "--mock-egress", "200")
    assert code == 1 and "no context scope" in out["error"], out                  # `access` performs no writes
    code, out = _run("act", "--program", PROGRAM, "--site", "File", "--request", h.write("w.json", {
        "method": "POST", "url": "https://mail.uni.example/x"}), "--allow-hosts", "mail.uni.example", "--mock-egress", "200")
    assert code == 2 and "--approval" in out["error"], out                        # the write asks for its approval
