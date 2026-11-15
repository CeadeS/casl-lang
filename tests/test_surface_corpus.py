"""casl.surface_corpus — the parse-differential ORACLE (CEP-0081). Verifies the LOCAL side of the
strangler-fig differential that will retire surface.py: the canonical serializer is deterministic and in
sync with the parser, the canonical example still round-trips, and the corpus actually covers the grammar.
The Rust side (casl-surface reproduces every `ast`) runs in CI. See docs/analyses/python-retirement-roadmap.md."""
import os

import pytest

from casl import core, surface, surface_corpus as sc

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _walk(node, comms, choices, recs):
    if not isinstance(node, dict):
        return
    n = node.get("node")
    if n == "comm":
        comms.append(node)
        _walk(node.get("on_crash"), comms, choices, recs)
        _walk(node.get("cont"), comms, choices, recs)
    elif n == "choice":
        choices.append(node)
        for b in node.get("branches", []):
            _walk(b.get("cont"), comms, choices, recs)
    elif n == "rec":
        recs.append(node)
        _walk(node.get("body"), comms, choices, recs)


def test_oracle_in_sync_and_deterministic():
    corpus = sc.build_corpus()
    assert len(corpus) >= 5
    for e in corpus:
        # the stored ast is exactly what the parser produces for the source (single-sourced; no drift)
        assert sc.protocol_to_json(surface.parse(e["casl"])) == e["ast"]
    assert sc.to_text() == sc.to_text()                       # deterministic emission


def test_canonical_example_round_trips():
    p = surface.parse_file(os.path.join(_ROOT, "examples", "budgeted_qa.casl"))
    assert p.gtype == core.G_OK                               # parser still builds the reference AST


def test_corpus_covers_grammar_features():
    protos = sc.build_corpus()
    comms, choices, recs = [], [], []
    for e in protos:
        _walk(e["ast"]["gtype"], comms, choices, recs)
    fields = [f for c in comms for f in c["fields"]]
    fields += [f for ch in choices for b in ch["branches"] for f in b["fields"]]
    contracts = [c["contract"] for c in comms if c["contract"]]
    contracts += [b["contract"] for ch in choices for b in ch["branches"] if b["contract"]]
    assert any(c["from_oracle"] for c in comms)
    assert any(c["uses"] for c in comms)
    assert any(c["irreversible"] for c in comms)
    assert any(c["verified"] for c in comms)
    assert any(c["on_crash"] for c in comms)
    assert any(f["source"] for f in fields)                   # data forwarding
    assert any(ch["approval"] for ch in choices)
    assert any(b["consent"] for ch in choices for b in ch["branches"])
    assert any(r["stream"] for r in recs)
    assert any(r["measure"] for r in recs)
    assert any(e["ast"]["async_k"] is not None for e in protos)
    assert any(len(e["ast"]["roles"]) >= 4 for e in protos)
    assert any(cap["mode"] for e in protos for caps in e["ast"]["caps"].values() for cap in caps)
    assert any(ct["relation"] and ct["relation"][0] == "le" for ct in contracts)
    assert any(ct["relation"] and ct["relation"][0] == "nonempty" for ct in contracts)


def test_rust_corpus_in_sync_if_present():
    path = os.path.join(_ROOT, "rust", "casl-surface", "tests", "corpus.json")
    if not os.path.exists(path):
        pytest.skip("rust corpus not generated yet (regen: python -m casl.surface_corpus)")
    with open(path, encoding="utf-8") as fh:
        on_disk = fh.read()
    assert on_disk == sc.to_text()                            # committed fixture must match the oracle
