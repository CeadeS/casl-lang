"""
Spike G — hardening winners (the A-approaches chosen by ab_candidates.py):

  linearity_check   (W6, static, stage B)  → realizes LH-Q-003a/b
  termination_check (W5, SMT,    stage S)  → realizes LH-Q-009 (progress/termination)
  ttl_safety_check  (W4, static, stage B)  → realizes LH-Q-010 (composes with W5 bound)

Each is the static winner of an A/B comparison; the runtime variants (fuel,
resolve-once monitor, ttl counter/revocation) remain documented fallbacks.
"""
from __future__ import annotations
from typing import List, Tuple
from z3 import Int, Solver, unsat, Not
from casl import core
from casl.core import G, Comm, Choice, Rec, End
from casl import spike_proj_mpst as mpst


# -------- promise discovery & linear usage (W6) --------
def _promises(g: G) -> List[Tuple[str, str]]:
    out = []

    def walk(n):
        if isinstance(n, Comm):
            if n.from_oracle:
                out.append((n.sender, n.label))
            walk(n.cont)
            if n.on_crash:
                walk(n.on_crash)
        elif isinstance(n, Choice):
            for b in n.branches:
                walk(b.cont)
        elif isinstance(n, Rec):
            walk(n.body)

    walk(g)
    return out


def _count_sends(l, label) -> Tuple[int, int]:
    """(min, max) count of LSend(label) along any path of a local type."""
    if isinstance(l, (mpst.LEnd, mpst.LVar)):
        return (0, 0)
    if isinstance(l, mpst.LRec):
        return _count_sends(l.body, label)
    if isinstance(l, mpst.LSend):
        c = 1 if l.label == label else 0
        mn, mx = _count_sends(l.cont, label)
        return (c + mn, c + mx)
    if isinstance(l, mpst.LRecv):
        return _count_sends(l.cont, label)
    if isinstance(l, (mpst.LExtChoice, mpst.LIntChoice)):
        rs = [_count_sends(c, label) for _, _, c in l.opts] or [(0, 0)]
        return (min(r[0] for r in rs), max(r[1] for r in rs))
    return (0, 0)


def linearity_check(g: G):
    """Each promise is resolved exactly once per loop body (write-once + obligation)."""
    viol = []
    for sender, label in _promises(g):
        mn, mx = _count_sends(mpst.project(g, sender), label)
        if not (mn == 1 and mx == 1):
            viol.append((sender, label, (mn, mx)))
    return (not viol), viol


# -------- termination via SMT ranking (W5) --------
def _wellfounded_lemma() -> bool:
    """A strictly-decreasing measure bounded below terminates: prove cost>=1 ∧ b>=0
    ⇒ b-cost < b (negation UNSAT)."""
    b, bp, cost = Int("b"), Int("bp"), Int("cost")
    s = Solver()
    s.add(b >= 0, cost >= 1, bp == b - cost)
    s.add(Not(bp < b))
    return s.check() == unsat


def _recs(g: G) -> List[Rec]:
    out = []

    def walk(n):
        if isinstance(n, Comm):
            walk(n.cont)
            if n.on_crash:
                walk(n.on_crash)
        elif isinstance(n, Choice):
            for b in n.branches:
                walk(b.cont)
        elif isinstance(n, Rec):
            out.append(n)
            walk(n.body)

    walk(g)
    return out


def termination_check(g: G):
    """Guaranteed iff the ranking lemma holds AND every loop declares a measure.
    Stream loops (LH-F-009, `stream`) are deliberately unbounded and EXEMPT from this — their
    liveness is 'every handler terminates' (checked separately via `stream_wellformed`), not a measure."""
    lemma = _wellfounded_lemma()
    recs = _recs(g)
    unranked = [r for r in recs if r.measure is None and not getattr(r, "stream", False)]
    guaranteed = lemma and not unranked
    bounds = [r.max_iters for r in recs if r.measure is not None]
    return guaranteed, {"lemma": lemma, "loops": len(recs), "unranked": len(unranked), "bounds": bounds}


# ---------- LH-F-009: stream / event loops (environment-driven, bounded handlers) ----------
def _handler_terminates(node) -> bool:
    """An event handler MUST terminate: no unbounded inner loop (no `stream`,
    no `rec` without a measure). A `continue` (TVar) back to the stream loop is allowed (the
    loop edge of the stream, not an inner loop)."""
    if isinstance(node, Comm):
        ok = _handler_terminates(node.cont)
        if node.on_crash is not None:
            ok = ok and _handler_terminates(node.on_crash)
        return ok
    if isinstance(node, Choice):
        return all(_handler_terminates(b.cont) for b in node.branches)
    if isinstance(node, Rec):
        if getattr(node, "stream", False) or node.measure is None:
            return False                       # unbounded inner loop ⇒ handler does not terminate
        return _handler_terminates(node.body)  # inner loop WITH a measure is allowed
    return True   # TVar / End


def stream_wellformed(g: G, env=()):
    """(ok, violations) for LH-F-009. Every `stream` loop MUST (a) dispatch via a
    **Choice** whose selector is an **env** role (each iteration consumes an
    external event ⇒ productivity), and (b) carry a **terminating handler** in every
    branch. The loop is thus deliberately unbounded, yet every reaction is finite."""
    env = set(env or ())
    viol: List[str] = []
    for r in _recs(g):
        if not getattr(r, "stream", False):
            continue
        body = r.body
        if not isinstance(body, Choice):
            viol.append(f"stream {r.var}: body is not a dispatch choice")
            continue
        if body.sender not in env:
            viol.append(f"stream {r.var}: dispatch selector {body.sender} is not an env role")
        for b in body.branches:
            if not _handler_terminates(b.cont):
                viol.append(f"stream {r.var}/{b.label}: handler does not terminate (unbounded inner loop)")
    return (not viol), viol


