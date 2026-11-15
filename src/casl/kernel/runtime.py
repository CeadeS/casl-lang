"""kernel.runtime — runtime mediation: approval, effect classification, tool broker, cost metering (split of the former kernel.py; see package __init__)."""
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


@building_block("runtime_approval", ["LH-Q-011"], "P8", ["T3"])
def runtime_approval() -> bool:
    """C3 (Red-Team v0.1.27), runtime side of LH-Q-011: at the approval gate the
    interpreter forces an EXTERNAL decision (default-deny) instead of a structural default.
    Denied (no --approve) ⇒ the irreversible effect branch is NOT entered;
    released ⇒ the consent branch runs. Proves that the lint now has an enforcement."""
    from casl import run as casl_run
    from casl import oracle
    mb = oracle.MockBackend("ok")
    denied = casl_run.run_protocol(appr.G_RESCHED_OK, mb, {"budget": 100}, max_loops=3, approve=False, caps=appr.CAPS_CAL)
    granted = casl_run.run_protocol(appr.G_RESCHED_OK, mb, {"budget": 100}, max_loops=3, approve=True, caps=appr.CAPS_CAL)
    # Denied (default-deny): the irreversible effect branch (Move/consent) is NOT entered —
    # the run takes the safe deny path (or aborts if there is none).
    # "• S→K: Move" is the EXECUTION line (the disclosure line starts with "• U→S:").
    ran_move = lambda r: any(e.startswith("• S→K: Move") for e in r.trace)
    denied_ok = (denied.accepted_label != "Approve") and not ran_move(denied)
    # Released: the consent branch runs, the effect takes place.
    granted_ok = (granted.accepted_label == "Approve") and ran_move(granted)
    return denied_ok and granted_ok


@building_block("effect_classification", ["LH-Q-012"], "P5", ["T4"])
def effect_classification() -> bool:
    """R-H1 (Red-Team v0.1.28): the effect of a capability follows from the structured,
    validated `mode` field (default `write`), NOT from a substring test over the
    free-text `scope`. `read` ⇒ non-effect-bearing; everything else ⇒ effect-bearing
    (deny-by-default). The earlier leak/spoof scopes are now correctly effect-bearing."""
    C = core.Capability
    cases = [
        (C("x", ("p",), "cal:read-write", 1, "s", "write"), True),   # former leak trap
        (C("x", ("p",), "db:readonly", 1, "s", "write"), True),      # former spoof trap (purge)
        (C("x", ("p",), "irgendwas", 1, "s"), True),                 # default = write = effect-bearing
        (C("x", ("p",), "irgendwas", 1, "s", "admin"), True),        # admin = effect-bearing
        (C("x", ("p",), "web:irrelevant", 1, "s", "read"), False),   # only explicit read is exempt
    ]
    return all(appr.effectful(c) is exp for c, exp in cases)


@building_block("gate_disclosure", ["LH-Q-013"], "P8", ["T3"])
def gate_disclosure() -> bool:
    """R-N1 (Red-Team v0.1.28), per-gate disclosure of LH-Q-013: the approval decision
    is bound to the DISCLOSURE — at the gate the triggering message AND the concrete
    effect-bearing action are shown, and consent holds per gate. Proves: (1) the disclosure names the
    effect action + the consent branch, (2) an approver bound to the content routes into it,
    (3) if it does NOT recognize the action, it is denied (no effect)."""
    from casl import run as casl_run
    from casl import oracle
    mb = oracle.MockBackend("ok")
    seen = {}

    def approver(d):
        seen["eff"], seen["label"], seen["disclosed"] = d.effects, d.consent_label, d.disclosed
        return any("Move" in e for e in d.effects)   # only consent if 'Move' is disclosed

    r = casl_run.run_protocol(appr.G_RESCHED_OK, mb, {"budget": 100}, max_loops=3,
                              on_approval=approver, caps=appr.CAPS_CAL)
    bound = (seen.get("label") == "Approve"
             and any("Move" in e for e in seen.get("eff", []))
             and "Conflict" in (seen.get("disclosed") or ""))
    ran_move = lambda rr: any(e.startswith("• S→K: Move") for e in rr.trace)
    routed = (r.accepted_label == "Approve") and bool(r.gate_disclosures) and ran_move(r)
    # Counter-check: if the approver does not recognize the disclosed action → denial, no effect
    r2 = casl_run.run_protocol(appr.G_RESCHED_OK, mb, {"budget": 100}, max_loops=3,
                               on_approval=lambda d: any("Delete" in e for e in d.effects),
                               caps=appr.CAPS_CAL)
    denied = (r2.accepted_label != "Approve") and not ran_move(r2)
    return bound and routed and denied


@building_block("tool_broker", ["LH-Q-014"], "P5", ["T4"])
def tool_broker() -> bool:
    """H3 (Red-Team v0.1.27), LH-Q-014: runtime confinement instead of a mere lint. The runner
    interposes on every tool use and denies a tool not carried at runtime —
    even if the spec declared it statically (e.g. an attenuated object with fewer
    capabilities than its kind). Proves: same choreography, search present ⇒ runs;
    search withdrawn at runtime ⇒ the broker blocks the step (`tool_denied`)."""
    from casl import run as casl_run
    from casl import oracle
    mb = oracle.MockBackend("ok")
    allowed = casl_run.run_protocol(core.G_OK, mb, {"budget": 100, "question": "q"},
                                    max_loops=3, caps=core.AGENT_CAPS)          # A carries search
    denied = casl_run.run_protocol(core.G_OK, mb, {"budget": 100, "question": "q"},
                                   max_loops=3, caps={"A": (), "C": (), "J": ()})  # search entzogen
    return allowed.outcome == "completed" and denied.outcome == "tool_denied"


@building_block("cost_metering", ["LH-Q-015"], "P8", ["T3"])
def cost_metering() -> bool:
    """H4 (Red-Team v0.1.27), LH-Q-015: the oracle does NOT itself report the quantity by which it
    is measured — the monitor checks against the out-of-band measurement (server usage/meter); the
    `cost` reported by the oracle is only an unchecked claim. Proof: an oracle that reports a
    budget-conformant claim but actually overspends (`underreport`) is detected via the
    measurement as a violation (blame A) — trusting the claim would have let it through."""
    from casl import oracle
    budget = 100
    under = oracle.oracle_step(oracle.MockBackend("underreport"), "q", budget)
    okk = oracle.oracle_step(oracle.MockBackend("ok"), "q", budget)
    claim_would_pass = (under.cost is not None and under.cost <= budget)   # the claim looks harmless
    caught_by_meter = (under.kind == "violation" and under.blame == "A")    # the measurement reveals it
    return claim_would_pass and caught_by_meter and okk.kind == "ok"

