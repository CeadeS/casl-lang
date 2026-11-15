# Retiring Python — the strangler-fig roadmap

*Design analysis. How CASL's Python reference is retired component-by-component in favour of the Rust
implementation, behind the frozen wire protocol + a conformance differential, "never two unpinned impls,
retire on parity." Formalize → literature → variants → compare → synthesize → residuals. Companion to
docs/engineering-plan.md (the WBS) and docs/architecture.md.*

## 1. What "retire Python" means (and does not)

"Retire" a component C means: its Rust twin R becomes the **authoritative** implementation and the Python C
is **deleted**. It does **not** mean:

- **Retiring the proof.** F\* stays the spec/proof of record. A hand Rust rewrite does *not* close the TCB
  gap — only F\*→extraction (P7, blocked today by krml/Eurydice) makes the *running* artifact the *proved*
  one. Retiring Python makes Rust the authoritative *implementation*; F\* remains the authoritative *proof*.
- **A big-bang cutover.** Python is removed per-component, only after R is conformance-pinned to it, and the
  step is reversible until the cut.

Today the system is **~11.9 kLoC Python (≈65 modules)** vs **~2.1 kLoC Rust (4 crates)**. Rust covers the
wire (`casl-proto`), the reference monitor (`casl-broker`), the confinement *policy* (`casl-host`), and
**well-formedness only** (`casl-core`). The parser, the full checker, the conductor/interpreter, the
project/trust layer, synthesis/IDE, and the CLI are Python-only.

## 2. The retire-criteria (formal)

A component C is **retire-eligible** iff all hold:

1. **Frozen contract.** C's interface is a stable, versioned boundary (the JSON-RPC wire for the broker; the
   canonical IR for the checker/parser; a manifest schema for the project layer).
2. **Conformance differential.** A single-sourced corpus `X` and an oracle `O` exist such that
   `∀ x∈X. R(x) = Python(x) = O(x)` — the corpus is emitted from one source (no hand-duplicated expectations),
   and the verdict is anchored (to F\* where a proof exists; to the Python reference by characterization
   otherwise).
3. **No second unpinned impl.** After the cut, exactly one implementation is authoritative for that contract;
   the other is deleted or demoted to a regression guard.
4. **Reversible until cut.** Python stays runnable behind a flag until R has soaked; the cut is one small,
   independently-verifiable change.

This is the existing project discipline, not a new invention: the broker (`tests/test_conformance.py`,
both brokers over one corpus) and well-formedness (`rust/casl-core/tests/` 412-protocol differential) already
satisfy it. The roadmap is to extend the *same* mechanism to the remaining components.

## 3. Parity ledger (per component, today)

| Component | Python | Rust | Pinned by | Status |
|---|---|---|---|---|
| wire protocol | broker/client | `casl-proto` | parity tests | **parity ✓** |
| reference monitor | `broker.py` | `casl-broker` | `test_conformance` (both brokers) | **parity ✓** (Python broker still used in-process) |
| well-formedness | `kernel`/`core` | `casl-core` | 412-protocol differential (F\*-anchored) | **parity ✓** |
| confinement policy | `host.py` | `casl-host` | policy unit tests (enforcement Linux-staged) | **parity ✓ (policy)** |
| surface parser | `surface.py` | `casl-surface` | 28-protocol parse-differential | **parity ✓ (brick 1)** |
| checker (core) | `check.py`/`kernel` | `casl-check` (`wellformed_core` + capability containment) | 28-protocol verdict differential | **brick 2 ✓ — rest pending** |
| checker (user-facing well-formedness: own roles + MSC) | `check.py` | — | — | pending (stricter `wellformed_core` ported first) |
| project / seam / capability / grade | `project`/`seam`/… | — | — | Python-only |
| conductor / interpreter | `conductor`/`run` | — | — | Python-only |
| synthesis / IDE / CLI | `synthesis`/`ide`/`check` | — | — | Python-only |
| audit / observability / completeness | (tooling) | — | — | Python-only (dev-tooling; may never need porting) |

## 4. Literature

- **Strangler fig** (Fowler; AWS Prescriptive Guidance): grow the new system around the old, replace
  component-by-component, **never bet the system on a single cutover**; each step small, reversible,
  independently verifiable.
- **Characterization / golden-master + differential testing**: prove the new path behaves *identically* to
  the old by capturing the legacy behaviour (quirks and edge cases) as tests and running both paths on
  identical inputs — "the tests become the proof that the replacement is safe to switch over." This is
  exactly our conformance-differential rule.
