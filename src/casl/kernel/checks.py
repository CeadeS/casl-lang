"""kernel.checks — the proof pipeline: well-formedness, contracts, resilience, attestation (split of the former kernel.py; see package __init__)."""
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


@building_block("core_ir", ["LH-F-001"], "P3", ["T2"])
def core_ir() -> bool:
    """The IR substrate: agents/roles are first-class typed values; messages,
    capabilities, contracts and recursion are data (casl_core). Foundation that
    every other block builds on. (Promise as a first-class type is still open —
    see LH-F-003 / W6.)"""
    return True


@building_block("project", ["LH-F-006", "LH-F-002"], "P4", ["T2", "T3"])
def project(g, role):
    """Project a global type onto a role's local session type."""
    return mpst.project(g, role)


@building_block("wellformed", ["LH-Q-001a", "LH-Q-001b", "LH-Q-001c"], "P2", ["T2"])
def wellformed(g, roles=None) -> bool:
    """Static well-formedness: MPST-projectable for every role AND MSC-realizable
    AND the two traditions agree (cross-check, convergence criterion 1).
    `roles` defaults to core.ROLES; the surface CLI passes the protocol's own
    declared roles so well-formedness binds to the file under test."""
    roles = roles if roles is not None else core.ROLES
    mpst_ok = True
    for r in roles:
        try:
            mpst.project(g, r)
        except mpst.NonProjectable:
            mpst_ok = False
    msc_ok = _quiet(msc.realizability, g, "", roles)
    return mpst_ok and msc_ok


@building_block("capabilities", ["LH-Q-002", "LH-F-005"], "P5", ["T4"])
def capabilities(g, caps=None) -> bool:
    """Least Privilege: every tool use is inside the sender's capability set.
    `caps` defaults to core.AGENT_CAPS; the surface CLI passes the protocol's
    own capability declarations."""
    return _quiet(cap.capability_check, g, "", caps)


@building_block("contract_smt", ["LH-Q-004", "LH-G-002"], "P1", ["T1", "T4"])
def contract_smt() -> bool:
    """Discharge the budget data-contract via Z3 (deterministic hull)."""
    proven = (smt.prove_budget_safety() == unsat)
    res2, _ = smt.find_overspend_without_stepwise_contract()
    return proven and (res2 == sat)


@building_block("monitor", ["LH-Q-005", "LH-G-002"], "P8", ["T3"])
def monitor(contract, producer):
    """Synthesize a runtime monitor with blame for an oracle boundary."""
    return mon.synth_monitor(contract, producer)


@building_block("tests", ["LH-Q-006"], "P7", ["T4"])
def tests(monitor_fn) -> int:
    """Property test derived from the contract; returns mismatch count."""
    _n, fails = mon.property_test(monitor_fn)
    return fails


@building_block("prompt", ["LH-F-006"], "P7", ["T2", "T3"])
def prompt(g, role) -> str:
    """Project a role's local type into an executable agent prompt skeleton."""
    lt = mpst.project(g, role)
    lines = [f"You are agent {role} ({core.ROLE_NAMES[role]}). Follow this protocol exactly:"]
    step = [1]

    def walk(l):
        if isinstance(l, mpst.LRecv):
            lines.append(f"  {step[0]}. Receive {l.label}({core.fields_str(l.fields)}) from {l.frm}.")
            step[0] += 1; walk(l.cont)
        elif isinstance(l, mpst.LSend):
            ct = (f"  CONTRACT: {core.C_COST_LE_BUDGET.text} (blamed if violated)."
                  if l.label == "Draft" else "")
            lines.append(f"  {step[0]}. Send {l.label}({core.fields_str(l.fields)}) to {l.to}.{ct}")
            step[0] += 1; walk(l.cont)
        elif isinstance(l, mpst.LRec):
            lines.append(f"  {step[0]}. Repeat (loop {l.var}) until accepted:")
            step[0] += 1; walk(l.body)
        elif isinstance(l, mpst.LVar):
            lines.append(f"     ↺ back to loop {l.var}.")
        elif isinstance(l, mpst.LExtChoice):
            opts = ", ".join(lbl for lbl, _, _ in l.opts)
            lines.append(f"  {step[0]}. Await one of {{{opts}}} from {l.frm}.")
            step[0] += 1
        elif isinstance(l, mpst.LIntChoice):
            opts = ", ".join(lbl for lbl, _, _ in l.opts)
            lines.append(f"  {step[0]}. Choose and send one of {{{opts}}} to {l.to}.")
            step[0] += 1

    walk(lt)
    caps = core.AGENT_CAPS.get(role, ())
    lines.append("Capabilities (and nothing else): "
                 + (", ".join(c.tool for c in caps) if caps else "none"))
    return "\n".join(lines)


