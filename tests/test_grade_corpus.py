"""casl.grade_corpus — the grade-flow differential ORACLE (CEP-0081, Track C brick 4). Verifies the LOCAL
side: the oracle is deterministic, exercises both strong (G0) and degraded (G3) sites and both present/absent
boundaries, equals the authority (`grade_flow.*`, apply_rebase=False), and matches the committed Rust fixture.
See docs/analyses/python-retirement-roadmap.md."""
import os
import tempfile

from casl import grade_flow, project
from casl import grade_corpus as gc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _setup(toml, choreos):
    d = tempfile.mkdtemp(prefix="casl_grade_test_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    os.makedirs(os.path.join(d, "casl"), exist_ok=True)
    for i, c in enumerate(choreos):
        with open(os.path.join(d, "casl", f"c{i}.casl"), "w", encoding="utf-8") as fh:
            fh.write(c)
    return d


def test_oracle_deterministic_and_covers_polarities():
    corpus = gc.build_corpus()
    assert len(corpus) >= 4
    assert gc.to_text() == gc.to_text()
    grades = {g for e in corpus for (_p, _l, g) in e["flow_grades"]}
    assert "G0" in grades and "G3" in grades, "corpus must exercise both strong and degraded site grades"
    assert any(e["boundaries"] for e in corpus) and any(not e["boundaries"] for e in corpus)


def test_verdicts_match_the_authority():
    for e in gc.build_corpus():
        d = _setup(e["toml"], e["choreos"])
        man = project.load_manifest(d)
        fg = grade_flow.flow_grades(man, d, apply_rebase=False)
        cb = grade_flow.containment_boundaries(man, d)
        assert e["flow_grades"] == sorted([p, l, g] for (p, l), g in fg.items())
        assert e["boundaries"] == sorted(s.split(" (", 1)[0] for s in cb)


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-project", "tests", "grade_corpus.json")
    if not os.path.exists(path):
        import pytest

        pytest.skip("rust grade corpus not generated yet (regen: python -m casl.grade_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == gc.to_text()
