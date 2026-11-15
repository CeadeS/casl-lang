"""casl.conductor_corpus — interpreter run-trace differential ORACLE (CEP-0081, COND). Verifies the LOCAL
side: deterministic, covers both completing and non-completing outcomes (loop bound / tool-denied /
forward-violation / approval-denied), equals the authority (`run.run_protocol` + `oracle.MockBackend`), and
matches the committed Rust fixture. See docs/analyses/python-retirement-roadmap.md."""
import os

from casl import conductor_corpus as cc
from casl import oracle, run, surface

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_oracle_deterministic_and_covers_outcomes():
    corpus = cc.build_corpus()
    assert len(corpus) >= 8
    assert cc.to_text() == cc.to_text()
    outcomes = {e["outcome"] for e in corpus}
    assert "completed" in outcomes
    assert {"loop_bound_reached", "tool_denied", "forward_violation", "approval_denied"} <= outcomes, (
        f"corpus must exercise every non-completing outcome; got {outcomes}"
    )


def test_verdicts_match_the_authority():
    for e in cc.build_corpus():
        p = surface.parse(e["casl"])
        rr = run.run_protocol(
            p.gtype, oracle.MockBackend(e["scenario"]), {"budget": e["budget"]},
            max_loops=e["max_loops"], approve=e["approve"], caps=p.caps,
        )
        assert e["outcome"] == rr.outcome
        assert e["loops"] == rr.loops
        assert e["last_verdict"] == rr.last_verdict
        assert e["accepted_label"] == rr.accepted_label
        assert e["forwards"] == list(rr.forwards)


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-conductor", "tests", "corpus.json")
    if not os.path.exists(path):
        import pytest

        pytest.skip("rust conductor corpus not generated yet (regen: python -m casl.conductor_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == cc.to_text()
