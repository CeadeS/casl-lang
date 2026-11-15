# CASL engineering program — to a use-ready language (Rust runtime, F\* proof)

**Date:** 2026-06-25 · **Status:** program plan (the systematization of the work). **North star:**
*clean Rust runtime core + bindings; the F\* proof stays the proof; F\*→extraction (TCB unification) afterwards
if feasible.* **Architecture rationale:** `docs/architecture.md` (the keystone). This document is the
*how-we-build-it*: components, work breakdown, milestones, test/CI strategy, risks, and the definition of
"use-ready."

---

## 0. Decision & guardrails

- **Two cores, decided separately.** The **proof core** stays **F\*** (`fstar/`) — no rewrite can "be the
  proof." The **runtime core** (broker, confinement host, conductor, checker) moves to **clean Rust**.
- **Rust, not C.** A memory-unsafe reference monitor contradicts the thesis; Rust gives memory safety *and* a
  C ABI for bindings, and is the language of `wasmtime` (the rung-4 confinement host).
- **No big-bang rewrite.** Strangler-fig migration behind the **stable wire protocol** and a **conformance
  differential** (Rust ↔ F\* ↔ the current Python reference). Python stays runnable until each piece is
  replaced *and* pinned. Tests stay green throughout.
- **Seed asset.** `engine/` already mirrors the verified core in Rust (gtyp/ltyp, projection, hardened merge,
  well-formedness, capability containment), conformance-tested to F\*/Python. `casl-core` is its promotion.
- **Authority.** The agent implements on feature branches; the human signs merges (the accountability layer).
  The F\* admits gate, the attack corpus, the living audit, and the conformance differential are CI gates.

---

## 0.5 Posture (2026-06-25) — the broker is an opt-in *service*, not a mandatory cage

*(This supersedes the "made unbypassable / complete-mediation-mandatory" framing of `docs/architecture.md` §3.)*

A programmer controls their own program; CASL must not imprison it. So **confinement is OPT-IN, not
mandatory** — it is one way to *raise an artifact's grade* (turn a declared capability into an enforced one),
alongside proof and attestation, never a requirement. The **broker is a capability *service*** an artifact
opts into: it provides unified, **monitored LLM connectors (Gemini / Claude / Ollama / OpenAI-compatible)**,
tool-call monitoring for agents, and an optional network/websocket capability — used because they give
monitoring + cost-tracking + accountability + a better grade, not because the artifact is forced through
them. An artifact may also just do its own efficient native I/O.

**Capability flags = declarations.** Each artifact *declares* (flags) the broker capabilities it uses
(`llm:claude`, `websocket`, `tool:mail`); the declaration drives monitoring + grade + the human-supervision
view. **Honesty rule** (keeps it sound; = "agents may veto, never vouch"): a declaration is trustworthy for a
**human-authored** artifact (the human signs it → *attested*); for **untrusted / LLM-generated** code a
self-declaration vouches for nothing, so it is believed only if **enforced** (confinement) or **statically
checked** — and the grade reflects which: declared/attested < monitored-through-broker < enforced-by-
confinement < proved.

**Effect on the WBS:** **P2 (confinement) → optional / opt-in grade-upgrade** (built for the untrusted-code
case, not as the default). The near-term build is the **capability service** (call it **P1.5**): the
multi-provider LLM connectors + the capability-flag model — more useful and more adoptable than a cage.
**Connector decisions (research-backed):** HTTP client = **`ureq` 3.3** (blocking, `rustls`, no async, no
OpenSSL — smallest auditable tree; `reqwest`+`rustls` is the fallback if HTTP/2/pooling is ever needed);
providers = OpenAI-compatible (Ollama/vLLM) + Anthropic Claude (Messages API) + Google Gemini
(generateContent), with provider-specific request-build + response-parse and **token-usage as the monitored
(H4) measure**; the live HTTP send is a thin, feature-gated `Transport` seam so the trusted/test path stays
offline + pure.

