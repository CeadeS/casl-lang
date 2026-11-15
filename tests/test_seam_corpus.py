"""casl.seam_corpus — the typed-seam differential ORACLE (CEP-0081, Track C brick 3). Verifies the LOCAL
side: the oracle is deterministic, covers BOTH polarities (bound ok / seam violations), equals the authority
(`seam.check_seam`), and matches the committed Rust fixture. The Rust side (casl-project::seam reproduces the
verdict + bindings) runs under cargo/CI. See docs/analyses/python-retirement-roadmap.md."""
import os
import tempfile

from casl import project, seam
from casl import seam_corpus as sc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _setup(toml: str, choreos):
    d = tempfile.mkdtemp(prefix="casl_seam_test_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    os.makedirs(os.path.join(d, "casl"), exist_ok=True)
    for i, c in enumerate(choreos):
        with open(os.path.join(d, "casl", f"c{i}.casl"), "w", encoding="utf-8") as fh:
            fh.write(c)
    return d


def test_oracle_deterministic_and_covers_both_polarities():
    corpus = sc.build_corpus()
    assert len(corpus) >= 5
    assert sc.to_text() == sc.to_text()                       # deterministic
    oks = {e["ok"] for e in corpus}
    assert oks == {True, False}, "corpus must contain BOTH bound-ok and seam-violating projects"
    assert any(e["bindings"] for e in corpus), "corpus must contain at least one successful binding"


def test_verdicts_match_the_authority():
    for e in sc.build_corpus():
        d = _setup(e["toml"], e["choreos"])
        man = project.load_manifest(d)
        ok, viol, bindings = seam.check_seam(man, d)
        assert e["ok"] == ok
        assert e["viol_count"] == len(viol)
        assert e["bindings"] == {name: [p, l, n] for name, (p, l, n) in bindings.items()}


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-project", "tests", "seam_corpus.json")
    if not os.path.exists(path):
        import pytest

        pytest.skip("rust seam corpus not generated yet (regen: python -m casl.seam_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == sc.to_text()
