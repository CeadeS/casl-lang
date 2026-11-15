# CASL Prototyping — parallel spikes + convergence log

**Strategy (Martin, 2026-06-15):** Do NOT decide the open alternatives up front on paper; instead **prototype them in parallel as minimal, runnable spikes** and then **iteratively adapt them to one another until the layers fit together**.

Reference: `CASL.md` appendix A, phase 2 (prototyping spikes); empirically resolves `TBD-003` (MPST vs. MSC), and prepares `TBD-004` (host language) and `TBD-006` (surface syntax). For the language-strategy decision see `CASL.md` v0.1.3.

**Iterations so far:** Round 1 — vertical slice across the tetrad (B/S/M/T). Round 1b — **recursion** (retry loop as a μ-type) + payloads/contracts on choice branches. Round 2 — **kernel architecture**: fundamental building blocks whose authority flows from the specification.

### Architecture — all authority from the specification

```
spec.py        Single Source of Authority (theses T1–T5, principles P0–P9,
               requirements, accepted gaps, tensions)
   │  (every building block cites ONLY items from spec.py)
   ▼
kernel.py      fundamental building blocks, each tagged with realizes/principle/thesis:
               core_ir · project · wellformed · capabilities · contract_smt ·
               monitor · tests · prompt · crash_tolerance · refusal_monitor ·
               linearity · termination · ttl_safety · living_audit
   │  (building blocks compose into features)
   ▼
kernel.compile_choreography(G)   FEATURE: well-formedness → capabilities →
               SMT contracts → projection+prompt → monitor+tests → bundle
   ▼
authority.py   authority chain: no building block without valid spec authority;
               coverage is derived FROM the building-block registry (not maintained)
   ▼
audit.py       living system: validates the chain, traceability, coverage and
               RUNS the feature; CI exit code. Every iteration runs through this.
```

The building blocks *take effect immediately*: `compile_choreography` accepts `G_OK` and rejects `G_BAD` (wellformed) and `G_CAP_BAD` (capabilities) respectively — each with an authority citation (LH-ID · principle · thesis).

---

## Shared fixture: `BudgetedQA` (`casl_core.py`)

A minimal example that deliberately touches **all four provability levels** and now contains a **retry loop**:

```
C -> A : Request(question, budget)                         budget >= 0
μLoop.
  A -> J : Draft(answer, cost)   [cost <= budget]          (oracle; A may `search`)
  J -> C : { Accept          : J -> A : Done . end
             Reject(reason)  : J -> A : Retry . Loop }      <- loops to a new Draft
```

| Language concept | in the example | LH reference |
|---|---|---|
| Multiparty choreography + projection | 3 roles C/A/J, global type → local types | `LH-F-006`, `LH-Q-001a/b/c` |
| **Recursion / loops** | μLoop, Retry jumps back | `LH-F-002` (recursive session types) |
| Promise / linearity | `Draft` as an asynchronous oracle result | `LH-F-003`, `LH-Q-003a` |
| Tool as capability `(tool,params,scope,ttl,σ)` | A holds `search` | `LH-F-005`, `LH-Q-002` |
| Data contract (refinement) | `cost <= budget`; branch contract `len(reason)>0` | `LH-Q-004` |
| Oracle boundary + blame | `Draft` from the oracle, monitored at the A→J boundary | `LH-G-002`, `LH-Q-005` |
| Testability from structure | dual mock + property test from the local type | `LH-Q-006` |

Two variants: **`G_OK`** (well-formed — J announces the outcome to A as well) and **`G_BAD`** (J informs only C → A cannot detect the branch locally, and with the loop this is even fatal: A does not know whether a new Draft is due).

---

## Running

```bash
pip install z3-solver --break-system-packages --only-binary :all:
python3 audit.py     # living system: authority + coverage + feature run (exit code!)
python3 kernel.py    # feature demo: building blocks accept/reject choreographies
python3 run_all.py   # original spike slice (provenance)
python3 harden_equivalence.py  # W2: adversarial MPST⇔MSC battery (10 cases)
python3 ab_candidates.py       # W4/W5/W6: A/B comparisons (static vs. runtime)
python3 spike_hardening.py     # winners: linearity · termination · ttl_safety
```

Individually: `python3 spike_proj_mpst.py` · `spike_proj_msc.py` · `spike_smt_contract.py` · `spike_monitor_test.py` · `spike_capability.py`.

---

## The four spikes

| File | Level | What it shows |
|---|---|---|
| `spike_proj_mpst.py` | B | MPST projection global→local (recursive, μ-types); **mergeability** decides projectability. |
| `spike_proj_msc.py`  | B | MSC projection onto lifelines (loop-back edge ↺); **realizability** (non-local choice) decides well-formedness. |
| `spike_smt_contract.py` | S | Z3 (QF_LIA): budget safety **proven** (UNSAT of the negation); counterexample without a stepwise contract (SAT). |
| `spike_monitor_test.py` | M, T | synthesized from contract+type: monitor with **blame**, dual mock, property test (2000 cases, 0 deviations). |
| `run_all.py` | — | orchestrates + **prompt projection** (`LH-F-006`): A's prompt (including the loop) is generated from A's local type. |

