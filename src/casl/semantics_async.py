"""
semantics_async.py — REFINEMENT: buffered (asynchronous) semantics, encapsulated & opt-in.

Reference: `docs/analyses/async.md` (proposal A + B-report), `docs/analyses/refinements.md` (encapsulation).

IMPORTANT — encapsulation (can NEVER weaken the proved default):
  * The synchronous core (`semantics.py`, `metatheory.py`, F* `CASL.fst`) stays UNTOUCHED.
  * This module IMPORTS core/projection read-only and adds async ON TOP.
  * Reachable ONLY via the per-protocol `async` marker (opt-in); without the marker nothing changes.
  * Its own, LABELLED guarantee: `async-rejected` < `async-bounded-safe` < `async-synchronizable`.

Model — ONE FIFO inbox per receiver (a realistic agent mailbox):
  * `send` is NON-BLOCKING: appends (sender,label) to the receiver's inbox (if |inbox|<k).
  * `receive` is BLOCKING and FIFO: the receiver can only read the HEAD of its inbox;
    if the head does not match what its local type expects next, it is BLOCKED
    (no reordering). This way ordering/reorder hazards become VISIBLE instead of defined away
    (a per-receiver inbox is more conservative than per-pair FIFO — "when in doubt, check").

Gate `async_safe(g, k)` — DENY-BY-DEFAULT (proposal A, bounded reachability):
  enumerates the FINITE k-bounded async state space and certifies
    (1) boundedness   — no inbox ever needs to exceed k,
    (2) orphan-freedom — no reachable final state leaves a message behind,
    (3) deadlock-freedom/progress — every non-final state can take a step.
  If anything fails (or the state space exceeds max_states), it is REJECTED.

`async_class(g, k)` layers the B-report (sync equivalence) on top:
  if the protocol is bounded-safe at k=1 AND has at most ≤1 message in flight system-wide,
  the async behaviour coincides with the SYNCHRONOUS semantics → it INHERITS the proved
  core guarantees → class `async-synchronizable` (the stronger, sound-conservative class).

By-test like the rest of the prototype. F* mechanization of bounded async = a tracked POSSIBLE future.
"""
from __future__ import annotations
from typing import Dict, Tuple, List, Optional

from casl import core
from casl import spike_proj_mpst as mpst
from casl.spike_proj_mpst import LEnd
from casl.semantics import config, unfold_local, _sends, _recv_cont   # read-only reuse

# Inbox entry = (sender, label); inbox = tuple (FIFO, head on the left). State = (cfg, inboxes).
Item = Tuple[str, str]
Inbox = Tuple[Item, ...]
Event = Tuple[str, str, str]   # (sender, receiver, label) — completed communication (at recv)


def _initial(g) -> Tuple[Dict[str, object], Dict[str, Inbox]]:
    cfg = config(g)                                  # = projection of every role (may raise NonProjectable)
    inboxes = {r: tuple() for r in cfg}              # empty mailboxes
    return cfg, inboxes


def _enabled_sends(cfg, inboxes, k) -> List[Tuple[Event, dict, dict]]:
    """All non-blocking sends whose target inbox still has room (|inbox|<k)."""
    out = []
    for p in cfg:
        for (q, label, cont_p) in _sends(cfg[p]):
            if len(inboxes[q]) < k:
                new_cfg = dict(cfg); new_cfg[p] = cont_p
                new_in = dict(inboxes); new_in[q] = inboxes[q] + ((p, label),)
                out.append(((p, q, label), new_cfg, new_in))
    return out


def _send_exists(cfg) -> bool:
    """Is there ANY send (possibly only blocked by a full inbox)? — for the buffer>k diagnosis."""
    return any(_sends(cfg[p]) for p in cfg)


