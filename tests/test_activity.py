"""casl.activity — the subprocess activity executor (docs/analyses/activity-executor.md).

An activity is an UNTRUSTED, out-of-process producer for an oracle site, run as a `backend` drop-in and
MONITORED by the same boundary as the mock (contract + blame; veto-never-vouch). Fail-closed: any failure
(crash / timeout / non-JSON / missing cost) ⇒ a typed refusal. These tests pin each property and an
end-to-end conduct of a project whose oracle site is realized by a REAL program (no key, cross-platform)."""
import os
import sys

import pytest

from casl import activity
from casl.oracle import oracle_step

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(_ROOT, "examples", "activities", "budgeted_draft.py")


def _prog(tmp_path, name, src, timeout_s=5.0):
    p = tmp_path / name
    p.write_text(src)
    return activity.SubprocessActivity(command=[sys.executable, str(p)], timeout_s=timeout_s, name=name)


def test_command_for_infers_and_denies():
    assert activity.command_for("x.py")[0] == sys.executable
    assert activity.command_for("x.py")[-1] == "x.py"
    assert activity.command_for("run", runner=["bash"]) == ["bash", "run"]
    with pytest.raises(ValueError):
        activity.command_for("mystery.rkt")          # unknown extension, no runner ⇒ deny-by-default


def test_happy_path_real_program():
    act = activity.SubprocessActivity(command=[sys.executable, EXAMPLE], timeout_s=5.0)
    out = act.generate("what is 2+2?", 100)
    assert not out.refused and out.answer.startswith("draft") and out.cost == 7


def test_crash_is_refusal(tmp_path):
    assert _prog(tmp_path, "boom.py", "import sys; sys.exit(3)").generate("q", 100).refused is True


def test_timeout_is_refusal(tmp_path):
    assert _prog(tmp_path, "slow.py", "import time; time.sleep(5)", timeout_s=0.5).generate("q", 100).refused is True


def test_nonjson_is_refusal(tmp_path):
    assert _prog(tmp_path, "noise.py", "print('hello, not json')").generate("q", 100).refused is True


def test_missing_cost_is_refusal(tmp_path):
    # mirrors oracle.parse_oracle_output: an answer with no integer cost cannot be budget-checked ⇒ refusal
    act = _prog(tmp_path, "nocost.py", "import json; print(json.dumps({'answer': 'hi'}))")
    assert act.generate("q", 100).refused is True


def test_activity_cannot_vouch(tmp_path):
    # the activity OVERSPENDS its claim and ALSO emits fabricated 'verdict'/'pass' fields — they are ignored;
    # the trusted monitor computes the verdict from the cost and BLAMES the producer (veto-never-vouch).
    src = ("import json,sys; req=json.loads(sys.stdin.readline());"
           "print(json.dumps({'answer':'x','cost':req['budget']+25,'verdict':'ok','pass':True}))")
    sr = oracle_step(_prog(tmp_path, "liar.py", src), "q", 100)
    assert sr.kind == "violation" and sr.blame == "A"


def test_refusal_drives_safe_outcome(tmp_path):
    act = _prog(tmp_path, "decline.py", "import json; print(json.dumps({'refused': True}))")
    assert oracle_step(act, "q", 100).kind == "refusal"


def test_conductor_runs_a_real_program(tmp_path):
    # END-TO-END: scaffold a gate-accepted project, bind its oracle site to a REAL program, conduct it.
    from casl import conductor, synth, synthesis
    res = synthesis.new_project("Budgeted QA with retry", str(tmp_path), synth.MockGenerator(), conduct=False)
    assert res.accepted
    (tmp_path / "artifacts").mkdir(exist_ok=True)
    with open(EXAMPLE) as fh:
        (tmp_path / "artifacts" / "draft.py").write_text(fh.read())
    toml = (tmp_path / "casl.toml").read_text()
    assert 'implements  = "BudgetedQA:Draft"' in toml
    (tmp_path / "casl.toml").write_text(toml.replace(
        'implements  = "BudgetedQA:Draft"',
        'implements  = "BudgetedQA:Draft"\nbody        = "artifacts/draft.py"'))
    cr = conductor.Conductor(str(tmp_path)).run(scenario="ok", approve=True,
                                                env={"budget": 100, "question": "what is 2+2?"})
    assert cr.run.outcome == "completed"
    assert any("draft:" in line for line in cr.run.trace)     # the REAL program's payload, not the mock
    assert "activity" in cr.summary
