"""kernel.concurrency — multiparty / streams / bounded async (split of the former kernel.py; see package __init__)."""
from __future__ import annotations
import io
from contextlib import redirect_stdout
from typing import Callable, Dict, List
from z3 import unsat, sat
from casl import spec
from casl import core
from casl import spike_proj_mpst as mpst
from casl import spike_proj_msc as msc
from casl import spike_smt_contract as smt
from casl import spike_monitor_test as mon
from casl import spike_capability as cap
from casl import spike_resilience as res
from casl import spike_hardening as hard
from casl import spike_approval as appr
from casl import spike_attenuation as att
from casl import spike_promise as prom
from casl import spike_judge as jdg

from casl.kernel._base import REGISTRY, building_block, authority_tag, _quiet, _repo_root
from casl.kernel.checks import *  # noqa: F401,F403


@building_block("multiparty", ["LH-F-008"], "P4", ["T2"])
def multiparty() -> bool:
    """Multiparty choreographies (≥4 roles): projection/merge/realizability and the
    operational semantics (`semantics.config`/`roles_of`) are parametric over the role set.
    Proof on the 4-role example `examples/secretariat.casl`: statically accepted (projectable
    for ALL 4 roles + MSC-realizable + approval-dominated) AND operational correspondence/progress
    by-test. HONEST LIMIT: the *concurrent* correspondence for role-disjoint actions
    (≥4 roles) needs a permutation rule in the global reduction system — `W9`, open; the
    generalized `metatheory.run(roles=…)` run shows this empirically (head-only ≠ configuration)."""
    import os
    from casl import surface as casl_surface
    from casl import check as casl_check
    from casl import metatheory
    p = os.path.join(_repo_root(), "examples", "secretariat.casl")
    if not os.path.exists(p):
        return False
    proto = casl_surface.parse_file(p)
    if len(proto.roles) < 4 or not casl_check.check_protocol(proto).get("accepted"):
        return False
    ok, _ = metatheory.check(proto.gtype)   # correspondence + progress for the concrete 4-role protocol
    return bool(ok)


@building_block("concurrency_certified", ["LH-Q-001d"], "P4", ["T2"])
def concurrency_certified(g) -> bool:
    """Concurrency gate (LH-Q-001d): accepts a protocol only if its global
    semantics (with the swap rule) captures that of the endpoint configuration **completely**
    ('certified'). 'incomplete' (endpoints more concurrent than captured) is REJECTED —
    deny-by-default, check when in doubt. The safety direction (global ⊆ config) is separately
    always guaranteed (otherwise 'unsound')."""
    from casl import semantics as sem
    return sem.correspondence_class(g)[0] == "certified"


@building_block("concurrency", ["LH-Q-001d"], "P2", ["T2"])
def concurrency() -> bool:
    """Self-test of grounded concurrency: (1) `examples/concurrent.casl` (disjoint
    pairs) is certified AND accepted by `casl check`; (2) a protocol with
    concurrency across a recursion is 'incomplete' and is REJECTED; (3) soundness
    (global ⊆ config) holds across a ≥4-role random battery (never 'unsound')."""
    import os
    import io
    from contextlib import redirect_stdout
    from casl import surface as casl_surface
    from casl import check as casl_check
    from casl import semantics as sem
    from casl import metatheory
    p = os.path.join(_repo_root(), "examples", "concurrent.casl")
    if not os.path.exists(p):
        return False
    proto = casl_surface.parse_file(p)
    certified_ok = (sem.correspondence_class(proto.gtype)[0] == "certified"
                    and casl_check.check_protocol(proto).get("accepted"))
    # concurrency across Rec → 'incomplete' → rejected by the gate
    g_rec = core.Comm("P", "Q", "a", tuple(),
                      core.Rec("t", core.Comm("R", "S", "b", tuple(), core.TVar("t"))))
    incomplete_rejected = (sem.correspondence_class(g_rec)[0] == "incomplete"
                           and not concurrency_certified(g_rec))
    with redirect_stdout(io.StringIO()):
        r = metatheory.run(n_random=80, roles=("C", "A", "J", "D", "E"))
    sound = (r["unsound"] == 0)
    return bool(certified_ok) and incomplete_rejected and sound


@building_block("stream_safe", ["LH-F-009"], "P2", ["T2", "T3"])
def stream_safe(g, env=()) -> bool:
    """Stream gate (LH-F-009): every `stream` loop is env-driven (dispatch choice of an
    environment selector) and runs a terminating handler in every branch. Without a
    stream loop, vacuously true."""
    from casl import spike_hardening as hard
    ok, _ = hard.stream_wellformed(g, env)
    return ok


