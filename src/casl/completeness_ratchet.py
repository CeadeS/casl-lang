"""CEP-0056 — the completeness ratchet (lightweight R2 enforcement).

Tracks the DISCLOSED human/oracle trust-budget residual across the shipped example corpus and
fails if it GROWS versus a committed baseline (a new reliance on a protocol, or a new protocol
that carries one). This is the honest, buildable core of CEP-0056:

  R1 — soundness is out of scope here: the sound core's safety verdict is never touched.
  R2 — monotone on the completeness/trust side only: the residual must not increase silently;
       shrinking it (mechanising more) is always allowed.
  R3 — the residual is irreducible (the requirement-faithfulness gap, W16/W17): the ratchet only
       forbids GROWTH, it does not require the residual to reach zero.

What is NOT here (documented future work, CEP-0056 "Open questions"): the QUANTITATIVE |H|/|A|
coverage metric against the CAV-2023 automata-complete denominator. Our semantic safety oracle
(`semantics_sync`) itself projects, so it cannot judge the safety of REJECTED (non-projectable)
protocols — the denominator needs the automata operator. Hence this module ratchets the *disclosed
trust budget* (which is concrete and sound today), not a completeness percentage.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Dict, List, Tuple

from casl import surface, levels

_HERE = os.path.dirname(os.path.abspath(__file__))
_EXAMPLES = os.path.normpath(os.path.join(_HERE, "..", "..", "examples"))
BASELINE = os.path.join(_HERE, "completeness_ratchet.baseline.json")


def _example_files(examples_dir: str) -> List[str]:
    """The example `.casl` files to ratchet over — git-TRACKED only, so untracked local
    scratch files never trip the gate and CI agrees with a local checkout. Falls back to a
    plain glob when not in a git work tree (e.g. an unpacked sdist)."""
    import subprocess
    try:
        out = subprocess.run(["git", "ls-files", "--", os.path.join(examples_dir, "*.casl")],
                              cwd=os.path.dirname(examples_dir) or ".",
                              capture_output=True, text=True, check=True).stdout
        rel = [l.strip() for l in out.splitlines() if l.strip().endswith(".casl")]
        if rel:
            root = os.path.dirname(examples_dir) or "."
            return sorted(os.path.join(root, p) for p in rel)
    except Exception:
        pass
    return sorted(glob.glob(os.path.join(examples_dir, "*.casl")))


def snapshot(examples_dir: str = _EXAMPLES) -> Dict[str, List[str]]:
    """Per-protocol disclosed trust-budget reliances (only protocols that carry any)."""
    out: Dict[str, List[str]] = {}
    for f in _example_files(examples_dir):
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            proto = surface.parse_file(f)
        except Exception:
            continue
        tb = sorted(f"{k}:{m}" for k, m in levels.trust_budget(proto))
        if tb:
            out[name] = tb
    return out


def load_baseline() -> Dict[str, List[str]]:
    if not os.path.exists(BASELINE):
        return {}
    with open(BASELINE, encoding="utf-8") as fh:
        return json.load(fh)


def check(examples_dir: str = _EXAMPLES) -> Tuple[bool, List[str]]:
    """(ok, violations): a violation is any reliance present now but absent from the baseline
    for that protocol (growth), or any new protocol carrying a reliance. Shrinking never violates."""
    cur = snapshot(examples_dir)
    base = load_baseline()
    viol: List[str] = []
    for name, rel in cur.items():
        b = set(base.get(name, []))
        grew = [r for r in rel if r not in b]
        if grew:
            viol.append(f"{name}: new disclosed trust reliance {grew} not in baseline")
    return (not viol, viol)


def update(examples_dir: str = _EXAMPLES) -> Dict[str, List[str]]:
    snap = snapshot(examples_dir)
    with open(BASELINE, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return snap


def main(argv=None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="casl-ratchet",
                                description="CEP-0056 completeness ratchet — the disclosed residual must not grow")
    p.add_argument("--check", action="store_true", help="exit 1 if the residual grew vs the baseline (R2)")
    p.add_argument("--update", action="store_true", help="re-baseline to the current snapshot (records the change)")
    a = p.parse_args(argv)
    if a.update:
        snap = update()
        print(f"baseline updated: {sum(len(v) for v in snap.values())} reliance(s) over {len(snap)} protocol(s)")
        return 0
    snap = snapshot()
    n = sum(len(v) for v in snap.values())
    print(f"completeness ratchet — disclosed human/oracle residual: {n} reliance(s) over {len(snap)} protocol(s)")
    ok, viol = check()
    if not ok:
        print("  ✗ RATCHET VIOLATION (residual grew vs baseline — CEP-0056 R2):")
        for v in viol:
            print("     " + v)
        print("  If intended, re-baseline: python -m casl.completeness_ratchet --update")
        return 1 if a.check else 0
    print("  ✓ residual has not grown vs baseline (CEP-0056 R2 holds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
