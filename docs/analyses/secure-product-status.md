# CASL — secure-product status (honest assurance map)

*Written 2026-06-27. A truthful snapshot of what RUNS, what is PROVED vs PINNED vs TESTED vs GATED, and what
remains. The project's discipline is "grade honestly — every layer is only as strong as it actually
enforces"; this doc applies that to the whole system. Verified state at the time of writing: pytest 216
passed / 1 skipped, living audit ✓ PASSED, whole Rust workspace fmt/clippy/test green, both Verus proofs
green (`no_self_verus` 5/0, `wellformed_verus` 28/0).*

## 1. Does it run? Yes.

- **Python reference** — fully runnable end to end: `casl check` (the gate), `casl new` (requirements →
  verified, conducted project), `casl run --project` (the conductor through the broker), `casl gate` (the
  obligation gate). `./scripts/demo.sh` runs the whole loop; the conductor runs the **mock** oracle, a
  **real program/agent** (the activity executor), or a **live local model** (Ollama, no key).
- **Rust workspace** — `casl-proto`, `casl-broker`, `casl-core`, `casl-host` (policy), `casl-surface`
  (parser), `casl-check` (checker) all build + test green.

So "a running version for testing and checking" exists today. "Secure" is the graded story below.

## 2. The assurance ladder (proved > gated/pinned > tested > attested)

**PROVED (machine-checked).**
- **F\*** (`fstar/CASL.fst`, 0 admits) — the MPST core: projection, well-formedness, and the metatheory
  (preservation/progress for the recursion-free fragment + the proven recursion lemmas). This is the
  spec/proof of record; `casl check --authoritative` runs the F\*-extracted (OCaml) checker as the trusted
  verdict.
- **Verus** (`rust/proofs/`) — the **Rust** well-formedness checker: `no_self`, `gdistinct`, `closed`,
  `contractive`, and the combined `wf_noproj` each proved to **refine their logical spec**, **terminate**,
  and be **panic-free**. This is the full *structural* `wellformed_core` (everything except the `projectable`
  conjunct). Caveat: it proves the *implementation matches the predicate* (functional correctness), not the
  MPST metatheory (that stays in F\*); the model uses faithful abstractions (n-ary branches as a cons-list to
  sidestep a documented Verus `Vec`-of-recursive limitation; roles/labels as `usize`).

**DIFFERENTIAL-PINNED (Rust == Python == F\*-anchored verdict, on a single-sourced corpus).**
- wire protocol (parity tests) · broker monitored verdicts (`test_conformance`) · well-formedness
  (`casl-core`, 412-protocol differential, F\*-anchored) · the **parser** (`casl-surface`, 28-protocol AST
  differential) · the **checker verdicts** (`casl-check`, 35-protocol differential: well-formedness (core
  predicate + the user-facing line with MSC-realizability), capability containment, approval dominance,
  pipeline-safety, promise-linearity, stream-safety, termination, crash-tolerance, ttl-safety — **10 of the
  11 `casl check` gate checks**).

**TESTED / characterization-pinned (no proof — pinned to the Python reference by-test).**
- capability containment, approval dominance, pipeline-safety, promise-linearity, stream-safety, termination,
  crash-tolerance, ttl-safety, and the user-facing well-formedness line (MSC-realizability) — these have **no
  F\* proof in either language**; their grade says "tested, not proved." The Rust ports are pinned to the
  Python authorities (`kernel.capabilities`, `kernel.approval_safety`, `spike_pipeline.pipeline_safe`,
  `kernel.linearity`, `kernel.stream_safe`, `kernel.termination`, `kernel.crash_tolerance`,
  `kernel.ttl_safety`, `kernel.wellformed`).

**ATTESTED (trusted by a human signature, opt-in).**
- artifact bodies + single-purpose capability providers; a spawned activity runs at *attested* grade until
  rung-3 confinement wraps it.

## 3. Retirement-to-Rust parity ledger

| Component | Rust | Pinned by | Status |
|---|---|---|---|
| wire protocol | `casl-proto` | parity tests | ✅ |
| reference monitor | `casl-broker` | `test_conformance` | ✅ |
| well-formedness (core predicate) | `casl-core` | 412-protocol differential (F\*-anchored) | ✅ |
| confinement **policy** | `casl-host` | policy unit tests | ✅ (enforcement Linux-gated) |
| **parser** | `casl-surface` | 28-protocol parse differential | ✅ |
| **checker** (wellformed_core + user-facing/MSC + capability + approval + pipeline + linearity + stream + termination + crash + ttl + **concurrency_certified**) | `casl-check` | 37-protocol verdict differential | ✅ (**11 of 11** always-run gate checks) |
| concurrency (LH-Q-001d) | `casl-check::concurrency` | 37-protocol verdict differential (both polarities) | ✅ NEW — bounded operational LTS (correspondence_class) over `casl-core::project`; characterization-pinned |
| remaining checks (branch_contracts, async_bounded) | — | — | branch_contracts = **vacuous** under the {le,nonempty} contract grammar; async_bounded = conditional (async-only; k-bounded state-space enumeration, L/hi) |
| user-facing well-formedness (own roles + MSC) | `casl-check` | 35-protocol verdict differential | ✅ |
| **project**: manifest + dependency ledger + typed seam + grade-flow + grade-composition | `casl-project` | 18-manifest + 8-ledger + 9-seam + 5-grade + 7-grade-composition differentials | ✅ (Track C, 5 bricks) |
| project: obligation **gate** (attestation crypto + git line-trace) · grade **re-base** (z3 SMT) | — | — | Python-only (security-central; deliberate, not rushed) |
| **conductor / interpreter** (`run_protocol` deterministic core — the runtime TCB) | `casl-conductor` | 14-case run-trace differential | ✅ (deterministic core; live-LLM/broker-dispatch out) |
| **front-end** (`casl` binary: `check` / `run` / `project` / `deps` / `seam` / `flow`) | `casl-cli` | 20-case exit-code differential + deferred-verb/version contract | ✅ (full verdict on ALL sync protocols; un-ported verbs decline with exit 2; only `async` ⇒ exit-2 UNDETERMINED, never wrong-accept) |
| synthesis / IDE / deferred verbs (`new`/`synth`/`ide`/`gate`/`trace`/`blame`/`observe`/`init`) | — | — | Python-only (the Rust `casl` defers to them) |