---

## Current result (reproduced)

Projected local types (recursive):

```
C: A!Request . μLoop. J&{ Accept: end,  Reject(reason): Loop }
A: C?Request . μLoop. J!Draft . J&{ Done: end,  Retry: Loop }
J: μLoop. A?Draft . C⊕{ Accept: A!Done.end,  Reject(reason): A!Retry.Loop }
```

```
MPST:  G_OK projectable;  G_BAD NON-PROJECTABLE (A not mergeable)
MSC:   G_OK realizable;  G_BAD REJECTED (non-local choice at A)
MPST & MSC agree in their verdict — via different mechanisms.
SMT:   (c1<=b ∧ c2<=b-c1) → c1+c2<=b  PROVEN;  naive contract: counterexample b=1,c1=1,c2=1
Monitor: pass OK; blame-case → BLAME A; Property-Test 0 Mismatches
RESULT: ALL LAYERS CONSISTENT on the shared fixture
```

**Core finding (TBD-003):** MPST and MSC reach the same verdict, via different theory:

| Criterion | MPST | MSC |
|---|---|---|
| Well-formedness | projection + **mergeability** | **realizability** / implied scenarios |
| Local type | session type (Send/Recv/⊕/&/μ) — direct to monitor/prompt | lifeline automaton — close to sequence diagrams |
| Choice | explicit (internal ⊕ / external &) | alternative of bMSCs |
| **Recursion** | μ-binder, natural | hMSC loop edge, somewhat more indirect |
| Refinements/contracts | natural at Send/Recv and branch | have to be glued on |
| LLM-agent relevance | Scribble ecosystem, lots of theory | arXiv:2604.17612, **mechanized in Lean 4** |

→ **Preliminary tendency:** MPST as the normative backbone (contracts/monitor/prompt fall out naturally from the Send/Recv types, μ directly available), MSC projection (Lean-4-mechanized) as a cross-check. Decision in L2.

---

## Convergence criteria — when do they "fit together"?

1. **Verdict equivalence:** MPST projectability ⇔ MSC realizability on every example. *(met for G_OK/G_BAD, recursive too.)*
2. **Layer compatibility:** the projected local type is exactly the interface that the SMT encoder, monitor, and prompt generator consume. *(met — all consume `casl_core`.)*
3. **Blame locality:** every contract violation at an oracle boundary is attributed to exactly one agent. *(met — blame A.)*

---

## Open points → drivers for the next iteration

- **[done]** Recursion/loops (retry loop as a μ-type) — built in, both projections.
- **[done]** Contracts/payloads on choice branches — `Branch` now carries `fields` + an optional `contract` (e.g. `len(reason)>0`); structurally unified across `Comm` and `Choice`.
- **[new, surfaced by recursion] Loop termination / budget decrease:** the retry loop raises the question of whether the loop terminates. The obvious approach: a contract "every retry consumes real budget" (`budget' < budget`) → as an SMT well-foundedness/termination lemma in round 2.
- **Branch contract not yet wired into monitor/SMT:** `len(reason)>0` is modeled, but monitor/SMT so far check only `cost<=budget`. Wiring to follow.
- **[hardened, W2]** Mergeability (MPST) and realizability (MSC) hardened against an adversarial 10-case battery: `merge` now recurses over common prefixes, and the realizability check examines the *first divergence* (not just the first event). MPST⇔MSC agree on all cases (`harden_equivalence.py`, anchored in the audit). Remains at spike level (one choice level per path), not a full algorithm.

---

## Round 2 — host-language spike (`TBD-004`)

Language strategy (3 axes, decision `CASL.md` v0.1.3): **spike substrate = Python (for now)**, **reference engine = Rust/OCaml**, **proof meta = Lean 4/F***. Since Lean 4 / F* / OCaml / Rust are not installed here, the current round is substrate-independent in Python. Round 2 prototypes **the same** core task — a type checker for (recursive) local types + a **soundness lemma** (e.g. capability containment, promise linearity) — in parallel across:

| Candidate | Role | Strength | to prototype |
|---|---|---|---|
| **Rust** | reference engine | move/borrow semantics = affine types → dogfoods `LH-Q-003a`/`LH-Q-002`; performant, distributable; `z3` crate | local-type enum + projection + capability check |
| **OCaml (+Z3)** | reference engine | lightweight, close to the compiler; F* extraction target | type checker + Z3 binding |
| **F*** | engine + proof | refinements + SMT built in → B **and** S in one language; extracts to OCaml | contract `cost<=budget` as a refinement type |
| **Lean 4** | proof | mechanized proofs; the MSC paper uses it | local type inductively + projection lemma |

Selection criteria: how naturally (i) the linearity/containment proof, (ii) SMT discharge, and (iii) monitor/prompt generation fall out of a language. Result → decision in L2.