## 1. Target state — "use-ready"

A developer **or a coding agent** can:

1. `casl init` a polyglot project (manifest, git, keys, layout).
2. Author a verified `.casl` choreography + implement artifacts in **≥2 languages** (e.g. Rust + Python + JS).
3. Have `casl gate` keep the artifacts honest in CI (seam, trace→requirement, attestation, deps, grade).
4. `casl run --entry` **conduct** those artifacts + LLM agents along the protocol — each artifact **confined**
   so its only channel is the **broker**; irreversible effects **human-gated**; every step **graded**.
5. Do all of the above from **one installed binary** (`casl`) + **binding packages** (pip / npm / JAR / C
   header), with the **F\* proof + conformance bridge** intact.

**Definition of done (acceptance for the program):** the secretariat/PDF dogfood (`docs/architecture.md` §7)
runs end-to-end through the Rust stack — confined, gated, graded — with the **negative-test matrix green**
(tamper / unattested / unapproved / unbound / bypass ⇒ refuse), shipped as a single binary + ≥2 language
bindings, F\* verifying at 0 admits, and the conformance differential green.

---

## 2. Architecture — component & crate inventory

Cargo workspace (`rust/`), the F\* proof (`fstar/`), the bindings (`bindings/`), and the Python reference
(`src/`, retired incrementally). Trust tier: **TCB** = must be correct for safety; **support** = outside the
safety boundary.

| Component | Crate / dir | Responsibility | Lang | Tier |
|---|---|---|---|---|
| Proof core | `fstar/` | Metatheory: projection/merge/safety, forwarding fidelity. The proof. | F\* | **TCB (proved)** |
| Protocol | `casl-proto` | Wire types + JSON-RPC framing; the single source for binding codegen. | Rust | TCB |
| Verified-mirror IR | `casl-core` | gtyp/ltyp, projection, merge, well-formedness, capability model. *(promote `engine/`)* | Rust | **TCB** |
| Surface | `casl-surface` | `.casl` parser → core IR. | Rust | support |
| Checker | `casl-check` | Well-formedness, projectability, concurrency/async gates, contract entailment (z3), assurance levels/grades. | Rust | **TCB** |
| Project/governance | `casl-project` | Manifest, deps ledger, traceability, seam, attestation, obligation gate, grade-flow. | Rust | **TCB** |
| Broker | `casl-broker` | Reference monitor: capability mediation, monitored oracle boundary, deny-by-default effects, observation capture. | Rust | **TCB** |
| Confinement host | `casl-host` | rung-3 OS sandbox (namespaces/seccomp) + rung-4 `wasmtime` WASI component host. | Rust | **TCB** |
| Conductor | `casl-conductor` | `casl run`: project-aware dispatch, runtime re-attestation, approval gate, supervision/failure-strategy, provenance trace. | Rust | **TCB** |
| C ABI | `casl-ffi` | `extern "C"` surface (cbindgen) over broker/conductor/check for native + FFI bindings. | Rust | TCB |
| CLI | `casl-cli` | The `casl` binary (init/check/gate/run/broker/seam/flow/trace/blame/observe). | Rust | support |
| Conformance | `casl-conformance` | The differential oracle: F\*-extracted core vs `casl-core` vs the Python reference, on the shared corpus (generalize `tcb_bridge`). | Rust+F\* | **TCB (gate)** |
| Bindings | `bindings/{python,js,java,c}` | Thin couriers over the protocol / C ABI; **untrusted**, generated from `casl-proto`. | per-lang | support |
| Python reference | `src/casl/` | The current impl; the migration oracle; retired piece-by-piece. | Python | support (transitional) |

**Dependency graph (build order):** `casl-proto` → `casl-broker`, bindings; `casl-core` → `casl-surface`,
`casl-check`, `casl-project`, `casl-conductor`; `casl-broker` + `casl-host` → `casl-conductor`;
{`casl-broker`,`casl-conductor`,`casl-check`} → `casl-ffi` → bindings; everything → `casl-cli`.

