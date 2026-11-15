"""kernel.ide — CASL-IDE gates: monotone tiers, pipeline trichotomy, MCP tools, self-audit (split of the former kernel.py; see package __init__)."""
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


@building_block("ide_monotone_gate", ["LH-G-004", "LH-Q-011"], "P1", ["T1", "T3"])
def ide_monotone_gate() -> bool:
    """CASL-IDE Phase 1 (docs/ide.md): the layered, MONOTONE gate — "agents may veto,
    never vouch". Self-test of the four load-bearing properties:
      (1) a safe artifact (budgeted QA, search=read) passes all layers (Tier 4);
      (2) a Tier-2 veto OVERTURNS a Tier-0 acceptance (an agent can only restrict, never open);
      (3) an effect-bearing artifact without human approval is rejected at Tier 3,
      (4) accepted with approval; and Tier 2 has STRUCTURALLY no APPROVE.
    Composes only what exists (Tier 0 = casl check, Tier 1 = casl_run, generator = casl_synth)."""
    from casl import ide
    from casl import synth as syn
    from casl import surface as surf
    o1, _ = ide.synthesize_gated("budgeted QA", syn.MockGenerator(),
                                 reviewer=ide.always_pass, approver=ide.deny_approver)
    o2, _ = ide.synthesize_gated("budgeted QA", syn.MockGenerator(),
                                 reviewer=lambda p: ide.Tier2.VETO, approver=ide.auto_approver)
    pr = surf.Protocol(name="Reschedule", roles=["S", "U", "K"], caps=appr.CAPS_CAL,
                       crash=set(), gtype=appr.G_RESCHED_OK)
    od = ide.monotone_gate(pr, caps=appr.CAPS_CAL, reviewer=ide.always_pass, approver=ide.deny_approver)
    oa = ide.monotone_gate(pr, caps=appr.CAPS_CAL, reviewer=ide.always_pass, approver=ide.auto_approver)
    structural = (not hasattr(ide.Tier2, "APPROVE")
                  and {t.name for t in ide.Tier2} == {"PASS", "VETO", "ESCALATE"})
    return (o1.accepted and o1.tier == 4
            and (not o2.accepted) and o2.tier == 2          # veto beats Tier-0 acceptance
            and (not od.accepted) and od.tier == 3          # human gates the irreversible
            and oa.accepted and oa.tier == 4
            and structural)


@building_block("ide_tier2_review", ["LH-Q-007", "LH-Q-011"], "P8", ["T3", "T4"])
def ide_tier2_review() -> bool:
    """CASL-IDE Phase 2: the Tier-2 LLM reviewer is an ORACLE whose output is DETERMINISTICALLY clamped to
    {PASS, VETO, ESCALATE} (can never open) and which on unreachability falls FAIL-CLOSED
    to ESCALATE (more human oversight, never silently PASS). Self-test:
      (1) clamp: APPROVE/LGTM→PASS, VETO→VETO, garbage/empty→ESCALATE;
      (2) an "APPROVE" reviewer does NOT open an EFFECT artifact — Tier 3 still decides;
      (3) reviewer unreachable → ESCALATE → rejected without human approval (fail-closed)."""
    from casl import ide
    from casl import surface as surf
    from casl import synth as syn
    from casl import oracle as o2
    T = ide.Tier2
    clamp = (ide.parse_tier2("APPROVE ship it") == T.PASS and ide.parse_tier2("LGTM") == T.PASS
             and ide.parse_tier2("VETO x") == T.VETO and ide.parse_tier2("???") == T.ESCALATE
             and ide.parse_tier2("") == T.ESCALATE)
    approve_chat = staticmethod(lambda s, u: "APPROVE great")

    def err_chat(s, u):
        raise o2.OracleUnavailable("down")

    pr = surf.Protocol(name="Reschedule", roles=["S", "U", "K"], caps=appr.CAPS_CAL,
                       crash=set(), gtype=appr.G_RESCHED_OK)
    rev_pass = ide.make_llm_reviewer(type("B", (), {"chat": approve_chat})())
    no_open = ((not ide.monotone_gate(pr, caps=appr.CAPS_CAL, reviewer=rev_pass, approver=ide.deny_approver).accepted)
               and ide.monotone_gate(pr, caps=appr.CAPS_CAL, reviewer=rev_pass, approver=ide.auto_approver).accepted)
    rev_err = ide.make_llm_reviewer(type("B", (), {"chat": staticmethod(err_chat)})())
    qa = surf.parse(syn._FIXED)   # budgeted QA, search=read ⇒ no effect
    fail_closed = not ide.monotone_gate(qa, caps=qa.caps, reviewer=rev_err, approver=ide.deny_approver).accepted
    return clamp and no_open and fail_closed