## 4. What remains — and why it is not an overnight job

- **Remaining checker ports** (branch_contracts, concurrency-certified, async-bounded): `branch_contracts` is
  **vacuously true** under the current contract grammar — `casl-surface` ALREADY parses the structured relation
  (`('le',·,·)` / `('nonempty',·,·)`, pinned by the parse differential), and the monitor synthesizer covers
  exactly those two forms, so no parseable protocol can make the check fail. It becomes a meaningful
  differential target only if the contract grammar grows beyond what `synth_monitor` handles; deferred as
  low-value for now. `concurrency-certified` (swap/confluence ≥4 roles) and `async-bounded` (k-bounded
  reachability; undecidable in general, W16) are L/hi prototype semantics — each a *separate* brick (mirror the
  sub-module, extend the differential, characterization-pin), deliberately **not rushed**: a subtly-wrong
  security check is worse than a missing one.
- **The `projectable` Verus conjunct** (to complete `wellformed_core`): needs `project`/`merge` proved in
  Verus — substantially harder than the structural conjuncts. The "gold" alternative is **Aeneas → F\***
  (translate the real Rust into F\* and reuse `CASL.fst`), which also dissolves the `Vec` limitation.
- **The project/conductor/CLI Rust ports**: the bottom-up retirement order continues after the checker.
  **Track C has started** — `casl-project` now ports the manifest load/validate (deny-by-default structured
  validation: kind/grade/trace/body rules, LH-F-013/LH-P-009/LH-Q-016) and the dependency burden ledger
  (LH-Q-020) at parity, each differential-pinned (18 manifests + 8 ledgers). The next project bricks (the
  typed **seam**, **grade-flow**, the **obligation gate**) are security-central; each will be a
  differential-pinned brick, deliberately reviewed rather than rushed. `casl-conductor` (interpreter core)
  and **`casl-cli` are now DONE** — the single use-ready `casl` binary exists, wiring the at-parity crates
  behind an exit-code differential. What's left to fully retire the Python CLI: the deferred engines
  (`gate`/`synth`/`ide`/`new`/`trace`/`blame`/`observe`/`init`, which the Rust `casl` cleanly defers to
  Python today). The 11th MUST check, **`concurrency_certified` (sync), is now ported** — the checker is
  complete on the synchronous fragment and the front-end gives a full verdict on every sync protocol; the
  last residual is `async_bounded` (async-only), after which the `async`-UNDETERMINED fallback becomes a
  full verdict too.
- **rung-3 OS confinement** (the enforced-grade upgrade for activities/untrusted code): the *policy* is
  written + unit-tested and the seccomp mechanism is verified on Linux, but the production Rust host +
  netns + WASI need a **Linux + Rust runner** — not available on this macOS dev machine.
- **Live cloud LLM**: the transport is wired and works against a local stub / Ollama with **no key**; the
  hosted providers need an **API key** (which is never embedded or handled here).
- **TCB unification** (F\*→extraction so the *running* artifact is the *proved* one): blocked for the
  current core's algebraic style by the krml/Eurydice pipeline (`TBD-004`); OCaml extraction already gives a
  proved artifact, and the Rust is differential-pinned to it.

## 5. Honest verdict

CASL **runs**, and it is **secure in the graded sense the project promises**: a machine-proved deterministic
hull (F\* + now a machine-proved Rust well-formedness checker), a monitored runtime (the broker reference
monitor, contract + cost monitors, no-ambient-authority), and honest grades that never claim more than is
enforced. It is **not** a *finished* "fully retired to Rust, fully proven, fully confined" product — that is a
multi-stage program. Recent work advanced it on several fronts (the full structural well-formedness **proof**;
the **checker port** now covering **10 of the 11 `casl check` gate checks** — well-formedness core + the
user-facing line/MSC, capability, approval, pipeline, linearity, stream, termination, crash-tolerance,
ttl-safety — each differential-pinned to the Python authority over 35 protocols; and this map), each
individually verified, with the remaining work scoped (only the vacuous `branch_contracts` and the L/hi
`concurrency_certified` checker checks remain) and the genuinely-gated items (Linux confinement, cloud keys,
F\*→extraction) named rather than faked.