**Repo layout (coexistence during migration):**

```
LLang/
  fstar/                  # the proof (unchanged) + casl-conformance bridge target
  rust/                   # NEW Cargo workspace
    Cargo.toml            # [workspace] members = casl-proto, casl-core, ...
    casl-proto/  casl-core/  casl-surface/  casl-check/  casl-project/
    casl-broker/ casl-host/ casl-conductor/ casl-ffi/ casl-cli/ casl-conformance/
  bindings/python|js|java|c/
  src/casl/               # Python reference — shrinks as crates land
  engine/                 # seed for casl-core (fold in, then retire)
  docs/  proposals/  examples/  tests/
```

---

## 3. Migration strategy (strangler-fig)

1. **Freeze the contracts first.** The JSON-RPC broker protocol (`docs/broker-protocol.md`) and the corpus
   format are the stable seams. Reimplement *behind* them; clients/tests don't change.
2. **Replace one component at a time**, each pinned by the **conformance differential** to the Python
   reference + F\* before the Python version is retired. Never two unpinned impls.
3. **Keep the system runnable at every step** (the Python stack works until its Rust replacement passes
   parity). CI runs both until a component is retired.
4. **Promote, don't rewrite, where possible** — `engine/` → `casl-core`; the Python broker (P1.0) *defines*
   what `casl-broker` must do behind the same wire.

---

## 4. Work breakdown structure (phases → exit criteria)

Sizes: S ≈ days, M ≈ 1–2 weeks, L ≈ multi-week. Each phase lands on feature branches behind the gates in §5.

| Phase | Epic / work packages | Exit criteria | Deps | Size |
|---|---|---|---|---|
| **P0 Foundations** | Cargo workspace scaffold; `casl-proto` (freeze the wire contract); Rust CI (build/test/clippy/fmt); `casl-conformance` skeleton + shared corpus port. | Workspace builds; `casl-proto` + round-trip tests; CI green; corpus shared with F\*/Python. | — | M |
| **P1 Rust broker (drop-in)** | Reimplement P1.0 broker in `casl-broker` behind the SAME protocol; monitored oracle boundary; deny-by-default effects; observation capture; stdio + lib transports. | The existing Python broker tests (ported) pass against `casl-broker`; byte-parity on the protocol; the Python clients work unchanged. | P0 | M |
| **P2 Confinement** | `casl-host`: rung-3 (subprocess + Linux namespaces + seccomp; the broker socket is the only egress) → rung-4 (`wasmtime` WASI component host; imports = CASL capabilities only). | **Mediation negative-test matrix green**: a confined artifact's direct model/network call FAILS; only the broker channel works. (Linux/CI; macOS via container — documented.) | P1 | L |
| **P3 C ABI + 2nd binding** | `casl-ffi` (cbindgen); a C binding; one of {JS, Java}; binding codegen from `casl-proto`. | A C and a JS/Java artifact reach the model *only* via the broker, confined; one policy across 3 languages. | P1 (P2 for confinement) | M |
| **P4 Checker port** | Promote `engine/`→`casl-core`; `casl-surface` parser; `casl-check` (projectability, concurrency/async gates, contract entailment via z3, grades); attack corpus + admits/audit equivalents. | Rust `casl check` matches Python+F\* on the whole corpus + attack corpus (rejected); conformance differential green; admits gate retained. | P0 | L |
| **P5 Conductor + project layer** | `casl-conductor` (dispatch + runtime re-attestation + approval gate + supervision/failure-strategy + provenance trace); `casl-project` (manifest/deps/trace/seam/attestation/gate/grade-flow). | The **secretariat/PDF dogfood runs end-to-end** through the Rust stack — confined, gated, graded — with the full negative-test matrix green. | P2, P4 | L |
| **P6 CLI + bindings GA** | `casl-cli` single binary (all verbs); publish bindings (pip/npm/JAR/C header); quickstart + per-crate READMEs; installer. | `cargo install`/download one binary; `casl init/gate/run`; bind from ≥2 languages; docs complete. → **use-ready (DoD §1).** | P3, P5 | M |
| **P7 TCB unification (if feasible)** | F\*→Rust/C extraction spike for `casl-core` (Aeneas/Charon, or Low\*/KaRaMeL); else strengthen the conformance differential to a ratcheted certificate. | Either the running core *is* the extracted proven artifact, or a documented, ratcheting conformance bound (honest residual). | P4 | L/research |

