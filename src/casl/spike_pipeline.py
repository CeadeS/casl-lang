"""
spike_pipeline.py — pipeline well-formedness (LH-F-011, CASL-IDE Phase 4): the node trichotomy.

A pipeline is a choreography whose value-producing nodes are ONE of three kinds:
  · oracle    — opaque, nondeterministic producer (LLM box): NEVER trusted, monitored at the boundary.
  · verified  — deterministic, VERIFIED program (within the proved hull): no monitor needed,
                but the machine cannot prove an external program ⇒ trust is NOT granted from
                the marker (human attestation in the IDE, Tier 3).
  · (plain)   — ordinary participant.

The Tier-0 gate checks the STRUCTURAL consistency of the trichotomy (deny-by-default):
  R1  no node is both `oracle` AND `verified` (opaque vs. proved — a contradiction).
  R2  every `oracle` node carries a contract — the monitored boundary; an unmonitored
      opaque output is not permitted.

Vacuously true for protocols WITHOUT `oracle`/`verified`. The trust attestation of `verified`
(R3) is NOT a Tier-0 matter but lives in the IDE gate (Tier 3) — see casl_ide.
"""
from __future__ import annotations
from casl import core


def _comms(g):
    out = []

    def w(n):
        if isinstance(n, core.Comm):
            out.append(n)
            w(n.cont)
            if n.on_crash is not None:
                w(n.on_crash)
        elif isinstance(n, core.Choice):
            for b in n.branches:
                w(b.cont)
        elif isinstance(n, core.Rec):
            w(n.body)
    w(g)
    return out


def pipeline_safe(g):
    """(ok, violations). violations: list of (node, reason)."""
    viol = []
    for n in _comms(g):
        ver = getattr(n, "verified", False)
        tag = f"{n.sender}→{n.receiver}:{n.label}"
        if n.from_oracle and ver:
            viol.append((tag, "both oracle AND verified (opaque vs. proven — a contradiction)"))
        if n.from_oracle and n.contract is None:
            viol.append((tag, "oracle node without a contract (monitored boundary missing)"))
    return (not viol), viol


def uses_markers(g) -> bool:
    """Does the protocol use the pipeline markers (oracle/verified)? — then `pipeline_safe` is relevant."""
    return any(c.from_oracle or getattr(c, "verified", False) for c in _comms(g))


def verified_nodes(g):
    """The `verified` nodes (trust claims that must be humanly attested in the IDE)."""
    return [f"{n.sender}→{n.receiver}:{n.label}" for n in _comms(g) if getattr(n, "verified", False)]


if __name__ == "__main__":
    from casl import surface
    import os
    EX = os.path.join(os.path.dirname(__file__), "..", "..", "examples")
    for fn in sorted(f for f in os.listdir(EX) if f.endswith(".casl")):
        try:
            p = surface.parse_file(os.path.join(EX, fn))
        except Exception as e:
            print(f"  {fn}: parse-fail {e!r}"); continue
        ok, viol = pipeline_safe(p.gtype)
        mark = "marker" if uses_markers(p.gtype) else "—"
        if not ok:
            print(f"  ✗ {fn} ({mark}): " + "; ".join(f"{t}: {r}" for t, r in viol))
        else:
            print(f"  ✓ {fn} ({mark})")