@building_block("stream", ["LH-F-009"], "P2", ["T2", "T3"])
def stream() -> bool:
    """Self-test: `examples/inbox.casl` (env-driven inbox, approval in the handler) is
    stream-well-formed AND accepted by `casl check`; a `stream` with a non-terminating
    handler (unbounded inner loop) is REJECTED (deny-by-default for the new construct)."""
    import os
    from casl import surface as casl_surface
    from casl import check as casl_check
    from casl import spike_hardening as hard
    p = os.path.join(_repo_root(), "examples", "inbox.casl")
    if not os.path.exists(p):
        return False
    proto = casl_surface.parse_file(p)
    good = (hard.stream_wellformed(proto.gtype, proto.env)[0]
            and bool(casl_check.check_protocol(proto).get("accepted")))
    # Counter-check: stream with an unbounded inner loop in the handler → rejected
    inner = core.Rec("I", core.Comm("X", "Y", "spin", tuple(), core.TVar("I")))   # rec without measure
    bad = core.Rec("L", core.Choice("Env", "S", (
        core.Branch("Ev", tuple(), core.Comm("S", "X", "h", tuple(), inner)),
        core.Branch("Quit", tuple(), core.End()),
    )), stream=True)
    bad_rejected = not hard.stream_wellformed(bad, ("Env",))[0]
    return bool(good) and bad_rejected


@building_block("revocation", ["LH-Q-008"], "P5", ["T4"])
def revocation() -> bool:
    """LH-Q-008 — capability lifecycle (refresh + revocation): (a) REFRESH — a `stream` loop
    re-grants per iteration, so a finite `ttl` in the deliberately unbounded inbox is
    ttl-safe (`examples/inbox.casl` is now ttl-safe). (b) REVOCATION — a tool revoked at
    runtime is denied by the broker (`tool_denied`), even if it is declared."""
    import os
    from casl import surface as casl_surface
    from casl import spike_hardening as h
    from casl import run as casl_run
    from casl import oracle
    p = os.path.join(_repo_root(), "examples", "inbox.casl")
    if not os.path.exists(p):
        return False
    proto = casl_surface.parse_file(p)
    refresh_ok = h.ttl_safety_check(proto.gtype, proto.caps)[0]          # (a) stream ttl-safe
    mb = oracle.MockBackend("ok")
    rev = casl_run.run_protocol(appr.G_RESCHED_OK, mb, {"budget": 100}, max_loops=3,
                                approve=True, caps=appr.CAPS_CAL, revoked={"calendar"})
    revoke_ok = (rev.outcome == "tool_denied")                          # (b) revoked → denied
    return bool(refresh_ok) and revoke_ok


@building_block("async_bounded", ["LH-F-010"], "P2", ["T2", "T3"])
def async_bounded(g, k: int = 1) -> bool:
    """async ENHANCEMENT (LH-F-010), DENY-BY-DEFAULT gate: a protocol marked `async` is
    admissible only if the buffered semantics at bound k is certified as `async-bounded-safe` OR
    `async-synchronizable` (bounded + orphan-free + deadlock-free). `async-rejected`
    (reorder/deadlock, orphan, buffer>k, state explosion) is REJECTED. Encapsulated: the proven
    synchronous core stays untouched; WITHOUT the `async` marker this block is never consulted — the
    enhancement can therefore never weaken the default (docs/analyses/refinements.md)."""
    from casl import semantics_async as a
    cls, _ = a.async_class(g, k)
    return cls in ("async-bounded-safe", "async-synchronizable")


@building_block("async_enhancement", ["LH-F-010"], "P2", ["T2", "T3"])
def async_enhancement() -> bool:
    """Self-test of the async enhancement (docs/analyses/async.md §3/§5): the example corpus classifies
    EXACTLY as designed — request/response `async-synchronizable` (≤1 in flight, inherits the proven
    core guarantees), independent fan-out `async-bounded-safe` (truly concurrent, safe), fan-in
    with reorder `async-rejected` (deny-by-default). Proves the three verdict levels AND that the
    realistic async trap (responses do not arrive in request order) is rejected, AND
    gate consistency (rejected ⇒ gate False, safe ⇒ gate True)."""
    from casl import semantics_async as a
    ok = all(a.async_class(g, k=2)[0] == expect for _n, (g, expect) in a.ASYNC_CORPUS.items())
    g_bad = a.ASYNC_CORPUS["fanin_reorder"][0]
    g_safe = a.ASYNC_CORPUS["fanout_safe"][0]
    return ok and (not async_bounded(g_bad, 2)) and async_bounded(g_safe, 2)