**Critical path to the first dogfood:** P0 → P1 → P2 → P4 → P5. P3 (more bindings) and P6 (packaging) and P7
(proof unification) parallelize/follow.

---

## 5. Cross-cutting engineering

**Testing & verification (the conformance pyramid):**

- **Unit** per crate (cargo test).
- **Conformance differential** (mandatory CI gate): `casl-conformance` runs the F\*-extracted core, `casl-core`,
  and the Python reference over one shared corpus; any divergence fails CI. This is how a Rust component is
  *pinned* before the Python one retires — and the honest TCB story until P7.
- **Property-based** (`proptest`) for parser round-trip, projection, merge.
- **Fuzzing** (`cargo-fuzz`) for `casl-surface` and the broker protocol parser.
- **Attack corpus**: `examples/attacks/*` MUST be rejected (ported gate).
- **Negative-test matrices**: mediation (P2 — bypass fails), dispatch (P5 — tamper/unattested/unapproved/
  unbound refuse).
- **F\* admits gate** (`scripts/check_admits.sh`) + the **living audit** retained as CI gates.

**CI:** cargo build/test/clippy/fmt; `cargo-audit` (dependency CVEs); F\* verify + admits; Python (transitional)
+ the differential; the attack corpus; branch-guard (signed TCB tip).

**Security invariants (must hold by construction — `docs/architecture.md`):** complete mediation (broker
always-invoked); no ambient authority (capabilities only, deny-by-default); confinement makes the broker the
sole channel (P2); honest, conservative grade (never `?`→✓). These are acceptance conditions, not aspirations.

**Versioning/release:** SemVer per crate; the protocol is **capability-negotiated** (bindings/broker evolve
independently); the proof core versioned separately; bindings published per-ecosystem, pinned to a protocol
capability set.

**Observability/ops:** structured provenance trace (tamper-evident); `casl observe` over the conductor;
metrics on broker calls/denials/approvals.

---

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Second-system rewrite stalls / regresses | high | high | Strangler-fig; conformance differential; Python runnable until each piece is pinned; ship value each phase (P1, P2 are usable alone). |
| F\* extraction blocked (krml/Eurydice) | high | medium | P7 is "if feasible"; the conformance differential is the fallback honest story; never block the product on it. |
| Two impls drift during migration | medium | high | One shared corpus; the differential is a hard CI gate; retire Python per-component only after parity. |
| WASI per-language maturity (Python/Java) | medium | medium | rung-3 OS sandbox is the portable floor; rung-4 per language as toolchains mature; macOS = container (documented). |
| Scope creep (rewrite everything) | medium | high | Runtime first (broker/host/conductor); checker porting (P4) is conformance-pinned; build-time tooling can stay Python longest. |
| TCB grows with the runtime in Rust | medium | medium | Keep crates small + audited; `casl-ffi` surface minimal; the broker is the only privileged path. |

---

## 7. Progress & next step

**DONE (2026-06-25, on `feat/broker-p1`):**
- **P0** — `rust/` Cargo workspace + `casl-proto` (the JSON-RPC wire protocol, 4 tests) + Rust CI
  (`.github/workflows/rust.yml`: fmt-check, clippy `-D warnings`, test, + a conformance job).
