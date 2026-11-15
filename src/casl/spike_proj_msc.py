"""
Spike B — MSC-style projection  [TBD-003 alternative 2]   (v2: + recursion)

Treats the choreography as a (High-level) MSC: each branch is a basic MSC of
send/receive events over lifelines; choice is alternative composition; the
Retry branch is a loop back-edge (rendered ↺Loop, not unrolled infinitely).
Projection = per-lifeline event sequence. Well-formedness is REALIZABILITY:
a "non-local choice" arises when a lifeline behaves differently across
alternatives without a distinguishing receive (implied-scenario problem).

Same canonical fixture as Spike A → head-to-head comparison for TBD-003.
Cf. arXiv:2604.17612 (projection-based MSC coordination for LLM agents).
"""
from __future__ import annotations
from typing import List, Tuple
from casl import core
from casl.core import G, Comm, Choice, Branch, Rec, TVar, End

Event = str


def scenarios(g: G, prefix=None) -> List[Tuple[str, List]]:
    """Expand the hMSC into basic MSCs (one per branch path). Recursion is
    entered once; a TVar emits a loop-marker event ("*","*",var) and stops."""
    prefix = prefix or []

    def name_of(pfx):
        labels = [p for p, _ in pfx if p]
        return "·".join(labels) if labels else "main"

    if isinstance(g, End):
        return [(name_of(prefix), prefix)]
    if isinstance(g, TVar):
        return [(name_of(prefix), prefix + [("", ("*", "*", g.var))])]
    if isinstance(g, Rec):
        return scenarios(g.body, prefix)
    if isinstance(g, Comm):
        return scenarios(g.cont, prefix + [("", (g.sender, g.receiver, g.label))])
    if isinstance(g, Choice):
        out = []
        for br in g.branches:
            tag = [(br.label, (g.sender, g.receiver, br.label))]
            out.extend(scenarios(br.cont, prefix + tag))
        return out
    raise TypeError(type(g))


def lifeline_projection(events: List, role: str) -> List[Event]:
    seq = []
    for _label, (s, r, lbl) in events:
        if s == "*" and r == "*":
            seq.append(f"↺{lbl}")
            continue
        if s == role:
            seq.append(f"!{r}:{lbl}")
        if r == role:
            seq.append(f"?{s}:{lbl}")
    return seq


def realizability(g: G, name: str, roles=None) -> bool:
    """Realizability over a role set. `roles` defaults to the canonical
    core.ROLES; the surface CLI passes the protocol's own declared roles so the
    check is protocol-parametric, not bound to the BudgetedQA fixture."""
    roles = roles if roles is not None else core.ROLES
    problems = []

    def check(node: G):
        if isinstance(node, Comm):
            check(node.cont)
        elif isinstance(node, Rec):
            check(node.body)
        elif isinstance(node, Choice):
            for role in roles:
                if role in (node.sender, node.receiver):
                    continue
                projs = []
                for br in node.branches:
                    evs = scenarios(br.cont)
                    seq = lifeline_projection(evs[0][1], role) if evs else []
                    projs.append(seq)
                if any(p != projs[0] for p in projs):
                    # hardened (W2): inspect the FIRST POSITION where branches
                    # differ, not just position 0; that event must be a receive.
                    maxlen = max(len(p) for p in projs)
                    for i in range(maxlen):
                        elems = [p[i] if i < len(p) else None for p in projs]
                        if all(e == elems[0] for e in elems):
                            continue
                        if any(e is None for e in elems):
                            problems.append(
                                f"role {role}: branches diverge in length at step {i + 1} "
                                f"without a distinguishing message → non-local choice")
                        elif any(not e.startswith("?") for e in elems):
                            bad = next(e for e in elems if not e.startswith("?"))
                            problems.append(
                                f"role {role}: first divergence {bad} is not a receive "
                                f"→ branch not locally determinable")
                        break
            for br in node.branches:
                check(br.cont)
        # End / TVar: nothing

    check(g)
    realizable = not problems
    print(f"  MSC realizability of {name}: "
          f"{'realizable (well-formed)' if realizable else 'REJECTED'}")
    for p in dict.fromkeys(problems):
        print(f"    ✗ {p}")
    return realizable


def show_lifelines(g: G, name: str):
    print(f"  MSC per-lifeline projections of {name} (by scenario):")
    for sname, evs in scenarios(g):
        print(f"    scenario [{sname}]:")
        for role in core.ROLES:
            seq = lifeline_projection(evs, role)
            print(f"      {role}: {' . '.join(seq) if seq else '(no events)'}")


def run():
    print("=" * 72)
    print("SPIKE B — MSC projection (recursive)")
    print("=" * 72)
    show_lifelines(core.G_OK, "G_OK")
    ok1 = realizability(core.G_OK, "G_OK")
    print()
    show_lifelines(core.G_BAD, "G_BAD")
    ok2 = realizability(core.G_BAD, "G_BAD")
    return {"G_OK_realizable": ok1, "G_BAD_realizable": ok2}


if __name__ == "__main__":
    run()
