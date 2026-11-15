# CASL — Coarse Specification & Requirements Specification

**Project:** Agent-oriented, choreographic specification language
**Working title:** CASL (*Choreographic Agent Specification Language*) — see `TBR-001`
**Document type:** Coarse specification (L0) + requirements specification / Stakeholder Requirements (L1)
**Version:** `0.1.45` (SemVer 2.0.0)
**Status:** Draft
**Date:** 2026-06-15
**Language:** German (normative); technical terms (Promise, Interface, Capability, Contract, Blame) remain in English and are defined in §3.

> This document is *docs-as-code*: plain text (Markdown), versioned in Git, tagged according to SemVer. Every change is traceable via Git commit + SemVer tag + requirement ID (`LH-P-003`). It also serves as a **process model** for bootstrapping the language (Appendix A).

---

## Document Control

### Version History

| Version | Date       | Author | Change                                                                                    | Baseline |
|--------:|------------|--------|-------------------------------------------------------------------------------------------|:--------:|
| 0.1.0   | 2026-06-15 | —     | Initial draft: coarse specification + requirements-specification skeleton from prior work  | no       |
| 0.1.1   | 2026-06-15 | —     | Review incorporation: T1–T5 legend, mandatory attributes/rationale, source correction (§9), tetrad, requirement splits, full RTM coverage | yes (candidate) |
| 0.1.2   | 2026-06-15 | —     | `TBR-003` closed (T1–T5 confirmed); bootstrap strategy "parallel prototyping spikes" added (Appendix A, `TBD-003/004/006`) | yes (candidate) |
| 0.1.3   | 2026-06-15 | —     | Language strategy added as 3 axes in `TBD-004`/Appendix A (spike=Python, engine=Rust/OCaml, proof=Lean 4/F*) | yes (candidate) |
| 0.1.4   | 2026-06-15 | —     | Principles audit: Capability containment (`LH-Q-002`) prototyped; living checker `prototype/audit.py`; new open items `TBD-007/008` | yes (candidate) |
| 0.1.5   | 2026-06-15 | —     | Crash/Refusal building blocks (`LH-F-007a` B / `LH-F-007b` M) prototyped → thesis T3 fully covered, `W3` resolved | yes (candidate) |
| 0.1.6   | 2026-06-15 | —     | `W2` hardened: adversarial MPST/MSC battery (10 cases); `merge` recursive + realizability sharpened to the first divergence → equivalence validated | yes (candidate) |
| 0.1.7   | 2026-06-15 | —     | A/B-driven hardening W4/W5/W6: building blocks `linearity` (`LH-Q-003a/b`), `termination` (`LH-Q-009`), `ttl_safety` (`LH-Q-010`); `TBD-007/008` closed | yes (candidate) |
| 0.1.8   | 2026-06-15 | —     | L3 started: operational semantics + metatheory-by-test (correspondence/deadlock freedom); `TBD-003` closed (MPST backbone); `docs/semantics-l3.md` | yes (candidate) |
| 0.1.9   | 2026-06-15 | —     | `TBD-004` closed: **F*** (verification B+S, extraction→OCaml) + **Rust** (engine via Pulse/KaRaMeL); mechanization scaffold `CASL.fst` + `docs/mechanization.md` | yes (candidate) |
| 0.1.10  | 2026-06-16 | —     | RTM §7 connected to real artifacts (prototype building blocks + F*); `audit.py` [3b] requirement→building block (mechanized); `run.sh` (log bridge) | yes (candidate) |
| 0.1.11  | 2026-06-16 | —     | L2 design specification created (`docs/requirements.md` v0.2.0, 24 PH items); LH→PH enforced mechanically (`pflichtenheft.py`, `audit.py` [3c]); RTM L2 column linked | yes (candidate) |
| 0.1.12  | 2026-06-16 | —     | **F* verified `CASL.fst` mechanically (RC=0)** on the target machine via Desktop Commander — kernel proven, 3 metatheorems still `admit`; surface parser `casl_surface.py` (`TBD-006`, round-trip == G_OK) + `PH-A-005` | yes (candidate) |
| 0.1.13  | 2026-06-16 | —     | F* metatheorems: `deadlock_free` + `fidelity_complete` **proven mechanically** (via DC); `fidelity_sound` = justified `admit` — soundness gap `W9` exposed by F* (the 250-case random test missed it), permutation rule needed | yes (candidate) |
| 0.1.14  | 2026-06-16 | —     | **All 3 F* metatheorems proven (0 `admit`)**: `fidelity_sound` via `cstep` inversion; `W9` clarified — soundness holds in the 3-role calculus (≥4 roles: permutation rule open) | yes (candidate) |
| 0.1.15  | 2026-06-16 | —     | **CLI frontend `casl check`** (`casl_check.py`): checks `.casl` protocol-parametrically against the file's *own* roles/caps/crash; MUST gates (well-formedness, least privilege, linearity) → Exit 0/1, SHOULD hints (termination/ttl/crash). Back end (kernel + spikes) decoupled from example globals (backward compatible, audit green). `TBD-006` realized; `PH-A-005` extended | yes (candidate) |
| 0.1.16  | 2026-06-16 | —     | **Rust reference engine** (`engine/`): hand-written crate mirrors the verified kernel structurally (`project`/hardened `merge`/well-formedness/capabilities), 7 `cargo` tests pin verdicts to F*/Python, `cargo run` = same projections as `casl check`. Finding: krml/Eurydice (Low\*) does not fit the string/ADT kernel → OCaml carries the verified kernel, Rust = engine (`TBD-004`); `PH-A-002` updated | yes (candidate) |
| 0.1.17  | 2026-06-16 | —     | **Direction A: oracle boundary productive** (`oracle.py`): LLM as a real nondeterministic oracle at the monitored edge — agent A produces a real `Draft` response, monitor checks the contract → ok/Blame A/Refusal. Verified live against Ollama (`.env` endpoint, OpenAI-compatible, model `granite3.1-moe:3b`); building block `kernel.oracle_boundary` (mock, offline) in the audit. `PH-V-002` extended | yes (candidate) |
| 0.1.18  | 2026-06-16 | —     | **Docs sync** (consistency review): "admit→proven" updated everywhere — `CASL.fst` comments, §7 RTM (`[proven, 0 admits]`), `docs/requirements.md` v0.2.1 (+`PH-A-005`, `PH-A-002`/`PH-V-002`/`PH-V-005` current, attachment→v0.1.18); § note "L2 created"; `oracle.py` default model = live-validated `granite3.1-moe:3b`. No logic change (all gates green: F* RC=0, audit exit 0, 7 cargo tests) | yes (candidate) |
| 0.1.19  | 2026-06-17 | —     | **`casl run` — operational end-to-end interpreter** (`casl_run.py`): checks first (MUST gate), then runs the global type — oracle at the boundary, monitor-driven `choice` (ok→terminating, violation/refusal→loop), `max_loops` bound, execution trace. Building block `kernel.interpreter` (mock `retry_then_ok`, deterministic) in the audit (17 building blocks); `casl check`/`casl run` one frontend; `PH-A-004` extended | yes (candidate) |
| 0.1.20  | 2026-06-17 | —     | **Approval invariant** (onion layer 1, `TBD-V-003`): new requirement **`LH-Q-011`** "irreversible ⇒ dominated by approval gate" (static, level B). Core flags `irreversible`/`approval`; checker `spike_approval` + building block `kernel.approval_safety` (18 building blocks); `PH-T-011`; audit on fixtures `G_RESCHED_OK/BAD`. `TBD-V-002` = strict. Surface keywords + branch contracts (`W7`) to follow | yes (candidate) |
| 0.1.21  | 2026-06-17 | —     | **Approval invariant in the language** + **`W7` resolved**: surface keywords `irreversible`/`approval` (parser), `casl check` enforces `LH-Q-011` as a MUST gate (`examples/reschedule.casl` ✓ / `reschedule_bad.casl` ✗ Exit 1); branch contracts (`len(reason)>0`) enforced via `kernel.branch_contracts` (nonempty monitor + property) (19 building blocks) | yes (candidate) |
| 0.1.22  | 2026-06-17 | —     | **MUST gap `LH-F-004` closed** (+ SHOULD `LH-G-003`): object = attenuated subtype of an agent kind — `spike_attenuation` + building block `kernel.attenuation` (tool subset, `ttl<=`, scope not wider; authority escalation flagged), `PH-T-004` realized (20 building blocks), removed from accepted gaps | yes (candidate) |
| 0.1.23  | 2026-06-17 | —     | **MUST gap `LH-F-003` closed**: Promise/Future as a first-class type — `spike_promise` (`Promise[T]`) + building block `kernel.promise` (resolve-once via linearity W6); `PH-T-003` realized (21 building blocks), removed from accepted gaps | yes (candidate) |
| 0.1.24  | 2026-06-17 | —     | **Traceability tool + last MUST gap `LH-C-001`**: new requirement **`LH-P-005`** (code↔commit↔requirement). `prototype/trace.py` (req→commits, `--blame` line→commit→req, verification of unknown IDs, `--json`) + building block `kernel.versioning` (offline) + `CONTRIBUTING.md` convention; `PH-V-011` (22 building blocks). `LH-C-001` removed from accepted gaps → **all MUST satisfied** | yes (candidate) |
| 0.1.25  | 2026-06-17 | —     | **Synthesis loop (vision core)**: new requirement **`LH-G-004`** — NL→spec→code→test→feedback. `casl_synth` (`casl synth`): draft oracle (mock + live Gemma) behind the `casl check` gate, repair loop (broken→corrected), derived tests; building block `kernel.synthesis` (23 building blocks), `PH-A-006` | yes (candidate) |
| 0.1.26  | 2026-06-17 | —     | **SHOULD `LH-Q-007` realized**: semantic checking — `spike_judge` (metamorphic battery over oracle scenarios + content judge: `MockJudge` deterministic, `OllamaJudge` live) + building block `kernel.semantic_judge` (24 building blocks); `PH-V-008` realized, removed from accepted gaps | yes (candidate) |
| 0.1.27  | 2026-06-17 | —     | **Process SHOULD `LH-P-004` + `LH-C-003` realized**: building blocks `kernel.norms` (CASL.md cites 29148/69901-5/3694) + `kernel.review` (approval gate in CONTRIBUTING.md), 26 building blocks. → **all MUST and SHOULD satisfied**; only accepted gap: MAY `LH-Q-008` (revocation, `TBR-002`) | yes (candidate) |
| 0.1.28  | 2026-06-17 | —     | **Red-team hardening (`docs/reviews/redteam-review-v0.1.27.md`)**: approval keystone `LH-Q-011` hardened against C1/C2/M2 — effect bound to capability (deny-by-default), only the `consent` branch is exempt, no consent across loops. `examples/attacks/` (deny branch/untagged effect/approve-once-spam) as a CI gate (`kernel.redteam_attacks`, 27 building blocks). `LH-Q-001b` reach stated honestly. C3 (runtime human)/H1/H3 documented as follow-up work | yes (candidate) |
| 0.1.29  | 2026-06-17 | —     | **C3 closed — runtime approval (`LH-Q-011` runtime side)**: `casl run` enforces an external decision at the approval gate (default-deny, `--approve`/callback), no structural default; without approval no effect branch is entered. Building block `kernel.runtime_approval` (28 building blocks). Residual red-team risks registered as tracked tensions `W10`–`W13` (C3 resolved; H1/H3/H4 open-documented). `docs/vision.md` §5 "safe-by-lint instead of by-construction" + `TBD-V-003` completed | yes (candidate) |
| 0.1.30  | 2026-06-17 | —     | **Fix-plan requirements created (traceability before implementation)** following `docs/reviews/redteam-review-v0.1.28.md`: `LH-Q-012` (R-H1, MUST), `LH-Q-013` (R-N1), `LH-Q-014` (H3), `LH-Q-015` (H4), `LH-C-004` (H1) as tracked issues — each with a requirement + `ACCEPTED_GAPS` + `PH` item (planned) + tension (`W14`/`W15` new) + RTM row. Audit green (39 requirements, 6 tracked gaps, 33 PH). Re-test confirms C1/C2/C3/M2 closed; R-H1 (effect classifier leaky/spoofable) as the top follow-up work | yes (candidate) |
| 0.1.31  | 2026-06-17 | —     | **R-H1 resolved — effect classification structured (`LH-Q-012`)**: `Capability.mode` (read\|write\|admin, default `write`); `effectful()` reads `mode` instead of a scope substring (only `read` is exempt, deny-by-default); building block `kernel.effect_classification`; surface keyword `mode`. Attacks `rw_naming` (`cal:read-write`) + `delete_readonly` (`db:readonly` on purge) in the corpus → rejected. Existing read-only caps migrated to `mode read` (round-trip holds). 29 building blocks, `W14` resolved | yes (candidate) |
| 0.1.32  | 2026-06-18 | —     | **R-N1 resolved — per-gate disclosure (`LH-Q-013`)**: `casl_run.GateDisclosure` discloses, per gate, the triggering message + the concrete effectful action of the consent branch; `on_approval(disclosure)` decides per gate (building block `kernel.gate_disclosure`); CLI per-gate prompt (default-deny without a TTY), `--approve` now only a demo blanket. 30 building blocks, `W15` resolved. Remaining: H3/`W12`, H1/`W11`, H4/`W13` | yes (candidate) |
| 0.1.33  | 2026-06-18 | —     | **H3 resolved — runtime tool broker (`LH-Q-014`)**: `casl_run._tool_allowed` interposes before every tool use and denies tools not carried at runtime (`tool_denied`) — checks against the runtime capmap, not only statically (also catches attenuated objects). Building block `kernel.tool_broker`. 31 building blocks, `W12` resolved. Remaining: H1/`W11`, H4/`W13` | yes (candidate) |
| 0.1.34  | 2026-06-18 | —     | **H4 resolved — out-of-band cost metering (`LH-Q-015`)**: `OracleResult.measured_cost` (live: server `usage`; mock: true value); the monitor checks `metered_cost(out)` instead of the oracle's claim, a misreport is flagged. Building block `kernel.cost_metering` (`underreport`). 32 building blocks, `W13` resolved. **All red-team findings v0.1.27/.28 closed** except MAY: `LH-Q-008` (revocation) + `LH-C-004`/H1 (TCB unification, `TBD-004`) | yes (candidate) |
| 0.1.35  | 2026-06-18 | —     | **Expressiveness: multiparty ≥4 roles (`LH-F-008`)** toward the target vision. `semantics.roles_of`/`config` parametric over the role set (3-role hardcoding resolved); `examples/secretariat.casl` (U/S/K/M, with approval gate) accepted + by-test correspondent (building block `kernel.multiparty`); `metatheory` battery generalized to N roles. 33 building blocks. `LH-F-009` (stream/event sessions) as a tracked issue (PR #25). `W9`: ≥4-role concurrency (permutation rule) remains open, now substantiated by-test | yes (candidate) |
| 0.1.36  | 2026-06-18 | —     | **Grounded concurrency (`LH-Q-001d`)**: swap rule in `step_global` (role-disjoint actions take precedence); `semantics.correspondence_class` → `certified`/`incomplete`/`unsound`; the `casl check` gate rejects non-certifiable concurrency (deny-by-default). Soundness (global ⊆ config) by-test without exception (≥4-role battery, 0 unsound); the diamond/confluence preserves all path invariants. `examples/concurrent.casl`; building blocks `kernel.concurrency`/`concurrency_certified`. 35 building blocks. `W9` from "open" → grounded by-test; only F\* mechanization (Direction C) open | yes (candidate) |
| 0.1.37  | 2026-06-18 | —     | **Streams/events (`LH-F-009`, synchronous/variant A)**: construct `stream Name { … }` + `env` role; deliberately unbounded, event-driven loop with **terminating handlers** (exempt from the termination obligation, but with env-driven dispatch choice + handler termination as a MUST gate, deny-by-default). `spike_hardening.stream_wellformed`, building blocks `kernel.stream`/`stream_safe`, `examples/inbox.casl` (inbox with approval handler). 37 building blocks. Async buffer semantics = later extension; only MAY `LH-Q-008`/`LH-C-004` still open | yes (candidate) |
| 0.1.38  | 2026-06-18 | —     | **F\* Direction C — permutation/confluence mechanized (`W9`)**: `CASL.fst` extended by a 4th role `RD` (concurrency non-vacuous); `cgstep` (permutation/swap rule) + lemma `diamond_indep` **proven mechanically** (F\* 2026.03.24, **0 admits**): independent (role-disjoint) actions commute. `fidelity_sound` honestly scoped to the head event. `docs/mechanization.md` updated. W9: from "by-test" → diamond F\*-proven; the rest (full inductive fidelity under permutation) Direction C, by-test | yes (candidate) |
| 0.1.39  | 2026-06-18 | —     | **Capability revocation & refresh (`LH-Q-008`, MAY realized)**: `ttl_safety_check` stream-aware — a `stream` loop re-grants per iteration, so a finite `ttl` in the unbounded inbox is ttl-safe (`inbox.casl` without WARN); `casl run --`/`revoked` set → tool broker denies revoked tools (`tool_denied`). Building block `kernel.revocation` (38 building blocks). **All MUST/SHOULD + all but one MAY gap satisfied** — only open: `LH-C-004`/H1 TCB unification (krml/Eurydice, `TBD-004`) | yes (candidate) |
| 0.1.40  | 2026-06-18 | —     | **Synthesis loop feedback-DRIVEN (`LH-G-004` deepened)**: `RepairMockGenerator` repairs CAUSALLY based on the `casl check` diagnostics (not scripted). Safety repair as the target vision in miniature: effectful action without approval → rejected (approval dominance) → approval consent gate added → accepted (2 iterations). Building block `kernel.synthesis_repair` (39 building blocks). Live path (`casl synth --live`) uses the same feedback machinery | yes (candidate) |
| 0.1.41  | 2026-06-18 | —     | **Self red-team on v0.7.4 (feature interactions)** — no finding: three interaction attacks in `examples/attacks/` (`stream_no_approval` = effect in stream handler without approval; `concurrency_cross_rec` = role-disjoint concurrency across recursion; `stream_not_env` = non-env-driven stream) are all rejected for the RIGHT reason (approval dominance / concurrency gate / stream well-formedness). 8 attacks in the corpus, audit green. Validates the new surface (multi-role/concurrency/streams) as regression protection | yes (candidate) |
| 0.1.42  | 2026-06-18 | —     | **TCB differential bridge (H1 partial step, `W11`)**: the F\*-extracted OCaml kernel (`fstar/ocaml/`, freshly extracted with 4 roles) and the Python checker AGREE on a projectability corpus (6 protocols, incl. 4-role + non-projectable) — `prototype/tcb_bridge.py`, `make -C fstar tcb-bridge`. **Offline/opt-in**, NOT in the living audit (toolchain-dependent); empirically bounds the TCB divergence. `LH-C-004` remains a MAY gap (full unification blocked by krml/Eurydice) | yes (candidate) |
| 0.1.43  | 2026-06-18 | —     | **F\* Direction C deepened — permutation/confluence on BOTH levels (`W9`)**: `proj_skip` (projection ignores non-head roles — the enabling lemma) and `cstep_diamond` (independent actions also commute at the ENDPOINT/configuration level, not only globally) proven mechanically (F\* 2026.03.24, **0 admits**). Commutation thereby proven at the global AND endpoint level. The only thing still open is the fully general inductive fidelity under permutation for ARBITRARY protocols (by-test) | yes (candidate) |
| 0.1.44  | 2026-06-18 | —     | **Async/buffered sessions (`LH-F-010`) — encapsulated enhancement, deny-by-default.** Literature (`docs/analyses/async.md`): async subtyping is UNDECIDABLE (Bravetti–Carbone–Zavattaro 2017, `W16`) ⇒ a hard barrier instead of an impossible oracle. New, ENCAPSULATED module `semantics_async.py` (one FIFO inbox/receiver, non-blocking send), opt-in via the `async [k N];` marker; gate `async_bounded` (k-bounded reachability) certifies **bounded + orphan-free + deadlock-free** and reports **sync equivalence** (≤1 message in flight ⇒ inherits the proven kernel guarantees); reorder/deadlock/orphan/buffer>k/explosion ⇒ REJECTED. Verdict levels `async-rejected < async-bounded-safe < async-synchronizable`. Building blocks `kernel.async_bounded`/`async_veredelung`, `examples/async_{request,fanout,fanin_bad}.casl`. **Synchronous proven kernel untouched** (without the marker nothing changes); F\* mechanization of bounded async = tracked MAY future. 40 building blocks | yes (candidate) |
| 0.1.45  | 2026-06-23 | —     | **Docs sync — full recursion soundness (`W19`, v0.27/0.28).** `CASL.fst` (0 admits): subject reduction now proven for the FULL calculus incl. recursion (`preservation_full` over `GS_Rec`, via `subst_g_wf`); well-formedness gained `gdistinct` (distinct branch labels) + `closed` (no free type vars), mirrored in the TCB bridge (412/412) and the `casl check` gate. Projection soundness/completeness resolved (`CEP-0055`): sound core + completeness maximised + residual behind the monitored oracle boundary (`casl check --attest`); **completeness ratchet** (`CEP-0056`, audit `[5e]`) guards the disclosed residual. README/`docs/{mechanization,requirements,vision}.md` honest-scope text updated. No new gaps; all gates green | yes (candidate) |

### Release

| Role          | Name | Date  | Status |
|---------------|------|-------|--------|
| Client        | —    | —     | open   |
| Contractor    | —    | —     | open   |

> Note (per DIN 69901-5 / VDI/VDE 3694): The requirements specification contains the requirements defined by the **client**. The **design specification** (L2, realized in `docs/requirements.md` + mechanically in `prototype/pflichtenheft.py`) is prepared by the **contractor**, includes this requirements specification as an attachment, and is ideally confirmed before implementation begins.
>
> **Baseline status:** `0.1.1` is a *baseline candidate*. A formal configuration baseline per ISO 10007 only comes into being once release has occurred (table above); until then the marking "baseline candidate" is an internal draft snapshot.

---

## 1. Purpose and Scope

### 1.1 Purpose

This document defines the coarse vision (L0) and the stakeholder requirements (L1) for a programming/specification language with which parallel LLM agents are **specified, orchestrated, proven, and tested**. Guiding principle: **anchor as much provability as possible structurally (statically)**, and provide a defined checking and testing strategy for the part that is not statically provable.

### 1.2 In scope

- L0 coarse specification (goals, scope, core principles).
- L1 requirements specification: functional, qualitative (NFR), process, and normative requirements with stable IDs.
- Definition of the ID scheme, requirement attributes, traceability, and versioning discipline.

### 1.3 Out of scope (→ subsequent versions)

- **L2 design specification** (SyRS/SRS): realization specifications per requirements-specification ID.
- **L3 formal specification**: grammar, type-system rules, operational semantics, projection algorithm.
- Implementation, toolchain, reference interpreter.

### 1.4 Refinement Ladder

```
L0 coarse specification / Vision     (this document)
 └─ L1 requirements spec / StRS      (this document)
     └─ L2 design spec / SyRS+SRS    (TBD) — each item references ≥1 L1 ID
         └─ L3 formal specification  (TBD) — each rule references ≥1 L2/L1 ID
```

Each deeper level is a refinement and MUST be bidirectionally traceable upward (`LH-P-002`).

---

## 2. Normative References

| Abbr.   | Norm / Standard                                                                                                | Use                                                                |
|---------|----------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|
| 29148   | ISO/IEC/IEEE 29148:2018 — *Systems and software engineering — Life cycle processes — Requirements engineering*  | Requirement attributes, quality, document structure (StRS/SyRS/SRS) |
| 69901-5 | DIN 69901-5:2009-01 — *Projektmanagement — Projektmanagementsysteme — Teil 5: Begriffe*                        | Definition of requirements/design specification, structuring        |
| 3694    | VDI/VDE 3694 (ed. 2014) — *Lastenheft/Pflichtenheft für den Einsatz von Automatisierungssystemen*              | Structure of requirements/design specification, mandatory norms     |
| BCP 14  | IETF RFC 2119 + RFC 8174                                                                                        | Requirement levels (MUST/SHOULD/MAY incl. negative forms)           |
| SemVer  | Semantic Versioning 2.0.0                                                                                       | Versioning of the documents and the language                        |
| 10007   | ISO 10007:2017 (configuration management) / IEEE 828-2012 (*Configuration Management in Systems and Software Engineering*; status: inactive/reserved) | Configuration management, baselines, change control |

---

## 3. Terms and Abbreviations

| Term                      | Definition (working definition v0.1)                                                                                                                                 |
|---------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Agent**                 | First-class, concurrent actor; the fundamental value of the language.                                                                                                 |
| **Agent kind** (data type) | Classification of agents = their behavioral/session type; defines the upper bound for capabilities and the protocol.                                                 |
| **Object**                | Tailored agent = subtype of an agent kind that carries a bundle of specific Promises, Interface/Tools, and Contracts.                                                 |
| **Promise**               | Future for an asynchronous result. **Write-once:** resolved exactly once (`LH-Q-003a`). Read access per the linearity policy (default: read-once, configurable) — see `LH-Q-003b`. |
| **Interface**             | Observable interaction protocol of an agent = (local) session type.                                                                                                  |
| **Capability**            | Unforgeable authorization to call a particular tool with particular parameters/scope; part of the agent type. **CASL's own model:** `Capability = (tool, params, scope, ttl, σ)` with `σ` = signature/provenance. Inspired by MCP security work (§9), but defined independently. |
| **Contract**              | Pre/postcondition (refinement) on an interface.                                                                                                                       |
| **Choreography**          | Global protocol over all participating agents.                                                                                                                       |
| **Projection**            | Syntax-driven derivation of local endpoint types from the choreography.                                                                                               |
| **Blame**                 | Assignment of responsibility on a runtime contract violation (oracle vs. orchestration).                                                                              |
| **Oracle**                | The LLM as a nondeterministic component whose output is not statically provable.                                                                                      |
| **RTM**                   | Requirements Traceability Matrix.                                                                                                                                     |
| StRS / SyRS / SRS         | Stakeholder / System / Software Requirements Specification (29148).                                                                                                   |

---

## 4. Conventions

### 4.1 Requirement Levels (BCP 14 / MUST-SHOULD-MAY)

- **MUST** (MUST/SHALL): mandatory; non-fulfillment is a knockout criterion.
- **MUST NOT** (MUST NOT/SHALL NOT): mandatory prohibition.
- **SHOULD** (SHOULD): expected; justified deviation possible.
- **SHOULD NOT** (SHOULD NOT): undesirable; justified deviation possible.
- **MAY** (MAY): optional; differentiating feature.

Only uppercase carries the normative meaning (RFC 8174).

### 4.2 ID Scheme

Stable, **never-reused** IDs. Scheme: `LH-<cat>-<seq>` or `PH-<cat>-<seq>` (L2). Splits carry suffixes (`-001a`, `-001b`).

| Category (L1)  | Meaning                | Category (L2)  | Meaning              |
|----------------|------------------------|----------------|----------------------|
| `LH-G`         | principle / goal       | `PH-A`         | architecture / calculus |
| `LH-F`         | functional             | `PH-T`         | type system / rule   |
| `LH-Q`         | quality (NFR)          | `PH-V`         | verification / test  |
| `LH-P`         | process / traceability |                |                      |
| `LH-C`         | constraint / norm      |                |                      |

Each `PH` ID references ≥1 `LH` ID.

### 4.3 Requirement Attributes (per 29148)

Each requirement carries at least: **ID**, **title**, **level**, **text** (a checkable statement), **rationale** (`Rat:`), **source** (`T1`–`T5`, see §4.6), **verification method** (`Verif:`), **status**, **introduced-in-version**.

> **Uniform attributes (v0.1.x):** Unless noted otherwise per requirement, uniformly **status = draft** and **introduced-in-version = 0.1.0** (splits: 0.1.1). These two mandatory attributes are thereby set globally; for each requirement, source, verification, and rationale are kept explicitly.

29148 quality characteristics **per individual requirement** (all nine to be aimed at): *necessary, appropriate, unambiguous, complete, singular, feasible, verifiable, correct, conforming*. **Per requirement set:** *complete, consistent, feasible, comprehensible, validatable*. Traceability is a relationship/management property and is ensured via `LH-P` and the RTM (§7), not as an individual-requirement characteristic.

### 4.4 Verification Methods (provability tetrad)

The `Verif` attribute directly encodes the provability level (four levels):

- **B** — *proven* (static): type-safety/linearity/conformance proof, no runtime cost.
- **S** — *SMT*: static via solver (e.g., Z3) on decidable, deterministic fragments (target fragments e.g. QF_LIA, EUF — to be fixed in L2).
- **M** — *Monitor*: runtime check at oracle boundaries with blame.
- **T** — *Test*: property/conformance test; semantically via metamorphic test / LLM judge.

### 4.5 Traceability & Versioning (`LH-P`)

- Requirements-specification ID ↔ design-specification ID ↔ design artifact ↔ proof/test in the **RTM** (Section 7), bidirectional, incl. upstream column (T source).
- Plain text in Git; every commit references the affected ID(s); SemVer tags mark baselines; change control per ISO 10007.
- Recommended tools (docs-as-code): Doorstop, Sphinx-Needs, or OpenFastTrace.

### 4.6 Sources of the Requirements (prior work `T1`–`T5`)

> **Status: confirmed on 2026-06-15 (`TBR-003` closed).** The `source` codes refer to the five guiding theses of the prior work:

| Code | Guiding thesis (reconstructed)                                                                                                                             |
|------|------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `T1` | **Provability/oracle thesis:** prove the deterministic hull, treat the LLM as a nondeterministic oracle; maximize what is statically provable, discharge decidable data conditions via SMT. |
| `T2` | **Agent-oriented-types thesis:** agents are values, their type is their session type, asynchronous results are Promises, global protocols project onto local endpoint types (static protocol fidelity). |
| `T3` | **Runtime/resilience thesis:** realization of local types as prompted agents; crash/refusal as typed cases; monitoring with blame at the oracle boundary. |
| `T4` | **Object/capability/contract thesis:** objects are tailored (attenuated) agents that bundle Promises, tools-as-capabilities, and Contracts; least privilege; refinement contracts; testability from structure. |
| `T5` | **Requirements-engineering/norms thesis:** traceability, docs-as-code, versioning, and norm conformance (29148, DIN 69901-5, VDI/VDE 3694) as the methodological basis. |

---

## 5. Coarse Specification (L0) — Vision

CASL is a **typed, agent-oriented, choreographic language**. Values are agents; types are behavioral/session types (an agent kind = the protocol it fulfills). Asynchronous results are Promises; abstracting boundaries are Interfaces; objects are tailored agents with bundled Promises, tools (as capabilities), and Contracts.

The semantics is **two-stage**:

1. **Specification stage (static):** a global choreography is decomposed via **projection** into local endpoint types. This is where the proofs take place (conformance, deadlock freedom, capability containment, Promise linearity, refinement contracts via SMT).
2. **Runtime stage:** the compiler realizes each local type as a concrete, prompted, parallel agent. Promise resolution = receipt of a typed message, **monitored** at the boundary with blame, because the content originates from the oracle.

In doing so, CASL draws on **two related but formally distinct projection traditions**: (a) *(Multiparty) Session Types* (MPST, in practice e.g. Scribble) and (b) *Message Sequence Charts* (MSC, projection-based coordination for LLM agents, §9). Which variant is taken as normative is to be decided in L2 (`TBD-003`).

**Guiding principle (`LH-G-002`):** *Prove the deterministic hull; treat the LLM as a nondeterministic oracle.* Provability and testability are the same investment: the same structural types deliver the static proofs **and** generate monitors and tests for the rest.

---

## 6. Requirements Specification (L1)

> Format per requirement: **`ID` — title** · level · source · `Verif:` · `Rat:` (rationale). Status/version uniform per §4.3.

### 6.1 Principles / Goals (`LH-G`)

**`LH-G-001` — Core purpose** · MUST · Source: T1–T4 · Verif: — (umbrella goal, verified via children)
The language MUST enable the specification, orchestration, verification, and testing of parallel LLM agents.
`Rat:` Umbrella goal that defines the language's reason for being and its scope; not directly checkable itself, but via the derived requirements.

**`LH-G-002` — Oracle principle** · MUST · Source: T1 · Verif: B/M
Statically provable properties MUST be structurally guaranteed; oracle-dependent properties MUST be checked/tested at runtime.
`Rat:` LLM output is in principle not statically provable; the dividing line between hull and oracle determines the entire architecture.

**`LH-G-003` — Correctness by construction** · SHOULD · Source: T4 · Verif: B
Correctness SHOULD preferably be achieved structurally (by construction) rather than by downstream checking.
`Rat:` Structural correctness eliminates entire classes of errors up front and lowers the test burden.

**`LH-G-004` — Requirement-driven synthesis with a verifier gate** · SHOULD · Source: T1/T2 · Verif: T
From a (co-developed) natural-language requirement, an LLM SHOULD propose a `.casl` specification that is accepted **only after passing `casl check`** (gate); derived tests run, and on rejection the diagnostics go back as feedback (repair loop), with the final adoption being human approval.
`Rat:` The design-time oracle is fenced in just like the runtime oracle — nothing unchecked gets through (core of the vision, `docs/vision.md`).

### 6.2 Functional Requirements (`LH-F`)

**`LH-F-001` — Agents as values** · MUST · Source: T2 · Verif: B
Agents MUST be first-class values; variables reference agents.
`Rat:` First-class status allows composition, passing, and typing of agents like ordinary values.

**`LH-F-002` — Type = session type** · MUST · Source: T2 · Verif: B
An agent's type MUST be its behavioral/session type.
`Rat:` The observable protocol is the only viable typing level for interacting agents.
*(The associated definitions "data types classify agent kinds" and "interfaces are protocols" have been moved to the terms in §3 — singularity per 29148.)*

**`LH-F-003` — Promises** · MUST · Source: T2 · Verif: B
Asynchronous results MUST be modeled as Promises (futures).
`Rat:` Asynchrony is the normal case for parallel agents; Promises make data dependencies explicit and typeable.

**`LH-F-004` — Objects as tailored agents** · MUST · Source: T4 · Verif: B
An object MUST be a subtype of an agent kind and carry a bundle of {specific Promises, Interface/Tools, Contracts}; the agent kind defines the upper bound, the object narrows it (subtype + attenuation).
`Rat:` Least privilege: concrete objects should be allowed at most what their kind permits — usually less.

**`LH-F-005` — Tools as capabilities** · MUST · Source: T4 · Verif: B
Tools MUST be part of the agent type as capabilities (`(tool, params, scope, ttl, σ)`, §3) (the agent's capability set).
`Rat:` Tools are security-relevant effects; only as a type-bound capability are they statically controllable.

**`LH-F-006` — Projection onto prompts** · MUST · Source: T2/T3 · Verif: B
A global protocol MUST be decomposable via (syntax-driven) projection into local endpoint types, which the compiler realizes as concrete, parallel, prompted agents.
`Rat:` Bridge from the global specification to individually executable, prompted agents.

**`LH-F-007a` — Crash tolerance** · SHOULD · Source: T3 · Verif: B
Crash behavior of agents (process stops) SHOULD be treated as a regular, typed case (crash-tolerant protocols).
`Rat:` Failures are the normal case in distributed LLM systems; crash is structurally typeable (cf. Generalised MPST w/ Crash-Stop, §9).

**`LH-F-007b` — Refusal handling** · SHOULD · Source: T3 · Verif: M
Refusal by an agent SHOULD be treated as a typed case and detected at runtime.
`Rat:` Refusal is oracle-specific and only detectable at runtime — hence a monitor rather than a proof. Deliberately separated from `LH-F-007a` because of the different provability level.

> **Expressiveness toward the target vision (VISION §3/§6).** Steps beyond the proven synchronous core, driven by the "autonomous secretariat" showcase.

**`LH-F-008` — Multiparty choreographies (≥4 roles)** · SHOULD · Source: T2 · Verif: T · *realized v0.6.9*
Choreographies with **more than three roles** SHOULD be expressible and checkable.
`Rat:` The secretary needs U/S/Mail/Calendar/… **Realized:** projection/merge/realizability/well-formedness and the operational semantics (`semantics.roles_of`/`config`) are parametric over the role set; `examples/secretariat.casl` (4 roles) is accepted and corresponds by-test (building block `kernel.multiparty`). **Honest limit (current):** the F\* calculus has 4 roles; **subject reduction is proven for the full calculus incl. recursion** (`preservation_full`), and the diamond/confluence of role-disjoint actions is proven (`diamond_indep`/`cstep_diamond`). Fully general inductive fidelity *under* permutation for arbitrary concurrent protocols remains `W9` (by-test).

**`LH-F-009` — Event-driven, long-running sessions** · SHOULD · Source: T2/T3 · Verif: T · *realized v0.7.1 (synchronous)*
An inbox is a **stream** of events, each triggering a handler choreography — not a single run.
`Rat:` Core of the secretariat (VISION §6). **Realized (synchronous, variant A):** construct `stream Name { … }` (= `Rec` with a `stream` flag) + `env` role (external event source). The stream loop runs **deliberately unbounded** (exempt from the termination obligation), but every **handler MUST terminate** and the loop is **productive** (env-driven dispatch choice — each iteration consumes an event). Checked via `spike_hardening.stream_wellformed` + building block `kernel.stream`/`stream_safe` (MUST gate, deny-by-default), example `examples/inbox.casl`. All invariants (approval/capability/concurrency) hold **per handler** unchanged. The **fully asynchronous semantics** (FIFO buffer, orphan/progress conditions) is now realized as the encapsulated enhancement `LH-F-010`; a finite `ttl` in the unbounded stream motivates the MAY revocation (`LH-Q-008`).

**`LH-F-010` — Async/buffered sessions (encapsulated enhancement)** · SHOULD · Source: T2/T3 · Verif: T · *realized v0.8.0*
Sending should **not block**: messages are buffered, the receiver reads later (a realistic world for concurrent agents whose responses arrive in arbitrary order).
`Rat:` Async subtyping is in general **undecidable** (Bravetti–Carbone–Zavattaro 2017; `W16`) — a complete async safety oracle cannot exist. Instead of promising one, CASL builds a **hard barrier** (`docs/analyses/async.md`): an **encapsulated, opt-in** enhancement `semantics_async.py` (one FIFO inbox per receiver, non-blocking send, FIFO recv), reachable only via the per-protocol marker `async [k N];`. The **deny-by-default** gate `kernel.async_bounded` enumerates the **k-bounded** state space and certifies **boundedness + orphan freedom + deadlock freedom**; in addition it reports **sync equivalence** (≤1 message in flight at a time ⇒ the behavior coincides with the proven synchronous kernel and inherits its guarantees). Verdict levels: `async-rejected` < `async-bounded-safe` < `async-synchronizable`. Anything not certifiable (reorder/deadlock, orphan, buffer > k, state explosion) is **rejected** — e.g. a fan-in where responses do not return in request order (`examples/async_fanin_bad.casl`). **Encapsulation:** WITHOUT the marker nothing changes — the proven synchronous kernel remains the default and can never be weakened by the enhancement (`docs/analyses/refinements.md`). Building blocks `kernel.async_bounded`/`async_veredelung`, examples `examples/async_{request,fanout,fanin_bad}.casl`. **Open:** F\* mechanization of bounded async (MAY future); fully unbounded async remains deliberately out of scope.

### 6.3 Quality / Non-functional (`LH-Q`)

**`LH-Q-001a` — Protocol conformance static** · MUST · Source: T2 · Verif: B
Protocol conformance MUST be statically guaranteed.
`Rat:` Core guarantee of session types; the very reason for the static stage.

**`LH-Q-001b` — Deadlock freedom static** · MUST · Source: T2 · Verif: B
Deadlock freedom MUST be statically guaranteed. *Reach (honest):* **subject reduction (well-formedness preservation) is mechanically proven (F\*) for the full calculus INCLUDING recursion** (`preservation_full` over `GS_Rec`, via `subst_g_wf`; well-formedness gained `gdistinct`+`closed`). Progress (`global_progress`) and head fidelity/`deadlock_free` are proven for the head/recursion-free fragment; progress *through* recursion (unfolding) is supported per-test (`metatheory.py`), not yet inductively proven.
`Rat:` Deadlocks are a major risk in concurrent agent systems; structurally excludable.

**`LH-Q-001c` — Session fidelity static** · MUST · Source: T2 · Verif: B
Session fidelity (fidelity between global and projected local protocols) MUST be statically guaranteed.
`Rat:` Ensures that the projected agents actually realize the specified choreography.

**`LH-Q-001d` — Correspondence under concurrency** · MUST · Source: T2 · Verif: B · *realized v0.7.0*
If two actions are **role-disjoint** (independent), they commute; the choreography MUST capture this concurrent endpoint behavior correctly — and whatever it does not capture MUST be rejected rather than silently assumed.
`Rat:` Sequentially written but independent actions fire concurrently at the endpoints. **Realized:** a **swap rule** in `semantics.step_global` brings role-disjoint actions of the comm prefix forward; `semantics.correspondence_class` classifies by-test per protocol: `certified` (global == config everywhere), `incomplete` (endpoints more concurrent than captured → **rejected** by the `casl check` gate, deny-by-default), `unsound` (global ⊋ config — must never occur). **Safety:** the soundness direction (global ⊆ config) holds by-test without exception (≥4-role battery, 0 `unsound`); because independent actions form a **diamond/confluence**, all path/structure invariants (approval, capability, effect, linearity) are preserved under any interleaving. **Mechanized (F\*):** the permutation/confluence diamond at the global *and* endpoint level (`diamond_indep`/`cstep_diamond`, the `W9` core); fully general inductive fidelity under permutation for arbitrary protocols remains by-test (Direction C).

**`LH-Q-002` — Capability containment** · MUST · Source: T4 · Verif: B/T
No agent MAY call a tool outside its capability set; such a call MUST be a type error. (Test: `T-CAP`.)
`Rat:` Prevents privilege escalation structurally (least privilege).

**`LH-Q-003a` — Promise linearity (resolution)** · MUST · Source: T4 · Verif: B
Every promised Promise MUST be resolved exactly once (write-once).
`Rat:` Prevents lost and duplicate results.

**`LH-Q-003b` — Obligation fulfillment** · MUST · Source: T4 · Verif: B
Every interface obligation MUST be fulfilled (linearity of obligations).
`Rat:` Ensures that promised behavior is fully delivered; deliberately separated from Promise resolution.

**`LH-Q-004` — Data contracts via SMT** · MUST · Source: T1/T4 · Verif: S
Data-level contracts (e.g., budget bounds, routing constraints, arithmetic/relational pre/postconditions) MUST be discharged statically via SMT, as far as decidable.
`Rat:` Decidable data conditions should not fail only at runtime; "as far as decidable" bounds the requirement cleanly.

**`LH-Q-005` — Runtime monitoring with blame** · MUST · Source: T3 · Verif: M
Oracle-dependent results MUST be monitored at runtime against their type at Promise boundaries, with blame assignment.
`Rat:` Provability ends at the oracle boundary; blame localizes the responsibility for the fault (oracle vs. orchestration).

**`LH-Q-006` — Testability from structure** · MUST · Source: T4 · Verif: T
From each local type, both (a) a dual mock for isolation tests and (b) a property generator MUST be derivable.
`Rat:` The same structure that proves should also generate tests/mocks — provability and testability as a single investment.

**`LH-Q-007` — Semantic checking** · SHOULD · Source: T4 · Verif: T
Non-typeable semantic properties SHOULD be checked via metamorphic testing / LLM judge.
`Rat:` Content correctness is not typeable and needs empirical checking.

**`LH-Q-008` — Capability revocation & refresh (lifecycle)** · MAY · Source: T4 · Verif: M · *realized v0.7.3*
The capability lifecycle MAY be dynamic: **refresh** (re-granting) and **revocation** (withdrawal) at runtime.
`Rat:` **Realized:** (a) **Refresh** — a `stream` loop re-grants per iteration, so a finite `ttl` in the deliberately unbounded inbox is ttl-safe (`ttl_safety_check` stream-aware: `ttl ≥` uses per iteration instead of ≥ an infinite bound; `inbox.casl` is now ttl-safe). (b) **Revocation** — `casl run` takes a `revoked` set; the tool broker denies a revoked tool (`tool_denied`), even if declared. Building block `kernel.revocation`. (Fully dynamic mid-run revocation via a specification construct remains the research frontier `TBR-002`.)

**`LH-Q-009` — Loop termination / progress** · SHOULD · Source: T1/T2 · Verif: S
Recursive (loop) protocols SHOULD carry a lower-bounded, strictly decreasing ranking measure whose well-foundedness is established statically (SMT); from this an upper bound on iterations follows.
`Rat:` Without a ranking measure a retry loop cannot terminate (audit finding W5; `TBD-008` closed).

**`LH-Q-010` — Capability `ttl` safety under recursion** · SHOULD · Source: T4 · Verif: B
If a capability with a finite `ttl` is used inside a loop, `ttl ≥` the proven iteration bound (`LH-Q-009`) MUST hold; otherwise the use is not ttl-safe. **Exception `stream` loop:** there it is re-granted per iteration (`LH-Q-008` refresh), so `ttl ≥` uses per iteration suffices.
`Rat:` Composes least privilege with termination (audit finding W4; `TBD-007` closed).

**`LH-Q-011` — Approval dominance for effectful actions** · MUST · Source: T3/T4 · Verif: B
Every **effectful** action MUST be dominated on every path by an **approval gate** via its **consent branch**. An action is effectful if it is explicitly `irreversible` OR uses a capability whose scope is not explicitly `readonly` (**deny-by-default** — effect bound to capability, not to an optional tag). Only a branch marked `consent` exempts the obligation; consent does **not** carry across loop iterations.
`Rat:` Safety foundation (`docs/vision.md` / `TBD-V-003`): no side effect without specific consent. After red-team v0.1.27, hardened against C1 (deny branch), C2 (untagged effect), and M2 (approve-once-spam); an attack corpus (`examples/attacks/`) enforces the rejection in the audit (`kernel.approval_safety` + `kernel.redteam_attacks`). **Reach:** (1) static lint on the spec **and** (2) since v0.6.4 **runtime enforcement** — `casl run` requires an external decision at the approval gate (default-deny; `--approve`/callback), never chooses a structural default, and enters no effect branch without approval (`kernel.runtime_approval`, closes `C3`/`W10`). What remains open is true tool confinement (broker, `H3`/`W12`) and binding the running checker to the proven artifact (`H1`/`W11`).

> **Red-team follow-up requirements (re-test v0.1.28).** Open, tracked issues (each a tension `W*` + a `PH` item with status "planned"); the named fix PR realizes them and removes them from the accepted gaps.

**`LH-Q-012` — Effect classification structured & validated** · MUST · Source: T4 · Verif: B · *realized v0.6.5 (`W14` resolved)*
Whether an action is **effectful** (dangerous) MUST follow from an **explicit, structured, validated** capability field (`mode: read | write | admin`, default `write`) — **effectful-by-default** — not from a substring test over the author-controlled free-text `scope`.
`Rat:` R-H1 (red-team v0.1.28): the C2 fix shifted trust from the `irreversible` boolean to the free-text `scope`; `effectful()` was leaky (`cal:read-write`→read-only) and spoofable (`db:readonly` on `purge`). **Realized:** `casl_core.Capability.mode` + `spike_approval.effectful` (only `mode=="read"` is exempt) + building block `kernel.effect_classification`; `scope` is since then descriptive and never security-deciding. Attack specs `rw_naming`/`delete_readonly` are rejected (`kernel.redteam_attacks`).

**`LH-Q-013` — Per-gate disclosure & specific consent** · SHOULD · Source: T3 · Verif: M · *realized v0.6.6 (`W15` resolved)*
An approval grant SHOULD be bound to the **message and concrete action disclosed** at the gate (per gate), not apply blanketly to a whole run.
`Rat:` R-N1 (red-team v0.1.28): closes the "approve X, branch does Y" gap. **Realized:** `casl_run.GateDisclosure` discloses, per gate, the triggering message AND the concrete effectful action(s) of the consent branch; `on_approval(disclosure)` decides per gate (building block `kernel.gate_disclosure`), the CLI asks interactively (default-deny without a TTY). `--approve` remains documented only as a non-interactive **demo blanket**. Prerequisite for the "autonomous secretariat" use case.

**`LH-Q-014` — Runtime tool mediation (confinement)** · SHOULD · Source: T4 · Verif: M · *realized v0.6.7 (`W12` resolved)*
At runtime a **broker** SHOULD interpose on tool calls and deny tools not carried at runtime — least privilege as enforcement, not only as lint.
`Rat:` H3 (red-team v0.1.27). **Realized:** `casl_run._tool_allowed` interposes before every tool use and checks against the **runtime capmap** (not only statically) → `tool_denied` if the acting role does not carry the tool (also catches an attenuated object with fewer capabilities than the spec declares); building block `kernel.tool_broker`. Requires `LH-Q-012` (otherwise the effect classification would be spoofable).

**`LH-Q-015` — Out-of-band cost metering** · SHOULD · Source: T3 · Verif: M · *realized v0.6.8 (`W13` resolved)*
The costs/effects evaluated in the contract SHOULD be measured **out-of-band**; numbers reported by the oracle itself count as unverified claims.
`Rat:` H4 (red-team v0.1.27): the oracle must not itself report the quantity it is measured against. **Realized:** `OracleResult.measured_cost` carries the out-of-band measurement (live: server `usage.completion_tokens`; mock: true value), the monitor checks `metered_cost(out)` instead of the oracle's claim; `oracle_step`/`casl_run` use the measured value, a misreport (claim≠measured) is flagged. Building block `kernel.cost_metering` (scenario `underreport`: budget-conforming claim, but measured overrun → violation/Blame A).

### 6.4 Process / Traceability (`LH-P`)

**`LH-P-001` — Requirement IDs & attributes** · MUST · Source: T5 · Verif: T
Every requirement MUST carry a stable, never-reused ID and the attributes per 29148 (§4.3).
`Rat:` Unambiguous, attributed requirements are a precondition for auditability and traceability.

**`LH-P-002` — Bidirectional traceability** · MUST · Source: T5 · Verif: T
Every design-specification, design, and test artifact MUST be traceable to ≥1 requirements-specification ID, and every requirement to its source (`T1`–`T5`) — RTM (§7).
`Rat:` Gapless traceability upward and downward is the backbone of the process model.

**`LH-P-003` — Version reference for every change** · MUST · Source: T5 · Verif: T
Every change MUST be relatable to a versioned document revision (SemVer tag + Git commit + requirement ID).
`Rat:` Reproducibility and change control per ISO 10007.

**`LH-P-004` — Norm conformance** · SHOULD · Source: T5 · Verif: T
Compliance with DIN 69901-5, VDI/VDE 3694, and ISO/IEC/IEEE 29148 SHOULD be documented.
`Rat:` Reference to norms increases acceptance, checkability, and reusability.

**`LH-P-005` — Code↔commit↔requirement traceability** · MUST · Source: T5 · Verif: T
Every line of code MUST be traceable via `git blame` → commit → the requirement IDs referenced in the commit message; per requirement, the associated commits MUST be automatically extractable (`prototype/trace.py`).
`Rat:` Gapless, mechanically checkable traceability across the entire change history — the basis for safe, derived development, including for opaque/LLM artifacts (`docs/vision.md`).

### 6.5 Constraints / Norms (`LH-C`)

**`LH-C-001` — Docs-as-code** · MUST · Source: T5 · Verif: T
Specification documents MUST be kept as plain text in Git and tagged per SemVer.
`Rat:` Versionability, diff/review capability, and tool support.

**`LH-C-002` — Requirement levels** · MUST · Source: T5 · Verif: T
Requirement levels MUST be marked per BCP 14 / MUST-SHOULD-MAY.
`Rat:` Uniform, unambiguous bindingness of every statement.

**`LH-C-003` — Norms before in-house builds** · SHOULD · Source: T5 · Verif: T
Where possible, external norms SHOULD be used instead of in-house developments.
`Rat:` Lower maintenance burden and higher interoperability.

**`LH-C-004` — Unity of proven artifact and running checker (TCB)** · MAY · Source: T1/T5 · Verif: T · *open → PR #23 (`W11`)*
The checker that checks at runtime MAY be bound to the artifact proven in F\* (single source of truth) rather than being a standalone Python re-implementation.
`Rat:` H1 (red-team v0.1.27): today F\* proves the definitions while unverified Python drives the gate (TCB inversion). Full unification is limited by the krml/Eurydice Low\* mismatch (`TBD-004`, see `docs/mechanization.md`) — hence MAY.

---

## 7. Requirements Traceability Matrix (RTM)

Bidirectional, incl. **upstream column (T source)**. Downstream columns (L2/L3) are marked `TBD` until the design specification is created. The matrix covers **all** L1 requirements; named artifacts are placeholders for L2/L3.

| L1 requirement | Level | Verif. | Upstream | L2 (design spec) | Design/proof artifact   | Test    |
|----------------|:-----:|:------:|:--------:|--------------------|-------------------------|---------|
| `LH-G-001`  | MUST | —   | T1–T4 | `PH-A-xxx` (TBD) | — (umbrella goal, verified via children) | — |
| `LH-G-002`  | MUST | B/M | T1    | `PH-A-xxx` (TBD) | `kernel.contract_smt`+`monitor`; F* `retry_safe` | `audit.py` |
| `LH-G-003`  | SHOULD | B | T4    | `PH-T-004`       | `kernel.attenuation` (`spike_attenuation`) | audit: OBJ_OK/BAD |
| `LH-G-004`  | SHOULD | T | T1/T2 | `PH-A-006`       | `casl_synth` + `kernel.synthesis` (gate `casl check`, repair loop) | audit: synth loop |
| `LH-F-001`  | MUST | B   | T2    | `PH-T-xxx` (TBD) | `kernel.core_ir` (`casl_core`); F* `gtyp`/`ltyp` | — |
| `LH-F-002`  | MUST | B   | T2    | `PH-T-xxx` (TBD) | `kernel.project` (`spike_proj_mpst`); F* `project` | — |
| `LH-F-003`  | MUST | B   | T2    | `PH-T-003`       | `kernel.promise` (`spike_promise`): `Promise[T]` + resolve-once (W6) | audit: G_OK/G_DUP |
| `LH-F-004`  | MUST | B   | T4    | `PH-T-004`       | `kernel.attenuation` (`spike_attenuation`): tool subset, ttl<=, scope | audit: OBJ_OK/BAD |
| `LH-F-005`  | MUST | B   | T4    | `PH-T-xxx` (TBD) | `kernel.capabilities` (`spike_capability`) | `T-CAP` (G_CAP_BAD) |
| `LH-F-006`  | MUST | B   | T2/T3 | `PH-A-xxx` (TBD) | `kernel.project`+`prompt`; `semantics`; F* `project` | `metatheory.py` |
| `LH-F-007a` | SHOULD | B | T3    | `PH-T-xxx` (TBD) | `kernel.crash_tolerance` (`spike_resilience`) | audit: G_OK_CRASH |
| `LH-F-007b` | SHOULD | M | T3    | `PH-V-xxx` (TBD) | `kernel.refusal_monitor` (`spike_resilience`) | audit: Refusal |
| `LH-F-008`  | SHOULD | T | T2    | `PH-A-008`       | `semantics.roles_of`/`config` + `kernel.multiparty`; `examples/secretariat.casl` (4 roles) | audit: multiparty |
| `LH-F-009`  | SHOULD | T | T2/T3 | `PH-A-009`       | `casl_core.Rec(stream)` + `casl_surface` (`stream`/`env`); `spike_hardening.stream_wellformed`; `kernel.stream`/`stream_safe`; `examples/inbox.casl` | audit: stream (inbox + reject) |
| `LH-F-010`  | SHOULD | T | T2/T3 | `PH-A-010`       | `semantics_async.py` (`async_safe`/`async_class`); `casl_surface` (`async` marker); `casl_check` (gate); `kernel.async_bounded`/`async_veredelung`; `examples/async_*.casl`; `docs/analyses/async.md` | audit: async_veredelung + async end-to-end |
| `LH-Q-001a` | MUST | B   | T2    | `PH-T-006`, `PH-V-005/006` | `kernel.metatheory` (`semantics`/`metatheory`); F* `fidelity_*` [proven, 0 admits] | `metatheory.py` (250+) |
| `LH-Q-001b` | MUST | B   | T2    | `PH-V-005` | `kernel.metatheory` (deadlock); F* `deadlock_free` [proven, 0 admits] | `metatheory.py` |
| `LH-Q-001c` | MUST | B   | T2    | `PH-T-xxx` (TBD) | `kernel.metatheory` (fidelity) | `metatheory.py` |
| `LH-Q-001d` | MUST | B   | T2    | `PH-V-013` | `semantics.step_global` (swap) + `correspondence_class`; `kernel.concurrency`/`concurrency_certified`; `examples/concurrent.casl` | audit: concurrency (sound, ≥4 roles) |
| `LH-Q-002`  | MUST | B/T | T4    | `PH-T-xxx` (TBD) | `kernel.capabilities` (`spike_capability`) | `T-CAP` (G_CAP_BAD) |
| `LH-Q-003a` | MUST | B   | T4    | `PH-T-xxx` (TBD) | `kernel.linearity` (`spike_hardening`) | audit: G_DUP |
| `LH-Q-003b` | MUST | B   | T4    | `PH-T-xxx` (TBD) | `kernel.linearity` (obligation) | audit: G_DUP |
| `LH-Q-004`  | MUST | S   | T1/T4 | `PH-V-xxx` (TBD) | `kernel.contract_smt` (`spike_smt_contract`, Z3); F* `retry_safe` [SMT] | `audit.py` |
| `LH-Q-005`  | MUST | M   | T3    | `PH-V-xxx` (TBD) | `kernel.monitor` (`spike_monitor_test`, blame) | audit: monitor blame |
| `LH-Q-006`  | MUST | T   | T4    | `PH-V-xxx` (TBD) | `kernel.tests` (`spike_monitor_test`, property) | audit: property test |
| `LH-Q-007`  | SHOULD | T | T4    | `PH-V-008`       | `kernel.semantic_judge` (`spike_judge`): metamorphic battery + content judge (mock/live) | audit: judge invariants |
| `LH-Q-008`  | MAY  | M   | T4    | `PH-V-009`       | `ttl_safety_check` (stream refresh) + `casl_run` (revoked) + `kernel.revocation` | audit: revocation |
| `LH-Q-009`  | SHOULD | S | T1/T2 | `PH-V-xxx` (TBD) | `kernel.termination` (`spike_hardening`, SMT ranking; `ab_candidates`) | audit: G_OK_TERM |
| `LH-Q-010`  | SHOULD | B | T4    | `PH-T-xxx` (TBD) | `kernel.ttl_safety` (`spike_hardening`) | audit: G_OK_TERM |
| `LH-Q-011`  | MUST | B   | T3/T4 | `PH-T-011`       | `kernel.approval_safety`+`runtime_approval` (`spike_approval`/`casl_run`) | audit: G_RESCHED_OK/BAD + runtime |
| `LH-Q-012`  | MUST | B   | T4    | `PH-T-012`       | `casl_core.mode` + `spike_approval.effectful` + `kernel.effect_classification` (`W14`/R-H1) | audit: effect_classification; `rw_naming`/`delete_readonly` |
| `LH-Q-013`  | SHOULD | M | T3    | `PH-T-013`       | `casl_run.GateDisclosure`/`on_approval` + `kernel.gate_disclosure` (`W15`/R-N1) | audit: gate_disclosure |
| `LH-Q-014`  | SHOULD | M | T4    | `PH-T-014`       | `casl_run._tool_allowed` (interposition) + `kernel.tool_broker` (`W12`/H3) | audit: tool_broker |
| `LH-Q-015`  | SHOULD | M | T3    | `PH-V-012`       | `oracle.measured_cost`/`metered_cost` + `kernel.cost_metering` (`W13`/H4) | audit: cost_metering (underreport) |
| `LH-P-001`  | MUST | T   | T5    | `PH-V-xxx` (TBD) | `audit.py` + `spec.py` (attributes) | `audit.py` |
| `LH-P-002`  | MUST | T   | T5    | `PH-V-xxx` (TBD) | `audit.py`/`authority.py` (coverage [3b]) + this RTM | `audit.py` |
| `LH-P-003`  | MUST | T   | T5    | `PH-V-xxx` (TBD) | Git/SemVer + version history | — |
| `LH-P-004`  | SHOULD | T | T5    | `PH-V-010`       | `kernel.norms`: §2 cites 29148/69901-5/3694 | audit: norms |
| `LH-P-005`  | MUST | T   | T5    | `PH-V-011`       | `trace.py` (req→commits, `--blame` line→commit→req) + `kernel.versioning` | `trace.py` verification |
| `LH-C-001`  | MUST | T   | T5    | `PH-A-001`, `PH-V-011` | `kernel.versioning`: docs-as-code/SemVer/`CONTRIBUTING.md` + `trace.py` | audit: versioning |
| `LH-C-002`  | MUST | T   | T5    | `PH-V-xxx` (TBD) | §4.1 BCP-14; `living_audit` | — |
| `LH-C-003`  | SHOULD | T | T5    | `PH-A-002`       | `kernel.review`: approval gate in `CONTRIBUTING.md` | audit: review |
| `LH-C-004`  | MAY  | T   | T1/T5 | `PH-A-007`       | *open (PR #23)* — TCB unity checker↔proven kernel (`W11`/H1, `TBD-004`) | — (planned) |

> **Downstream status:** The *design/proof artifact* column now points to real artifacts — prototype building blocks (`prototype/kernel.py` + `spike_*`/`semantics`/`metatheory`) and F* (`fstar/CASL.fst`, mapping in `docs/mechanization.md`). Kept current mechanically via `audit.py` section **[3b]** (requirement → building block, derived from the registry). The **L2 column (design spec)** is now realized in `docs/requirements.md` (v0.2.0) — ≥1 `PH` item per LH requirement, mechanically checked via `prototype/pflichtenheft.py` + `audit.py` [3c].

---

## 8. Open Items (TBD / TBR)

| ID        | Item                                                                              | Type           |
|-----------|-----------------------------------------------------------------------------------|----------------|
| `TBR-001` | Final language name (working title CASL retained until a decision)                | to be decided  |
| `TBR-002` | Capability revocation at runtime (research frontier)                              | open           |
| `TBR-003` | `T1`–`T5` legend (§4.6) — **closed (confirmed 2026-06-15)**                        | done           |
| `TBD-003` | MPST backbone chosen, MSC as cross-check (equivalence hardened, `W2`) — **closed** | done |
| `TBD-004` | Host language — **decided:** F* (verification B+S; extraction→OCaml) + Rust (engine via Pulse/KaRaMeL); Python remains the spike substrate | done |
| `TBD-005` | Document structuring: merge DIN 69901-5 + 29148 — **closed (merge chosen as default)** | done |
| `TBD-006` | Surface syntax — **realized: `casl_surface.py` (Scribble-like, round-trip == G_OK) + CLI `casl check` (`casl_check.py`, protocol-parametric, Exit 0/1) (`PH-A-005`)** | done |
| `TBD-007` | Capability `ttl` semantics under recursion — **closed → `LH-Q-010`**               | done           |
| `TBD-008` | Loop termination (budget monotonicity) — **closed → `LH-Q-009`**                   | done           |

---

## 9. Informative References (technical foundations)

Non-normative; as a technical basis for L2/L3. All arXiv IDs were verified against arxiv.org (as of 2026-06-15).

- **Agent-Oriented Programming** (Shoham 1993, *Artificial Intelligence* 60(1):51–92) — agents as fundamental units.
- **(Multiparty) Session Types / Behavioural Types** — protocol conformance, deadlock freedom, projection; **Scribble** as a practical MPST language (Yoshida et al.).
- **Provable Coordination for LLM Agents via Message Sequence Charts** — arXiv:2604.17612 (Bollig, Függer, Nowak, 2026). Projection-based coordination via **MSC** (related to, but distinct from, MPST), deadlock-free local agent programs; mechanized in **Lean 4** (relevant for `TBD-004`).
- **Type-Driven Prompt Programming** — arXiv:2508.12475 (Paul, 2025). Extended abstract; proposes λPrompt as a type-driven prompt calculus (explicitly described by the author as "not yet a full calculus").
- **Monitorability of Session Types / Run-time Verification** — arXiv:2105.06291. Static/dynamic conformance, monitor synthesis.
- **Generalised MPST with Crash-Stop Failures** — arXiv:2207.02015 (Barwell, Scalas, Yoshida, Zhou; CONCUR 2022, extended version). Crash-tolerant protocols (basis for `LH-F-007a`).
- **A Formal Security Framework for MCP-Based AI Agents** — arXiv:2604.05969 (Acharya & Gupta, 2026); framework "MCPShield", system model `M=(A,S,T,R,C,ℓ)`. Motivation for least-privilege/capability control. *Note: the CASL capability tuple `(tool, params, scope, ttl, σ)` (§3) is CASL's own model, not taken from this paper.*
- **Prompt Flow Integrity** — arXiv:2503.15547. Motivation for least privilege / prevention of privilege escalation in LLM agents.

---

## Appendix A — Refinement Roadmap (bootstrap process model)

This document is not only a specification but also the **process plan** by which CASL is bootstrapped. Each level refines the previous one and remains traceable upward (`LH-P-002`).

1. **v0.1.x — Stabilization (now).** Review findings incorporated (v0.1.1); `TBR-003` closed (v0.1.2). Remaining: `TBR-001` (name). Result: released L1 baseline.
2. **Prototyping spikes (parallel — ongoing).** The alternatives from `TBD-003` (MPST vs. MSC), `TBD-004` (host language), and `TBD-006` (surface syntax) are prototyped **in parallel** on a shared canonical example as minimal, runnable spikes and then **iteratively aligned with one another** until the projection model, proof/SMT layer, monitor/test, and prompt generation fit together. Result: empirically grounded decisions for L2.
3. **v0.2.0 — L2 design specification.** ≥1 `PH` item per `LH` ID; fill in the RTM downstream; commit the decisions from the spikes (`TBD-003/004`); formally fix the capability model `(tool, params, scope, ttl, σ)`. *(Achieved: `docs/requirements.md` v0.2.0 — 25 PH items, all LH realized, enforced in the audit [3c]; F* metatheorems proven (0 `admit`); surface syntax + CLI `casl check` (`TBD-006`) realized.)*
4. **v0.3.0 — L3 formal specification.** Grammar, typing rules, projection algorithm, operational semantics; every rule carries a trace to L2. *(Started: operational semantics `prototype/semantics.py` + metatheory-by-test `prototype/metatheory.py`; MPST committed as the backbone (`TBD-003`); rules in `docs/semantics-l3.md`. Mechanized proofs → Direction C / `TBD-004`.)*
5. **Implementation.** Reference type checker + projection + monitor/test synthesis; minimal interpreter on top of the chosen runtime.

**Language strategy (decision 2026-06-15):** Three separate axes instead of a single language choice —
(1) *Spike substrate:* **Python** during design convergence (fast iteration; z3 binding and DSPy runtime available).
(2) *Reference engine:* **Rust or OCaml** — Rust's move/borrow semantics is affine typing and thereby dogfoods linearity (`LH-Q-003a`) and capability containment (`LH-Q-002`); OCaml is the lighter, compiler-near alternative.
(3) *Proof metalanguage:* **Lean 4 or F*** — Python/Rust do not deliver the B level as machine-checked proofs; F* covers B+S in one language and extracts to OCaml.
**Decision 2026-06-15 (`TBD-004` closed):** (3) proof meta = **F*** (refinements + SMT, covers B+S) → extraction to OCaml; (2) engine = **Rust** as the extraction target via Pulse/KaRaMeL (affine types ↔ linearity). Python remains the spike substrate. Mechanization: `CASL.fst`, workflow in `docs/mechanization.md`.

*End of v0.1.44.* <!-- L1-Lastenheft; L2 siehe docs/requirements.md -->