# -------- ttl-safety, composed with the loop bound (W4) + Refresh/Revokation (LH-Q-008) --------
def _path_uses(n, sender, tool):
    """Max. uses of (sender, tool) along a SINGLE iteration path (up to `continue`/end,
    without crossing the back edge). An inner bounded loop counts uses × max_iters."""
    if isinstance(n, Comm):
        h = 1 if (n.sender == sender and n.uses_capability == tool) else 0
        nxt = _path_uses(n.cont, sender, tool)
        if n.on_crash is not None:
            nxt = max(nxt, _path_uses(n.on_crash, sender, tool))
        return h + nxt
    if isinstance(n, Choice):
        return max((_path_uses(b.cont, sender, tool) for b in n.branches), default=0)
    if isinstance(n, Rec):
        per = _path_uses(n.body, sender, tool)
        if getattr(n, "stream", False):
            return per                                   # inner stream: likewise refresh/iteration
        return per * (n.max_iters if n.max_iters else 1)  # bounded inner loop
    return 0   # TVar (back edge) / End


def _uses_in(n, acc):
    if isinstance(n, Comm):
        if n.uses_capability:
            acc.add((n.sender, n.uses_capability))
        _uses_in(n.cont, acc)
        if n.on_crash is not None:
            _uses_in(n.on_crash, acc)
    elif isinstance(n, Choice):
        for b in n.branches:
            _uses_in(b.cont, acc)
    elif isinstance(n, Rec):
        _uses_in(n.body, acc)


def ttl_safety_check(g: G, caps=None):
    """A finite-ttl capability used inside a loop is safe iff ttl >= the loop's
    proven iteration bound (max_iters). Unbounded loop ⇒ unsafe for finite ttl.
    `stream` loops (LH-Q-008): the capability is re-granted PER ITERATION (refresh), so
    ttl >= uses per iteration (handler path) suffices — an unbounded stream loop is
    ttl-safe even with a finite ttl. `caps` defaults to core.AGENT_CAPS."""
    capmap = caps if caps is not None else core.AGENT_CAPS
    unsafe = []

    def walk(n, loop_bound):
        if isinstance(n, Comm):
            if n.uses_capability:
                ncaps = {c.tool: c for c in capmap.get(n.sender, ())}
                cap = ncaps.get(n.uses_capability)
                if cap is not None and cap.ttl is not None and loop_bound is not None:
                    if loop_bound == "unbounded" or cap.ttl < loop_bound:
                        unsafe.append((n.sender, n.uses_capability, cap.ttl, loop_bound))
            walk(n.cont, loop_bound)
            if n.on_crash:
                walk(n.on_crash, loop_bound)
        elif isinstance(n, Choice):
            for b in n.branches:
                walk(b.cont, loop_bound)
        elif isinstance(n, Rec):
            if getattr(n, "stream", False):
                # Refresh per iteration: ttl must cover the uses of a SINGLE iteration.
                used = set()
                _uses_in(n.body, used)
                for sender, tool in used:
                    cap = {c.tool: c for c in capmap.get(sender, ())}.get(tool)
                    if cap is not None and cap.ttl is not None:
                        need = _path_uses(n.body, sender, tool)
                        if cap.ttl < need:
                            unsafe.append((sender, tool, cap.ttl, f"{need}/Iteration (Strom)"))
                walk(n.body, None)   # inner bounded loops check themselves; no "unbounded" flag
            else:
                walk(n.body, n.max_iters if n.max_iters is not None else "unbounded")

    walk(g, None)
    return (not unsafe), unsafe


# -------- non-linear fixture for the A/B / demo --------
G_DUP = Comm("C", "A", "Request", (core._q, core._b),
             Comm("A", "J", "Draft", (core._ans, core._cost),
                  Comm("A", "J", "Draft", (core._ans, core._cost), End(), from_oracle=True),
                  from_oracle=True))


def run():
    print("=" * 72)
    print("SPIKE G — linearity (W6) · termination (W5) · ttl-safety (W4)")
    print("=" * 72)
    lin_ok, _ = linearity_check(core.G_OK)
    dup_ok, dup_v = linearity_check(G_DUP)
    print(f"  linearity  G_OK={lin_ok}   G_DUP={dup_ok} (viol {dup_v})")

    t_ok, t_d = termination_check(core.G_OK)
    t_term, t_d2 = termination_check(core.G_OK_TERM)
    print(f"  termination G_OK={t_ok} ({t_d['unranked']} loop without measure)   "
          f"G_OK_TERM={t_term} (bound {t_d2['bounds']}, lemma={t_d2['lemma']})")

    ttl_ok, ttl_v = ttl_safety_check(core.G_OK)
    ttl_ok2, _ = ttl_safety_check(core.G_OK_TERM)
    print(f"  ttl-safety  G_OK={ttl_ok} (unsafe {ttl_v})   G_OK_TERM={ttl_ok2} (ttl 3 ≥ Bound 3)")

    return {
        "linearity_G_OK": lin_ok, "linearity_G_DUP_flagged": not dup_ok,
        "termination_G_OK": t_ok, "termination_G_OK_TERM": t_term,
        "ttl_G_OK_unsafe": not ttl_ok, "ttl_G_OK_TERM_safe": ttl_ok2,
    }


if __name__ == "__main__":
    run()