@building_block("crash_tolerance", ["LH-F-007a"], "P2", ["T3"])
def crash_tolerance(g, crash_prone=None) -> bool:
    """Static crash-tolerance (SHOULD): every receiver of a crash-prone sender has
    a typed on_crash continuation (else it could block forever).
    `crash_prone` defaults to core.CRASH_PRONE; the surface CLI passes the
    protocol's own `crash` declarations."""
    ok, _ = res.crash_tolerance(g, crash_prone)
    return ok


@building_block("refusal_monitor", ["LH-F-007b"], "P1", ["T3"])
def refusal_monitor(contract, producer):
    """Runtime monitor treating oracle refusal as a typed outcome (no blame)."""
    return res.synth_refusal_monitor(contract, producer)


@building_block("linearity", ["LH-Q-003a", "LH-Q-003b"], "P6", ["T4"])
def linearity(g) -> bool:
    """Each promise is resolved exactly once per loop body (write-once + obligation)."""
    ok, _ = hard.linearity_check(g)
    return ok


@building_block("termination", ["LH-Q-009"], "P2", ["T1", "T2"])
def termination(g) -> bool:
    """SMT-ranking: loop terminates iff a decreasing, bounded measure is declared."""
    ok, _ = hard.termination_check(g)
    return ok


@building_block("ttl_safety", ["LH-Q-010"], "P5", ["T4"])
def ttl_safety(g, caps=None) -> bool:
    """Finite-ttl capability inside a loop is safe iff ttl >= proven iteration bound.
    `caps` defaults to core.AGENT_CAPS; the surface CLI passes the protocol's own
    capability declarations."""
    ok, _ = hard.ttl_safety_check(g, caps)
    return ok


@building_block("metatheory", ["LH-Q-001a", "LH-Q-001b", "LH-Q-001c"], "P2", ["T2"])
def metatheory(g) -> bool:
    """Operational correspondence + deadlock-freedom hold for g (proof-by-test over
    its reachable states) — theorem-level evidence for conformance/fidelity (L3)."""
    from casl import metatheory as mt   # lazy: metatheory imports kernel
    ok, _ = mt.check(g)
    return ok


@building_block("living_audit", ["LH-P-001", "LH-P-002", "LH-P-003", "LH-C-002"], "P9", ["T5"])
def living_audit() -> bool:
    """The audit itself is a building block: it keeps traceability/versioning
    honest (realized operationally by audit.py)."""
    return True


@building_block("oracle_boundary", ["LH-G-002", "LH-Q-005"], "P1", ["T1", "T3"])
def oracle_boundary() -> bool:
    """Two-stage semantics, productively (Richtung A): the static hull is proven,
    the LLM oracle's payload is checked at the boundary by the synthesized monitor
    with blame on the producer. Runs the DETERMINISTIC mock backend (no network),
    so the living system stays self-contained: ok→ok, overspend→blame A, refusal→typed.
    The real Ollama endpoint is exercised by `python oracle.py --live`."""
    from casl import oracle  # lazy: oracle imports spike_resilience
    ok = oracle.oracle_step(oracle.MockBackend("ok"), "q", 100)
    bad = oracle.oracle_step(oracle.MockBackend("overspend"), "q", 100)
    ref = oracle.oracle_step(oracle.MockBackend("refusal"), "q", 100)
    return (ok.kind == "ok"
            and bad.kind == "violation" and bad.blame == "A"
            and ref.kind == "refusal")


@building_block("interpreter", ["LH-G-001", "LH-G-002"], "P1", ["T2", "T3"])
def interpreter() -> bool:
    """The two-stage semantics EXECUTING end-to-end: walk the global type, call
    the oracle at the boundary, let the monitor verdict drive the choice, bound the
    recursion. Deterministic mock `retry_then_ok` (overspend → Reject → loop, then
    ok → Accept → end) so the living system needs no network."""
    from casl import run as casl_run
    from casl import oracle
    r = casl_run.run_protocol(core.G_OK, oracle.MockBackend("retry_then_ok"),
                              {"budget": 100, "question": "q"}, max_loops=5)
    return r.outcome == "completed" and r.loops == 1 and r.last_verdict == "ok"


@building_block("approval_safety", ["LH-Q-011"], "P2", ["T3"])
def approval_safety(g, caps=None) -> bool:
    """Approval dominance (stage B, hardened): every effect-bearing action (explicitly
    `irreversible` OR using a non-readonly capability) is dominated on every path by
    an approval gate via its `consent` branch; consent survives no
    loop iteration. No side effect without specific consent."""
    ok, _ = appr.approval_dominated(g, caps)
    return ok


