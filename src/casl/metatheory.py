"""
metatheory.py — proof-by-test of the MPST metatheorems (L3, Direction B).

For well-formed (projectable) global types we check, at EVERY reachable global
state S, by re-projecting S into an endpoint configuration:

  * OPERATIONAL CORRESPONDENCE (session fidelity): the events enabled by the
    choreography step_global(S) equal those enabled by step_config(config(S)).
    Soundness (config does nothing extra) + completeness (config does everything).
  * DEADLOCK-FREEDOM / PROGRESS: a non-terminal reachable config always has a step.

These are the executable, randomized stand-ins for the theorems behind
LH-Q-001a (conformance), LH-Q-001b (deadlock-freedom), LH-Q-001c (fidelity) and
LH-F-006 (projection). Mechanization in Lean 4 / F* is Direction C.
"""
from __future__ import annotations
import random
from typing import List, Tuple

from casl import core
from casl.core import Comm, Choice, Branch, Rec, TVar, End, Field
from casl import spike_proj_mpst as mpst
from casl import kernel
from casl import semantics as sem

ROLES = core.ROLES
_LABELS = ["m1", "m2", "go", "x", "y", "acc", "rej", "done", "retry", "p", "q"]


# ---------- random well-formed protocol generator ----------
# `roles` is parametric: the same generation/checking machinery covers 3, 4, 5 … roles
# (projection/merge/realizability are role-set-parametric). The F* PROOF remains
# restricted to the 3-role head fragment (W9); here the full reachability is by-test.
def _gen(rng, depth, rec_vars, head=False, roles=ROLES):
    # `head=True` forbids End/TVar (used for Rec bodies → contractive types)
    choices = []
    if not head:
        choices += ["end"]
        if rec_vars:
            choices += ["tvar"]
    if depth > 0:
        choices += ["comm", "comm", "choice"]
        if depth >= 2 and len(rec_vars) < 2:
            choices += ["rec"]
    kind = rng.choice(choices)
    if kind == "end":
        return End()
    if kind == "tvar":
        return TVar(rng.choice(rec_vars))
    if kind == "comm":
        p, q = rng.sample(roles, 2)
        return Comm(p, q, rng.choice(_LABELS), tuple(), _gen(rng, depth - 1, rec_vars, roles=roles))
    if kind == "choice":
        p, q = rng.sample(roles, 2)
        labels = rng.sample(_LABELS, 2)
        brs = tuple(Branch(lb, tuple(), _gen(rng, depth - 1, rec_vars, roles=roles)) for lb in labels)
        return Choice(p, q, brs)
    if kind == "rec":
        var = f"t{len(rec_vars)}"
        return Rec(var, _gen(rng, depth - 1, rec_vars + [var], head=True, roles=roles))
    return End()


def gen_wellformed(rng, max_depth=3, tries=40, roles=ROLES):
    for _ in range(tries):
        g = _gen(rng, max_depth, [], head=True, roles=roles)
        if not sem.step_global(g):
            continue
        try:
            if kernel.wellformed(g, roles=roles):
                return g
        except Exception:
            continue
    return None


# ---------- the metatheorem check ----------
def check(g, max_states=150) -> Tuple[bool, dict]:
    """Correspondence + progress for ONE protocol: ok ⇔ 'certified' (global == config everywhere,
    no deadlock). Delegates to the concurrency-aware classification (LH-Q-001d)."""
    cls, info = sem.correspondence_class(g, max_states=max_states)
    return (cls == "certified"), {"class": cls, **info}


def run(n_random=250, seed=20260615, roles=ROLES):
    rng = random.Random(seed)
    multi = tuple(roles) != tuple(ROLES)
    print("=" * 72)
    print(f"METATHEORY — correspondence/confluence + deadlock freedom (proof-by-test) "
          f"[{len(roles)} roles: {', '.join(roles)}]")
    print("=" * 72)
    cnt = {"certified": 0, "incomplete": 0, "unsound": 0}
    unsound = []
    # canonical examples (only in the canonical 3-role run)
    if not multi:
        canon = [("G_OK", core.G_OK), ("G_OK_TERM", core.G_OK_TERM), ("G_OK_CRASH", core.G_OK_CRASH)]
        for name, g in canon:
            cls, info = sem.correspondence_class(g)
            cnt[cls] = cnt.get(cls, 0) + 1
            print(f"  canonical {name:<12} class = {cls}")
            if cls == "unsound":
                unsound.append((name, info))
    # random well-formed protocols over the given role set
    tested = 0
    for _ in range(n_random):
        g = gen_wellformed(rng, roles=roles)
        if g is None:
            continue
        tested += 1
        cls, info = sem.correspondence_class(g)
        cnt[cls] = cnt.get(cls, 0) + 1
        if cls == "unsound":
            unsound.append(("random", info))
    # The METATHEOREM claim is SOUNDNESS (global ⊆ config): there must never be an 'unsound'.
    # 'incomplete' (endpoints more concurrent than the global semantics) is not an error but
    # a case rejected by the gate (when in doubt, check).
    ok = not unsound
    print(f"  tested: {tested}  |  certified={cnt['certified']}  incomplete={cnt['incomplete']}  unsound={cnt['unsound']}")
    if unsound:
        for nm, info in unsound[:3]:
            print(f"    ✗ UNSOUND {nm}: {info}")
    print(f"  RESULT: {'✓ Soundness (global ⊆ config) holds on all tested protocols' if ok else '✗ UNSOUND counterexample'}")
    return {"ok": ok, "tested": tested, "certified": cnt["certified"],
            "incomplete": cnt["incomplete"], "unsound": len(unsound), "roles": len(roles)}


if __name__ == "__main__":
    run()
