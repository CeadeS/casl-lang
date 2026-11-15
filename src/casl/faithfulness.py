"""
faithfulness.py — SP-4: the proof-faithfulness anti-vacuity front-line (CEP-0004).

A machine-checked proof guarantees only that the code meets the WRITTEN statement, never that
the statement matches intent. There is no algorithmic closure of that gap (Lahiri 2024), so the
root is human attestation — but pure "LLM-pre + human-post" wastes the human on failures that
cheap mechanical proxies catch. This module is that front-line: it kills the documented failure
modes BEFORE the human, who then attests only the residual.

Three checks (see docs/analyses/verification-mode-and-tcb-unification.md §3):
  1. NON-VACUITY WITNESSES — every metatheorem must have a firing witness so its preconditions
     are demonstrably satisfiable (Beer et al. vacuity). The F* core carries `_ex_*`/`_fid_demo`/
     `_conserv_demo`; here we GATE that they still exist (a future edit that drops them, making a
     theorem potentially vacuous, fails loudly).
  2. DISCRIMINATING POWER (spec mutation, IronSpec/MutDafny) — a curated set of ill-formed
     protocols that the checker MUST reject; a survivor means the spec is too weak.
  3. CONSISTENCY TRIANGULATION (Clover) — the per-feature CEPs' natural-language claims must agree
     with the formal `levels.FEATURES` table (NL ↔ formal must not drift).
"""
from __future__ import annotations

import os
import re
from typing import List, Tuple

from casl.core import Comm, Choice, Branch, End
from casl import spike_proj_mpst as mpst
from casl import levels

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
_FST = os.path.join(_ROOT, "fstar", "CASL.fst")

# Non-vacuity witnesses that must remain present in the F* core.
WITNESS_LEMMAS = ["_ex_msg", "_ex_ch", "_fid_demo", "_conserv_demo"]


def missing_witnesses() -> List[str]:
    """Witness lemmas absent from CASL.fst — non-empty ⇒ a metatheorem may be vacuous."""
    try:
        txt = open(_FST, encoding="utf-8").read()
    except OSError:
        return []                       # F* sources absent (pip install) — gate is repo-only
    return [w for w in WITNESS_LEMMAS
            if re.search(r"\blet\s+(rec\s+)?" + re.escape(w) + r"\b", txt) is None]


def _projectable(g) -> bool:
    """The spec under test: MPST-projectable for all four roles (mirrors F* `wellformed`)."""
    for r in ("C", "A", "J", "D"):
        try:
            mpst.project(g, r)
        except Exception:
            return False
    return True


def must_die() -> List[Tuple[str, object]]:
    """Curated ILL-FORMED protocols the checker MUST reject (hand-verified non-projectable):
    each has a third role whose branch behaviours cannot be merged."""
    return [
        # role J: sends in l1 but is absent in l2 → LSnd vs LEnd not mergeable
        ("J_send_vs_absent",
         Choice("C", "A", (Branch("l1", (), Comm("J", "A", "m", (), End())),
                           Branch("l2", (), End())))),
        # role J: receives from A in l1 but absent in l2 → LRcv vs LEnd not mergeable
        ("J_recv_vs_absent",
         Choice("C", "A", (Branch("l1", (), Comm("A", "J", "m", (), End())),
                           Branch("l2", (), End())))),
        # role J: sends in l1, role D acts in l2 → J: LSnd vs LEnd not mergeable
        ("J_send_vs_D_act",
         Choice("C", "A", (Branch("l1", (), Comm("J", "A", "x", (), End())),
                           Branch("l2", (), Comm("D", "A", "y", (), End()))))),
    ]


def mutation_survivors() -> List[str]:
    """Names of must-die protocols the checker WRONGLY accepts — non-empty ⇒ spec too weak."""
    return [n for n, g in must_die() if _projectable(g)]


# feature CEP number -> feature key
_CEP_FEATURE = {5: "nary_choice", 6: "async", 7: "oracle", 8: "verified"}


def cep_feature_consistency() -> List[str]:
    """Drift between each per-feature CEP's natural-language (profile, grade) and the formal
    `levels.FEATURES` table. Non-empty ⇒ the prose and the code disagree."""
    from casl import cep
    out: List[str] = []
    by_num = {}
    for c in cep.load_ceps():
        try:
            by_num[int(str(c.get("cep")))] = c
        except (TypeError, ValueError):
            continue
    for num, feat in _CEP_FEATURE.items():
        c = by_num.get(num)
        if not c:
            out.append(f"CEP-{num:04d} ({feat}) missing")
            continue
        title = c.get("title", "")
        prof, grade = levels.FEATURES[feat]
        m = re.search(r"(core|extended|advisory).*?(G[0-3])", title)
        if not m:
            out.append(f"CEP-{num:04d} title states no (profile, grade)")
        elif (m.group(1), m.group(2)) != (prof, grade):
            out.append(f"CEP-{num:04d} says {m.group(1)}/{m.group(2)} but FEATURES has {prof}/{grade}")
    return out


def report() -> dict:
    return {"missing_witnesses": missing_witnesses(),
            "mutation_survivors": mutation_survivors(),
            "cep_drift": cep_feature_consistency()}


def ok() -> bool:
    r = report()
    return not (r["missing_witnesses"] or r["mutation_survivors"] or r["cep_drift"])
