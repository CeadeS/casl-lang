"""
tcb_bridge.py — TCB differential bridge (a step toward H1 / LH-C-004).

H1 (red-team v0.1.27): the running checker is Python, the proof is F*; the full
unification (running the extracted kernel AS the checker) is blocked by the krml/Eurydice
Low* mismatch. This bridge does NOT unify the TCB, it BOUNDS its
divergence EMPIRICALLY: the F*-extracted OCaml kernel (`fstar/ocaml/driver.exe`) and the
Python checker compute MPST projectability for the SAME corpus (for all 4 roles);
any discrepancy would be a bug in exactly one implementation.

What is compared is the SHARED semantics (MPST projection for {C,A,J,D}) — Python's full
`kernel.wellformed` adds MSC realizability that the F* kernel does not (yet) have, so here
deliberately only the projection (apples-to-apples).

Offline/encapsulated: touches neither the runtime nor the living audit. Run: `make -C fstar tcb-bridge`.
"""
from __future__ import annotations
import os
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_OCAML = os.path.join(_ROOT, "fstar", "ocaml")
sys.path.insert(0, os.path.dirname(_HERE))

from casl import core            # noqa: E402
from casl.core import Comm, Choice, Branch, Rec, TVar, End  # noqa: E402
from casl import spike_proj_mpst as mpst      # noqa: E402

_ROLES = ("C", "A", "J", "D")

# Corpus — single-sourced from casl.tcb_corpus: the SAME bounded enumeration also generates
# the OCaml driver.ml (via tcb_corpus.write_driver), so the two sides of the bridge test the
# identical protocols by construction and cannot drift. Several hundred protocols (vs 6 before).
from casl.tcb_corpus import build_corpus  # noqa: E402

CORPUS = dict(build_corpus())


def projectable(g) -> bool:
    """Contractive AND MPST-projectable for ALL 4 roles — mirrors F* `wellformed`
    (which now includes the contractiveness/guardedness conjunct)."""
    from casl import semantics_sync as _ss
    if not _ss.contractive(g) or not _ss.no_self_comm(g) \
       or not _ss.gdistinct(g) or not _ss.closed(g):
        return False
    for r in _ROLES:
        try:
            mpst.project(g, r)
        except Exception:
            return False
    return True


def fstar_verdicts() -> dict:
    """Builds + runs the extracted OCaml kernel and reads `name=bool` lines."""
    subprocess.run(["dune", "build", "./driver.exe"], cwd=_OCAML, check=True,
                   capture_output=True, text=True)
    out = subprocess.run(["dune", "exec", "--no-build", "./driver.exe"], cwd=_OCAML,
                         check=True, capture_output=True, text=True).stdout
    res = {}
    for line in out.splitlines():
        line = line.strip()
        if "=" in line and line.split("=", 1)[1] in ("true", "false"):
            name, val = line.split("=", 1)
            res[name] = (val == "true")
    return res


def run() -> bool:
    py = {n: projectable(g) for n, g in CORPUS.items()}
    fs = fstar_verdicts()
    print("=" * 72)
    print("TCB DIFFERENTIAL BRIDGE — F*-extracted kernel vs. Python checker (projectability)")
    print("=" * 72)
    names = sorted(set(py) | set(fs))
    disagree = []
    for n in names:
        p, f = py.get(n), fs.get(n)
        mark = "✓" if p == f and p is not None else "✗"
        if p != f or p is None:
            disagree.append(n)
        print(f"  {mark} {n:<12} python={p}  fstar={f}")
    print("-" * 72)
    ok = not disagree
    print(f"  Result: {'✓ kernels agree on all ' + str(len(names)) + ' protocols' if ok else '✗ DIVERGENCE: ' + ', '.join(disagree)}")
    return ok


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
