"""
Spike E — capability containment  [LH-Q-002, LH-F-005; stage B]  (closes audit W1)

Grundsatz P5 (Least Privilege): a tool may only be used via a capability in the
agent's set; a use outside the set is a TYPE ERROR (static, stage B). This spike
walks the global type and checks every `uses_capability` against the sender's
capability set (casl_core.AGENT_CAPS).

It also reports the ttl-vs-recursion tension (audit W4): a capability with a
finite ttl used inside a mu-loop can be invoked more often than ttl allows.
"""
from __future__ import annotations
from typing import List, Tuple
from casl import core
from casl.core import G, Comm, Choice, Rec, TVar, End, Field


def _capset(role: str, capmap=None):
    capmap = capmap if capmap is not None else core.AGENT_CAPS
    return {c.tool: c for c in capmap.get(role, ())}


def capability_check(g: G, name: str, caps=None):
    """Least-Privilege containment over a capability map (role -> Capability tuple).
    `caps` defaults to the canonical core.AGENT_CAPS; the surface CLI passes the
    protocol's own `agent ... caps {}` declarations so the check binds to the
    file under test, not the BudgetedQA fixture."""
    capmap = caps if caps is not None else core.AGENT_CAPS
    violations: List[Tuple[str, str, str]] = []
    ttl_in_loop: List[Tuple[str, str, int]] = []

    def walk(node: G, under_rec: bool):
        if isinstance(node, Comm):
            if node.uses_capability:
                caps = _capset(node.sender, capmap)
                if node.uses_capability not in caps:
                    violations.append((node.sender, node.uses_capability, node.label))
                elif under_rec and caps[node.uses_capability].ttl != 0:
                    ttl_in_loop.append((node.sender, node.uses_capability,
                                        caps[node.uses_capability].ttl))
            walk(node.cont, under_rec)
        elif isinstance(node, Choice):
            for b in node.branches:
                walk(b.cont, under_rec)
        elif isinstance(node, Rec):
            walk(node.body, True)
        # TVar / End: stop

    walk(g, False)
    ok = not violations
    print(f"  capability containment for {name}: {'OK (well-typed)' if ok else 'TYPE ERROR'}")
    for s, t, l in violations:
        allowed = sorted(_capset(s, capmap).keys()) or "∅"
        print(f"    ✗ agent {s} uses tool '{t}' (msg {l}) outside its capability set {allowed}")
    for s, t, ttl in ttl_in_loop:
        print(f"    ⚠ ttl tension (W4): {s} uses '{t}' (ttl={ttl}) inside a loop → "
              f"may exceed ttl across iterations")
    return ok


# A deliberately ill-typed protocol: A uses 'delete', which is NOT in A's set.
G_CAP_BAD = Comm("C", "A", "Request", (core._q, core._b),
                 Comm("A", "J", "Draft", (core._ans, core._cost), End(),
                      contract=core.C_COST_LE_BUDGET,
                      uses_capability="delete", from_oracle=True))


def run():
    print("=" * 72)
    print("SPIKE E — capability containment (Least Privilege, stage B)")
    print("=" * 72)
    ok_good = capability_check(core.G_OK, "G_OK")           # uses 'search' ∈ A's set
    ok_bad = capability_check(G_CAP_BAD, "G_CAP_BAD")       # uses 'delete' ∉ A's set
    return {"G_OK_well_typed": ok_good, "G_CAP_BAD_rejected": (ok_bad is False)}


if __name__ == "__main__":
    run()
