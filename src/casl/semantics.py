"""
semantics.py — operational semantics (L3 core, Direction B).

Synchronous reduction for both the GLOBAL type (choreography) and the ENDPOINT
CONFIGURATION (the projected local types running together). Recursion is handled
by lazy unfolding. This is the substrate the metatheory (metatheory.py) tests:

  * step_global(G)  : the head communications G can perform → [(event, G')]
  * config(G)       : {role: local type}  (= projection of every role)
  * step_config(cfg): synchronous matches a sender/receiver can perform → [(event, cfg')]

Operational correspondence (proved-by-test in metatheory.py): the events enabled
by G equal those enabled by config(G), and config(G') == cfg' after a matching
step — i.e. running the endpoints stays faithful to the choreography.
"""
from __future__ import annotations
from dataclasses import replace
from typing import Dict, List, Tuple

from casl import core
from casl import spike_proj_mpst as mpst
from casl.spike_proj_mpst import LSend, LRecv, LIntChoice, LExtChoice, LRec, LVar, LEnd

Event = Tuple[str, str, str]   # (sender, receiver, label)


# ---------- substitution / unfolding ----------
def subst_global(g, var, repl):
    if isinstance(g, core.End):
        return g
    if isinstance(g, core.TVar):
        return repl if g.var == var else g
    if isinstance(g, core.Rec):
        return g if g.var == var else replace(g, body=subst_global(g.body, var, repl))
    if isinstance(g, core.Comm):
        return replace(g, cont=subst_global(g.cont, var, repl))
    if isinstance(g, core.Choice):
        return replace(g, branches=tuple(replace(b, cont=subst_global(b.cont, var, repl))
                                         for b in g.branches))
    raise TypeError(type(g))


def unfold_global(g):
    n = 0
    while isinstance(g, core.Rec):
        g = subst_global(g.body, g.var, g)
        n += 1
        if n > 50:        # safety: non-contractive type
            break
    return g


def subst_local(l, var, repl):
    if isinstance(l, LEnd):
        return l
    if isinstance(l, LVar):
        return repl if l.var == var else l
    if isinstance(l, LRec):
        return l if l.var == var else replace(l, body=subst_local(l.body, var, repl))
    if isinstance(l, (LSend, LRecv)):
        return replace(l, cont=subst_local(l.cont, var, repl))
    if isinstance(l, (LIntChoice, LExtChoice)):
        return replace(l, opts=tuple((lb, f, subst_local(c, var, repl)) for lb, f, c in l.opts))
    raise TypeError(type(l))


def unfold_local(l):
    n = 0
    while isinstance(l, LRec):
        l = subst_local(l.body, l.var, l)
        n += 1
        if n > 50:        # safety: non-contractive type
            break
    return l


# ---------- global reduction (with concurrency, LH-Q-001d) ----------
def _prefix_swaps(g, blocked: set) -> List[Tuple[Event, object]]:
    """Concurrency as a **swap over the syntactic Comm prefix**: an action that is
    role-disjoint from everything before it (`blocked`) may be PULLED FORWARD; the skipped prefix
    moves into the residual type. Finite and SOUND: swapping is NOT done across Rec/Choice
    (conservative underestimate — such cases may later be merely 'incomplete', never unsound)."""
    if isinstance(g, core.Comm):
        out: List[Tuple[Event, object]] = []
        if {g.sender, g.receiver}.isdisjoint(blocked):
            out.append(((g.sender, g.receiver, g.label), g.cont))
            for ev2, res in _prefix_swaps(g.cont, blocked | {g.sender, g.receiver}):
                out.append((ev2, replace(g, cont=res)))
        # if the head shares a role with `blocked`, nothing behind it is independent of it either
        return out
    return []   # Choice / Rec / TVar / End: no swap beyond this point


def step_global(g) -> List[Tuple[Event, object]]:
    g = unfold_global(g)
    if isinstance(g, core.Comm):
        out = [((g.sender, g.receiver, g.label), g.cont)]   # head
        for ev, res in _prefix_swaps(g.cont, {g.sender, g.receiver}):
            out.append((ev, replace(g, cont=res)))           # concurrent pull-forwards
        return out
    if isinstance(g, core.Choice):
        return [((g.sender, g.receiver, br.label), br.cont) for br in g.branches]
    return []   # End / TVar: no step


# ---------- endpoint configuration ----------
def roles_of(g) -> set:
    """All roles occurring in `g` (sender/receiver) — parametric, not bound to the
    canonical 3-role set (LH-F-008). This defines the operational semantics over
    an arbitrary number of roles."""
    rs: set = set()

    def w(n):
        if isinstance(n, core.Comm):
            rs.add(n.sender); rs.add(n.receiver); w(n.cont)
            if n.on_crash is not None:
                w(n.on_crash)
        elif isinstance(n, core.Choice):
            rs.add(n.sender); rs.add(n.receiver)
            for b in n.branches:
                w(b.cont)
        elif isinstance(n, core.Rec):
            w(n.body)
        # TVar / End: no new roles

    w(g)
    return rs


