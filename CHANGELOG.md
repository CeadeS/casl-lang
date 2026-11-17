# Changelog

All notable changes are recorded here. Versions follow SemVer; the authoritative
per-requirement history lives in the Git tags, the `LH-*` requirements, and the
CEP decision records under `proposals/`.

## [Unreleased] — OS pilot: signed approvals, effect outcomes, run journal

The broker pieces the AI-OS pilot needs (approve one concrete action → perform it through the broker → keep
the record). Both brokers, pinned by shared corpora (`tests/test_approval_signed.py`, `tests/test_effect_journal.py`).

- **Signed approvals** (`casl.approval`, `casl-broker::approval`): with a trust store, `consent` mints a token only
  for an Ed25519-signed approval bound to request digest, site, capability, program version, nonce and expiry.
  An `approved: true` assertion then mints nothing (closes agent self-approval). Approver classes
  `human` < `personal`, minimum per capability.
- **Request-bound consent at Rust parity**; the Rust digest reproduces the reference byte for byte.
- **Mediated egress in the Rust broker** (`casl-broker::egress`) with a destination check stricter than the
  reference.
- **Effect outcomes**: `performed` · `rejected` · `not_sent` · `unknown`. An irreversible request whose outcome is
  unknown is blocked — even with a fresh approval — until `resolve`d (no blind repeat). New method `resolve`.
  The destination policy now runs before consent is consumed.
- **Run journal** (`casl.journal`, `casl-broker::journal`): broker-owned SQLite file, append-only and
  hash-chained; approval → intent (before the send) → result. Replay protection and unknown outcomes survive
  a restart. `python -m casl.journal verify PATH` / `casl-broker verify-journal PATH`.
- **Live HTTPS leaf** (`casl-broker::live`, ureq + rustls): no redirects, no environment proxy, resolved
  addresses must be public; only failures that prove the request never left count as `not_sent`.
- **Broker-held credentials**: a mediated capability can add headers on the wire (`Authorization`); a request
  that supplies such a header itself is refused.
