# Remaining steps — the plan to a finished, secure CASL

*Written 2026-06-27. A sequenced plan for the open work in `docs/analyses/secure-product-status.md`. Every
brick follows the project pipeline — **draft → research → propose alternatives → compare → synthesize →
verify → implement** — and the standing discipline: never two unpinned implementations, retire-on-parity,
honest grades, one verified brick per commit, and **signed merges/tags are the user's act**.*

Legend — effort: S/M/L · risk: lo/med/hi · who: **me** (non-gated, verifiable here) / **you** (signed act
or an environment I don't have).

---

## Track 0 — Land what already exists (you; S)

Six stacked branches (`quickstart-e2e → … → feat/overnight`, 10 commits) are verified and pushed but not on
`main`. This blocks everything else from being "real."

- **0.1** Merge the tip: `git merge --no-ff -S feat/overnight` (signed — the diff touches `check.py`, a
  CODEOWNERS path), then push. Lands all six branches. (commands: `docs/RELEASES.md §7`.)
- **0.2** Tag the batch v0.31.1 … v0.40.0 (`docs/RELEASES.md §1–7`).
- **0.3** (optional) `git push origin --delete feat/synthesis-loop` (the stray ancient branch).

*Until 0.1, the Rust parser/checker/broker, real execution, and the proofs live only on branches.*

---

## Track A — Finish the Rust checker (`casl-check`) — retirement, bottom-up (me)

Goal: `casl-check` reproduces **every** `casl check` MUST/SHOULD verdict, so the Python checker's verdict path
can retire. Each brick = mirror the Python check (on the surface AST or via casl-core) → single-source the
verdict into `check_corpus.py` → extend the Rust differential → verify (`cargo` + `pytest` + `audit`). Done so
far (**10 of 11 gate checks**, 35-protocol differential): well-formedness (core predicate + user-facing/MSC),
capability containment, approval-dominance, pipeline-safety, promise-linearity, stream-safety, termination,
crash-tolerance, ttl-safety.

Ordered by dependency + ascending risk:

- **A1 — user-facing well-formedness** (own declared roles + MSC-realizability). ✅ DONE (`815a9f8`).
  Distinguishes `casl check`'s line from the stricter `wellformed_core`; faithful MSC-realizability port.
- **A2 — `pipeline_safe`** (oracle monitored; `oracle ⊕ verified` exclusive). ✅ DONE (`1ce726a`) — structural.
- **A4 — `linearity`** (promise resolve-once / write-once). ✅ DONE (`6501d8a`) — ported `hard.linearity_check`
  onto casl-core (promise = oracle output; counted once along the producer's projected local type).
- **A5 — `stream_safe`** (env-driven loop, handlers terminate). ✅ DONE (`1a1a4b7`) — ported
  `spike_hardening.stream_wellformed` + `_handler_terminates` on the surface AST.
- **A-term — `termination`** (every non-`stream` loop declares a ranking measure). ✅ DONE (`ca206f1`) —
  the well-founded ranking lemma is a protocol-independent SMT tautology (constant True), so no z3 in Rust.
- **A-crash — `crash_tolerance`** (crash-prone sender ⇒ typed `on_crash`). ✅ DONE (`38c32de`) — structural.
- **A-ttl — `ttl_safety`** (finite-ttl cap in a loop ⇒ ttl ≥ iteration bound; stream refreshes per
  iteration). ✅ DONE (`79e9c80`) — surface-AST walk with a 3-state loop bound.
- **A3 — `branch_contracts`** (every branch contract synthesizes a sound monitor). **Vacuous → deferred.**
  NOT parser-blocked: `casl-surface` already parses the structured relation (pinned by the parse
  differential). But under the current grammar {`('le',·,·)`, `('nonempty',·,·)`} the monitor synthesizer
  covers every producible relation, so the check can never fail on a parseable protocol. Worth porting only
  if the contract grammar grows; low value now.
- **A6 — `concurrency_certified`** (swap/confluence ≥4 roles). L/hi — prototype semantics.
- **A7 — `async_bounded`** (k-bounded reachability: bounded + orphan-free + deadlock-free). L/hi — the
  hardest; undecidable in general (W16), so port the k-bounded enumerator faithfully.
- **A8 — combined gate verdict** — differential on the full MUST conjunction (accept/reject) so the Rust
  `casl check` matches the Python end to end.

**Cut:** once A1–A8 soak green in CI, retire the Python checker's verdict path (keep Python as a regression
oracle until then).

---

## Track B — Finish "prove the Rust" (Verus / F*) (me, partly gated)

Done: the full **structural** well-formedness (`no_self`, `gdistinct`, `closed`, `contractive`, `wf_noproj`).

- **B1 — the `projectable` conjunct in Verus** → completes the `wellformed_core` proof. L/hi — pulls in
  `project`/`merge` (mergeability + the non-local-choice rejection); the genuinely hard proof.
- **B2 — (alternative / strategic) Aeneas → F\***. L/hi, **needs Charon + Lean installed**. Translate the real
  `casl-core` Rust into F\* and prove it against the *same* `CASL.fst` spec — this would (a) prove the actual
  Rust (not a faithful model), (b) dissolve the `Vec`-of-recursive Verus limitation, and (c) move toward TCB
  unification. Recommend a scoping spike before committing.
- **B3 — prove a ported *checker* (not just well-formedness)** e.g. capability containment in Verus — turns a
  "tested" grade into "proved" for a security check. M/med, after A + the Verus pattern is mature.

---

## Track C — Continue the retirement past the checker (me)

Bottom-up order resumes once the checker is done:

- **C1 — `casl-project`** → Rust; differential-pinned. L/med. **5 bricks DONE:** ✅ manifest (`111ac46`)
  + ✅ dependency ledger (`bdd3971`) [merged to main] + ✅ typed seam (`3b13754`) + ✅ grade-flow structural
  (`14099da`) + ✅ grade-composition (`4f8be89`) [on `feat/track-c`, awaits merge]. **DEFERRED (security-central,
  for a supervised session):** the obligation **gate** (attestation-signature crypto + git line-trace +
  keyring), and the grade **re-base** (z3 SMT contract entailment + CERT-FID).
- **C2 — `casl-conductor`** (the interpreter) → Rust; pinned by run-trace differentials (same `.casl` +
  scenario ⇒ same trace + verdict + grants), reusing the already-at-parity broker. L/med.
- **C3 — `casl-cli` + synthesis/IDE** → the single Rust GA binary (`casl` on PATH). Retire the Python CLI
  last. L/med. *This is the "use-ready" milestone.*
- `audit`/`observability`/`completeness` stay Python (dev-tooling, not runtime TCB) unless a reason appears.

---

## Track D — Gated: needs you or an environment

- **D1 — rung-3 OS confinement** (enforced-grade for activities/untrusted code): the Rust `casl-host` syscall
  port + empty-netns + seccomp + rung-4 WASI. **Needs a Linux + Rust runner/CI** (this dev box is macOS; the
  policy is already written + unit-tested and the seccomp mechanism is verified on Linux).
- **D2 — live cloud LLM** (hosted Claude/Gemini/OpenAI): **needs an API key** (I won't embed/handle one).
  Local Ollama already works with no key.
- **D3 — TCB unification** (F\*→extraction so the running checker *is* the proved artifact): blocked by
  krml/Eurydice for the algebraic core (`TBD-004`); revisit if the Aeneas path (B2) matures.

---

## Recommended sequence

1. **You:** Track 0 (merge + tag) — make it all real on `main`.
2. **Me, interleaved:** Track A brick by brick (start A1/A2 — lowest risk, highest parity value) alongside
   **B1** (the projectable proof) when I want a depth day.
3. **Me:** Track C (project → conductor → CLI) once the checker is complete → the use-ready Rust binary.
4. **When unblocked:** D1 (give me a Linux+Rust runner), D2 (a key), B2 (install Charon+Lean), D3 (after B2).

Inherent limits remain by design (not "steps"): requirement↔spec fidelity (validation ≠ verification);
seccomp "modulo timing/covert channels"; characterization-pinned checks carry a "tested, not proved" grade.

**Next non-gated brick I'd pick:** A2 (`pipeline_safe`, structural, low risk) or A1 (the user-facing
well-formedness, highest parity value), or B1 if you want the hard proof. Say which and I run the pipeline.
