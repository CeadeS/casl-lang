"""
pflichtenheft.py — machine-readable L2 (Pflichtenheft), derived-from + checked-against L1.

Each PH item: id -> (title, realizes[LH-IDs], artifact, verif-stage, status).
The check enforces the L1↔L2 link (LH-P-002): every L1 requirement is realized by
>=1 PH item, and every PH item cites only existing LH requirements. audit.py runs it,
so the Pflichtenheft can't silently drift from the Lastenheft.

The prose document is docs/requirements.md; this module is its enforced spine.
"""
from __future__ import annotations
from casl import spec

# id -> (title, realizes[LH], artifact, verif, status)
PH = {
    # --- PH-A : architecture / calculus ---
    "PH-A-001": ("Living-system architecture: spec→building blocks→feature→audit",
                 ["LH-G-001", "LH-P-001", "LH-P-002", "LH-P-003", "LH-C-001", "LH-C-002"],
                 "spec.py / kernel.py / authority.py / audit.py", "T", "realized"),
    "PH-A-002": ("Host-language stack: F* (verification B+S) → OCaml (verified core) + Rust (engine)",
                 ["LH-G-003", "LH-C-003"], "fstar/CASL.fst / fstar/ocaml / engine/ (Rust) / docs/mechanization.md", "B", "F* verified (RC=0, 0 admits, 3 metatheorems); OCaml extraction runnable (= verified core); Rust reference engine (engine/, 7 cargo tests, structure-faithful) — verified krml/Eurydice extraction open (Low* mismatch, see C_Mechanisierung)"),
    "PH-A-003": ("MPST backbone + projection pipeline (global→local→prompt)",
                 ["LH-G-001", "LH-F-006"], "kernel.project / prompt / semantics.py", "B", "realized"),
    "PH-A-004": ("Two-stage semantics: static envelope + monitored oracle boundary (operational, `casl run`)",
                 ["LH-G-001", "LH-G-002"], "semantics.py / casl_run.py / kernel.interpreter / docs/semantics-l3.md", "B/M",
                 "realized; end-to-end interpreter executes the protocol (oracle at the boundary, monitor-driven choice, bounded recursion)"),
    "PH-A-005": ("Surface syntax + parser + CLI frontend (`casl check`) → casl_core AST",
                 ["LH-F-006"], "casl_surface.py / casl_check.py / examples/*.casl", "T",
                 "realized; CLI checks .casl protocol-parametrically (own roles/caps/crash), MUST gates → exit 0/1"),
    "PH-A-006": ("Requirement-driven synthesis (NL→spec→code→test→feedback loop)",
                 ["LH-G-004"], "casl_synth.py (RepairMockGenerator/OllamaGenerator) / kernel.synthesis + synthesis_repair", "T",
                 "realized; design oracle behind the casl-check gate; loop is FEEDBACK-DRIVEN: one safety repair (effectful action without approval → casl check rejects → approval-consent gate added → accepted), caused by the verifier diagnosis; mock deterministic, live Gemma optional"),
    "PH-A-007": ("H1: unity of proven artifact ↔ running checker (TCB, single source of truth)",
                 ["LH-C-004"], "fstar extraction ↔ prototype/engine (TBD-004)", "T", "planned (separate architectural effort; krml/Eurydice mismatch)"),
    "PH-A-008": ("Multiparty choreographies ≥4 roles (prototype generic over the role set + by-test)",
                 ["LH-F-008"], "casl_core (parametric roles), kernel.multiparty, metatheory (N roles), examples/secretariat.casl", "T",
                 "realized (PR #24, v0.6.9); projection/merge/realizability parametric, by-test on N roles; proof remains the head fragment (W9)"),
    "PH-A-009": ("Event-driven, long-running sessions (stream = sequence of events, one handler each)",
                 ["LH-F-009"], "casl_core.Rec(stream) + casl_surface (stream/env), spike_hardening.stream_wellformed, kernel.stream(_safe), examples/inbox.casl", "T",
                 "realized (PR #26, v0.7.1); env-driven loop deliberately unbounded, every handler terminates; synchronous — for the buffered variant see PH-A-010"),
    "PH-A-010": ("Async/buffered sessions — encapsulated, opt-in refinement with a deny-by-default gate",
                 ["LH-F-010"], "semantics_async.py (inbox semantics + async_safe/async_class), casl_surface (`async` marker), casl_check (gate), kernel.async_bounded/async_enhancement, examples/async_*.casl, docs/analyses/async.md", "T",
                 "realized (PR #33, v0.8.0); async subtyping undecidable (W16) ⇒ hard barrier: k-bounded reachability certifies bounded + orphan-free + deadlock-free, reports sync equivalence; non-certifiable cases REJECTED. Synchronous proven core untouched; F* mechanization of bounded async = MAY future"),
    "PH-A-011": ("Pipeline-node trichotomy (program | LLM box | verified) + monitored boundary (CASL-IDE phase 4)",
                 ["LH-F-011"], "casl_core.Comm.verified + casl_surface (`verified` marker), spike_pipeline.pipeline_safe, casl_check (MUST gate), kernel.pipeline(_safe), casl_ide (verified ⇒ tier-3 attestation), examples/pipeline_*.casl, docs/ide.md", "T",
                 "realized (v0.12.0); tier 0 checks structure (R1 oracle⊕verified exclusive, R2 oracle monitored, deny-by-default); `verified` trust is NOT granted from the marker but attested by a human in the IDE (tier 3, W17). Opt-in; unchanged without the marker"),

    # --- PH-T : type system / rules ---
    "PH-T-001": ("Agent IR: agents/roles as first-class values",
                 ["LH-F-001"], "casl_core.py / F* gtyp,ltyp", "B", "realized"),
    "PH-T-002": ("Type = session type", ["LH-F-002"], "kernel.project / F* project", "B", "realized"),
    "PH-T-003": ("Promise/Future as a first-class type (resolve-once)",
                 ["LH-F-003"], "kernel.promise / spike_promise.py (Promise[T]); linearity → PH-T-007", "B",
                 "realized (Promise[T] first-class + resolve-once via linearity W6)"),
    "PH-T-004": ("Object = attenuated subtype of an agent kind",
                 ["LH-F-004", "LH-G-003"], "kernel.attenuation / spike_attenuation.py", "B",
                 "realized (tool subset, ttl<=, scope not wider; authority escalation flagged)"),
    "PH-T-005": ("Tools as capabilities + containment (least privilege)",
                 ["LH-F-005", "LH-Q-002"], "kernel.capabilities / spike_capability.py", "B", "realized"),
    "PH-T-006": ("Projection + mergeability (protocol conformance)",
                 ["LH-F-006", "LH-Q-001a"], "kernel.project + merge (hardened, W2)", "B", "realized"),
    "PH-T-007": ("Promise linearity + obligation fulfillment",
                 ["LH-Q-003a", "LH-Q-003b"], "kernel.linearity / spike_hardening.py", "B", "realized"),
    "PH-T-008": ("Recursion + termination via ranking measure",
                 ["LH-Q-009"], "kernel.termination / Rec.measure / spike_hardening.py", "S", "realized"),
    "PH-T-009": ("Capability-ttl safety under recursion",
                 ["LH-Q-010"], "kernel.ttl_safety / spike_hardening.py", "B", "realized"),
    "PH-T-010": ("Crash tolerance as a typed case (on_crash)",
                 ["LH-F-007a"], "kernel.crash_tolerance / spike_resilience.py", "B", "realized"),
    "PH-T-011": ("Approval dominance: irreversible action ⇒ dominated by an approval gate",
                 ["LH-Q-011"], "kernel.approval_safety / spike_approval.py / casl_surface (irreversible/approval) / casl_check (MUST gate)", "B",
                 "realized; surface keywords irreversible/approval + casl check gate (examples/reschedule[_bad].casl)"),
    "PH-T-012": ("R-H1: effect classification as a structured, validated capability field (mode, effectful-by-default) instead of a scope substring",
                 ["LH-Q-012"], "casl_core.Capability (mode) / spike_approval.effectful / kernel.effect_classification / casl_surface / examples/attacks/{rw_naming,delete_readonly}", "B",
                 "realized (PR #20); mode read|write|admin, default write; attacks rw_naming/delete_readonly rejected"),
    "PH-T-013": ("R-N1: per-gate disclosure + specific consent (on_approval bound to the disclosed action)",
                 ["LH-Q-013"], "casl_run.GateDisclosure/on_approval / kernel.gate_disclosure / casl_check (interactive per-gate prompt)", "M",
                 "realized (PR #21); disclosure = message + concrete effect action, consent per gate; `W15` fixed"),
    "PH-T-014": ("H3: runtime tool mediation/confinement (broker denies tools not declared at runtime)",
                 ["LH-Q-014"], "casl_run._tool_allowed (interposition, `tool_denied`), kernel.tool_broker", "M",
                 "realized (PR #22, v0.6.7); checks against the runtime capmap, not only statically; `W12` fixed"),

    # --- PH-V : verification / test ---
    "PH-V-001": ("Data contracts statically via SMT (Z3)",
                 ["LH-Q-004"], "kernel.contract_smt / spike_smt_contract.py / F* retry_safe", "S", "realized"),
    "PH-V-002": ("Runtime monitor + blame at the oracle boundary (with a real LLM oracle)",
                 ["LH-Q-005", "LH-G-002"], "kernel.monitor / kernel.oracle_boundary / spike_monitor_test.py / oracle.py", "M",
                 "realized; direction A in production: oracle.py binds the Ollama endpoint, monitor checks contract+blame/refusal (live verdict ok); mock in the audit (offline)"),
    "PH-V-003": ("Refusal monitor (refusal as a typed outcome)",
                 ["LH-F-007b"], "kernel.refusal_monitor / spike_resilience.py", "M", "realized"),
    "PH-V-004": ("Testability from structure: dual mock + property generator",
                 ["LH-Q-006"], "kernel.tests / spike_monitor_test.py", "T", "realized"),
    "PH-V-005": ("Metatheory: correspondence/fidelity/deadlock-freedom + concurrency confluence",
                 ["LH-Q-001a", "LH-Q-001b", "LH-Q-001c", "LH-Q-001d"],
                 "metatheory.py (by-test, full reachability) / F*: deadlock_free + fidelity_complete + fidelity_sound (head event) + cgstep/diamond_indep PROVEN (0 admits)", "B",
                 "F*-proven (0 admits): head fragment + 4 roles; permutation/confluence (diamond_indep) machine-checked; full inductive fidelity under permutation by-test (Direction C)"),
    "PH-V-006": ("MPST⇔MSC equivalence (adversarial hardening battery)",
                 ["LH-Q-001a"], "harden_equivalence.py (10 cases)", "T", "realized"),
    "PH-V-007": ("Living audit + traceability (RTM, authority chain)",
                 ["LH-P-001", "LH-P-002", "LH-P-003"], "audit.py / authority.py", "T", "realized"),
    "PH-V-008": ("Semantic check (metamorphic / LLM judge)",
                 ["LH-Q-007"], "kernel.semantic_judge / spike_judge.py (MockJudge + OllamaJudge)", "T",
                 "realized (metamorphic battery over oracle scenarios + content judge; mock deterministic, live Gemma)"),
    "PH-V-009": ("Capability revocation + refresh at runtime (lifecycle)",
                 ["LH-Q-008"], "spike_hardening.ttl_safety_check (stream refresh), casl_run (revoked → tool_denied), kernel.revocation", "M",
                 "realized (PR #28, v0.7.3); refresh per stream iteration (inbox ttl-safe) + runtime revoke at the broker"),
    "PH-V-010": ("Standards conformance documented (29148/DIN 69901-5/VDI-VDE 3694)",
                 ["LH-P-004"], "CASL.md §2 / this Pflichtenheft", "T", "realized"),
    "PH-V-011": ("Code↔commit↔requirement traceability + versioning discipline",
                 ["LH-P-005", "LH-C-001"], "trace.py / kernel.versioning / CONTRIBUTING.md", "T",
                 "realized (trace.py: req→commits, --blame line→commit→req, verification; versioning building block offline)"),
    "PH-V-012": ("H4: out-of-band cost metering (oracle `cost` = unchecked claim; monitor checks the measured value)",
                 ["LH-Q-015"], "oracle.OracleResult.measured_cost/metered_cost (server usage), oracle_step/casl_run, kernel.cost_metering", "M",
                 "realized (PR #23, v0.6.8); underreport detected by the meter (blame A); `W13` fixed"),
    "PH-V-013": ("Concurrency grounded: independence + swap rule; correspondence/confluence by-test; non-certifiable concurrency is rejected (deny-by-default)",
                 ["LH-Q-001d"], "semantics.step_global (swap), semantics.correspondence_class, casl_check (gate), kernel.concurrency, examples/concurrent.casl", "B",
                 "realized (PR #25, v0.7.0); soundness global⊆config by-test over ≥4 roles; F* mechanization of permutation/confluence open (Direction C, W9)"),

    # --- PH-AT : artifact-trust layer (P10 — accountability where proof is impossible; CEP-0057) ---
    "PH-AT-001": ("Artifact as a declared, governed unit (manifest + structured kind + typed seam binding)",
                  ["LH-F-012", "LH-F-013"], "src/casl/project.py (Manifest/Artifact) / src/casl/seam.py (implements<->site) / kernel.artifact_manifest + typed_seam", "T",
                  "realized (feat/artifact-trust + feat/typed-seam; CEP-0058/0059/0074)"),
    "PH-AT-002": ("Dependency burden ledger — pinned + owned, deny-by-default (imports are carried liabilities)",
                  ["LH-Q-020"], "src/casl/dependency.py / kernel.dependency_burden / deps.lock", "M",
                  "realized (feat/artifact-trust; CEP-0069)"),
    "PH-AT-003": ("Project-wide line traceability + blame + ownership-fixed trace regime",
                  ["LH-P-006", "LH-P-007", "LH-P-009"], "src/casl/traceability.py / project.py (trace regime follows ownership) / kernel.line_traceability + trace_regime / casl trace|blame", "T",
                  "realized (feat/artifact-trust; CEP-0062/0063/0064)"),
    "PH-AT-004": ("Human-identity attestation — content-bound, non-self, signed AS a human",
                  ["LH-Q-016", "LH-Q-017", "LH-Q-018"], "src/casl/attestation.py (GPG/SSH-signed commit; plaintext rejected) / kernel.human_attestation / attestations/*.json", "M",
                  "realized (feat/artifact-trust; CEP-0065/0066/0067)"),
    "PH-AT-005": ("Tier-0 obligation gate + effective grade (weakest-link, per-requirement, per-flow)",
                  ["LH-G-006", "LH-Q-019"], "src/casl/obligation_gate.py (gate + grade_by_requirement) / src/casl/grade_flow.py (flow-graph) / kernel.obligation_gate + grade_flow / casl gate|flow", "M",
                  "realized (feat/artifact-trust + feat/grade-flow; CEP-0061/0068/0070)"),
    "PH-AT-006": ("Artifact observability — capture each oracle call's prompt→response for human review",
                  ["LH-G-005"], "src/casl/observability.py (OracleObservation) / run.py capture / casl run|observe / kernel.observability", "M",
                  "realized (feat/observability; CEP-0060 Final)"),
}


def check():
    reqs = set(spec.REQS)
    bad_refs = [(p, l) for p, (_, lhs, _, _, _) in PH.items() for l in lhs if l not in reqs]
    realized = {l for (_, lhs, _, _, _) in PH.values() for l in lhs}
    uncovered = [r for r in reqs if r not in realized]
    ok = not bad_refs and not uncovered
    return ok, {"n_ph": len(PH), "bad_refs": bad_refs, "uncovered": uncovered}


if __name__ == "__main__":
    ok, d = check()
    print("Pflichtenheft check:", "OK" if ok else "FAIL", "—", d["n_ph"], "PH items")
    if d["bad_refs"]:
        print("  invalid LH references:", d["bad_refs"])
    if d["uncovered"]:
        print("  NOT realized by any PH:", d["uncovered"])
