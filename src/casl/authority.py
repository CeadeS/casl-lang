"""
authority.py — enforces "all authority derives from the specifications".

It derives the coverage map FROM the kernel's building-block registry (not a
hand-maintained list), and validates that:
  (a) every building block cites only spec items that actually exist
      (requirements in spec.REQS, a principle in spec.GRUNDSAETZE, theses in
      spec.THESES) — a block with invented authority is a violation;
  (b) every executable-verifiable requirement is realized by >=1 block or is a
      tracked, accepted gap.

This is the chain of authority: spec.py -> building blocks -> features.
"""
from __future__ import annotations
from typing import Dict, List, Tuple

from casl import spec
from casl import kernel


def derive_coverage() -> Dict[str, List[str]]:
    """requirement id -> [building-block ids that realize it] (derived, not declared)."""
    cov: Dict[str, List[str]] = {}
    for bid, m in kernel.REGISTRY.items():
        for rid in m["realizes"]:
            cov.setdefault(rid, []).append(bid)
    return cov


def validate_blocks() -> List[Tuple[str, str]]:
    """Each block may only cite authority that exists in spec.py."""
    violations: List[Tuple[str, str]] = []
    for bid, m in kernel.REGISTRY.items():
        for rid in m["realizes"]:
            if rid not in spec.REQS:
                violations.append((bid, f"realizes unknown requirement {rid}"))
        if m["grundsatz"] not in spec.GRUNDSAETZE:
            violations.append((bid, f"cites unknown principle {m['grundsatz']}"))
        for t in m["these"]:
            if t not in spec.THESES:
                violations.append((bid, f"cites unknown thesis {t}"))
    return violations


def uncovered_requirements(cov: Dict[str, List[str]]) -> List[str]:
    out = []
    for rid, (_stufe, verif, _src) in spec.REQS.items():
        if not spec.is_executable(verif):
            continue
        if cov.get(rid) or rid in spec.ACCEPTED_GAPS:
            continue
        out.append(rid)
    return out


def thesis_coverage(cov: Dict[str, List[str]]) -> Dict[str, List[str]]:
    tc = {t: [] for t in spec.THESES}
    for rid in cov:
        for t in spec.REQS[rid][2]:
            tc[t].append(rid)
    return tc


def check() -> Tuple[bool, dict]:
    cov = derive_coverage()
    block_violations = validate_blocks()
    uncovered = uncovered_requirements(cov)
    tc = thesis_coverage(cov)
    empty_theses = [t for t, rs in tc.items() if not rs]
    ok = not block_violations and not uncovered and not empty_theses
    return ok, {
        "coverage": cov,
        "block_violations": block_violations,
        "uncovered": uncovered,
        "thesis_coverage": tc,
        "empty_theses": empty_theses,
    }


if __name__ == "__main__":
    ok, d = check()
    print("authority OK" if ok else "authority VIOLATION", "—", len(d["coverage"]), "covered reqs")
