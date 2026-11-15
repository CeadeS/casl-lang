# CASL — Direction C: Mechanization (F* + Rust)

**Date:** 2026-06-15 · **Reference:** `CASL.md` v0.1.9 (`TBD-004` closed), `fstar/CASL.fst`, `prototype/`
**Status:** Verification scaffold **authored, not executed in this sandbox** (aarch64 without an F* binary). The Python audit (`prototype/audit.py`) remains the in-sandbox truth; F* is the parallel mechanization track for *machine* proofs on your machine.

## Decision (`TBD-004`)

| Axis | Choice | Why |
|---|---|---|
| Proof meta (B + S) | **F*** | Refinements + SMT (Z3) in one language → covers type proofs (B) *and* data contracts (S); extracts to OCaml/F#. |
| Engine | **Rust** | Extraction via **Pulse** (F* DSL for concurrent-imperative code) → **KaRaMeL** → Rust/C. Rust's move/borrow semantics = affine types ↔ our linearity (`LH-Q-003a`) and capability containment (`LH-Q-002`). |
| Spike substrate | **Python** (stays) | fast iteration; `audit.py` as the lived system. |

## Workflow

```
                 verify                       extract
  CASL.fst  ───────────────▶  (F* + Z3)  ──────────────▶  OCaml/F#   (Referenz-Interpreter)
     │                                       --codegen OCaml
     │  Pulse-Teile (imperative Laufzeit)        │  KaRaMeL
     └────────────────────────────────────────────▶  Rust / C        (performante Engine)
```

Locally: `fstar.exe fstar/CASL.fst` (verify) · `fstar.exe --codegen OCaml fstar/CASL.fst` (extract).

## Python kernel ↔ F* core (mapping)

| Python (`prototype/`) | F* (`CASL.fst`) | Proof status |
|---|---|---|
| `casl_core.gtyp/ltyp` (AST) | `gtyp` / `ltyp` | — |
| `spike_proj_mpst.project` / `merge` | `project` / `merge` (hardened, W2) | terminating (`decreases`) |
| `spike_smt_contract` (Z3) | `draft`, `retry_safe` | **[SMT]** — discharged by Z3 (already confirmed in Python) |
| `semantics.gstep` | `gstep` (inductive relation, incl. `GS_Rec`) | — |
| `metatheory` (subject reduction / correspondence / deadlock) | `preservation_full`, `fidelity_complete/sound`, `deadlock_free` | **proven (0 admits)** — subject reduction FULL incl. recursion (`preservation_full` over `GS_Rec`, via `subst_g_wf`); progress + `fidelity_sound` scoped to the head/rec-free fragment |
| `metatheory` (concurrency/W9) | `cgstep` (permutation/swap) + `diamond_indep` | **proven (0 admits)** — 4 roles (`RD`); independent actions commute (diamond) |
| `casl_core.gtyp/ltyp`, `project`/`merge`, full `wellformed` (Rust core) | `rust/casl-core/` (workspace, hand-written) | structure-faithful; `wellformed_core` = the full F* predicate; pinned to the F*-extracted verdicts on a 412-protocol differential (`tests/differential.rs`); **no** verified extraction |
| `kernel.wellformed`/`mpst.project` ↔ extracted F* core | `fstar/ocaml/` (extracted) + `prototype/tcb_bridge.py` | **TCB differential bridge** (`make -C fstar tcb-bridge`): both agree on a projectability corpus (offline; H1 sub-step) |

## What Already Holds vs. Open

