"""casl.project_corpus — the manifest-differential ORACLE (CEP-0081, Track C brick 1). Verifies the LOCAL
side of the differential that will retire the Python manifest-load verdict: the oracle is deterministic,
covers BOTH polarities (accept + deny-by-default reject), equals a fresh `project.load_manifest`, and matches
the committed Rust fixture. The Rust side (casl-project reproduces every verdict + model from text) runs under
cargo/CI. See docs/analyses/python-retirement-roadmap.md."""
import os
import tempfile

import pytest

from casl import project
from casl import project_corpus as pc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(toml: str):
    d = tempfile.mkdtemp(prefix="casl_manifest_test_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    return project.load_manifest(d)


def test_oracle_deterministic_and_covers_both_polarities():
    corpus = pc.build_corpus()
    assert len(corpus) >= 5
    assert pc.to_text() == pc.to_text()                       # deterministic
    oks = {e["ok"] for e in corpus}
    assert oks == {True, False}, "corpus must contain BOTH accepted and rejected manifests"
    # accepted entries carry a model; rejected ones do not
    for e in corpus:
        assert (e["model"] is not None) == e["ok"]


def test_verdicts_match_the_authority():
    # the stored verdict equals a fresh load via the SAME function the CLI/conductor use (no drift)
    for e in pc.build_corpus():
        if e["ok"]:
            m = _load(e["toml"])
            assert e["model"] == pc._manifest_json(m)
        else:
            with pytest.raises(project.ManifestError):
                _load(e["toml"])


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-project", "tests", "corpus.json")
    if not os.path.exists(path):
        pytest.skip("rust project corpus not generated yet (regen: python -m casl.project_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == pc.to_text()                      # committed fixture must match the oracle
