# CASL — Design Specification (L2 / SyRS + SRS)

**Project:** CASL (*Choreographic Agent Specification Language*)
**Document type:** Design specification (L2) — realization requirements per requirements-specification requirement
**Version:** `0.2.5` (SemVer 2.0.0) · **Status:** Draft · **Date:** 2026-06-18
**Attachment:** `CASL.md` (L1 requirements specification, v0.1.18) — normatively superordinate

> Per DIN 69901-5 / VDI/VDE 3694, the design specification contains the realization requirements developed by the **contractor** on the basis of the requirements specification. Each `PH` item realizes **≥1** `LH` requirement (bidirectional traceability, `LH-P-002`) and refers to the **real artifact**. This mapping is machine-enforced: `prototype/pflichtenheft.py` + `audit.py` (Section [3c]) verify that every LH requirement is realized by ≥1 PH.

---

## 1. Purpose & Scope

This document refines the L1 requirements specification (`CASL.md`) into concrete realization requirements: **how** each requirement is implemented, with which artifact, and at which provability level (B/S/M/T). It covers the core realized today — prototype `prototype/`, machine-verified F* core `fstar/CASL.fst` (RC=0, **0 admits**, runnable as OCaml extraction), Rust reference engine `engine/`, surface CLI `casl check`, and the production oracle boundary (direction A, `oracle.py`) — as well as the remaining planned realizations (capability revocation, semantic judge test).

**ID scheme** (from `CASL.md` §4.2): `PH-A` architecture/calculus · `PH-T` type system/rule · `PH-V` verification/test. Each `PH` ID references ≥1 `LH` ID.

**Status values:** *realized* (artifact exists, green in the audit) · *scaffold* (code present, to be verified locally — F*) · *partial* (model present, full build-out pending) · *planned* (not yet begun).

---

## 2. References

| Doc | Role |
|---|---|
| `CASL.md` | L1 requirements specification (normative), RTM upstream |
| `docs/semantics-l3.md` | L3 formal rules (grammar, projection, reduction, metatheorems) |
| `docs/mechanization.md` | Host-language stack F*+Rust, Python↔F* mapping |
| `prototype/` | runnable reference core + living audit |
| `fstar/CASL.fst` | F* verification core |

---

## 3. Realization Architecture (`PH-A`)

The realization follows the principle **"all authority from the specification"**: `spec.py` is the single source of authority, the kernel consists of authority-tagged building blocks, the feature `compile_choreography` composes them, and `audit.py` enforces the chain.