- **Approvals name the target account** (casl-lang#2): when the broker holds a credential for a capability,
  the approval must carry that credential's identity (`account`); it is compared at consent and again at
  execution (`account_mismatch`, `account_unbound`). Identity = a configured reference or
  issuer/tenant/subject derived from the JWT (`--account ID` | `--account-from-token`); journaled, never
  the secret. `tests/test_account_binding.py`.
- **Reservations across broker processes** (casl-lang#4): using an approval, starting an attempt and
  resolving one are guarded appends — state replay, check and write in one journal transaction. Twelve
  concurrent `casl act` on one approval perform once.
- **Attempts, scoped to the account** (casl-lang#5): an irreversible request has an attempt id; an unknown
  outcome blocks the scope (account, request digest), not the digest alone; `resolve` takes the attempt
  (`casl resolve --attempt N`) and reports whose it was. Effect results carry `attempt`, `account`,
  `request` instead of `effect`.
- **Context grants, the contract** (casl-lang#6; `docs/context-grants.md`): a capability can declare the
  data scope it requests — `context search|read source "…" resource "…"` or
  `context disclose receiver "…" from <caps>` — validated at parse (Python + Rust, an unsupported clause
  does not parse). `casl.context` / `casl-broker::context`: signed grants (user key, or OS policy key
  inside a user-signed frame, or derived from a parent grant), containment, intersection for delegation,
  and the typed decision `granted | needs_grant | denied`. One corpus of 43 decisions, 39 verifications,
  9 intersections and 16 rejected programs drives both implementations. Example
  `examples/os_pilot/seminar_review.casl`. No runtime enforcement yet (casl-lang#7).
- **Host interface** (`casl prepare | act | resolve | journal verify`, Rust CLI): one approved action through
  the broker, JSON out. Template `examples/os_pilot/create_task.casl`; walkthrough `docs/os-pilot.md`;
  end-to-end acceptance `tests/test_os_pilot_act.py`.
- New Rust dependencies: `ed25519-dalek`, `sha2`, `rusqlite` (bundled), `ureq`. Python stays stdlib-only
  (`casl.ed25519` is an RFC 8032 reference for tests/tooling).

Open: `act` runs one site, not the conducted choreography; signed/anchored journal head; key validity
windows and issuer-signed approver credentials; `resolve` is not yet signed; OAuth token refresh.

## [0.45.0] — 2026-06-30 — mediated-egress reference (b) + Layer-2 review scaffold

The offline-safe Python **reference** for generic mediated egress (b), red-team-hardened, plus the **Layer-2**
semantic-review scaffold. Both additive — v0.44.0 approval-binding + the 28-case Python↔Rust conformance
parity are untouched. See `docs/analyses/mediated-egress-and-approval-tokens.md` §8.

### Added
- **`casl.egress` — generic, domain-agnostic mediated egress (offline-safe reference).** `DestinationPolicy`
  (https-only, host allowlist, loopback/link-local/private blocked **before connect** — the SSRF guard),
  `RequestSpec.digest()`, `MockTransport`, `MediatedCapability`. The broker gains a `transports` registry: it
  PERFORMS a request under an abstract capability (`net:http`) and **request-binds** the one-shot consent
  token (red-team Crit-2). Additive — no live network, parity preserved. Live HTTPS transport + Rust parity
  deferred (supervised).
- **`casl.review2` — Layer-2 semantic requirement review (scaffold).** Per-requirement LLM review over the
  changed files, **vetoes-never-vouches**, oracle pluggable (mock offline); complements the formal Layer-1
  `casl.requirecheck`. Real wiring = the broker's monitored `llm:*` oracle.

### Verified
Python: **269 passed / 21 skipped** (the 2 pre-existing rust-corpus-sync failures unchanged); `casl.audit` ✓.
Mac cross-impl: 28 conformance green (parity intact). New tests: `test_mediated_egress`, `test_review2`.

### Deferred (supervised / needs Mac+Linux)
Live HTTPS transport (the audited leaf); **Rust parity** for the egress path; B (conductor-driven app
effects); C (confinement rung-3/WASI). WASI `wasi:http/outgoing-handler` is the by-construction endgame.

## [0.44.0] — 2026-06-29 — approval-binding at Rust parity + mediated-egress design

(a) The broker's approval-binding (one-shot consent token for irreversible caps) now lands in the **Rust**
broker at parity with the Python reference, pinned by the cross-impl conformance corpus — closing the
Python/Rust gap v0.43.0 opened. (b) A red-team-hardened design for **generic mediated egress** (the broker
performs I/O under an abstract `net:http` capability so programs do no raw I/O and CASL stays
domain-agnostic); its code is deferred to a supervised build. See
`docs/analyses/mediated-egress-and-approval-tokens.md`.

### Added
- **Rust broker approval-binding (`rust/casl-broker`, `rust/casl-proto`).** A `consent` method + one-shot
  token bound to `(cap, site)`; `effect` denies an irreversible cap without a fresh matching token,
  mirroring `src/casl/broker.py`. New `EffectParams.approval`, `ConsentParams`/`ConsentResult`.
- **5 cross-impl conformance cases (`tests/test_conformance.py`)** pinning (a) across BOTH brokers:
  irreversible-needs-token, withheld, consent→effect, one-shot, site-mismatch; harness gained multi-call
  sequences + `irreversible_caps` threading. **28 conformance cases green.**

### Verified
Rust (Mac): workspace `cargo test` + `clippy -Dwarnings` + `fmt --check` clean. Python: **256 passed / 21
skipped** (the 2 pre-existing rust-corpus-sync failures unchanged); `casl.audit` ✓.

### Designed (deferred — security-central)
Generic mediated egress (b): broker performs I/O via a per-capability transport; domain-agnostic; consent
must bind the **request digest**; destination policy is **manifest-sourced**; the egress performer is a
separate audited component. WASI host-imports (`wasi:http/outgoing-handler`) are the by-construction endgame.

## [0.43.0] — 2026-06-29 — approval-binding (A) + the Layer-1 requirement checker

Closes the approval-gate bypass as a *class*: an irreversible effect can no longer happen on a path that
never sought consent. Plus the deterministic, per-commit requirement checker. See
`docs/analyses/requirement-checker-and-approval-binding.md`.

### Added
- **(A) broker approval-binding (`broker.py`).** An IRREVERSIBLE capability requires a fresh, broker-minted,
  one-shot consent token bound to `(cap, site)`; `_effect` denies it without a matching token
  (deny-by-default), and a new `consent` method mints one only after the human approval gate. A forgotten
  gate **FAILS CLOSED**. Reversible caps unaffected (backward compatible).
- **`casl.requirecheck` — Layer-1 requirement checker.** Static, fast, per-commit: PROVENANCE (every effect
  call traces to a requirement) + APPROVAL-DOMINANCE (every irreversible effect call is approval-bound).
  Runnable as `python -m casl.requirecheck PROJECT FILE…`; `scripts/pre-commit-requirecheck.sh` runs it on
  staged files. Deliberately unsound for bypasses — it pairs with `importlint` + the runtime cage.

### Verified
pytest **251 passed / 16 skipped** (the 2 pre-existing Rust-corpus-sync failures unchanged); `casl.audit` ✓.
New: `tests/test_broker_approval.py`, `tests/test_requirecheck.py`.

### Next
Layer-2 (semantic LLM review on a diff); B (conductor-driven effects); C (confinement, needs Linux).
scriptorium: the seam funnel + `SCRIPTORIUM_ENFORCE_APPROVAL` flag are in place; route migration + flag-on remains.

## [0.42.0] — 2026-06-28 — confinement-by-default for LLM-authored artifacts

Closes the gap that `confined` was an accounting label with no runtime teeth: an LLM-authored body
(`kind = generated|oracle`) is now confined by default, cannot opt out, and **fails closed** at run time
where the host cannot enforce the cage. Runtime hardening of CEP-0078 (capability providers / confinement);
design in `docs/analyses/confinement-by-default-llm-artifacts.md`.

### Added
- **Fail-closed runtime (`activity.py` + `host.can_enforce`).** A `confined` `SubprocessActivity` refuses to
  run where rung-3 cannot be enforced (e.g. macOS) instead of spawning the body unconfined; on an enforcing
  host it installs the seccomp cage (`preexec_fn`) and scrubs inherited secrets from the child environment.
- **Opt-out impossible for LLM kinds (`project.py`).** The manifest loader rejects `unconfined`/`native`/
  `confined = false` for `generated`/`oracle`, and parses `confined` as a strict bool (no `bool("false")`
  fail-open). A human-kind opt-out is rejected until the graded obligation exists (fail-closed).
- **Gate obligation (`obligation_gate.py`).** Deny-by-default: a `generated`/`oracle` artifact must be `confined`.
- **Read-capability exemption (`capability.py`).** A confined artifact bound to a read-mode site (the
  broker-mediated oracle boundary) needs no provider; only effect capabilities do — so confined "brains" are
  representable.
- **`casl.importlint`** — a deny-only AST lint over artifact bodies (raw-I/O imports, `eval`/`exec`/
  `__import__`, effectful `os.*`). Explicitly UNSOUND and never a confinement substitute; it makes a bypass loud.

### Verified
pytest **237 passed / 16 skipped** (2 pre-existing Rust-corpus-sync failures, unrelated — `surface`/`check`
untouched); `casl.audit` ✓ PASSED. New: `tests/test_confinement_default.py`, `tests/test_importlint.py`.

### Deferred (security-central → supervised)
P3 finish rung-3 (real netns+seccomp on Linux; only then may a confined grade rise above attested);
P4 bind `kind`/`producer` into attestation + close the confused-deputy (shared-provider / in-process import)
+ TOCTOU hash-at-spawn; P5 WASI rung-4.

## [0.41.0] — 2026-06-28 — the `casl` single binary + concurrency-certified (sync-complete checker)

The use-ready milestone: one standalone `casl` Rust binary wiring the at-parity crates, and the static
checker completed on the synchronous fragment (all 11 always-run MUST checks). `casl-check` now reproduces
ALL 11 always-run `casl check` gate verdicts on the SYNC fragment, and the Rust `casl` front-end gives a
full verdict on every sync protocol (no more UNDETERMINED for ≥4 roles).

### Added
- **`casl-check::concurrency` — founded concurrency (LH-Q-001d)**, a faithful port of
  `semantics.correspondence_class` + `kernel.concurrency_certified`: a bounded operational LTS (project every
  role via `casl-core`, then at each reachable state compare the events the GLOBAL type enables — head +
  role-disjoint prefix swaps — against the endpoint CONFIGURATION's; `global ⊋ config` = unsound,
  `global ⊊ config` = incomplete, deadlock = unsound; accept only `certified`). `Report` gains
  `concurrency_certified`. Pinned by the verdict differential, now **37 protocols** (+GoodConc certified via
  the swap rule, +BadConc incomplete across a recursion) — Rust agrees with `kernel.concurrency_certified` on
  all, both polarities. casl-check now reproduces **11 of 11** always-run gate checks (only `branch_contracts`
  — vacuous under the contract grammar — and `async_bounded` — async-only — remain).
- **CLI verdict completed on the sync fragment.** `concurrency_certified` is now a real gating check in the
  `casl` accept rule, so the ≥4-role UNDETERMINED heuristic is gone: a sync protocol gets a full
  Accept/Reject. The only remaining UNDETERMINED case is an `async` protocol (the `async_bounded` gate is not
  ported) — still sound (never a wrong-accept). The CLI exit-code differential grew to **20 cases** (+ a
  certified and an incomplete ≥4-role protocol).

### Verified
Whole Rust workspace fmt/clippy/test green (casl-check 37-protocol differential; casl-cli 20-case exit-code
differential + deferred contract); pytest 237/1; audit ✓. Examples sweep: **21 exact-agree + 3
safe-UNDETERMINED (the async protocols) + 0 mismatch** (was 15 + 9 + 0).

### The `casl` single binary (Rust front-end)

One `casl` binary (`casl-cli`) ties the at-parity crates together, so the verified core is runnable as a
standalone Rust tool.

### Added
- **`casl-cli` — the `casl` command-line front-end** (`rust/casl-cli`, zero external runtime deps): wires
  `casl-surface` (parse) + `casl-check` (the ported MUST checks) + `casl-core` (structural conjuncts) +
  `casl-project` (manifest/deps/seam/grade-flow) + `casl-conductor` (the deterministic interpreter) into the
  verbs `check`, `run` (single-file, mock oracle), `project`, `deps`, `seam`, `flow`. Exit-code contract
  mirrors the Python front-end: 0 ok/accepted · 1 rejected/violations · 2 usage/IO/parse/undetermined ·
  3 ran-but-incomplete.
- **Strangler-fig honesty.** The un-ported verbs (`new` / `synth` / `ide` / `gate` / `trace` / `blame` /
  `observe` / `init`) are recognised and DECLINE with exit 2 + a "use the Python `casl`" message rather than
  pretend. Inside the covered set, the one residual gap — the 11th MUST check, concurrency-/async-
  certification (not yet in `casl-check`) — is handled SOUNDLY: when the ported checks pass but the protocol
  is `async` or ≥4 roles, the front-end returns **UNDETERMINED (exit 2)**, never a wrong-accept (e.g. it
  declines `async_fanin_bad`, which Python rejects, instead of accepting it). Projectability uses the
  user-facing (own-roles) verdict + the role-independent structural conjuncts from `casl-core`, not the
  fixed-{C,A,J,D} core `wellformed` (which spuriously rejects good own-role loops via a phantom bystander).
- Pinned by a **17-case CLI exit-code differential** (`src/casl/cli_corpus.py` → `rust/casl-cli/tests/`):
  the built `casl` binary reproduces the Python front-end's exit code on the same argv+fixtures, across the
  covered fragment (the oracle's `covered` guard keeps every check/run fixture in-fragment), plus a Rust test
  pinning the `--version`/`--help`/deferred-verb contract.

### Verified
Whole Rust workspace fmt/clippy/test green (incl. `casl-cli`: the 17-case exit-code differential + the
deferred-contract test); pytest 237 passed / 1 skipped (incl. the new `test_cli_corpus.py`); audit ✓. A
24-protocol sweep over `examples/*.casl` shows 0 verdict mismatches with the Python `casl` (15 exact, 9
safely UNDETERMINED). Remaining to retire the Python CLI fully: the deferred engines (gate/synth/ide/…) and
porting the concurrency/async certification.

## [Unreleased] — runtime interpreter (Rust) + projectable proof progress

### Added
- **`casl-conductor`: the deterministic interpreter core** (ports `run.run_protocol`, `dispatch=None`, mock
  oracle) — the verified-shape walk + tool-broker check + interpreter-enforced forwarding (A1) + oracle step
  (budget/refusal monitor) + monitor-verdict branch policy + deny-by-default approval gate + loop bound →
  structured `RunResult`. Pinned by a **14-case run-trace differential** (`src/casl/conductor_corpus.py`):
  same `.casl` + scenario + budget + approve ⇒ same outcome/loops/verdict/accepted-label/forwards as Python.
  The live-LLM + broker-process dispatch paths stay out (key-gated; the Rust broker is separate + at parity).
  On `feat/casl-conductor`.
- **`projectable` in Verus — first machine-checked progress** (`rust/proofs/projectable_verus.rs`, 6 verified
  / 0 errors): `project` is proved TOTAL + TERMINATING + PANIC-FREE over the cons-list model, and
  `choice_free_projects` proves a choice-free global type is projectable for every role. The bystander-choice
  merge is a SOUND under-approximation (branches must project equal; projectability only inspects Some/None).
  Residual: the full `merge_pair` external-choice label-union (Aeneas→F\* recommended). On `feat/projectable-verus`.

### Verified
pytest 234 passed / 1 skipped; whole Rust workspace fmt/clippy/test green (incl. casl-conductor: 4 unit + the
14-run differential); both Verus proofs green (`wellformed_verus` 28/0, `projectable_verus` 6/0). DELIBERATELY
DEFERRED (security-central; with your review): the obligation **gate** (attestation-signature crypto + git
line-trace) and the grade **re-base** (z3 SMT entailment) — only a small le/ge entailment decider is portable.

## [Unreleased] — project layer, Track C begins (CEP-0081 retirement)

A new **`casl-project`** crate begins the bottom-up retirement of the project layer to Rust, each piece
differential-pinned to its Python authority. On `feat/casl-project`.

### Added
- **`casl-project`: manifest load/validate** (`load_manifest_text`) — a zero-dependency TOML-subset reader +
  the deny-by-default structured validation of `casl.toml`: `kind` ∈ a fixed set (LH-F-013, never
  name-inferred), the trace regime follows ownership (LH-P-009), unprovable provenances floor at G3
  (LH-Q-016), owned non-oracle artifacts require a body. `Manifest`/`Artifact` model + `floor`/`owned`.
  Pinned by an 18-manifest differential (`src/casl/project_corpus.py`, 8 accepted + 10 deny-by-default
  rejected) reproducing the accept/reject decision AND the validated model.
- **`casl-project::dependency`: burden ledger** (LH-Q-020) — parse `deps.lock`, deny-by-default
  well-formedness (pinned AND owned AND known evidence), the supply-chain floor (weakest of
  `pin<sbom<slsa<signed`), and `check_min_evidence`. Pinned by an 8-ledger differential
  (`src/casl/dep_corpus.py`).
- **`casl-project::seam`: typed `.casl`↔artifact binding** (LH-F-012 full) — each artifact that declares
  `implements="Protocol:Label"` binds to a choreography site and its `kind` must realize the site nature
  (oracle/verified/effect/plain). Adds a `casl-surface` dep. Pinned by a 9-case seam differential.
- **`casl-project::grade_flow`: grade flow-graph** (CEP-0070, sound structural core) — per bound site, the
  weakest assurance floor at-or-upstream in protocol order (never raised) + containment-boundary detection.
  The z3/CERT-FID forwarding re-base layer stays Python (deferred). Pinned by a 5-fixture differential.
- **`casl-project::obligation`: assurance-grade composition** — `effective_grade` (weakest artifact floor,
  LH-Q-019) + `grade_by_requirement` (CEP-0070 model A). The full Tier-0 gate (attestation crypto, git
  line-trace) stays Python (deferred). Pinned by a 7-manifest differential.

### Verified
pytest 231 passed / 1 skipped; whole Rust workspace fmt/clippy/test green (`casl-project`: 15 unit + five
differentials — 18-manifest, 8-ledger, 9-seam, 5-grade, 7-grade-composition). Ring-1/2 (no verified-core
path); characterization-pinned (no F\* proof). DELIBERATELY DEFERRED as security-central (not rushed
unsupervised): the obligation **gate**'s attestation-signature crypto + git line-trace, the grade **re-base**
SMT entailment (z3), and the **conductor/interpreter** runtime (`run_protocol`). The CLI is retired last.

## [Unreleased] — checker port (Track A, CEP-0081 retirement)

`casl-check` now reproduces **10 of the 11 `casl check` gate checks**, each ported END-TO-END (`.casl` text →
verdict) and differential-pinned to the Python authority over a single-sourced 35-protocol corpus (both
polarities of each).

### Added — MUST checks (`feat/checker-rest`)
- **user-facing well-formedness** (`wellformed_user`) — projectability over the protocol's OWN declared roles
  + a faithful MSC-realizability port (`spike_proj_msc.realizability`: leading-scenario lifeline projection;
  first divergence must be a receive; no length divergence without a distinguishing message).
- **pipeline-safety** (`pipeline_safe`) — `spike_pipeline.pipeline_safe`: R1 no node is both `oracle` and
  `verified`; R2 every `oracle` node carries a contract.
- **promise-linearity** (`linearity`) — `spike_hardening.linearity_check`: every oracle output is sent exactly
  once along its producer's projected local type (write-once + obligation).
- **stream-safety** (`stream_safe`) — `spike_hardening.stream_wellformed`: every `stream` loop dispatches via a
  Choice whose selector is an env role, and every branch handler terminates.

### Added — SHOULD checks (`feat/checker-shoulds`)
- **termination** (`termination`) — `spike_hardening.termination_check`: every non-`stream` loop declares a
  ranking measure. The well-founded ranking lemma is a protocol-independent SMT tautology (constant True), so
  no z3 dependency is pulled into Rust — only the measure-coverage obligation is computed structurally.
- **crash-tolerance** (`crash_tolerance`) — `spike_resilience.crash_tolerance`: every receive from a
  crash-prone sender carries a typed `on_crash` continuation.
- **ttl-safety** (`ttl_safety`) — `spike_hardening.ttl_safety_check`: a finite-ttl capability used in a loop has
  ttl covering the loop's iteration bound (a `stream` loop refreshes per iteration, so ttl need only cover a
  single handler path).

### Verified
pytest 216 passed / 1 skipped; whole Rust workspace fmt/clippy/test green; `casl-check` 35-protocol verdict
differential green (10 verdicts). Honest scope: every ported check beyond `wellformed_core` is
**characterization-pinned** (no F\* proof). NOT ported: `branch_contracts` — `casl-surface` ALREADY parses the
structured contract relation (pinned by the parse differential), so it is NOT parser-blocked; it is
**vacuously true** under the current contract grammar {`le`, `nonempty`} (the monitor synthesizer covers
exactly those, so no parseable protocol makes it false) ⇒ a low-value differential target — and
`concurrency_certified` (L/hi prototype semantics). Branches `feat/checker-rest` (merged to `main`) +
`feat/checker-shoulds`; await the user's signed tag.

## [0.40.0] — 2026-06-27

**Overnight hardening** — depth + breadth, each individually verified on the Mac.

### Added
- **Machine proof of the Rust well-formedness checker** (Verus): `rust/proofs/wellformed_verus.rs` proves
  `no_self`, `gdistinct`, `closed`, `contractive`, and the combined `wf_noproj` — each exec-refines-spec +
  terminating + panic-free (28 obligations, 0 errors); `rust/proofs/no_self_verus.rs` (5/0) is the n-ary
  first brick. This is the FULL structural `wellformed_core` (everything except the `projectable` conjunct).
- **`casl-check`: approval-dominance** — third ported MUST check, run on the rich surface AST (it needs the
  `irreversible`/`approval`/`consent` markers + cap `mode` the bridge drops), mirroring
  `kernel.approval_safety`; differential-pinned over a 29-protocol verdict corpus (both polarities). `Report`
  gains `approval_safe`.
- **`docs/analyses/secure-product-status.md`** — an honest assurance map (proved / differential-pinned /
  tested / attested / environment-gated) + exactly what remains and why.

### Verified
pytest 216 passed / 1 skipped; living audit ✓ PASSED; whole Rust workspace fmt/clippy/test green; both Verus
proofs green. Honest scope unchanged: the Verus proofs cover functional correctness of the *implementation*,
not the MPST metatheory (F\*); capability containment + approval dominance are characterization-pinned (no
F\* proof). Remaining checker ports, the `projectable` conjunct, the project/conductor/CLI ports, rung-3
confinement, live cloud keys, and F\*→extraction are scoped in the status doc.

## [0.39.0] — 2026-06-26

**Retiring Python — brick 2** (CEP-0081): the checker port begins. A Rust `casl-check` runs the first MUST
checks END-TO-END from text, at parity with the Python checker's own authorities.

### Added
- **`rust/casl-check`** — the static checker, end-to-end (`.casl` text → verdicts). Bridges the `casl-surface`
  AST to `casl-core` and reuses its **well-formedness** (`wellformed_core`, the F\*-pinned predicate) and
  **Least-Privilege capability containment** (`capability_check`). Zero new runtime deps (path deps on the two
  crates). `check_text()` / `check()` / `to_core()`.
- **`src/casl/check_corpus.py`** — the verdict-differential **oracle**: per `.casl` source, the Python
  checker's own authorities — `wellformed = tcb_bridge.projectable`, `capability_contained =
  kernel.capabilities` — single-sourced to `rust/casl-check/tests/corpus.json` (28 protocols, both polarities).
- **`rust/casl-check/tests/differential.rs`** — `casl-check` reproduces BOTH verdicts for all 28 (Rust ==
  Python). **`tests/test_check_corpus.py`** (3) pins the oracle locally.

### Note
`wellformed` here is the F\*-core predicate `wellformed_core` (fixed roles {C,A,J,D}) — STRICTER than `casl
check`'s user-facing well-formedness (own roles + MSC); matching that exactly is a later brick. Capability
containment is characterization-pinned to the Python reference (no F\* proof). Verified on the Mac: cargo
fmt/clippy/test green; Python 216 passed/1 skipped; audit ✓ PASSED.

## [0.38.0] — 2026-06-26

**Retiring Python begins** (CEP-0081): the first strangler-fig brick — a Rust `.casl` parser at **parity**
with the Python reference, pinned by a parse-differential. Rust becomes authoritative one component at a
time, behind the frozen contract; F\* stays the proof of record.

### Added
- **`rust/casl-surface`** — a hand-written recursive-descent `.casl` parser (text → canonical AST), **zero
  runtime dependencies**, mirroring `src/casl/surface.py` 1:1. `parse()` + `to_json()` (canonical schema).
- **`src/casl/surface_corpus.py`** — the parse-differential **oracle**: a single-sourced corpus of `.casl`
  text + canonical AST JSON (`rust/casl-surface/tests/corpus.json`, 28 protocols), emitted from the Python
  parser. `casl-surface` reproduces every AST — verified by `cargo test` (locally on the Mac + in CI).
- **`tests/test_surface_corpus.py`** (4) — the oracle is deterministic + in sync with the parser + the
  committed Rust fixture; the canonical example round-trips; the corpus covers the grammar.
- **`rust/casl-surface/tests/differential.rs`** — Rust-parse(text) == the pinned Python AST for all 28.
- **CEP-0081** + **`docs/analyses/python-retirement-roadmap.md`** — what "retire" means (Rust authoritative,
  Python deleted, F\* still the proof; not a big-bang), the retire-criteria (frozen contract + conformance
  differential + no second unpinned impl + reversible), the parity ledger, variants/compare/synthesis
  (bottom-up order; hand-written zero-dep parser), and honest residuals.

### Note
The FIRST brick: `surface.py` retires on soak. Order: parser → checker → project → conductor → CLI. Only
well-formedness has an F\* proof, so the later non-core checks are characterization-pinned, not proved.

## [0.37.0] — 2026-06-26

**Real execution** (CEP-0080): the conductor goes from *conducting a mock* to conducting **real programs and
a real model** — two thin drivers on the existing monitored seam, no new architecture and no new trust.

### Added
- **`src/casl/activity.py`** — the **activity executor**. `SubprocessActivity` runs the project's own program
  (or agent) out of process as an untrusted *producer* bound to an oracle site, over the same one-line JSON
  contract the LLM oracle uses (`{"question","budget"}` → `{"answer","cost"}`, parsed by the reused
  `oracle.parse_oracle_output`). A `backend` drop-in, monitored identically (contract + H4 + blame). Polyglot,
  no key, cross-platform; **fail-closed** (crash/timeout/non-JSON/missing-cost ⇒ typed refusal) and
  **veto-never-vouch** (the activity emits no verdict — the trusted monitor decides). `command_for` infers
  the runner (deny-by-default for unknown extensions).
- **`conductor.py`** — auto-selects a `SubprocessActivity` backend when an oracle site is bound (typed seam)
  to an **executable** artifact (kind `oracle` + runnable `body`); the proven mock/provider default path is
  untouched. `run(..., oracle_backend=)` lets a caller inject a backend (tests / a live provider).
- **`providers.UrllibTransport`** — the **live transport**: a real HTTPS POST (stdlib `urllib`, zero new deps)
  behind the existing `build_request`/`parse_response`. `live_backend_from_env` builds a live `ProviderBackend`
  from the broker's environment; the **no-key local path** is `openai`-shape + `http://localhost:11434`
  (Ollama). Key injected from env only — never embedded, never sent by the client. Fail to a typed refusal.
- **CLI** — `casl run --project --live [--provider … --model …]` now drives the oracle from a live model.
- **`examples/activities/budgeted_draft.py`** — a tiny, committed, polyglot activity (stdin→stdout).
- **`tests/test_activity.py`** (9) + **`tests/test_live_transport.py`** (6) — every property + an end-to-end
  conduct of a project whose oracle is a REAL program, and the live transport proven against a localhost stub.
- **CEP-0080** + **`docs/analyses/activity-executor.md`** — formalization (orchestrator/activity split),
  literature (Temporal/Step-Functions, PFI/least-privilege agents, AgentSpec), the five properties, residuals.

### Note
Both drivers are confinement-ready but do not themselves confine: a spawned activity runs at **attested**
grade until rung-3 (CEP-0078) wraps the same subprocess. The live transport is "modulo TLS/endpoint trust";
egress from a *confined* caller is still cut (the transport is broker-side).

## [0.36.0] — 2026-06-26

The **authoring front door** (CEP-0079): `casl new DIR "wish"` — a requirement in natural language → an
*untrusted* generator proposes a `.casl` → the monotone gate decides (Tier-0 the sole opener, "agents veto,
never vouch") → on acceptance, emit a complete, conductable project → conduct it through the broker. Closes
the loop from intent to a running, verified system. CEGIS-shaped: **soundness from the gate, never the
proposer; fail-closed** (no gate-accepted spec ⇒ nothing emitted).

### Added
- **`src/casl/synthesis.py`** — `new_project(wish, dir, generator, …)` reusing `ide.synthesize_gated` (the
  monotone CEGIS loop) + `project.init_project` + `conductor.Conductor`; `derive_manifest` emits one `oracle`
  artifact per oracle site (typed-seam-bound) and one single-purpose `external` provider per effect
  capability; `format_new`. Emits **only** on gate acceptance; fail-closed otherwise.
- **CLI** `casl new` (`--live`/`--coder` for the real generator, deferred; deterministic mock by default).
- **`tests/test_synthesis.py`** (4) — requirement → accepted project that conducts to completion; rejected
  proposal → nothing emitted; manifest binds oracle + provider; emitted project re-gates + conducts.
- **CEP-0079** — the loop + the soundness guarantee (gate sound + sole arbiter ⇒ every emitted project ⊨ S,
  regardless of proposer) + the honest residual risks (requirement↔spec fidelity / validation ≠ verification,
  vacuity, over-restriction, reward-hacking, TCB integrity). The loop produces attestation *obligations*; the
  human signs them.

## [0.35.0] — 2026-06-26

CEP-0078's **runtime side**: the conductor now routes a confined caller's effect through its bound,
single-purpose provider — and refuses at dispatch if there is none. No ambient authority is now enforced at
*both* the gate (build-time, `casl gate`) and the conductor (run-time). Additive; projects with no providers
and no confined artifacts behave exactly as before.

### Changed
- **`conductor.py` — `BrokerDispatch` is provider-aware.** At an effect step it resolves
  `uses_capability` → its signed provider (from the manifest's provider index) and records the delegation
  ("served by / delegated to provider X"). For a **confined** artifact realizing the site, a capability with
  **no provider** is denied at dispatch (the run-time twin of the gate-time no-ambient-authority check) —
  before the broker is even asked. The `Conductor` passes the provider index + the confined set + the
  site→artifact map; the run summary now lists the capability providers.
- **`run.py`** — the dispatch grant trace now carries the provider/delegation reason (the proven
  single-file path, `dispatch=None`, is unchanged).
- **`examples/projects/triage`** — `notify` now declares `provides = "mail"`, so the dogfood shows the
  Notify effect dispatched through its signed provider at run time.

### Added
- **`tests/test_conductor.py`** — a confined caller delegating to its provider (routed, completes), and a
  confined caller with no provider refused at run time ("no ambient authority"); the canonical run asserts
  the provider routing. 172 passed / 16 skipped, audit ✓.

## [0.34.0] — 2026-06-26

The **Rust checker port** begins (strangler-fig P4): the verified core's well-formedness now runs in Rust,
pinned to the F\*-extracted verdicts by a conformance differential. A step toward retiring the Python
checker once the Rust alternative is capable.

### Added / Changed
- **`rust/casl-core`** — promoted the former standalone `engine/` into the `rust/` workspace and completed
  its `wellformed`: `wellformed_core(g)` = `contractive ∧ no_self ∧ gdistinct ∧ closed ∧ projectable for
  {C,A,J,D}`, mirroring `fstar/CASL.fst` exactly (the prior engine checked only projectability). Pure Rust,
  fmt + clippy clean.
- **412-protocol conformance differential** (`rust/casl-core/tests/differential.rs`) — `casl-core` is pinned
  to the authoritative verdicts on a shared corpus single-sourced from `casl.tcb_corpus` (each verdict is
  `tcb_bridge.projectable`, itself pinned to the F\*-extracted kernel). Rust ↔ Python(↔F\*) agree on every
  protocol — the strangler-fig safety net (never two unpinned impls).
- **`casl.tcb_corpus`** gains `to_json` + `write_rust_corpus` (regenerates the JSON corpus from the same
  enumeration that feeds the OCaml driver). `python -m casl.tcb_corpus` now writes both.
- Docs: `docs/mechanization.md` + `docs/engineering-plan.md` §7 repoint `engine/` → `rust/casl-core` and
  record the P4 start.

## [0.33.0] — 2026-06-26

**Capability providers** — the no-ambient-authority model (P2 confinement, rung-2 + the rung-3 scaffold).
Raw I/O lives only in single-purpose, human-signed *provider* artifacts; a `confined` artifact has no
ambient I/O and may act only by invoking a granted provider. This is what makes orchestrating untrusted /
LLM-generated artifacts safe. Object-capability / POLA / powerbox / seL4-grounded; see `docs/confinement.md`,
CEP-0078. Additive; inert for manifests with no providers and no confined artifacts.

### Added
- **`src/casl/capability.py`** — the gate-time capability-provider checks (rung-2, by construction):
  `provider_index`, `check_providers` (single-purpose + unambiguous), `check_no_ambient_authority` (a
  confined artifact's used capabilities must each resolve to a granted provider — deny-by-default),
  `io_grade` (a confined caller's I/O grade = its provider's floor; the honesty rule). Reuses the existing
  attenuation / attestation / grade machinery.
- **Manifest** (`project.py`): `Artifact` gains `provides = "<capability>"` (a single-purpose provider) and
  `confined` (opt-in: no ambient I/O).
- **`rust/casl-host`** (new crate, scaffold): the rung-3 confinement *policy* as pure, dependency-free data —
  the seccomp allow/deny lists (`MUST_DENY` networking + namespace-escape syscalls; `BASE_ALLOW`
  compute+broker-I/O) and the egress plan (only the broker + granted-provider fds are kept) — defined and
  unit-tested on every OS (7 tests). `launch` fails closed and **never silently confines**; the syscall-level
  enforcement (empty network namespace + seccomp-bpf + inherited `socketpair` fd) is Linux-only and staged
  for a CI runner.
- **`src/casl/host.py`** — the rung-3 confinement **reference** (Python sibling of `rust/casl-host`): a
  per-arch (x86_64/aarch64) seccomp-bpf filter + `confine()` (NO_NEW_PRIVS + the filter, fail-closed off
  Linux) + `run_bypass_check()`. The **seccomp egress cut is verified on real Linux** — `tests/test_host.py`
  executes the bypass-fails test: a confined child's `socket()` returns `EPERM` while its inherited broker fd
  (stdio read/write) still works (skips on macOS). The empty-netns layer + the Rust syscall port remain
  staged for a Rust+Linux runner.
- **`tests/test_capability.py`** (9 tests) + **`tests/test_host.py`** (6) + **CEP-0078** +
  **`docs/confinement.md`** (the model, the research basis, the rung-2→3→4 ladder, the research-rated
  decisions, the honest claim + what's verified where).

### Changed
- **Obligation gate** (`obligation_gate.py`): a capability *provider* requires a human attestation even when
  its `kind` is `verified` (granting world-access is an unprovable trust act, CEP-0078); the project gate now
  also runs the capability check.

### Decided / documented
- **Rung-3 = empty network namespace + seccomp-bpf allow-list + broker-only inherited fd** (Landlock as an
  optional filesystem layer, **never** the egress cut — it doesn't cover UDP/raw/syscalls); **`casl-host` is
  pure Rust**; **rung-4 WASI** is the by-construction endgame. Research-rated on security + understandability
  + feasibility (speed not a priority); `docs/confinement.md` §5. Honest claim: "no authorized egress except
  the broker + granted providers, conditional on the monitor/kernel/filter, modulo timing/covert channels."

## [0.32.0] — 2026-06-26

The **conductor** (Layer 3 — Execution): `casl run --project` drives a *verified* choreography end-to-end,
dispatching every model/tool call through the broker (the one reference monitor). Additive; the proven
single-file interpreter path is byte-for-byte unchanged. See `docs/conductor.md`, CEP-0077.

### Added
- **`src/casl/conductor.py`** — the project-aware conductor: `Conductor(project_dir)` loads the manifest +
  choreographies + typed-seam bindings, gates the hull (`check_protocol`), stands up the broker (granted
  tools = the choreography's declared agent caps), and conducts the run. Two thin seams onto the broker:
  `BrokerBackend` (oracle sites → `client.oracle`, capability-gated + H4 cost) and `BrokerDispatch` (effect
  sites → `client.effect`, deny-by-default). The verified `.casl` IS the state machine (determinism by F\*
  proof, not by runtime replay — the declarative model, not event-sourced replay).
- **CLI**: `casl run --project DIR [--protocol N] [--provider P]` conducts a whole project (vs. the
  single-file `casl run FILE.casl`).
- **Dogfood** `examples/projects/triage/` — an oracle site (Classify) + an approval-gated effect site
  (Notify uses mail), both bound via the typed seam, conducted end-to-end through the broker.
- **`tests/test_conductor.py`** — 10 tests: bindings resolve; oracle + effect cross the broker; default-deny
  at the approval gate blocks the effect; tool / provider denial; overspend flagged at the boundary; the
  hull is gated before running; the in-process interpreter path is unchanged.

### Changed
- **`run.py`**: one additive optional `dispatch=` parameter. At an effect-bearing step it routes the
  capability check through the broker (the reference monitor) when set; `dispatch=None` ⇒ the proven path is
  unchanged. The broker is the *access* monitor; the conductor is the *contract* monitor (two policies, not
  redundant — `docs/conductor.md` §3).

### Decided / documented
- **CEP-0077 + `docs/conductor.md`**: the conductor design, the variant rating (Variant B — broker-mediated
  oracle *and* effect via the additive hook — adopted; Variant C, polyglot confined subprocess activities,
  deferred to P2), and the literature basis (declarative state machine + reference monitor; diverge from
  Temporal/Step-Functions by proving determinism ahead-of-time and grading the mediated effect).

## [0.31.0] — 2026-06-25

Runtime-core seed (Rust) + the opt-in capability-service posture. Additive; backward-compatible (the Python
toolchain is unchanged).

### Added
- **Rust runtime workspace** (`rust/`, pure-Rust default): `casl-proto` (the JSON-RPC wire protocol — the
  single source of truth for the broker↔binding contract) and `casl-broker` (the reference monitor in Rust:
  the monitored oracle boundary mirroring the Python `oracle_step` + cost/refusal monitor with the H4
  measured-cost check, deny-by-default effects, stdio + in-process transports). 24 Rust unit tests; Rust CI
  (`.github/workflows/rust.yml`: fmt / clippy `-D warnings` / test / conformance).
- **Cross-impl conformance**: the existing Python client (`casl.client`) drives the Rust broker binary
  unchanged over the wire (`tests/test_broker_rust_parity.py`, the seed of `casl-conformance`).
- **Multi-provider LLM connector** (P1.5): a unified, monitored connector for OpenAI-compatible
  (Ollama/vLLM), Anthropic Claude (Messages API), Google Gemini (generateContent) — pure, offline-tested
  request-build + response-parse (token usage = the H4 measured cost) behind a thin `Transport` seam.
- **Capability flags**: artifacts declare broker capabilities at `initialize` (`llm:claude`, `websocket`,
  `tool:*`); `oracle` is gated on `llm:<provider>` being declared (deny-by-default, `-32011`).

### Decided / documented
- **Posture (engineering-plan §0.5):** confinement is **opt-in, not mandatory**; the broker is an opt-in
  **capability service**; capability flags are **declarations** that drive grade + monitoring (trusted for
  human authors; enforced for untrusted/LLM code). Supersedes the mandatory-mediation framing of
  `architecture.md` §3.
- Research-backed decisions (engineering-plan §8): pure Rust default · `wasmi` confinement engine ·
  dalek+fiat crypto · JSON-RPC/stdio bindings · `z3` shell-out for SMT · WASI rung-4 for Rust/C · retire
  Python on parity. HTTP client = `ureq` 3.3 (rustls, no async/OpenSSL).

### Notes / residuals
- The Rust P1.5 provider/capability-gating path is Rust-only (the Python reference broker has no provider
  gate) — pinned by Rust unit tests + the §0.5 spec, not yet by the cross-impl differential (acceptable
  under strangler-fig).
- Live LLM HTTP (`ureq`) and OS-level confinement (rung-3/4, opt-in) are the next increments.

## [0.30.0] — 2026-06-25

Consolidation release: the **project / governance layer** (artifact-trust) is now
a first-class, documented part of the language alongside the choreography layer.

### Added
- **Data forwarding (lineage) syntax** `field = Src.field` (or `field: Sort = Src.field`)
  in the surface language and `core.Field.source`. A forwarded field carries an earlier
  site's value unchanged, making data lineage explicit and statically checked
  (guide §4).
- **Typed seam** (`LH-F-012` full): `implements="Proto:Label"` binds an artifact to a
  choreography site; `casl seam` reports the bindings and flags unbound sites.
- **Grade flow-graph** (`CEP-0070`): `casl flow` reports a grade **per site** along the
  parsed-protocol edges — a site upstream of a weak artifact keeps its strong grade —
  and soundly **re-bases** to G2 a site that forwards a value from a `verified` boundary
  whose proved contract entails the site's contract (A2; SMT entailment without forwarding
  stays a surfaced *candidate*, never applied).
- **Oracle observability** (`LH-G-005`): `casl observe` replays the captured
  prompt→response of each oracle call (primary rubber-stamp mitigation).
- Root `CHANGELOG.md`.

### Documented
- Guide §4: the `field = Src.field` forwarding syntax + its grade-flow consequence.
- Guide §10: the project-layer CLI verbs `seam`, `flow`, `observe` (alongside
  `init`/`project`/`deps`/`trace`/`blame`/`gate`).
- README: a concise **Project / Governance Layer** section (kinds, G3 floor,
  weakest-link effective grade, `casl gate`, the typed seam, forwarding re-base).

### Invariants (unchanged)
- The verified F\* core is untouched (0 admits); the seam bridge is field-blind.
- The project headline stays the global **weakest link**; per-site grades are an
  additional finer view that can never raise the headline on their own. A re-base
  exceeds an upstream floor only via checked structural lineage, capped at G2 — G0
  still requires an F\* forwarding-fidelity proof (A1, deferred).
- Unprovable artifact kinds floor at G3; *agents may veto, never vouch*.