- **Holds:** syntax, projection + hardened merge, the global reduction relation, the refinement contract `retry_safe` (the same statement that the Python Z3 spike already proved as UNSAT-of-the-negation → F* discharges it automatically via Z3).
- **Also holds (W9):** `cstep` is defined, the metatheorems are proven 0-admit, and for ≥4 roles the permutation/confluence is mechanized — `cgstep` + `diamond_indep` (global), `proj_skip` (projection ignores non-head roles) and `cstep_diamond` (the same commutation at the endpoint/configuration level). Independent actions thus commute mechanically at BOTH levels.
- **Also holds (H1 sub-step, `W11`):** the **TCB differential bridge** does not bind the running Python checker 1:1 to the proof, but shows by-test that the extracted F* core and the Python checker deliver the SAME verdicts on a projectability corpus (incl. 4 roles) — any divergence would be a bug on exactly one side. Full unification remains blocked by the krml/Eurydice Low* mismatch.
- **Open (Direction C):** the FULL inductive fidelity *under permutation* (config step of an independent non-head action ⇒ global swap step) as well as recursion-crossing concurrency — `metatheory.py` provides the exhaustive test evidence that supports these statements.
- **Open (async enhancement, `LH-F-010`/`W16`):** the buffered semantics (`prototype/semantics_async.py`) and its deny-by-default gate (`async_bounded`: k-bounded + orphan-free + deadlock-free, sync equivalence reported) are realized **by-test**, the proven synchronous core remains untouched. Async subtyping is in general **undecidable** (`docs/analyses/async.md`), so the mechanization deliberately targets ONLY the **bounded** fragment: the F\* formalization of the k-bounded async configuration (inbox as a bounded FIFO in the state, preservation of orphan-freedom/progress under `cstep`) is **tracked MAY-future** — the `cstep_diamond`/`proj_skip` core is the natural starting point for it.
- **Simplification of the first mechanization:** binary choice (two branches) instead of n-ary; extension is routine work.

## Next Steps

1. Verify `CASL.fst`: `make -C fstar verify` (F* 2026.03.24, **0 admits**).
2. Prove full inductive fidelity under permutation (swap step ↔ independent config step) — the `diamond_indep` core is in place.
3. Add n-ary choice + recursion well-foundedness (`LH-Q-009`) as refinements.
4. **[done] OCaml extraction runnable** — `make -C fstar ocaml-run` extracts the verified core, builds it with `fstar.lib`/dune, and runs the driver (`fstar/ocaml/driver.ml`). This is the **verified** core as running code.
5. **[done] Rust reference core** (`rust/casl-core/`, promoted from the former `engine/` into the `rust/` workspace, P4) — a hand-written, idiomatic-Rust crate that mirrors `gtyp/ltyp`, `project`/hardened `merge`, capability containment, and now the **full** `wellformed_core` (`contractive ∧ no_self ∧ gdistinct ∧ closed ∧ projectable for {C,A,J,D}`, matching `fstar/CASL.fst`). Its verdicts are pinned to the F*-extracted kernel by a **412-protocol conformance differential** (`tests/differential.rs`, corpus single-sourced from `casl.tcb_corpus`); `cargo test` is green. Dogfoods Rust's move/borrow semantics ↔ linearity (`LH-Q-003a`). The strangler-fig step toward the Rust core becoming authoritative (retire Python on parity).
6. **[done] Oracle boundary (Direction A)** — `prototype/oracle.py` binds the Ollama endpoint (`.env`, OpenAI-compatible) as a real, nondeterministic oracle: agent A produces a real `Draft` response, the synthesized monitor checks the contract `cost<=budget` at the boundary (ok → Accept, violation → Blame A, refusal/malformed → typed Refusal). Live-verified against the dedicated vLLM server (betty, default model `google/gemma-4-31b-it`; early validation also with `granite3.1-moe:3b`). H4 hardening takes effect for real here: the monitor checks the out-of-band measured `completion_tokens`, not the oracle claim. In the lived system the building block `kernel.oracle_boundary` runs with a deterministic mock (the audit stays offline-green).

## Finding: Why Rust = Engine (Not Verified Extraction)

F* has **no** direct Rust codegen; the path would be `--codegen krml` → **KaRaMeL** → **Eurydice** → Rust. This path targets **Low\*** (machine integers, GC-free, allocation-lean). Our verified core is the opposite: **string-labeled, recursive session types with `option`** — the natural extraction target for this is **OCaml** (step 4, done), not Low\*/Rust. `krml` is available via opam (`karamel 1.0.0`) and Eurydice is buildable, but they would hit an "unsupported feature" on our ADT core.

Therefore (consistent with `TBD-004`): **OCaml carries the verified core, Rust is the engine.** The engine is *by construction* spec-faithful and pinned against F*/Python via `cargo test`. A *verified* Rust extraction would require the core rewritten in **Pulse**/Low\* (imperative runtime code) — deliberately future work, not a blocker for the engine.