- **Rust parsing strategies**: hand-written recursive descent is "more fit-for-purpose, more readable," with
  no framework constraint; the caveat (poor fit for *unstable, evolving* grammars) does not bite here — the
  `.casl` grammar is small, stable, and already has a reference parser to mirror. `nom`/`chumsky`/`pest` add
  a dependency (a new entry in CASL's burden ledger), and PEG/untyped output drifts from the AST.

## 5. Variants

### 5a. Port order

| | V1 bottom-up (data-first) | V2 top-down (CLI-first) | V3 risk-first (TCB-first) |
|---|---|---|---|
| Sequence | parser → checker → project → conductor → CLI | CLI/conductor shells first, call into Python | the safety checks / proved core first |
| Each step independently runnable + pinnable | **yes** (each layer feeds the next) | no (shells need the lower layers) | partial (checks need a parsed AST) |
| Differential is natural | **yes** (text→IR, IR→verdict, …) | hard (end-to-end only) | medium |
| Matches what's already done | **yes** (proto→broker→core was bottom-up) | no | no |

### 5b. Parser strategy

| | hand-written recursive descent | nom / chumsky (combinators) | pest (PEG) |
|---|---|---|---|
| New dependency (burden ledger) | **none** | yes | yes |
| 1:1 readability vs `surface.py` | **highest** (mirrors it line-for-line) | medium | low (separate grammar file) |
| Differential-pin auditability | **highest** | medium | low (untyped output → AST drift) |
| Error control / recovery | full | good (chumsky) | poor |
| Risk | low (grammar is small + stable) | exp-backtracking footguns | grammar/AST sync drift |

## 6. Synthesis — the plan

**Order = V1 bottom-up; parser strategy = hand-written recursive descent, zero-dependency, mirroring
`surface.py` 1:1.** Both maximize the project's stated weighting (security + understandability over speed):
no new supply-chain burden, a parser whose every line maps to the audited Python reference, and a differential
that is trivial to anchor.

Staged retirement, each stage gated by §2's criteria:

1. **`casl-surface` (the parser) — NEXT.** Rust `.casl` text → the IR `casl-core` consumes. Pin with a
   **parse-differential**: a corpus of `.casl` text + its canonical AST (JSON), single-sourced from the
   Python parser; `R(text)` must reproduce it. Retires `surface.py` on parity. *(This turn: build the Python
   oracle + the Rust crate + the differential; cargo verification is CI-gated.)*
2. **`casl-check` (the remaining MUST checks).** Capability containment, approval-dominance, concurrency,
   async-bounded, pipeline, contracts — into `casl-core`/a new `casl-check`. Pin by extending the differential
   with the *safety verdict* per corpus protocol. **Honest caveat:** only well-formedness has an F\* proof;
   these checks are anchored to the Python reference *by characterization*, not to a proof.
3. **`casl-project` (trust layer).** Manifest load/validate, seam, capability/provider index, grade-flow,
   obligation gate. Pin with manifest-fixture differentials.
4. **`casl-conductor` (interpreter).** Pin with run-trace differentials (same `.casl` + scenario ⇒ same trace
   + verdict + grants), reusing the broker that is already at parity.
5. **CLI + synthesis/IDE.** The front door retires last; `casl` becomes the single Rust binary (P6 = GA).

`audit`/`observability`/`completeness` are dev-tooling, not runtime TCB — they may stay Python indefinitely.

## 7. Residuals (honest)

- **The proof is untouched.** Retiring Python ≠ closing the TCB gap. Until F\*→extraction, the *proved*
  artifact (F\* `wellformed`) and the *running* one (Rust) are pinned to each other by the differential, not
  unified. Stage 2's non-core checks have *no* proof at all — they are tested, not verified; their grade
  reflects that.
- **The parser is outside the proved hull.** A parser bug cannot violate the proved hull (the hull is checked
  on the AST), but a parser that silently builds the *wrong* AST misrepresents intent. Defense: the
  parse-differential **plus fuzzing** (random well-formed `.casl` ⇒ Python-AST == Rust-AST).
- **Write-blind velocity tax.** This environment has no Rust toolchain, so Rust ports are written here and
  verified only by CI — a slow loop. A local Rust+Linux dev loop (or a Rust-capable runner) is the right
  investment before the heavier stages (checker, conductor).
- **Don't retire prematurely.** Until a stage's differential is green in CI *and* has soaked, Python stays the
  default; the cut is the last, smallest step.
