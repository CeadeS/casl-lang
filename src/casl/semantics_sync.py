"""
semantics_sync.py — W19: the synchronous endpoint SAFETY ORACLE (semantic ground truth).

Projection (mergeability) is *syntactic*; whether it is SOUND (accepted ⇒ the endpoints actually run
safely) is the subtle question Scalas–Yoshida (POPL 2019) showed classic MPST got wrong. This module is
the semantic yardstick: it projects a global type to every role, then executes the endpoint system under
SYNCHRONOUS rendezvous semantics and decides safety by exploring the reachable configuration space.

Verdicts:
  SAFE        — every reachable configuration is terminal or can take a step (deadlock-free), and no
                role's send can be mis-received (no reception error).
  DEADLOCK    — a reachable non-terminal configuration with no enabled step.
  RECV_ERROR  — a sender is in rendezvous with a partner that cannot receive a label it may send
                (demonic internal choice; the classic mergeability hazard).
  DIVERGENT   — non-contractive recursion (e.g. μt.t): a silent infinite loop with no communication.
                Distinct from DEADLOCK; flagged so guardedness can be enforced separately.
  UNKNOWN     — state-space bound exceeded (treated conservatively, never "safe").

This is an OFFLINE analysis tool / oracle (it touches neither the runtime nor the living-audit gate).
It is used to (a) empirically certify soundness of CASL's projection, and (b) serve as the completeness
yardstick and certificate re-validator for W19. See docs/analyses/w19-projection-completeness.md.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

from casl.core import Comm, Choice, Rec, TVar, End
from casl import spike_proj_mpst as mpst
from casl.spike_proj_mpst import (LSend, LRecv, LIntChoice, LExtChoice, LRec, LVar, LEnd,
                                   NonProjectable, project)

_MAX_STATES = 50000


def collect_roles(g) -> Tuple[str, ...]:
    s = set()
    def w(g):
        if isinstance(g, Comm):
            s.add(g.sender); s.add(g.receiver); w(g.cont)
        elif isinstance(g, Choice):
            s.add(g.sender); s.add(g.receiver)
            for b in g.branches:
                w(b.cont)
        elif isinstance(g, Rec):
            w(g.body)
    w(g)
    return tuple(sorted(s))


def no_self_comm(g) -> bool:
    """True iff every communication has distinct endpoints (no p->p). Mirrors F* `no_self`."""
    if isinstance(g, Comm):
        return g.sender != g.receiver and no_self_comm(g.cont)
    if isinstance(g, Choice):
        return g.sender != g.receiver and all(no_self_comm(b.cont) for b in g.branches)
    if isinstance(g, Rec):
        return no_self_comm(g.body)
    return True


def gdistinct(g) -> bool:
    """True iff every choice has distinct branch labels. Mirrors F* `gdistinct` (W19-A, v0.27.0)."""
    if isinstance(g, Comm):
        return gdistinct(g.cont)
    if isinstance(g, Choice):
        labels = [b.label for b in g.branches]
        return len(labels) == len(set(labels)) and all(gdistinct(b.cont) for b in g.branches)
    if isinstance(g, Rec):
        return gdistinct(g.body)
    return True


def closed(g, bound=frozenset()) -> bool:
    """True iff g has no free type variables (every TVar bound by an enclosing Rec).
    Mirrors F* `closed` / `cl []` (W19-A, v0.27.0)."""
    if isinstance(g, TVar):
        return g.var in bound
    if isinstance(g, Rec):
        return closed(g.body, bound | {g.var})
    if isinstance(g, Comm):
        return closed(g.cont, bound)
    if isinstance(g, Choice):
        return all(closed(b.cont, bound) for b in g.branches)
    return True


def contractive(g, unguarded=frozenset()) -> bool:
    """True iff every recursion variable occurrence is guarded by a communication (no μt.t)."""
    if isinstance(g, TVar):
        return g.var not in unguarded
    if isinstance(g, End):
        return True
    if isinstance(g, Rec):
        return contractive(g.body, unguarded | {g.var})
    if isinstance(g, Comm):
        return contractive(g.cont, frozenset())
    if isinstance(g, Choice):
        return all(contractive(b.cont, frozenset()) for b in g.branches)
    return True


# --- local-type μ-unfolding ---
def _subst(l, var, repl):
    if isinstance(l, LVar):
        return repl if l.var == var else l
    if isinstance(l, LRec):
        return l if l.var == var else LRec(l.var, _subst(l.body, var, repl))
    if isinstance(l, LSend):
        return LSend(l.to, l.label, l.fields, _subst(l.cont, var, repl))
    if isinstance(l, LRecv):
        return LRecv(l.frm, l.label, l.fields, _subst(l.cont, var, repl))
    if isinstance(l, LIntChoice):
        return LIntChoice(l.to, tuple((lb, f, _subst(c, var, repl)) for lb, f, c in l.opts))
    if isinstance(l, LExtChoice):
        return LExtChoice(l.frm, tuple((lb, f, _subst(c, var, repl)) for lb, f, c in l.opts))
    return l


def _unfold(l):
    seen = 0
    while isinstance(l, LRec):
        l = _subst(l.body, l.var, l)
        seen += 1
        if seen > 2000:               # non-contractive (μt.t-like) — silent loop
            return None
    return l


def _sends(l) -> Dict[Tuple[str, str], object]:
    l = _unfold(l)
    out: Dict[Tuple[str, str], object] = {}
    if isinstance(l, LSend):
        out[(l.to, l.label)] = l.cont
    elif isinstance(l, LIntChoice):
        for lb, f, c in l.opts:
            out[(l.to, lb)] = c
    return out


def _recvs(l) -> Dict[Tuple[str, str], object]:
    l = _unfold(l)
    out: Dict[Tuple[str, str], object] = {}
    if isinstance(l, LRecv):
        out[(l.frm, l.label)] = l.cont
    elif isinstance(l, LExtChoice):
        for lb, f, c in l.opts:
            out[(l.frm, lb)] = c
    return out


def _is_end(l) -> bool:
    return isinstance(_unfold(l), LEnd)


def safe_config(cfg0: Dict[str, object], roles) -> Tuple[Optional[bool], str]:
    """Explore the reachable synchronous configuration space from cfg0 (role -> local type)."""
    start = tuple(cfg0[r] for r in roles)
    seen = set()
    stack = [start]
    n = 0
    while stack:
        st = stack.pop()
        if st in seen:
            continue
        seen.add(st)
        n += 1
        if n > _MAX_STATES:
            return (None, "UNKNOWN: state-space bound exceeded")
        cfg = dict(zip(roles, st))
        if any(_unfold(cfg[r]) is None for r in roles):
            return (False, "DIVERGENT: non-contractive recursion (silent loop)")
        stepped = False
        for p in roles:
            for (q, a), cp in _sends(cfg[p]).items():
                if q not in cfg:
                    return (False, f"RECV_ERROR: {p} sends {a} to absent {q}")
                rq = _recvs(cfg[q])
                if p in {pp for (pp, _) in rq}:          # q is in rendezvous with p
                    if (p, a) not in rq:
                        return (False, f"RECV_ERROR: {p} may send {a} to {q}; {q} cannot receive it")
                    stepped = True
                    nxt = dict(cfg); nxt[p] = cp; nxt[q] = rq[(p, a)]
                    stack.append(tuple(nxt[r] for r in roles))
        if not stepped:
            if all(_is_end(cfg[r]) for r in roles):
                continue
            return (False, "DEADLOCK: non-final configuration with no enabled step")
    return (True, "SAFE")


def classify(g) -> Tuple[Optional[bool], str]:
    """Top-level: is the projected endpoint system of global type g SAFE? Returns (verdict, reason).
    verdict True = safe, False = unsafe (reason names the kind), None = unknown (bound exceeded).
    Non-projectable g returns (None, 'NOT-PROJECTABLE') — out of scope for the semantic oracle."""
    if not contractive(g):
        return (False, "DIVERGENT: non-contractive recursion")
    roles = collect_roles(g) or ("C", "A")
    try:
        cfg = {r: project(g, r) for r in roles}
    except NonProjectable:
        return (None, "NOT-PROJECTABLE")
    except Exception as e:                                # noqa: BLE001
        return (None, f"NOT-PROJECTABLE: {e!r}")
    return safe_config(cfg, roles)


def is_safe(g) -> Optional[bool]:
    return classify(g)[0]