@building_block("branch_contracts", ["LH-Q-004", "LH-Q-005"], "P8", ["T3", "T4"])
def branch_contracts(g) -> bool:
    """W7: every branch contract (e.g. `len(reason)>0`) is synthesized into a monitor with blame
    and property-checked against the contract — no longer merely decorative."""
    ok, _ = mon.branch_contract_monitors_sound(g)
    return ok


@building_block("attenuation", ["LH-F-004", "LH-G-003"], "P5", ["T4"])
def attenuation(obj_caps, kind_caps) -> bool:
    """Object = attenuated subtype of an agent kind: an object carries only capabilities
    of its kind and no stronger (tool subset, ttl<=, scope not broader) — never more
    authority than the kind (Least Privilege under attenuation)."""
    ok, _ = att.attenuation_sound(obj_caps, kind_caps)
    return ok


@building_block("promise", ["LH-F-003"], "P6", ["T2"])
def promise(g) -> bool:
    """Promise/Future as a first-class type: every oracle output is a typed
    Promise[T] with a resolve-once obligation (write-once / linearity, W6)."""
    ok, _, _ = prom.promise_discipline(g)
    return ok


@building_block("versioning", ["LH-C-001", "LH-P-005"], "P9", ["T5"])
def versioning() -> bool:
    """Versioning / traceability discipline (offline, deterministic): `CONTRIBUTING.md`
    documents the commit convention (reference requirement IDs), SemVer, and the
    tool `trace.py` (code↔commit↔requirement). The actual git extraction runs
    via `trace.py` on the machine, not in the offline audit."""
    import os
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    contrib = os.path.join(root, "CONTRIBUTING.md")
    if not (os.path.exists(contrib) and os.path.exists(os.path.join(root, "src", "casl", "trace.py"))):
        return False
    with open(contrib, encoding="utf-8") as f:
        txt = f.read().lower()
    return all(k in txt for k in ("semver", "requirement", "trace.py"))


@building_block("synthesis", ["LH-G-004"], "P1", ["T1", "T2"])
def synthesis() -> bool:
    """Requirement-driven synthesis behind the verifier gate (NL→Spec→code→test→loop):
    the (mock) design-time oracle proposes, `casl check` decides, the repair loop converges
    (broken → corrected), the derived tests pass. Deterministic, offline."""
    from casl import synth as casl_synth
    r = casl_synth.synthesize("budgeted QA", casl_synth.MockGenerator(), max_iters=4)
    return r.accepted and r.iterations == 2 and bool(r.tests) and all(r.tests.values())


@building_block("synthesis_repair", ["LH-G-004"], "P1", ["T1", "T2"])
def synthesis_repair() -> bool:
    """Feedback-DRIVEN synthesis on a SAFETY repair (the target picture in miniature):
    a draft with an effect-bearing action WITHOUT approval is rejected by `casl check`
    (approval dominance), and exactly this diagnostic drives the repair (approval-consent gate)
    → accepted. Causality: the feedback-responsive generator stays unsafe WITHOUT the approval
    hint — the repair depends on the feedback content, not on a call counter."""
    from casl import synth as casl_synth
    gen = casl_synth.RepairMockGenerator()
    r = casl_synth.synthesize("Reschedule an appointment, only with consent", gen, max_iters=4)
    if not (r.accepted and r.iterations == 2):
        return False
    first_rejected_for_approval = (r.trace[0][1] == "rejected"
                                   and "approval" in (r.trace[0][2] or "").lower())
    second_accepted = (r.trace[1][1] == "accepted")
    causal = gen.propose("x", "") != gen.propose("x", "approval dominance violated")
    return first_rejected_for_approval and second_accepted and causal


@building_block("semantic_judge", ["LH-Q-007"], "P8", ["T4"])
def semantic_judge() -> bool:
    """Semantic check (LH-Q-007): metamorphic invariants over varied oracle scenarios
    (ok⇒answer judged ok; refusal⇒detected; overspend⇒violation) + content judge
    (MockJudge deterministic; live LLM judge optional)."""
    ok, _ = jdg.metamorphic_battery(jdg.MockJudge())
    return ok


@building_block("norms", ["LH-P-004"], "P9", ["T5"])
def norms() -> bool:
    """LH-P-004: standards conformance documented — `CASL.md` names ISO/IEC/IEEE 29148,
    DIN 69901-5 and VDI/VDE 3694 (checked offline, deterministically)."""
    import os
    p = os.path.join(_repo_root(), "CASL.md")
    if not os.path.exists(p):
        return False
    with open(p, encoding="utf-8") as f:
        t = f.read()
    return all(k in t for k in ("29148", "69901", "3694"))