def _enabled_recvs(cfg, inboxes) -> List[Tuple[Event, dict, dict]]:
    """FIFO receive: only the HEAD of each inbox, and only if the local type expects it."""
    out = []
    for q in cfg:
        if not inboxes[q]:
            continue
        (p, label) = inboxes[q][0]                   # head — no reordering
        cont_q = _recv_cont(cfg[q], p, label)
        if cont_q is not None:
            new_cfg = dict(cfg); new_cfg[q] = cont_q
            new_in = dict(inboxes); new_in[q] = inboxes[q][1:]
            out.append(((p, q, label), new_cfg, new_in))
    return out


def _final(cfg, inboxes) -> bool:
    return (all(isinstance(unfold_local(l), LEnd) for l in cfg.values())
            and all(len(b) == 0 for b in inboxes.values()))


def _all_ended(cfg) -> bool:
    return all(isinstance(unfold_local(l), LEnd) for l in cfg.values())


def _key(cfg, inboxes):
    return (frozenset((r, cfg[r]) for r in cfg),
            frozenset((r, inboxes[r]) for r in inboxes))


def async_safe(g, k: int = 1, max_states: int = 4000) -> dict:
    """DENY-BY-DEFAULT gate (proposal A). Verdict dict:
       {verdict: 'async-bounded-safe'|'async-rejected', reason, states, max_inflight, bound_hit}."""
    if k < 1:
        return {"verdict": "async-rejected", "reason": "k<1 (buffer must be ≥1)", "states": 0}
    try:
        cfg0, in0 = _initial(g)
    except mpst.NonProjectable:
        return {"verdict": "async-rejected", "reason": "not projectable (not well-formed)", "states": 0}

    seen = set()
    frontier = [(cfg0, in0)]
    states = 0
    max_inflight = 0
    bound_hit = False
    while frontier:
        cfg, inboxes = frontier.pop()
        kk = _key(cfg, inboxes)
        if kk in seen:
            continue
        seen.add(kk)
        states += 1
        if states > max_states:
            return {"verdict": "async-rejected", "reason": f"state space > {max_states} "
                    f"(unbounded/too large at k={k}) — not certifiable", "states": states}
        inflight = sum(len(b) for b in inboxes.values())
        max_inflight = max(max_inflight, inflight)
        if any(len(b) == k for b in inboxes.values()):
            bound_hit = True

        if _final(cfg, inboxes):
            continue
        sends = _enabled_sends(cfg, inboxes, k)
        recvs = _enabled_recvs(cfg, inboxes)
        if not sends and not recvs:
            # Stuck & not final → classify WHY (deny-by-default in every case).
            if _all_ended(cfg) and inflight > 0:
                orph = sorted({f"{p}->{q}:{l}" for q in inboxes for (p, l) in inboxes[q]})
                return {"verdict": "async-rejected", "reason": f"orphan message(s) left undelivered: "
                        f"{', '.join(orph)}", "states": states, "max_inflight": max_inflight}
            if _send_exists(cfg):
                return {"verdict": "async-rejected", "reason": f"buffer too small: a send needs "
                        f"|Inbox| > {k} → deadlock at k={k}", "states": states,
                        "max_inflight": max_inflight, "bound_hit": True}
            # Receiver sees an inbox head its type does not expect (reorder/mismatch) or a true deadlock.
            heads = {q: inboxes[q][0] for q in inboxes if inboxes[q]}
            return {"verdict": "async-rejected", "reason": "deadlock (reorder/mismatch: inbox head "
                    f"not expected) — heads={heads}", "states": states, "max_inflight": max_inflight}

        for (_ev, c2, i2) in sends + recvs:
            frontier.append((c2, i2))

    return {"verdict": "async-bounded-safe", "reason": "bounded + orphan-free + deadlock-free",
            "states": states, "max_inflight": max_inflight, "bound_hit": bound_hit}


