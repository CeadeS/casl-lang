"""casl.dep_corpus — the dependency-ledger differential ORACLE (CEP-0081, Track C brick 2).

Emits, per `deps.lock` source, the Python authority's parse + deny-by-default verdicts — computed by the SAME
functions the gate uses (`dependency.parse_ledger` / `check_ledger` / `supply_chain_floor` /
`check_min_evidence`), so the Rust `casl-project::dependency` differential is pinned to the reference:

  · `parse_ok`           = the ledger parses (a line with < 2 tokens is a structural error ⇒ reject).
  · `ledger_ok`          = every entry is pinned AND owned AND has a known evidence level (LH-Q-020).
  · `floor`              = the WEAKEST supply-chain evidence across deps (D5), or null when empty.
  · `min_evidence_slsa`  = check_min_evidence(deps, "slsa") — a representative threshold probe.
  · per-dep `well_formed`.

Single-sourced → `rust/casl-project/tests/dep_corpus.json`. See docs/analyses/python-retirement-roadmap.md.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from casl import dependency as dep

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-project", "tests", "dep_corpus.json"
)


def verdict(text: str) -> Dict[str, Any]:
    try:
        deps = dep.parse_ledger(text)
    except dep.LedgerError:
        return {"text": text, "parse_ok": False, "model": None}
    model: Dict[str, Any] = {
        "ledger_ok": dep.check_ledger(deps)[0],
        "floor": dep.supply_chain_floor(deps),
        "min_evidence_slsa": dep.check_min_evidence(deps, "slsa")[0],
        "deps": [
            {
                "name": d.name,
                "version": d.version,
                "sha256": d.sha256,
                "accepted_by": d.accepted_by,
                "date": d.date,
                "evidence": d.evidence,
                "well_formed": d.well_formed()[0],
            }
            for d in deps
        ],
    }
    return {"text": text, "parse_ok": True, "model": model}


_LEDGERS: List[str] = [
    # -- parses; both ledger_ok polarities, varied evidence floor --
    "# just a comment, no deps\n",                                              # empty ⇒ ok, floor null
    "requests 2.32.3 sha256:6f1ed002ab55 accepted-by:Martin date:2026-06-24\n",  # pin, well-formed
    "lib 1.0 sha256:aa11 accepted-by:Alice evidence:slsa\n",                    # floor slsa
    "a 1 sha256:aa accepted-by:A evidence:signed\nb 2 sha256:bb accepted-by:B\n",  # floor pin (weakest)
    # -- parses but NOT ledger_ok (deny-by-default) --
    "x 1.0 accepted-by:A\n",                                                    # not pinned (no sha256:)
    "y 2.0 sha256:bb\n",                                                        # no accepting human
    "z 3.0 sha256:cc accepted-by:A evidence:bogus\n",                           # unknown evidence level
    # -- structural parse error --
    "loneword\n",                                                              # < 2 tokens
]


def build_corpus() -> List[Dict[str, Any]]:
    return [verdict(t) for t in _LEDGERS]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} ledger verdict(s) → {out}")