- **P1** — `casl-broker`: the reference monitor in Rust (monitored oracle boundary mirroring
  `oracle.oracle_step` + the cost/refusal monitor; deny-by-default effects; capability negotiation; stdio
  server). clippy + fmt clean; 11 Rust tests; and the **cross-impl parity** is green — the existing Python
  client (`casl.client`) drives the Rust broker binary unchanged over the wire (`tests/test_broker_rust_parity.py`,
  the seed of `casl-conformance`). This validated the migration mechanic: Rust behind the frozen contract,
  pinned by a differential, with the Python reference still runnable.
- **P1.5** — the broker as a multi-provider **capability service** (`provider.rs`): `Provider {OpenAiCompat,
  Claude, Gemini}` with pure, offline-tested request-build + response-parse (token usage = the H4 measured
  cost) behind a thin `Transport` seam; **capability flags** — an artifact declares `llm:<provider>` (etc.)
  at `initialize`, and `oracle` is gated on the declaration (deny-by-default, `-32011`). 17 broker + 4 proto
  tests; parity still green. Live `ureq` HTTP send deferred (needs a key + network). Encodes the **opt-in
  posture** (§0.5): the broker is a service, not a cage.
- **P1.5 Python parity + conformance corpus** (`feat/python-parity-p1.5`) — the gating path is **no longer
  Rust-only**. The Python reference now mirrors it: `src/casl/providers.py` (the same `Provider{OpenAiCompat,
  Claude, Gemini}` build/parse + `Transport`/`ProviderBackend`), capability declaration at `initialize`, and
  `oracle` provider-gating (`-32011`) in `src/casl/broker.py`. A single shared corpus
  (`tests/test_conformance.py`) drives **both** brokers over the one wire protocol — covering the gating
  **and** the monitored verdicts (ok / overspend→violation+blame / refusal / H4 underreport→violation). On a
  built host every case runs live against the Rust binary (9 Python + 9 Rust); the differential — not §0.5
  prose — now pins the posture. (Also: `Client(env=…)` makes the subprocess transport hermetic and removes a
  latent cross-test env-pollution.) Booked as **CEP-0076**. **161 passed / 0 skipped, audit ✓.** Awaits the
  user's signed merge. Still deferred: live `ureq`/provider HTTP send (needs a key).

- **Conductor slice (Layer 3, `feat/conductor`)** — `casl run --project` now drives a *verified*
  choreography end-to-end **through the broker**: `src/casl/conductor.py` (project-aware: manifest +
  choreographies + typed-seam bindings; gates the hull, then conducts) + one additive `dispatch=` hook in
  `run.py` (broker-mediated effect check; `dispatch=None` ⇒ the proven interpreter is unchanged). The broker
  is the *access* monitor, the conductor the *contract* monitor (two policies; `docs/conductor.md` §3).
  Dogfood `examples/projects/triage/` (oracle + approval-gated effect, both seam-bound) conducted
  end-to-end; `tests/test_conductor.py` (10 tests) + audit green. Booked as **CEP-0077**. This is the rung
  that makes CASL a *runtime*; **P2 confinement** is the rung that makes that runtime *containment-enforced*
  (Variant C in `docs/conductor.md` §4: polyglot artifact-as-confined-subprocess activities).

- **Capability providers / P2 confinement — rung-2 done + rung-3 scaffolded (`feat/confinement`).** The
  no-ambient-authority model (CEP-0078, `docs/confinement.md`): raw I/O lives only in single-purpose,
  human-signed *provider* artifacts; a `confined` artifact may act only through a granted provider. Rung-2
  (gate-time, by construction) is realized end-to-end + verified: `src/casl/capability.py` (single-purpose +
  unambiguous + no-ambient-authority + io_grade), the `provides`/`confined` manifest fields, the obligation
  gate (a provider needs a human signature), `tests/test_capability.py` (9). Rung-3 is scaffolded as
  `rust/casl-host`: the seccomp allow/deny lists + egress plan as pure data, unit-tested on every OS (7
  tests), `launch` fail-closed; the syscall-level enforcement (empty netns + seccomp + broker-only fd) is
  **staged for a Linux CI runner**. Decisions research-rated (`docs/confinement.md` §5): netns+seccomp (not
  Landlock as the egress cut), pure-Rust host, WASI rung-4 endgame.

