#!/usr/bin/env python3
"""
audit.py — the LIVED SYSTEM (principle P0/P9, LH-P-002).

Everything here DERIVES from spec.py and the kernel's building-block registry —
nothing is hand-duplicated. The audit:

  [0] validates the AUTHORITY CHAIN (every block cites only real spec items),
  [1] checks traceability (every requirement -> valid theses),
  [2] checks thesis coverage (every thesis realized by >=1 block),
  [3] checks requirement gaps (covered, or accepted+tracked),
  [4] RUNS THE FEATURE (compile_choreography) — building blocks actually accept
      G_OK and reject G_BAD / G_CAP_BAD,
  [5] lists open tensions,
  [6] exits non-zero on any hard failure (run it every iteration).
"""
from __future__ import annotations
import io
import sys
from contextlib import redirect_stdout

from casl import spec
from casl import kernel
from casl import authority
from casl import core
from casl import spike_capability as cap
from casl import spike_hardening as hard
from casl import spike_approval as appr
from casl import spike_attenuation as att
from casl import harden_equivalence as harden
from casl import metatheory as mt
from casl import requirements as ph
from casl import cep


def _quiet(fn, *a, **k):
    with redirect_stdout(io.StringIO()):
        return fn(*a, **k)


def _async_examples_ok() -> bool:
    """End-to-end (P0): the async examples run through the full casl-check pipeline
    (parser → check_protocol) — the safe ones are accepted, the reorder trap rejected.
    The `async` marker adds the buffered enhancement in an encapsulated way (deny-by-default)."""
    import os
    from casl import surface as casl_surface
    from casl import check as casl_check
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    want = {"async_request.casl": True, "async_fanout.casl": True, "async_fanin_bad.casl": False}
    for fn, expect in want.items():
        p = os.path.join(root, "examples", fn)
        if not os.path.exists(p):
            return False
        proto = casl_surface.parse_file(p)
        if proto.async_k is None:                      # marker must have been parsed
            return False
        if casl_check.check_protocol(proto)["accepted"] is not expect:
            return False
    return True


