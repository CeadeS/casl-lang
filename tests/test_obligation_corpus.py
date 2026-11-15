"""casl.obligation_corpus — grade-composition differential ORACLE (CEP-0081, Track C brick 5). Verifies the
LOCAL side: deterministic, exercises both strong (G0) and weakest (G3) effective grades + multi-requirement
buckets, equals the authority (`obligation_gate.effective_grade`/`grade_by_requirement`), and matches the Rust
fixture. See docs/analyses/python-retirement-roadmap.md."""
import os
import tempfile

from casl import obligation_gate as og
from casl import obligation_corpus as oc
from casl import project

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(toml):
    d = tempfile.mkdtemp(prefix="casl_oblig_test_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    return project.load_manifest(d)


def test_oracle_deterministic_and_covers_polarities():
    corpus = oc.build_corpus()
    assert len(corpus) >= 5
    assert oc.to_text() == oc.to_text()
    effs = {e["effective_grade"] for e in corpus}
    assert "G0" in effs and "G3" in effs, "corpus must exercise both the strongest and weakest effective grade"
    assert any(len(e["grade_by_requirement"]) >= 2 for e in corpus), "need a multi-requirement case"


def test_verdicts_match_the_authority():
    for e in oc.build_corpus():
        man = _load(e["toml"])
        assert e["effective_grade"] == og.effective_grade(man)
        assert e["grade_by_requirement"] == og.grade_by_requirement(man)


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-project", "tests", "obligation_corpus.json")
    if not os.path.exists(path):
        import pytest

        pytest.skip("rust obligation corpus not generated yet (regen: python -m casl.obligation_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == oc.to_text()