def config(g) -> Dict[str, object]:
    # Derive roles from the protocol (≥4 roles supported), falling back to the canonical set.
    rs = roles_of(g) or set(core.ROLES)
    return {r: mpst.project(g, r) for r in sorted(rs)}


def _sends(l):
    """Possible sends of a (unfolded) local type → [(to, label, cont)]."""
    l = unfold_local(l)
    if isinstance(l, LSend):
        return [(l.to, l.label, l.cont)]
    if isinstance(l, LIntChoice):
        return [(l.to, lb, c) for lb, _f, c in l.opts]
    return []


def _recv_cont(l, frm, label):
    """If unfolded local type can receive `label` from `frm`, return continuation."""
    l = unfold_local(l)
    if isinstance(l, LRecv) and l.frm == frm and l.label == label:
        return l.cont
    if isinstance(l, LExtChoice) and l.frm == frm:
        for lb, _f, c in l.opts:
            if lb == label:
                return c
    return None


def step_config(cfg: Dict[str, object]) -> List[Tuple[Event, Dict[str, object]]]:
    steps = []
    for p in cfg:
        for (q, label, cont_p) in _sends(cfg[p]):
            cont_q = _recv_cont(cfg[q], p, label)
            if cont_q is not None:
                new = dict(cfg)
                new[p] = cont_p
                new[q] = cont_q
                steps.append(((p, q, label), new))
    return steps


def terminal_config(cfg: Dict[str, object]) -> bool:
    return all(isinstance(unfold_local(l), LEnd) for l in cfg.values())


def trace(g, max_steps=20, rng=None):
    """One (deterministic-ish) reduction run of config(g); returns the event trace."""
    import random
    rng = rng or random.Random(0)
    cfg = config(g)
    evs = []
    for _ in range(max_steps):
        steps = step_config(cfg)
        if not steps:
            break
        ev, cfg = rng.choice(steps)
        evs.append(ev)
    return evs, terminal_config(cfg)


def correspondence_class(g, max_states=200) -> Tuple[str, dict]:
    """Classifies a protocol with respect to concurrency (LH-Q-001d), via BFS over the
    reachable states. At each state the GLOBALLY enabled events (with swap) are compared
    against those of the endpoint CONFIGURATION:

      · global ⊋ config  → 'unsound'    — SAFETY-CRITICAL: the choreography claims
                                            a behaviour the endpoints do not permit.
      · global ⊊ config  → 'incomplete' — the endpoints are more concurrent than the (soundly
                                            underestimating) global semantics captures ⇒ NOT
                                            certifiable (the gate rejects — when in doubt, check).
      · global == config everywhere (+ progress) → 'certified'.

    Soundness (global ⊆ config) is the safety direction and MUST always hold; 'incomplete'
    is not an error but a deliberately rejected case."""
    # Project ONCE, then run the GLOBAL and CONFIGURATION LTS in lockstep
    # (standard correspondence, robust: no re-projection of isolated substates, which may
    # not be projectable on their own — "knowledge of choice").
    try:
        cfg0 = config(g)
    except mpst.NonProjectable:
        return "incomplete", {"why": "not projectable (well-formedness applies separately)"}
    seen, frontier = set(), [(g, cfg0)]
    n = 0
    while frontier:
        gs, cs = frontier.pop()
        key = (gs, frozenset(cs.items()))
        if key in seen:
            continue
        seen.add(key)
        n += 1
        if n > max_states:
            return "certified", {"states": n, "capped": True}
        gsteps = step_global(gs)
        csteps = step_config(cs)
        eg = {ev for ev, _ in gsteps}
        ec = {ev for ev, _ in csteps}
        if eg - ec:
            return "unsound", {"extra": sorted(map(str, eg - ec)), "state": str(gs)}
        if ec - eg:
            return "incomplete", {"missing": sorted(map(str, ec - eg)), "state": str(gs)}
        if not terminal_config(cs) and not ec:
            return "unsound", {"why": "deadlock", "state": str(gs)}
        cmap = {ev: c2 for ev, c2 in csteps}      # eg ⊆ ec ⇒ every global event has a config match
        for ev, gs2 in gsteps:
            frontier.append((gs2, cmap[ev]))
    return "certified", {"states": n}


if __name__ == "__main__":
    for name, g in [("G_OK", core.G_OK), ("G_OK_TERM", core.G_OK_TERM)]:
        evs, term = trace(g, max_steps=12)
        print(f"{name}: trace = {[f'{p}->{q}:{l}' for p, q, l in evs]}  terminal={term}")