| PH-ID | Title | realizes | Verif | Artifact | Status |
|---|---|---|:--:|---|---|
| `PH-A-001` | Living-system architecture (spec→building blocks→feature→audit) | `LH-G-001`,`LH-P-001/002/003`,`LH-C-001/002` | T | `spec/kernel/authority/audit.py` | realized |
| `PH-A-002` | Host-language stack: F* (B+S) → OCaml (verified core) + Rust (engine) | `LH-G-003`,`LH-C-003` | B | `fstar/CASL.fst` (0 admits), `fstar/ocaml`, `engine/`, `docs/mechanization.md` | realized (verified krml/Eurydice extraction pending, Low\* mismatch) |
| `PH-A-003` | MPST backbone + projection pipeline (global→local→prompt) | `LH-G-001`,`LH-F-006` | B | `kernel.project/prompt`, `semantics.py` | realized |
| `PH-A-004` | Two-stage semantics: static hull + monitored oracle boundary (operational, `casl run`) | `LH-G-001`,`LH-G-002` | B/M | `semantics.py`, `casl_run.py`, `kernel.interpreter`, `docs/semantics-l3.md` | realized (end-to-end interpreter) |
| `PH-A-005` | Surface syntax + parser + CLI frontend (`casl check`) → `casl_core` AST | `LH-F-006` | T | `casl_surface.py`, `casl_check.py`, `examples/*.casl` | realized (protocol-parametric, exit 0/1) |
| `PH-A-006` | Requirement-driven synthesis (NL→spec→code→test→feedback loop) | `LH-G-004` | T | `casl_synth.py`, `kernel.synthesis`, `casl synth` | realized (draft oracle behind `casl check` gate, repair loop; mock deterministic, live Gemma) |
| `PH-A-007` | H1: unity of proven artifact ↔ running checker (TCB, single source of truth) | `LH-C-004` | T | F* extraction ↔ `prototype`/`engine` (`TBD-004`) | planned (PR #23, `W11`) |

---

## 4. Type System / Rules (`PH-T`)

| PH-ID | Title | realizes | Verif | Artifact | Status |
|---|---|---|:--:|---|---|
| `PH-T-001` | Agent IR: agents/roles as first-class values | `LH-F-001` | B | `casl_core`, F* `gtyp/ltyp` | realized |
| `PH-T-002` | Type = session type | `LH-F-002` | B | `kernel.project`, F* `project` | realized |
| `PH-T-003` | Promise/future as a first-class type (resolve-once) | `LH-F-003` | B | `kernel.promise`, `spike_promise` (`Promise[T]`) | realized (first-class + resolve-once via W6) |
| `PH-T-004` | Object = attenuated subtype of an agent kind | `LH-F-004`,`LH-G-003` | B | `kernel.attenuation`, `spike_attenuation` | realized (tool subset, `ttl<=`, scope; escalation flagged) |
| `PH-T-005` | Tools as capabilities + containment (least privilege) | `LH-F-005`,`LH-Q-002` | B | `kernel.capabilities`, `spike_capability` | realized |
| `PH-T-006` | Projection + mergeability (protocol conformance) | `LH-F-006`,`LH-Q-001a` | B | `kernel.project`+`merge` (hardened, W2) | realized |
| `PH-T-007` | Promise linearity + obligation fulfillment | `LH-Q-003a/b` | B | `kernel.linearity`, `spike_hardening` | realized |
| `PH-T-008` | Recursion + termination via ranking measure | `LH-Q-009` | S | `kernel.termination`, `Rec.measure` | realized |
| `PH-T-009` | Capability `ttl` safety under recursion | `LH-Q-010` | B | `kernel.ttl_safety` | realized |
| `PH-T-010` | Crash tolerance as a typed case (`on_crash`) | `LH-F-007a` | B | `kernel.crash_tolerance`, `spike_resilience` | realized |
| `PH-T-011` | Approval dominance: **effectful** action (irreversible OR non-`readonly` capability, deny-by-default) ⇒ dominated by approval gate via `consent` branch; consent not over loops. **Static** (lint) **+ runtime** (default-deny, `--approve`) | `LH-Q-011` | B | `kernel.approval_safety`, `kernel.redteam_attacks`, `kernel.runtime_approval`, `spike_approval`, `casl_run`, `casl_surface`/`casl_check` (gate), `examples/attacks/` | realized; red-team v0.1.28 (C1/C2/M2) + C3 runtime v0.6.4; H1/H3 (`W11`/`W12`) documented-as-open |
| `PH-T-012` | R-H1: effect classification as a structured, validated `mode` field (read\|write\|admin, default `write`) instead of scope substring | `LH-Q-012` | B | `casl_core.Capability.mode`, `spike_approval.effectful`, `kernel.effect_classification`, `casl_surface`, `examples/attacks/{rw_naming,delete_readonly}` | realized (PR #20, v0.6.5); `W14` fixed |
| `PH-T-013` | R-N1: per-gate disclosure + specific consent (`on_approval` bound to the disclosed action) | `LH-Q-013` | M | `casl_run.GateDisclosure`/`on_approval`, `kernel.gate_disclosure`, `casl_check` (interactive per-gate prompt) | realized (PR #21, v0.6.6); disclosure = message + concrete effect action; `W15` fixed |
| `PH-T-014` | H3: runtime tool mediation/confinement (broker refuses tools not declared at runtime) | `LH-Q-014` | M | `casl_run._tool_allowed` (interposition, `tool_denied`), `kernel.tool_broker` | realized (PR #22, v0.6.7); checks against the runtime capmap; `W12` fixed |

---

## 5. Verification / Test (`PH-V`)

| PH-ID | Title | realizes | Verif | Artifact | Status |
|---|---|---|:--:|---|---|
| `PH-V-001` | Data contracts statically via SMT (Z3) | `LH-Q-004` | S | `kernel.contract_smt`, F* `retry_safe` | realized |
| `PH-V-002` | Runtime monitor + blame at the oracle boundary (with a real LLM oracle) | `LH-Q-005`,`LH-G-002` | M | `kernel.monitor`, `kernel.oracle_boundary`, `kernel.branch_contracts`, `oracle.py`, `spike_monitor_test` | realized (direction A in production: Ollama live, mock in the audit; W7: branch contracts enforced) |
| `PH-V-003` | Refusal monitor (refusal as a typed exit) | `LH-F-007b` | M | `kernel.refusal_monitor`, `spike_resilience` | realized |
| `PH-V-004` | Testability from structure: dual mock + property generator | `LH-Q-006` | T | `kernel.tests`, `spike_monitor_test` | realized |
| `PH-V-005` | Metatheory: correspondence/fidelity/deadlock-freedom | `LH-Q-001a/b/c` | B | `metatheory.py`; F* `preservation_full`,`fidelity_*`,`deadlock_free` **proven (0 admits)** | realized (F* machine-proven; subject reduction FULL incl. recursion; progress/fidelity head fragment; 4 roles) |
| `PH-V-006` | MPST⇔MSC equivalence (adversarial hardening battery) | `LH-Q-001a` | T | `harden_equivalence.py` (10 cases) | realized |
| `PH-V-007` | Living audit + traceability (RTM, authority chain) | `LH-P-001/002/003` | T | `audit.py`, `authority.py` | realized |
| `PH-V-008` | Semantic check (metamorphic / LLM judge) | `LH-Q-007` | T | `kernel.semantic_judge`, `spike_judge` (MockJudge + OllamaJudge) | realized (metamorphic battery + content judge; mock/live) |
| `PH-V-009` | Capability revocation at runtime | `LH-Q-008` | M | planned (`TBR-002`) | planned |
| `PH-V-010` | Standards conformance documented | `LH-P-004` | T | `CASL.md` §2 / this document | realized |
| `PH-V-011` | Code↔commit↔requirement traceability + versioning discipline | `LH-P-005`,`LH-C-001` | T | `trace.py`, `kernel.versioning`, `CONTRIBUTING.md` | realized (`trace.py`: req→commits, `--blame` line→commit→req, verification) |
| `PH-V-012` | H4: out-of-band cost metering (oracle `cost` = unchecked claim; monitor checks the measured value) | `LH-Q-015` | M | `oracle.measured_cost`/`metered_cost` (server usage), `oracle_step`/`casl_run`, `kernel.cost_metering` | realized (PR #23, v0.6.8); underreport detected by the meter (blame A); `W13` fixed |

---

## 6. Traceability L1 → L2 (excerpt, bidirectional)

Fully machine-derivable from `pflichtenheft.py`. Every L1 requirement is realized by ≥1 PH (enforced by `audit.py` [3c]):

| L1 | → PH | L1 | → PH |
|---|---|---|---|
| `LH-G-002` | PH-A-004, PH-V-002 | `LH-Q-002` | PH-T-005 |
| `LH-F-002` | PH-T-002 | `LH-Q-003a/b` | PH-T-007 |
| `LH-F-005` | PH-T-005 | `LH-Q-004` | PH-V-001 |
| `LH-F-006` | PH-A-003, PH-T-006 | `LH-Q-005` | PH-V-002 |
| `LH-F-007a` | PH-T-010 | `LH-Q-006` | PH-V-004 |
| `LH-F-007b` | PH-V-003 | `LH-Q-001a/b/c` | PH-T-006, PH-V-005/006 |
| `LH-Q-009` | PH-T-008 | `LH-Q-010` | PH-T-009 |
| `LH-P-001/002/003` | PH-A-001, PH-V-007 | `LH-C-001/002` | PH-A-001 |

---

## 7. Open Realization Items

- **`PH-V-009`** (`LH-Q-008`, revocation): research frontier `TBR-002`.
- **verified Rust extraction:** the ADT/string core does not fit into the Low\* model of krml/Eurydice → OCaml carries the verified core, Rust is the (cargo-tested) engine; verified Rust extraction via Pulse remains future work (`docs/mechanization.md`).
- **n-ary choice** (the F* core uses binary choice) and **data layer in the operational semantics** — L3 deepening.

---

## 8. Provability Levels (as of v0.2.1)

| Level | realized | open/planned |
|---|---|---|
| **B** (statically proven) | projection, mergeability, capability containment, linearity, ttl safety, crash tolerance (prototype); **F* metatheory machine-proven (0 admits)**, runnable as OCaml; Rust engine cargo-tested | n-ary choice in the F* core; verified Rust extraction (Pulse) |
| **S** (SMT) | data contracts, termination ranking (Z3); F* `retry_safe` (discharged by Z3) | — |
| **M** (monitor) | blame at the oracle boundary, refusal; **real LLM oracle live (`oracle.py`)** | revocation (`PH-V-009`) |
| **T** (test) | property/dual mock, equivalence battery, living audit, surface CLI `casl check`, semantic judge (`PH-V-008`) | — |

*End of v0.2.1.*
