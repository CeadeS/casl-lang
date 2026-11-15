"""casl.obligation_corpus — assurance-grade-composition differential ORACLE (CEP-0081, Track C brick 5).

Emits, per `casl.toml`, the Python authority's grade arithmetic — computed by `obligation_gate.effective_grade`
(weakest artifact floor, LH-Q-019) and `obligation_gate.grade_by_requirement` (weakest floor per requirement,
CEP-0070 model A). These are the PURE grade functions the Tier-0 gate reports; the deny-by-default gate itself
(attestation crypto, git line-trace) stays in Python. Single-sourced → `rust/casl-project/tests/obligation_corpus.json`.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List

from casl import obligation_gate as og
from casl import project

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-project", "tests", "obligation_corpus.json"
)


def verdict(toml: str) -> Dict[str, Any]:
    d = tempfile.mkdtemp(prefix="casl_oblig_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    man = project.load_manifest(d)
    return {
        "toml": toml,
        "effective_grade": og.effective_grade(man),
        "grade_by_requirement": og.grade_by_requirement(man),
    }


def _man(*arts: str) -> str:
    return 'name = "p"\nversion = "0.1.0"\n' + "".join(arts)


def _art(name: str, kind: str, req: str, *, grade: str = "G3", body: bool = False) -> str:
    s = f'[[artifact]]\nname = "{name}"\nkind = "{kind}"\nrequirement = "{req}"\ngrade = "{grade}"\n'
    if body:
        s += f'body = "artifacts/{name}.py"\n'
    return s


_MANIFESTS: List[str] = [
    _man(),                                                              # empty ⇒ G0
    _man(_art("s", "verified", "R", grade="G0", body=True)),            # G0
    _man(_art("o", "oracle", "R")),                                    # oracle ⇒ floor G3
    _man(_art("s", "verified", "R1", grade="G0", body=True), _art("o", "oracle", "R2")),  # weakest G3; per-req split
    _man(_art("s", "verified", "R", grade="G0", body=True), _art("g", "generated", "R", grade="G2", body=True)),  # same req, weakest G3
    _man(_art("g", "generated", "R", grade="G1", body=True)),           # declares G1 but floors G3 (unprovable)
    _man(_art("v1", "verified", "R1", grade="G0", body=True), _art("v2", "verified", "R2", grade="G2", body=True)),  # G0/G2 buckets, eff G2
]


def build_corpus() -> List[Dict[str, Any]]:
    return [verdict(t) for t in _MANIFESTS]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} grade-composition verdict(s) → {out}")
