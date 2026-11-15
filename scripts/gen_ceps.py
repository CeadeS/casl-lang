#!/usr/bin/env python3
"""
gen_ceps.py — generate the CEP corpus from the runtime spine, then PROVE fidelity.

One requirement (`spec.REQS`) → one CEP file in `proposals/`, with `realized-by` pulled
from the kernel building-block registry (via authority.derive_coverage). Status is derived,
never asserted by hand:

    Deferred   if the requirement is a tracked accepted gap (spec.ACCEPTED_GAPS)
    Final      if at least one building block realizes it
    Draft      otherwise

After writing, it asserts the round-trip:  cep.requirements(load) == spec.REQS  — i.e. the
generated versioned log reproduces the runtime spine exactly. The living audit then keeps
them in lock-step on every run.

Idempotent: re-running regenerates the requirement CEPs and the index. Run from the repo:
    PYTHONPATH=src python3 scripts/gen_ceps.py
"""
from __future__ import annotations
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))

from casl import spec, authority, cep  # noqa: E402

PROP = os.path.join(ROOT, "proposals")
os.makedirs(PROP, exist_ok=True)

CATEGORY = {"G": "general goal", "F": "functional", "Q": "quality",
            "P": "process / RE", "C": "core / mechanization"}
BASE = 10  # CEP numbers 1-9 reserved for process/meta CEPs (0001 process, 0002 repo structure)


def category_of(rid: str) -> str:
    parts = rid.split("-")
    return CATEGORY.get(parts[1], "requirement") if len(parts) > 1 else "requirement"


def body(rid, level, verif, theses, realized, status, gap_reason):
    th = ", ".join(f"{t} ({spec.THESES.get(t, '?')})" for t in theses)
    rb = ", ".join(f"`{b}`" for b in realized) if realized else "_(none yet)_"
    stage = {"B": "build-time check", "S": "SMT", "M": "runtime monitor",
             "T": "test / property", "—": "n/a"}.get(verif, verif)
    lines = [
        f"# CEP — Requirement {rid}",
        "",
        f"**Category:** {category_of(rid)} · **Conformance:** {level} (RFC 2119) · "
        f"**Verification stage:** {verif} ({stage})",
        "",
        "## Summary",
        "",
        f"Requirement `{rid}` of the CASL specification. This CEP is the versioned, "
        f"machine-checked record of that requirement; the runtime spine is `spec.REQS`, "
        f"and the living audit enforces that this record and the spine agree exactly.",
        "",
        "## Theses served",
        "",
        f"{th}",
        "",
        "## Realization (proof obligation)",
        "",
        f"Realized by the kernel building block(s): {rb}. The audit runs each block's "
        f"self-test; a `Final` status holds only while those blocks are present and green.",
    ]
    if status == "Deferred" and gap_reason:
        lines += ["", "## Deferral", "", f"Tracked accepted gap: {gap_reason}"]
    lines += ["", "---", "", "_Generated from `spec.REQS` by `scripts/gen_ceps.py`; "
              "edit the spec and regenerate, or promote this CEP to a hand-curated record._", ""]
    return "\n".join(lines)


def main() -> int:
    cov = authority.derive_coverage()                 # requirement-id -> [block ids]
    ids = sorted(spec.REQS)
    num = {rid: BASE + i for i, rid in enumerate(ids)}

    # clean previously-generated requirement CEPs (keep hand-written cep-0001..0009)
    for f in os.listdir(PROP):
        if f.startswith("cep-") and f.endswith(".md"):
            try:
                n = int(f.split("-")[1])
            except ValueError:
                continue
            if n >= BASE:
                os.remove(os.path.join(PROP, f))

    written = 0
    for rid in ids:
        level, verif, theses = spec.REQS[rid]
        realized = cov.get(rid, [])
        gap = rid in spec.ACCEPTED_GAPS
        status = "Deferred" if gap else ("Final" if realized else "Draft")
        n = num[rid]
        fm = [
            "---",
            f"cep: {n}",
            f"requirement-id: {rid}",
            f"title: Requirement {rid} ({category_of(rid)})",
            f"status: {status}",
            "type: Standards",
            f"level: {level}",
            f"verification: {verif}",
            f"theses: [{', '.join(theses)}]",
            f"realized-by: [{', '.join(realized)}]",
            "created: 2026-06-18",
            "version: 1.0",
            "---",
            "",
        ]
        text = "\n".join(fm) + body(rid, level, verif, theses, realized, status,
                                    spec.ACCEPTED_GAPS.get(rid, ""))
        fn = f"cep-{n:04d}-{rid.lower()}.md"
        open(os.path.join(PROP, fn), "w", encoding="utf-8").write(text)
        written += 1

    # index (CEP-0000)
    ceps = cep.load_ceps(PROP)
    idx = ["# CEP-0000 — Index", "",
           "Auto-generated. One row per CASL Enhancement Proposal.", "",
           "| CEP | Requirement | Title | Status | Level | Realized by |",
           "|----:|:-----------|:------|:-------|:------|:------------|"]
    for c in sorted(ceps, key=lambda c: int(str(c.get("cep", 0)))):
        rb = ", ".join(cep._as_list(c.get("realized-by"))) or "—"
        idx.append(f"| {c.get('cep')} | {c.get('requirement-id', '—')} | {c.get('title', '')} "
                   f"| {c.get('status', '')} | {c.get('level', '—')} | {rb} |")
    open(os.path.join(PROP, "index.md"), "w", encoding="utf-8").write("\n".join(idx) + "\n")

    # PROVE fidelity: the generated log reproduces the runtime spine exactly
    diffs = cep.roundtrip_diff(spec.REQS, ceps)
    if diffs:
        print("ROUND-TRIP MISMATCH (generated CEP corpus != spec.REQS):")
        for d in diffs:
            print("   ", d)
        return 1
    print(f"generated {written} requirement CEPs + index; round-trip exact "
          f"({len(spec.REQS)} requirements).")
    # report status breakdown
    from collections import Counter
    sc = Counter(c.get("status") for c in ceps if c.get("requirement-id"))
    print("status:", dict(sc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