def async_class(g, k: int = 1, max_states: int = 4000) -> Tuple[str, dict]:
    """Verdict tiers (docs/analyses/async.md §5): async-rejected < async-bounded-safe < async-synchronizable.
       'synchronizable' = sound-conservative sync equivalence: bounded-safe at k=1 AND at most
       ≤1 message in flight system-wide ⇒ every send is consumed immediately ⇒ behaviour = synchronous
       core ⇒ inherits its PROVED guarantees."""
    res = async_safe(g, k, max_states)
    if res["verdict"] == "async-rejected":
        return "async-rejected", res
    # B-report: at k=1, check whether system-wide there are always ≤1 in flight (⇒ sync-equivalent).
    one = async_safe(g, 1, max_states)
    if one["verdict"] == "async-bounded-safe" and one.get("max_inflight", 99) <= 1:
        return "async-synchronizable", {**res, "note": "sync-equivalent (≤1 message in flight at a time) "
                                        "→ inherits the synchronous core guarantees"}
    return "async-bounded-safe", res


def async_trace(g, k: int = 1, max_steps: int = 40, rng=None) -> Tuple[List[Event], bool]:
    """One async run (for demonstration): returns the sequence of COMPLETED communications + terminal?."""
    import random
    rng = rng or random.Random(0)
    try:
        cfg, inboxes = _initial(g)
    except mpst.NonProjectable:
        return [], False
    evs: List[Event] = []
    for _ in range(max_steps):
        sends = _enabled_sends(cfg, inboxes, k)
        recvs = _enabled_recvs(cfg, inboxes)
        if not sends and not recvs:
            break
        ev, cfg, inboxes = rng.choice(sends + recvs)
        if any(ev == r[0] for r in recvs):           # only recv = completed communication
            evs.append(ev)
    return evs, _final(cfg, inboxes)


# --------------------------------------------------------------------------
# Example corpus (also used by audit.py). All protocols are well-formed
# (projectable); the DIFFERENCE lies in their async behaviour.
# --------------------------------------------------------------------------
def _req_response():
    """C->A:Req . A->C:Res . end — only 1 message in flight at a time ⇒ sync-equivalent."""
    return core.Comm("C", "A", "Req", tuple(),
                     core.Comm("A", "C", "Res", tuple(), core.End()))


def _fanout_safe():
    """Fan-out to independent workers with DISJOINT receivers — genuinely concurrent, but each
       inbox has only ONE sender ⇒ no reorder contention ⇒ bounded-safe (max_inflight=2)."""
    # C->A:task . C->B:task . A->C:done . B->E:done . end
    return core.Comm("C", "A", "task", tuple(),
             core.Comm("C", "B", "task", tuple(),
               core.Comm("A", "C", "done", tuple(),
                 core.Comm("B", "E", "done", tuple(), core.End()))))


def _fanin_reorder_bad():
    """C waits for A's reply BEFORE B's, but both write into C's single inbox and B can reply
       first ⇒ reorder mismatch ⇒ deadlock ⇒ async-rejected. (A realistic async trap!)"""
    # C->A:Req . C->B:Req . A->C:ResA . B->C:ResB . end  (C type: ... A?ResA . B?ResB)
    return core.Comm("C", "A", "Req", tuple(),
             core.Comm("C", "B", "Req", tuple(),
               core.Comm("A", "C", "ResA", tuple(),
                 core.Comm("B", "C", "ResB", tuple(), core.End()))))


ASYNC_CORPUS = {
    "req_response":  (_req_response(),     "async-synchronizable"),
    "fanout_safe":   (_fanout_safe(),      "async-bounded-safe"),
    "fanin_reorder": (_fanin_reorder_bad(), "async-rejected"),
}


if __name__ == "__main__":
    print("=" * 72)
    print("ASYNC (ENHANCEMENT) — buffered semantics, deny-by-default gate")
    print("=" * 72)
    for name, (g, expect) in ASYNC_CORPUS.items():
        cls, info = async_class(g, k=2)
        mark = "✓" if cls == expect else "✗"
        print(f"  {mark} {name:<14} → {cls:<22} (expected {expect})")
        print(f"       {info.get('reason','')}  [states={info.get('states')}, "
              f"max_inflight={info.get('max_inflight')}]")
