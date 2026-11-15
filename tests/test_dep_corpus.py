"""casl.dep_corpus — the dependency-ledger differential ORACLE (CEP-0081, Track C brick 2). Verifies the
LOCAL side: the oracle is deterministic, covers BOTH polarities (parse ok/error, ledger ok/violating), equals
the authority (`dependency.*`), and matches the committed Rust fixture. The Rust side (casl-project reproduces
every verdict from text) runs under cargo/CI. See docs/analyses/python-retirement-roadmap.md."""
import os

import pytest

from casl import dependency as dep
from casl import dep_corpus as dc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_oracle_deterministic_and_covers_both_polarities():
    corpus = dc.build_corpus()
    assert len(corpus) >= 5
    assert dc.to_text() == dc.to_text()                       # deterministic
    parse = {e["parse_ok"] for e in corpus}
    assert parse == {True, False}, "corpus must contain BOTH parseable and structurally-malformed ledgers"
    ledger = {e["model"]["ledger_ok"] for e in corpus if e["parse_ok"]}
    assert ledger == {True, False}, "corpus must contain BOTH well-formed and deny-by-default ledgers"
    # parse_ok ⇔ a model is present
    for e in corpus:
        assert (e["model"] is not None) == e["parse_ok"]


def test_verdicts_match_the_authority():
    for e in dc.build_corpus():
        if not e["parse_ok"]:
            with pytest.raises(dep.LedgerError):
                dep.parse_ledger(e["text"])
            continue
        deps = dep.parse_ledger(e["text"])
        m = e["model"]
        assert m["ledger_ok"] == dep.check_ledger(deps)[0]
        assert m["floor"] == dep.supply_chain_floor(deps)
        assert m["min_evidence_slsa"] == dep.check_min_evidence(deps, "slsa")[0]
        assert [d["well_formed"] for d in m["deps"]] == [d.well_formed()[0] for d in deps]


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-project", "tests", "dep_corpus.json")
    if not os.path.exists(path):
        pytest.skip("rust dep corpus not generated yet (regen: python -m casl.dep_corpus)")
    with open(path, encoding="utf-8") as fh:
        assert fh.read() == dc.to_text()                      # committed fixture must match the oracle