@building_block("pipeline_safe", ["LH-F-011"], "P1", ["T2", "T4"])
def pipeline_safe(g) -> bool:
    """Pipeline node trichotomy (CASL-IDE Phase 4): R1 no node is both `oracle` AND `verified`
    (opaque vs. proven); R2 every `oracle` node carries a contract (monitored boundary, deny-by-
    default). Vacuously true without markers. The TRUST of `verified` is NOT granted here — that
    is an IDE/Tier-3 attestation (W17)."""
    from casl import spike_pipeline as p
    ok, _ = p.pipeline_safe(g)
    return ok


@building_block("pipeline", ["LH-F-011"], "P2", ["T2", "T4"])
def pipeline() -> bool:
    """Self-test: a mixed pipeline (verified program node + oracle box WITH contract) is
    pipeline-safe; an oracle node WITHOUT a contract (R2) and an oracle+verified node (R1) are
    REJECTED (deny-by-default)."""
    from casl import spike_pipeline as p
    F = core.Field
    # P→Q is a verified program node; Q→C is an oracle box with a contract (monitored).
    good = core.Comm("C", "P", "in", tuple(),
                     core.Comm("P", "Q", "mid", tuple(),
                               core.Comm("Q", "C", "out", (F("cost", "Int"),), core.End(),
                                         contract=core.C_COST_LE_BUDGET, from_oracle=True),
                               verified=True),
                     )
    bad_unmonitored = core.Comm("A", "B", "x", (F("cost", "Int"),), core.End(), from_oracle=True)        # R2
    bad_both = core.Comm("A", "B", "x", tuple(), core.End(), from_oracle=True, verified=True)            # R1
    return (p.pipeline_safe(good)[0]
            and not p.pipeline_safe(bad_unmonitored)[0]
            and not p.pipeline_safe(bad_both)[0])


@building_block("ide_mcp_tools", ["LH-G-001", "LH-Q-011"], "P1", ["T3", "T5"])
def ide_mcp_tools() -> bool:
    """CASL-IDE Phase 3: the MCP server exposes the IDE tools to ANY MCP client (Claude Code/Codex).
    BOUNDARY INVARIANT: the tools check/synthesize/REPORT, but NEVER release and run nothing
    — monotonicity is preserved across the MCP boundary. Self-test of the handlers (without SDK):
      · `casl_check` accepts the valid, rejects an unmonitored oracle box;
      · `casl_gate` on an EFFECT artifact is NOT adoptable and reports `needs_human` (no auto-approve);
      · `casl_synthesize` returns a Tier-0-checked candidate."""
    from casl import mcp
    from casl import synth as syn
    chk_ok = mcp.tool_check(syn._FIXED)["accepted"] is True
    chk_bad = mcp.tool_check("protocol X { roles A, B; A -> B : M() oracle; }")["accepted"] is False
    g = mcp.tool_gate(syn._RESCHED_SAFE)
    boundary = (g["adoptable"] is False and len(g["needs_human_attestation"]) >= 1)
    syn_ok = mcp.tool_synthesize("budgeted QA")["converged"] is True
    return chk_ok and chk_bad and boundary and syn_ok


@building_block("ide_self_audit", ["LH-P-001", "LH-G-001"], "P0", ["T5"])
def ide_self_audit() -> bool:
    """CASL-IDE Phase 5 (P0, living system): the IDE describes its OWN gate pipeline as a CASL
    choreography (`examples/casl_ide_pipeline.casl`) — generator/reviewer = oracle boxes (monitored),
    checker = `verified` node, adoption = irreversible behind the approval gate — and passes its
    OWN gate. Self-test: (1) Tier 0 (`casl check`) accepts the pipeline; (2) the monotone gate
    demands human attestation for its `verified`/effect nodes (without → Tier-3 reject; with →
    accepted). The IDE thus checks itself with its own means."""
    import os
    from casl import surface as surf
    from casl import check as chk
    from casl import ide
    p = os.path.join(_repo_root(), "examples", "casl_ide_pipeline.casl")
    if not os.path.exists(p):
        return False
    proto = surf.parse_file(p)
    t0 = chk.check_protocol(proto)["accepted"]
    deny = ide.monotone_gate(proto, caps=proto.caps, reviewer=ide.always_pass, approver=ide.deny_approver)
    grant = ide.monotone_gate(proto, caps=proto.caps, reviewer=ide.always_pass, approver=ide.auto_approver)
    return bool(t0) and (not deny.accepted) and deny.tier == 3 and grant.accepted