- **P4 checker port — started (`feat/casl-core-checker`).** Promoted the former `engine/` into the
  `rust/` workspace as **`casl-core`** and completed its `wellformed` to the full F* predicate
  (`wellformed_core` = contractive ∧ no_self ∧ gdistinct ∧ closed ∧ projectable for {C,A,J,D}, mirroring
  `fstar/CASL.fst`). Pinned by a **412-protocol conformance differential** (`tests/differential.rs`): the
  corpus is single-sourced from `casl.tcb_corpus` and each verdict is `tcb_bridge.projectable` (itself
  pinned to the F*-extracted kernel) — so casl-core ↔ Python(↔F*) agree on every protocol (the strangler-fig
  safety net; never two unpinned impls). `cargo test` green (proto 4 / broker 17 / host 7 / core 7 + the
  differential); fmt + clippy clean. This advances the "retire Python once the Rust alternative is capable"
  decision (§8); remaining: the surface parser + the per-feature checks (level/assurance, capability,
  approval-dominance, …) ported behind the same differential, then promote casl-core to authoritative.

**Next: continue the program (2→1→4): wire confinement into the conductor → requirements→verified-project
loop → finish rung-3/rung-4. (P2 rung-3 enforcement still needs a Rust+Linux runner.)** `casl-host`: rung-3 first (Linux namespaces + seccomp so the broker socket is the
artifact's only egress; the **bypass-fails negative test**), then rung-4 (`wasmi`/`wasmtime` WASI host). This
turns "the binding goes through the broker by convention" into an enforced guarantee. (Linux/CI; macOS via
container — documented.) Then P3 (C/JS bindings from the schema) and P4 (checker port).

---

## 8. Resolved decisions (2026-06-25, research-backed; weighting: security + understandability > speed)

| Decision | Resolution | Why |
|---|---|---|
| Core language | **Pure Rust** default; relax only for FIPS-required crypto, hard side-channel crypto, or a proven WASM perf need | Every needed piece has a mature pure-Rust crate; only a FIPS cert is out of reach. |
| Confinement engine | **`wasmi`** (pure-Rust interpreter) default; C-free `wasmtime`/Cranelift only if WASI perf demands | No-JIT, deterministic, twice-audited; far smaller attack surface (wasmtime carries 2026 Critical sandbox-escape CVEs). |
| Crypto / attestation | dalek + RustCrypto with the `fiat` (formally-verified) field backend; pin + `cargo audit` | Pure Rust, verified arithmetic, no asm/C in the TCB. |
| Bindings transport | **JSON-RPC over stdio** (broker = subprocess); in-process C ABI reserved for a future *non-monitor*, single-language, latency-bound component only | OS-enforced isolation + one inspectable wire contract (LSP/MCP) vs N unsafe shims sharing the monitor's failure domain. |
| SMT entailment | **Shell out to a pinned `z3` binary** over SMT-LIB2 (fail-closed on `unknown`) | Keeps Z3's correctness while moving ~371K lines of C++ out of the TCB; no mature pure-Rust SMT exists. |
| WASM packaging | rung-4 **now for Rust + C/C++**; size-budgeted for JS/Python; **Java stays rung-3** | Sandbox strength is uniform (capability, no ambient authority); only toolchain maturity differs; Java→component is still experimental in 2026. |
| Retire Python reference | **Only once the Rust alternative is capable** (parity via the conformance differential); keep it as a differential oracle while useful | The strangler-fig invariant — never two unpinned impls. |

Residual genuinely-open items: whether a FIPS 140-3 cert is ever required (→ `aws-lc-rs(fips)`); `libcrux`
maturation as the pure-Rust high-assurance crypto path; WASI's still-moving 0.3→1.0 surface. Full rated
brief with references is archived with this program.