def main() -> int:
    hard_fail = False
    print("=" * 72)
    print("CASL LIVING AUDIT — authority from the specification, applied to ourselves")
    print("=" * 72)

    ok_auth, d = authority.check()
    cov = d["coverage"]

    # [0] authority chain
    print("\n[0] Authority chain (every block cites only real spec items):")
    if d["block_violations"]:
        hard_fail = True
        for bid, msg in d["block_violations"]:
            print(f"    ✗ block '{bid}' {msg}")
    else:
        print(f"    ✓ all {len(kernel.REGISTRY)} blocks are spec-authorized "
              f"(realize {len(cov)} requirements)")

    # [1] traceability
    print("\n[1] Traceability (requirement → thesis):")
    bad_trace = [(rid, s) for rid, (_, _, srcs) in spec.REQS.items()
                 for s in srcs if s not in spec.THESES]
    if bad_trace:
        hard_fail = True
        for rid, s in bad_trace:
            print(f"    ✗ {rid} → unknown thesis {s}")
    else:
        print(f"    ✓ all {len(spec.REQS)} requirements reference valid theses")

    # [2] thesis coverage
    print("\n[2] Thesis coverage (≥1 realizing requirement):")
    for t, rs in d["thesis_coverage"].items():
        mark = "✓" if rs else "✗"
        if not rs:
            hard_fail = True
        print(f"    {mark} {t} ({spec.THESES[t]}): {', '.join(sorted(rs)) if rs else 'NONE'}")

    # [3] requirement coverage
    print("\n[3] Requirement coverage (verif ∈ B/S/M/T):")
    if d["uncovered"]:
        hard_fail = True
        for rid in d["uncovered"]:
            print(f"    ✗ UNCOVERED (not accepted): {rid} {spec.REQS[rid][:2]}")
    n_exec = sum(1 for _, (_, v, _) in spec.REQS.items() if spec.is_executable(v))
    n_cov = sum(1 for rid in spec.REQS if cov.get(rid))
    n_gap = sum(1 for rid in spec.ACCEPTED_GAPS if rid in spec.REQS and not cov.get(rid))
    print(f"    covered={n_cov}, accepted gaps={n_gap}, uncovered={len(d['uncovered'])} "
          f"(of {n_exec} executable-verifiable)")

    # [4] feature execution — the building blocks at work
    print("\n[3b] Traceability (requirement → realizing block, derived from the registry):")
    for rid in spec.REQS:
        bl = cov.get(rid)
        if bl:
            print(f"    {rid:<10} → {', '.join(bl)}")

    ph_ok, ph_d = ph.check()
    print("\n[3c] Specification sheet (L2): LH → PH realization")
    print(f"    {ph_d['n_ph']} PH items · uncovered LH: {ph_d['uncovered'] or 'none'} · invalid refs: {ph_d['bad_refs'] or 'none'}")

    print("\n[4] Feature execution (compile_choreography composes the building blocks):")
    b_ok = _quiet(kernel.compile_choreography, core.G_OK, "G_OK", verbose=False)
    b_bad = _quiet(kernel.compile_choreography, core.G_BAD, "G_BAD", verbose=False)
    b_cap = _quiet(kernel.compile_choreography, cap.G_CAP_BAD, "G_CAP_BAD", verbose=False)
    b_crash = _quiet(kernel.compile_choreography, core.G_OK_CRASH, "G_OK_CRASH", verbose=False)
    b_term = _quiet(kernel.compile_choreography, core.G_OK_TERM, "G_OK_TERM", verbose=False)
    b_dup = _quiet(kernel.compile_choreography, hard.G_DUP, "G_DUP", verbose=False)
    h = _quiet(harden.run)
    m = _quiet(mt.run, 120)
    checks = [
        ("G_OK accepted", b_ok.get("accepted") is True),
        ("G_BAD rejected @ wellformed", b_bad.get("stage") == "wellformed"),
        ("G_CAP_BAD rejected @ capabilities", b_cap.get("stage") == "capabilities"),
        ("G_DUP rejected @ linearity", b_dup.get("stage") == "linearity"),
        ("G_OK: SMT contract ok", b_ok.get("contracts_ok") is True),
        ("G_OK: monitor blame ok", b_ok.get("blame_ok") is True),
        ("G_OK: property test 0 fails", b_ok.get("test_fails") == 0),
        ("G_OK_CRASH crash-tolerant (SHOULD)", b_crash.get("crash_tolerant") is True),
        ("G_OK refusal typed", b_ok.get("refusal_typed") is True),
        ("Oracle boundary (mock): ok/blame-A/refusal correct", kernel.oracle_boundary() is True),
        ("Interpreter (mock): G_OK runs to Accept (1 loop)", kernel.interpreter() is True),
        ("Approval dominance: effect⇒approval-consent (OK ok / BAD+C1+C2 flagged)",
         kernel.approval_safety(appr.G_RESCHED_OK, appr.CAPS_CAL) is True
         and kernel.approval_safety(appr.G_RESCHED_BAD, appr.CAPS_CAL) is False
         and kernel.approval_safety(appr.G_DENY_ATTACK, appr.CAPS_CAL) is False
         and kernel.approval_safety(appr.G_SILENT_SEND, appr.CAPS_MAIL) is False),
        ("Branch contracts wired up (G_OK: len(reason)>0 monitored)", kernel.branch_contracts(core.G_OK) is True),
        ("Attenuation: object subtype sound (OK ok / escalation flagged)",
         kernel.attenuation(att.OBJ_OK, att.A_KIND) is True
         and kernel.attenuation(att.OBJ_BAD_TTL, att.A_KIND) is False
         and kernel.attenuation(att.OBJ_BAD_TOOL, att.A_KIND) is False),
        ("Promise first-class + resolve-once (G_OK ok / G_DUP flagged)",
         kernel.promise(core.G_OK) is True and kernel.promise(hard.G_DUP) is False),
        ("Versioning/traceability discipline (CONTRIBUTING + trace.py)", kernel.versioning() is True),
        ("Synthesis loop (mock): NL→Spec→code→test converges (broken→corrected)", kernel.synthesis() is True),
        ("Synthesis feedback-driven: safety repair (missing approval → added, causal)", kernel.synthesis_repair() is True),
        ("Semantic judge (metamorphic, mock): ok/refusal/overspend invariants", kernel.semantic_judge() is True),
        ("Standards conformance documented (CASL.md: 29148/69901/3694)", kernel.norms() is True),
        ("Review/release process documented (CONTRIBUTING approval-gate)", kernel.review() is True),
        ("Red-team attacks rejected (examples/attacks/* → exit≠0)", kernel.redteam_attacks() is True),
        ("Runtime approval (C3): default-deny at the gate, no effect without release", kernel.runtime_approval() is True),
        ("Effect classification structured (R-H1): mode field, not scope substring", kernel.effect_classification() is True),
        ("Per-gate disclosure (R-N1): consent bound to the disclosed action", kernel.gate_disclosure() is True),
        ("Tool broker (H3): undeclared tool denied at runtime", kernel.tool_broker() is True),
        ("Out-of-band cost metering (H4): underreport detected by the meter (blame A)", kernel.cost_metering() is True),
        ("G_OK_TERM terminates (SHOULD)", b_term.get("terminates") is True),
        ("G_OK_TERM ttl-safe (SHOULD)", b_term.get("ttl_safe") is True),
        (f"MPST⇔MSC equivalence hardened ({h['n_cases']} cases)", h["ok"] is True),
        (f"Metatheorems: correspondence + deadlock-free ({m['tested']} protocols)", m["ok"] is True),
        ("Multiparty ≥4 roles (secretariat.casl + 5-role by-test)", kernel.multiparty() is True),
        ("Concurrency well-founded (swap/correspondence, sound; non-certifiable rejected)", kernel.concurrency() is True),
        ("Streams/events (LH-F-009): env-driven loop, handlers terminate (inbox.casl)", kernel.stream() is True),
        ("Capability revocation/refresh (LH-Q-008): stream ttl-safe + revoke denied", kernel.revocation() is True),
        ("Async enhancement (LH-F-010): corpus classified (sync-equiv/bounded-safe/rejected) + gate consistent", kernel.async_enhancement() is True),
        ("Async end-to-end: safe examples accepted, reorder trap rejected (encapsulated, deny-by-default)", _async_examples_ok() is True),
        ("CASL-IDE monotone gate (Tier 0–3; veto overturns Tier 0; human gates effect; Tier 2 without APPROVE)", kernel.ide_monotone_gate() is True),
        ("CASL-IDE Tier-2 review (LLM clamped to PASS/VETO/ESCALATE; APPROVE does not open; fail-closed)", kernel.ide_tier2_review() is True),
        ("Pipeline trichotomy (LH-F-011): verified+oracle box safe; oracle without contract / oracle+verified rejected", kernel.pipeline() is True),
        ("CASL-IDE MCP server tools (Phase 3): check/gate/synthesize; boundary — reports needs-human, never releases", kernel.ide_mcp_tools() is True),
        ("CASL-IDE self-audit (Phase 5, P0): the IDE describes itself as a CASL pipeline + passes its own gate", kernel.ide_self_audit() is True),
        ("Specification sheet (L2) realizes all LH (≥1 PH)", ph_ok is True),
    ]
    for name, ok in checks:
        if not ok:
            hard_fail = True
        print(f"    [{'PASS' if ok else 'FAIL'}] {name}")

    # [CEP] enhancement-proposal corpus — versioned + machine-checked requirement log
    print("\n[CEP] Enhancement-proposal corpus (versioned + proven):")
    ceps = cep.load_ceps()
    if not ceps:
        print("    ⚠ no CEP corpus found (proposals/ absent) — skipped")
    else:
        cep_schema = cep.validate(ceps)
        cep_rt = cep.roundtrip_diff(spec.REQS, ceps)
        cep_status = cep.status_consistency(set(kernel.REGISTRY), set(spec.ACCEPTED_GAPS), ceps)
        for f_, m_ in cep_schema:
            hard_fail = True
            print(f"    ✗ schema  {f_}: {m_}")
        for d_ in cep_rt:
            hard_fail = True
            print(f"    ✗ round-trip (CEP↔spec): {d_}")
        for f_, m_ in cep_status:
            hard_fail = True
            print(f"    ✗ status  {f_}: {m_}")
        if not (cep_schema or cep_rt or cep_status):
            n_req = sum(1 for c in ceps if c.get("requirement-id"))
            n_final = sum(1 for c in ceps if c.get("status") == "Final")
            n_def = sum(1 for c in ceps if c.get("status") == "Deferred")
            print(f"    ✓ {len(ceps)} CEPs ({n_req} requirements): schema valid, "
                  f"CEP↔spec round-trip exact, status↔realization consistent "
                  f"({n_final} Final, {n_def} Deferred)")

    # [5] tensions
    print("\n[5] Open tensions (tracked, not a hard failure):")
    for wid, sev, text, status in spec.TENSIONS:
        print(f"    {wid} [{sev}] {text} — {status}")

    # [5b] layering — compile-out precondition (CEP-0003 step 5): inner rings must not
    # import outer rings at module level, else `core` cannot be shipped without the outer code.
    print("\n[5b] Layering (compile-out precondition — inner rings must not import outer):")
    from casl import profiles as prof
    hard_edges = prof.layering_violations()
    soft_edges = prof.deferred_layering_edges()
    for (a, b, ri, ro) in hard_edges:
        hard_fail = True
        print(f"    ✗ HARD {a} ({prof.RING_NAME[ri]}) imports {b} ({prof.RING_NAME[ro]}) at module level")
    if not hard_edges:
        print(f"    ✓ no module-level inner→outer imports — core TCB "
              f"({len(prof.tcb_modules('core'))} modules) is free of extended/advisory deps")
    if soft_edges:
        uniq = sorted({(a, b) for (a, b, _, _) in soft_edges})
        print(f"    · {len(uniq)} deferred (lazy) outer-ring edges, loaded only on their path: "
              + ", ".join(f"{a}→{b}" for a, b in uniq))

    # [5c] assurance modes + trust budget (CEP-0003 / SP-1): make the discharge mode of each
    # grade an explicit, machine-queryable token, and state the kernel axiom budget (à la `#print
    # axioms`). The `core` profile admits a protocol-level trust budget of 0 (binary/G0 only).
    print("\n[5c] Assurance modes + trust budget (machine-queryable trust):")
    from casl import levels as _lv
    print("    modes: " + ", ".join(f"{g}->{_lv.assurance_mode(g)}" for g in _lv.ASSURANCE)
          + ", assumed (explicit trust)")
    print("    core profile ⇒ trust budget = 0 (binary/G0 only); F* axiom budget enforced = 0 "
          "by scripts/check_admits.sh (admits/assume/magic, CI)")

    # [5d] proof-faithfulness anti-vacuity front-line (SP-4 / CEP-0004): non-vacuity witnesses
    # present, discriminating power (must-die mutants rejected), NL↔formal consistency. These run
    # mechanically BEFORE human attestation so the human attests only the residual.
    print("\n[5d] Proof-faithfulness front-line (anti-vacuity, before human attestation):")
    from casl import faithfulness as _faith
    _mw, _ms, _cd = _faith.missing_witnesses(), _faith.mutation_survivors(), _faith.cep_feature_consistency()
    for w in _mw:
        hard_fail = True
        print(f"    ✗ missing non-vacuity witness: {w} (metatheorem may be vacuous)")
    for s in _ms:
        hard_fail = True
        print(f"    ✗ spec too weak: ill-formed '{s}' wrongly accepted (discriminating power)")
    for d in _cd:
        hard_fail = True
        print(f"    ✗ NL↔formal drift: {d}")
    if not (_mw or _ms or _cd):
        print(f"    ✓ {len(_faith.WITNESS_LEMMAS)} non-vacuity witnesses present; "
              f"{len(_faith.must_die())} must-die mutants rejected; CEP↔levels consistent")

    # [5e] completeness ratchet (CEP-0056 / R2): the disclosed human/oracle trust-budget residual
    # over the example corpus must NOT grow vs the committed baseline (shrinking is always fine).
    print("\n[5e] Completeness ratchet (CEP-0056 — disclosed residual must not grow):")
    from casl import completeness_ratchet as _ratchet
    _snap = _ratchet.snapshot()
    _n = sum(len(v) for v in _snap.values())
    _rok, _rviol = _ratchet.check()
    for v in _rviol:
        hard_fail = True
        print(f"    ✗ ratchet: {v}")
    if _rok:
        print(f"    ✓ residual stable: {_n} disclosed reliance(s) over {len(_snap)} protocol(s), "
              f"none grown vs baseline (R2)")

    # [6] result
    print("\n" + "-" * 72)
    if hard_fail:
        print("  AUDIT: ✗ FAILED — gap/contradiction above.")
        return 1
    print("  AUDIT: ✓ PASSED — authority anchored, complete (modulo gaps), feature green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