@building_block("review", ["LH-C-003"], "P9", ["T5"])
def review() -> bool:
    """LH-C-003: review / release process documented — `CONTRIBUTING.md` describes the
    explicit approval gate (`approved` before `--no-ff` merge into `main`)."""
    import os
    p = os.path.join(_repo_root(), "CONTRIBUTING.md")
    if not os.path.exists(p):
        return False
    with open(p, encoding="utf-8") as f:
        t = f.read().lower()
    return all(k in t for k in ("approval", "--no-ff", "main"))


@building_block("redteam_attacks", ["LH-Q-011"], "P0", ["T3"])
def redteam_attacks() -> bool:
    """Red-team regression gate (self-application P0): every attack spec in
    examples/attacks/ MUST be REJECTED by the full casl-check pipeline (parser → check_protocol).
    If one is accepted, the keystone has been torn open again."""
    import os
    from casl import surface as casl_surface
    from casl import check as casl_check
    d = os.path.join(_repo_root(), "examples", "attacks")
    if not os.path.isdir(d):
        return False
    specs = [f for f in os.listdir(d) if f.endswith(".casl")]
    if not specs:
        return False
    for f in specs:
        proto = casl_surface.parse_file(os.path.join(d, f))
        if casl_check.check_protocol(proto)["accepted"]:
            return False
    return True


def compile_choreography(g, name: str, verbose: bool = True) -> dict:
    def say(s):
        if verbose:
            print(s)

    say(f"compile_choreography({name}) — composing building blocks:")

    if not wellformed(g):
        say(f"  ✗ rejected at [wellformed] ({authority_tag('wellformed')})")
        return {"accepted": False, "stage": "wellformed"}
    say(f"  ✓ wellformed        ({authority_tag('wellformed')})")

    if not capabilities(g):
        say(f"  ✗ rejected at [capabilities] ({authority_tag('capabilities')})")
        return {"accepted": False, "stage": "capabilities"}
    say(f"  ✓ capabilities      ({authority_tag('capabilities')})")

    if not linearity(g):
        say(f"  ✗ rejected at [linearity] ({authority_tag('linearity')})")
        return {"accepted": False, "stage": "linearity"}
    say(f"  ✓ linearity         ({authority_tag('linearity')})")

    contracts_ok = contract_smt()
    say(f"  ✓ contract_smt={contracts_ok}  ({authority_tag('contract_smt')})")

    locals_ = {r: project(g, r) for r in core.ROLES}
    prompts = {r: prompt(g, r) for r in core.ROLES}
    say(f"  ✓ project+prompt for {list(locals_)}  ({authority_tag('project')})")

    mon_fn = monitor(core.C_COST_LE_BUDGET, "A")
    v = mon_fn({"cost": 125, "budget": 100})
    blame_ok = (not v.ok and v.blame == "A")
    say(f"  ✓ monitor blame_ok={blame_ok}  ({authority_tag('monitor')})")

    test_fails = tests(mon_fn)
    say(f"  ✓ tests fails={test_fails}  ({authority_tag('tests')})")

    # SHOULD advisories: crash/refusal resilience (report, do not gate — SHOULD level)
    crash_ok = crash_tolerance(g)
    say(f"  {'✓' if crash_ok else '⚠'} crash_tolerance={crash_ok} (SHOULD)  ({authority_tag('crash_tolerance')})")
    rmon = refusal_monitor(core.C_COST_LE_BUDGET, "A")
    refusal_typed = rmon({"refused": True, "cost": 0, "budget": 100}).kind == "refusal"
    say(f"  {'✓' if refusal_typed else '⚠'} refusal handled={refusal_typed} (SHOULD)  ({authority_tag('refusal_monitor')})")

    term_ok = termination(g)
    say(f"  {'✓' if term_ok else '⚠'} termination={term_ok} (SHOULD)  ({authority_tag('termination')})")
    ttl_ok = ttl_safety(g)
    say(f"  {'✓' if ttl_ok else '⚠'} ttl_safety={ttl_ok} (SHOULD)  ({authority_tag('ttl_safety')})")

    return {"accepted": True, "contracts_ok": contracts_ok, "blame_ok": blame_ok,
            "test_fails": test_fails, "crash_tolerant": crash_ok, "refusal_typed": refusal_typed,
            "terminates": term_ok, "ttl_safe": ttl_ok,
            "locals": locals_, "prompts": prompts}

