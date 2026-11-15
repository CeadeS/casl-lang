"""
proof_loop.py — SP-5: the LLM-proposes / F*-decides proof loop.

The robust pattern (COPRA, Draft-Sketch-Prove; 4/δ convergence): an LLM is an UNTRUSTED proposer
inside a search whose every candidate is adjudicated by the trusted prover. Here F* is the SOLE
acceptor — a candidate proof is accepted iff (1) it contains NO proof hole (admit/assume/sorry/
magic) and (2) `fstar.exe` discharges all verification conditions (RC=0). The LLM verdict is never
trusted; on failure the goal stays OPEN (fail-closed), never "assumed". This mirrors
scripts/check_admits.sh, so the loop cannot manufacture a verdict.

Targets the genuinely-hard residual obligations (D2 merge/projection completeness à la
Scalas–Yoshida = W19; the merge recursion-DEPTH bound = W18). Honest expectation: those may not
close — what the loop cannot prove stays a tracked, bounded result, not a silent assumption.

See docs/analyses/verification-mode-and-tcb-unification.md §SP-5 and CEP-0054.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_FSTAR_DIR = os.path.join(_ROOT, "fstar")

# Anything that would let a "proof" pass vacuously / on trust — forbidden in a candidate.
_HOLE = re.compile(r"\b(admit|assume|sorry|magic|Admitted|admit_smt_queries)\b")


def proof_holes(text: str) -> List[str]:
    return sorted(set(_HOLE.findall(text)))


@dataclass
class ProofGoal:
    """An F* obligation: `header` is the full lemma signature ending in `=`, the generator supplies
    the body. `open`-ing the verified CASL core lets goals refer to merge/projection/etc."""
    name: str
    header: str
    status: str = "open"          # open | proved | bounded (tracked, unproved)
    note: str = ""


# A generator: (header, prior_error) -> proposed proof body (untrusted).
Generator = Callable[[str, Optional[str]], str]


def toolchain_available() -> bool:
    import shutil
    return shutil.which("fstar.exe") is not None and os.path.isfile(os.path.join(_FSTAR_DIR, "CASL.fst"))


def verify_candidate(header: str, body: str, timeout: int = 120) -> Tuple[bool, str]:
    """F* is the SOLE acceptor. Reject pre-emptively if the candidate has any proof hole; else
    write `module CASLProof; open CASL; <header><body>` and run fstar.exe. Accept iff RC=0."""
    candidate = header.rstrip() + "\n" + body.rstrip() + "\n"
    holes = proof_holes(candidate)
    if holes:
        return False, f"rejected (fail-closed): proof holes {holes} — the prover cannot be bypassed"
    src = "module CASLProof\nopen CASL\n\n" + candidate
    path = os.path.join(_FSTAR_DIR, "CASLProof.fst")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(src)
        r = subprocess.run(["fstar.exe", "--include", ".", "CASLProof.fst"], cwd=_FSTAR_DIR,
                           capture_output=True, text=True, timeout=timeout)
        ok = (r.returncode == 0 and "All verification conditions discharged" in r.stdout)
        return ok, ("verified" if ok else (r.stdout + r.stderr)[-800:])
    except subprocess.TimeoutExpired:
        return False, "rejected: F* timeout"
    finally:
        for p in (path, path + ".checked"):
            try:
                os.remove(p)
            except OSError:
                pass


def attempt(goal: ProofGoal, generator: Generator, max_iters: int = 4) -> dict:
    """Fail-closed proof search: the generator proposes a body, F* decides, the error feeds the
    next attempt. Returns the working body iff F* verified it; otherwise verified=False (the goal
    stays open). The loop terminates (bounded iters); convergence-if-provable is the 4/δ result."""
    err: Optional[str] = None
    for i in range(1, max_iters + 1):
        body = generator(goal.header, err)            # untrusted proposal
        ok, msg = verify_candidate(goal.header, body)
        if ok:
            return {"verified": True, "body": body, "iters": i, "error": None}
        err = msg
    return {"verified": False, "body": None, "iters": max_iters, "error": err}


class MockGenerator:
    """Deterministic offline generator: yields the given candidate bodies in order (simulating an
    LLM that may need a few tries). For tests/demos without a live model."""
    def __init__(self, bodies: List[str]):
        self._bodies = list(bodies)
        self._i = 0

    def __call__(self, header: str, prior_error: Optional[str]) -> str:
        b = self._bodies[min(self._i, len(self._bodies) - 1)]
        self._i += 1
        return b


# ---------------------------------------------------------------------------
# Goal registry — the residual obligations the loop targets. (W18's fuel
# sufficiency is now PROVED in the core: CASL.merge_complete, 0 admits.) W19
# projection/merge completeness remains a tracked bounded result.
# ---------------------------------------------------------------------------
PENDING_GOALS: List[ProofGoal] = [
    ProofGoal(
        name="merge_projection_completeness",
        header=("// W19: projection/merge completeness (Scalas–Yoshida): every coherent global type\n"
                "// projects + merges. Genuinely hard; may stay a tracked bounded result.\n"
                "// let project_complete (g:gtyp) : Lemma (requires coherent g) (ensures wellformed g) ="),
        status="bounded",
        note="Scalas–Yoshida-grade; tracked as W19, not assumed."),
    # proj_subst_commute (W19-A c': projectability preserved by unfolding GRec) — DISCHARGED, 0 admits,
    # in fstar/W19ProjSubst.fst (unfold_projectable, for gdistinct protocols). subst_opts_inj closed via
    # merge_opts_lookup (assoc-lookup characterisation of merge_opts_f). No longer a pending goal; to land
    # in the core: add gdistinct to wellformed + extend preservation's GS_Rec case. See docs §8c.
]
