# CASL — Principles (First Principles) & Consistency Audit

**Version:** `1.0` · **Date:** 2026-06-15 · **Reference:** `CASL.md` v0.1.3, `prototype/`
**Purpose:** Make explicit the principles in which we think — and immediately apply them to our own work (completeness & contradictions). This is the *lived system*: CASL is developed with CASL's principles. The executable mirror of this document is `prototype/audit.py`.

---

## Part A — The Principles (from which we derive everything)

Each principle: statement · *why* · source (thesis/LH) · *embodiment* (which spike lives it).

**P1 — Oracle separation.** Prove the deterministic hull; treat the LLM as a nondeterministic oracle. *Why:* LLM output is not statically provable — the dividing line determines the entire architecture. · T1 / `LH-G-002` · Embodiment: SMT spike (hull) + monitor (oracle boundary).

**P2 — Correctness by construction.** Check structurally rather than after the fact. *Why:* eliminates whole error classes upfront. · T4 / `LH-G-003` · Embodiment: type projection rejects G_BAD before anything runs.

**P3 — Behavior is type.** Agents are values; their type is their session type. *Why:* the observable protocol is the only viable type level. · T2 / `LH-F-001`,`LH-F-002` · Embodiment: Spike A (MPST).

**P4 — Global → local via projection.** A choreography is projected onto endpoint types in a syntax-directed way. *Why:* the bridge from global specification to individually executable agents. · T2/T3 / `LH-F-006` · Embodiment: Spikes A & B.

**P5 — Least privilege.** Tools only as capability `(tool, params, scope, ttl, σ)`; a call outside the set is a **type error**. *Why:* prevents privilege escalation structurally. · T4 / `LH-F-005`,`LH-Q-002` · Embodiment: Spike Capability (new in this iteration).

**P6 — Linearity.** Promises are write-once; every interface obligation is fulfilled exactly once. *Why:* prevents lost/duplicate results and unfulfilled commitments. · T4 / `LH-Q-003a/b` · Embodiment: **still open** (audit gap G2).

**P7 — One structure proves and tests.** The same types yield proof, monitor, test **and** prompt (the B/S/M/T tetrad). *Why:* provability and testability are one investment. · T4 / `LH-Q-006` · Embodiment: Spike D + prompt projection.

**P8 — Blame locality.** Every contract violation at the oracle boundary is assigned to exactly one responsible party. *Why:* localizes errors (oracle vs. orchestration). · T3 / `LH-Q-005` · Embodiment: Spike D.

**P9 — Traceability & docs-as-code.** Everything versioned, traced, norm-referenced. *Why:* auditability is the foundation of the bootstrap. · T5 / `LH-P`,`LH-C` · Embodiment: **`audit.py`** (lived — checks traceability automatically).

**P0 — Self-application (the lived system).** We develop CASL according to CASL's own principles. Concretely: P9 (traceability) and P7 (structural verification) are applied to the project itself via `audit.py` — every iteration step runs through the same completeness/contradiction check that the language demands for agents.

---

## Part B — Completeness Audit (theses → spikes)

| Thesis | Content | Requirements | Spike coverage | Gap |
|---|---|---|---|---|
| T1 | Oracle/provability/SMT | `LH-G-002`, `LH-Q-004` | SMT (C), oracle boundary (D) | semantic oracle check missing (→ `LH-Q-007`) |
| T2 | agent-/session-typed, projection | `LH-F-001/002/003/006`, `LH-Q-001a/b/c` | Spikes A, B | — (well covered) |
| T3 | runtime/resilience/monitor/blame | `LH-F-006/007a/007b`, `LH-Q-005` | monitor/blame (D), projection (A/B) | **Crash (`LH-F-007a`) & Refusal (`LH-F-007b`) not prototyped** |
| T4 | objects/capabilities/contracts/tests | `LH-G-003`, `LH-F-004/005`, `LH-Q-002/003/004/006/007/008` | Capability (new), SMT (C), Test (D) | **Promise linearity (`LH-Q-003`) not checked**; semantic test (`LH-Q-007`) open |
| T5 | RE/traceability/norms | `LH-P-001..004`, `LH-C-001..003` | **`audit.py`** (new) | closed by the lived system |

**Finding:** T2 complete; T1/T4 partial; T3 has a genuine gap (crash/refusal); T5 is for the first time *lived* via `audit.py` rather than merely documented.

---

## Part C — Contradictions & Tensions

| # | Severity | Finding | Status / Measure |
|---|:---:|---|---|
| W1 | high | **Capability containment** (`LH-Q-002`) claimed as B-verifiable, but checked in no spike. | **resolved this iteration** → `spike_capability.py` |
| W2 | high | Equivalence "MPST projectability ⇔ MSC realizability" (convergence criterion 1) supported by only 2 examples; both checks are heuristics → possible over-claim. | Measure: add adversarial examples (e.g. mergeable-but-MSC-tricky) before the criterion counts as met. |
| W3 | high | **Crash/refusal** (`LH-F-007a/b`, T3) required, but not prototyped. | next iteration: crash-stop spike (B) + refusal monitor (M). |
| W4 | medium | **Capability `ttl` vs. recursion:** `search` has `ttl=3`, but the retry loop is unbounded → tool use can exceed `ttl`. Contradiction between ttl semantics and the μ-loop. | new open point in `CASL.md`; define ttl semantics under recursion. |
| W5 | medium | **Loop termination:** no proof that the retry loop terminates (budget must strictly decrease). | SMT well-foundedness lemma `budget' < budget` (next iteration). |
| W6 | medium | **Promise linearity** (`LH-Q-003a`, write-once) unclear under recursion: one new draft per iteration → "exactly once" holds per iteration, not per session. | make precise + linearity check spike. |
| W7 | low | Branch contract `len(reason)>0` modeled, but not actively checked in monitor/SMT. | follow up the wiring. |
| W8 | low | `σ` (provenance/signature) in the capability tuple unused. | later: provenance check. |

---

## Part D — Recommended Adjustments (iterative, prioritized)

1. **[this iteration, done]** Close W1: `spike_capability.py` (least privilege as a type error).
2. **[this iteration, done]** Live P0/P9: `audit.py` as an executable consistency/traceability checker.
3. **[this iteration, done]** `CASL.md`: record W4/W5 as open points; note capability containment as prototyped.
4. **[next]** W3: crash/refusal spike. · W2: adversarial MPST/MSC examples. · W5/W6: termination & linearity lemmas.
5. **[later]** W7 (wire up branch contracts), W8 (σ provenance), `LH-Q-007` (semantic test via metamorphic/judge).

> Living the system: running `audit.py` reproduces Parts B/C mechanically and fails as soon as a gap/contradiction arises. Thus this document is not a snapshot but a *running* check.
