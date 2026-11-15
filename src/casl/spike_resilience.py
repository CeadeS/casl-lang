"""
Spike F — resilience: crash tolerance + refusal handling  (closes audit W3, thesis T3)

Two distinct failure modes, two distinct verification stages:

  * CRASH  (LH-F-007a, stage B): a crash-prone role stops. A crash-tolerant
    protocol gives every receiver of a crash-prone sender a typed crash
    continuation (`on_crash`), so no role blocks forever. This is a STATIC,
    structural check (cf. Generalised MPST with Crash-Stop, arXiv:2207.02015).

  * REFUSAL (LH-F-007b, stage M): the oracle declines to produce a valid output.
    Refusal is a RUNTIME event in the message content, so it is handled by a
    MONITOR that treats refusal as a regular typed outcome (not blame) and a
    contract breach as blame. (Grundsatz P1: oracle behaviour handled at runtime.)
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple
from casl import core
from casl.core import G, Comm, Choice, Rec, TVar, End
from casl import spike_monitor_test as mon


# ---------- CRASH (stage B) ----------
def crash_tolerance(g: G, crash_prone=None) -> Tuple[bool, List[Tuple[str, str, str]]]:
    """Return (tolerant, gaps). A gap = a receive from a crash-prone sender that
    has no `on_crash` continuation (the receiver could block forever).
    `crash_prone` defaults to core.CRASH_PRONE; the surface CLI passes the
    protocol's own `crash` declarations."""
    crash_set = crash_prone if crash_prone is not None else core.CRASH_PRONE
    gaps: List[Tuple[str, str, str]] = []

    def walk(node: G):
        if isinstance(node, Comm):
            if node.sender in crash_set and node.on_crash is None:
                gaps.append((node.receiver, node.sender, node.label))
            walk(node.cont)
            if node.on_crash is not None:
                walk(node.on_crash)
        elif isinstance(node, Choice):
            for b in node.branches:
                walk(b.cont)
        elif isinstance(node, Rec):
            walk(node.body)
        # TVar / End: stop

    walk(g)
    return (not gaps), gaps


# ---------- REFUSAL (stage M) ----------
@dataclass(frozen=True)
class Outcome:
    ok: bool
    kind: str            # "ok" | "refusal" | "violation"
    blame: Optional[str]
    reason: str


def synth_refusal_monitor(contract, producer: str):
    """Monitor for an oracle boundary: refusal is a typed outcome (no blame),
    a contract breach is blame, otherwise ok. Wraps the budget monitor."""
    base = mon.synth_monitor(contract, producer)

    def monitor(env: dict) -> Outcome:
        if env.get("refused"):
            return Outcome(False, "refusal", None,
                           f"oracle {producer} refused — route to refusal branch (typed, no blame)")
        v = base(env)
        if v.ok:
            return Outcome(True, "ok", None, v.reason)
        return Outcome(False, "violation", v.blame, v.reason)

    return monitor


def run():
    print("=" * 72)
    print("SPIKE F — crash tolerance (B) + refusal handling (M)")
    print("=" * 72)

    tol_ok, _ = crash_tolerance(core.G_OK)
    tol_crash, gaps = crash_tolerance(core.G_OK_CRASH)
    print(f"  crash tolerance G_OK:       {'tolerant' if tol_ok else '⚠ NOT tolerant (SHOULD)'}")
    if not tol_ok:
        _, g = crash_tolerance(core.G_OK)
        for r, s, l in g:
            print(f"      · {r} waits on crash-prone {s} ({l}) with no on_crash")
    print(f"  crash tolerance G_OK_CRASH: {'tolerant ✓' if tol_crash else 'NOT tolerant'}")

    rmon = synth_refusal_monitor(core.C_COST_LE_BUDGET, "A")
    o_ok = rmon({"cost": 100, "budget": 100})
    o_ref = rmon({"refused": True, "cost": 0, "budget": 100})
    o_vio = rmon({"cost": 125, "budget": 100})
    print(f"  refusal-monitor normal:   {o_ok.kind}")
    print(f"  refusal-monitor refused:  {o_ref.kind} — {o_ref.reason}")
    print(f"  refusal-monitor overspend: {o_vio.kind} (blame {o_vio.blame})")

    return {
        "G_OK_crash_tolerant": tol_ok,            # expected False (SHOULD advisory)
        "G_OK_CRASH_tolerant": tol_crash,         # expected True
        "refusal_typed": o_ref.kind == "refusal",
        "violation_blamed": o_vio.kind == "violation" and o_vio.blame == "A",
        "normal_ok": o_ok.kind == "ok",
    }


if __name__ == "__main__":
    run()
