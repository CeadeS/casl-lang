# Confinement-by-default for LLM-authored artifacts

*Research → variants → rating → synthesis → verification → implementation plan.*
Status: design analysis (not yet implemented). Date: 2026-06-28.

## 1. Motivation

The motivating case is the `scriptorium` project (`../Work`): a CASL desk app whose
choreographies, manifest, and typed seam are complete and green, but whose **live
code bypasses CASL entirely**. `app/mail.py::move_to_preda` deletes mail with raw
`imaplib` (`COPY` + `\Deleted` + `EXPUNGE`); `send_reply` sends with raw `smtplib`;
the "approval gate" is a hand-rolled Flask confirm. Nothing routes through the broker
or the conductor. The code was **LLM-authored**.

That sharpens the policy question into the one this doc answers:

> Since the artifact bodies are written by an LLM (untrusted), confinement should be
> the **default**, and any opt-out for performance should be a per-artifact decision
> that an LLM body cannot grant itself.

The instinct is right; the naïve implementation is dangerous (see §7). This doc fixes
both the policy and its ordering.

## 2. Threat model

- **Adversary**: an LLM-authored (or compromised-dependency) artifact body. It may do
  anything Python lets it do at runtime: open sockets, read the filesystem, exfiltrate
  secrets from the environment, `import` siblings, spawn subprocesses.
- **Trusted base**: the human author/attester (signs *accountability* for specific
  content), the F\* kernel, the broker as reference monitor, the OS confinement layer
  *if and when it actually runs*.
- **Goal**: an effect on the world (send/move/delete/post/network) happens **only**
  through a granted, single-purpose provider mediated by the broker — never via ambient
  authority the body took for itself.
- **Non-goals**: defeating a dishonest *human* attester (that is the accountability
  anchor, not a mechanism), or side-channels.

## 3. Findings

### 3.1 External (literature + current practice)

- **Object-capability model / PoLA.** Authority is an unforgeable reference; there is
  **no ambient authority** — a component can reach only what it was explicitly handed,
  and capabilities *attenuate*. This is the theoretical frame for "default-deny + grant
  handles." [ocap-wiki], [capmyths]
- **WASI / Wasm.** A module "starts with **no ambient authority** and can only do what
  the host explicitly grants." Direct file/network access is *unrepresentable* unless a
  capability handle is passed. This is confinement **by construction** — the strongest
  end state. [wasi], [wasmtime]
- **OS sandboxing (seccomp-bpf + Landlock + netns).** The current production pattern for
  untrusted code: layered, independent, **deny-by-default**, with a standard blocklist
  (`ptrace`, `mount`, `unshare`, `setns`, `pivot_root`, `bpf`, raw `socket`). Network
  exfiltration is closed by a per-job **network namespace** or a seccomp socket deny.
  This is *exactly* the policy `casl-host` already encodes as data. [landlock], [sandlock]
- **LLM-code is the named threat, and sandboxing is mandatory, not optional.** A 2025
  Veracode study found **45% of AI-generated code fails security tests**; OWASP's Agentic
  Top-10 **ASI05 (Unexpected Code Execution)** lists sandboxing as a *required control*;
  real 2025 CVEs are agent sandbox escapes. Guidance converges on **default-deny fs +
  network, kernel-level isolation, per-task secrets, egress allowlists**, and
  **per-tool** (not one-size) sandboxes. [llm-sandbox], [sandlock]

The external consensus and CASL's own "no-ambient-authority" design agree completely.
The gap is purely one of *implementation completeness*, not direction.

### 3.2 Internal (CASL today, with file refs)

- **The gate** (`src/casl/obligation_gate.py::check_project`) is a deny-by-default
  conjunction over `man.artifacts`; new obligations slot into the `for a in man.artifacts`
  loop. Obligations today: manifest validity, dependency burden/evidence, external-pinned,
  requirement present, body exists, line-trace, **human attestation** (for
  `generated`/`oracle`/provider), typed seam, capability no-ambient check.
- **`kind`** ∈ `{external, generated, verified, oracle}` (`project.py:25`); `generated`
  /`oracle`/`external` are `UNPROVABLE` and **hard-floored at G3 "attested"**
  (`project.py:126-128`). Trust derives from *structured* kind + signatures, never free
  text (the R-H1 / LH-F-013 lesson).
- **`confined`** is a manifest bool, currently **opt-in** (`project.py:124,210`).
- **Rung-2 (gate-time no-ambient)** is real and wired: `capability.check_no_ambient_authority`
  rejects any capability a confined artifact uses that doesn't resolve to a granted
  provider (`capability.py:66-82`).
- **Rung-3 (OS sandbox)** is **policy-as-data + a Python PoC, but not enforced in
  production**: the Rust `casl-host::launch()` returns `EnforcementStaged` (Linux) /
  `UnsupportedOs` (`rust/casl-host/src/lib.rs:198-205`); `host.confine()` is only invoked
  by its own self-test (`host.py:121`). **Rung-4 (WASI)** is docs-only.
- **Broker** (`src/casl/broker.py`, `rust/casl-broker`) is a working reference monitor:
  undeclared LLM provider ⇒ `-32011 CAPABILITY_DENIED`; undeclared tool ⇒
  `{allowed:false}` deny-by-default.
- **Conductor** (`src/casl/conductor.py`) gates the hull first ("prove, then execute"),
  then dispatches effect sites through the broker; `BrokerDispatch.effect` refuses an
  ambient effect for a confined actor (`conductor.py:62-78`).
- **No body-scanning lint exists.** `dependency.check_imports` exists but **has no caller**
  and no `used`-extractor (`dependency.py:117`); `profiles.py`'s AST scan guards CASL's
  *own* module layering, not user bodies. The gate checks *binding + boundary, not body*.
- **The actual executor is unconfined.** `activity.SubprocessActivity` runs a body via
  `subprocess.run(..., env=self.env)` with `env` defaulting to `None` → the child
  **inherits the full environment and all host I/O** (`activity.py:75-93`). Nothing in the
  run path consumes `confined` as an OS-enforcement signal.

**Headline:** today `confined` is an *accounting label with no runtime teeth on any OS*.

## 4. Variants

| # | Variant | One line |
|---|---------|----------|
| **A** | Gate-only mandatory `confined` | Deny at gate if `kind∈{generated,oracle}` and not `confined`. Cheap; **structural only**. |
| **B** | Finish rung-3 OS sandbox | Land netns+seccomp so a confined body physically can't open a socket. Real enforcement; Linux-only; host TCB. |
| **C** | WASI rung-4 (by-construction) | Run bodies as Wasm components; ambient I/O unrepresentable. Strongest; large lift; not built. |
| **D** | Static import/effect lint | Revive `check_imports` + AST extractor; deny raw-I/O imports not backed by a capability. Cheap; **unsound** alone. |
| **E** | microVM / external sandbox | Firecracker/gVisor/E2B per artifact. Strong isolation; heavy ops; outside the in-process broker model. |
| **F** | **Graded ladder keyed to kind+attestation** | Confinement mandatory & **fail-closed at runtime** for LLM kinds; rung chosen by what the host can enforce; lint as deny-only layer; opt-out is an attested, graded obligation LLM bodies can't claim; perf via grant granularity. |

## 5. Rating

Criteria scored ▲ strong / ◧ partial / ▽ weak.

| Variant | Enforcement (stops direct I/O) | LLM-fit | Perf | Effort vs today | TCB / by-construction | Lang-agnostic | Fit with gate/grade |
|---|---|---|---|---|---|---|---|
| A gate-only | ▽ (structural) | ◧ | ▲ | ▲ lowest | ▲ tiny | ▲ | ▲ |
| B rung-3 | ▲ | ▲ | ▲ (compute free) | ◧ med (+Linux runner) | ◧ host+kernel | ▲ | ▲ |
| C WASI | ▲▲ | ▲▲ | ◧ | ▽ highest | ▲ by-construction | ▲ | ▲ |
| D lint | ◧ (catches obvious) | ◧ | ▲ | ▲ low | ▲ tiny | ◧ (Python) | ▲ |
| E microVM | ▲ | ▲ | ▽ | ▽ infra | ▽ large | ▲ | ▽ |
| **F ladder** | **▲→▲▲** | **▲▲** | **▲** | **phased** | **graded** | **▲** | **▲** |

A alone is a **false sense of security** (it changes labels, not behaviour). D alone is
evadable. E is overkill for a desk app and breaks the in-process model. B is the real
near-term enforcement; C is the end state. **F sequences them honestly** and is the
recommendation.

## 6. Synthesis (recommended design)

**Principle:** *confinement is a property the gate REQUIRES, the runtime PROVIDES, and the
grade HONESTLY REFLECTS; trust never comes from an LLM body's self-declaration.*

Five rules:

1. **Default-deny confinement for LLM kinds.** `kind∈{generated,oracle}` ⇒ `confined`
   is mandatory. But — corrected by verification — this is only meaningful when paired
   with rule 2.
2. **Fail-closed runtime (load-bearing).** When an artifact is `confined` and the host
   **cannot actually enforce** confinement, the runtime **refuses to spawn it** rather
   than running it unconfined. "Confined-but-unenforceable" ⇒ no execution, not silent
   bypass. This is the single most important change and it is *independent of Linux*
   (on macOS the correct behaviour is to refuse).
3. **The per-artifact knob is the capability GRANT, never confinement on/off.** Widen what
   a confined body may reach by granting providers (coarse handles in the egress plan),
   not by un-caging it. Performance: seccomp/Wasm leave **compute** free; only the broker
   boundary costs, and coarse grants amortize it. The "opt out for performance" case is
   therefore mostly illusory.
4. **Opt-out (`unconfined`) is an attested, graded obligation.**
   - For `generated`/`oracle`: **rejected in the loader** — cannot be claimed at all.
   - For human kinds: allowed only with valid human attestation **that binds `kind` and
     `producer`** (so mislabeling is a signed lie), the static lint passing, and a
     **computed grade floor** that caps any ambient-authority/`unconfined` artifact at G3
     until rung-3 is verifiably enforced. Never silent, never free.
5. **Static lint is deny-only defense-in-depth, never a confinement substitute.** It bans
   raw-I/O *and* dynamic-import primitives (`__import__`, `importlib`, `eval`, `exec`,
   `ctypes`) in confined bodies, while we rely on rule 2 for actual containment.

**For scriptorium**, the design says: mark the four brains `generated`+`confined` with
only `llm:*`; move `imaplib`/`smtplib` out of `app/` into the `external` providers behind
the broker; run via the conductor. The static lint **fails today** on `app/mail.py`'s
`import imaplib` — which is exactly the alarm that converts CASL from blueprint to
enforced.

## 7. Verification (adversarial red-team)

A red-team pass against the real code found the central claim ("a confined LLM artifact
cannot reach the world") **false today**, and several holes in the naïve design. Verbatim
priorities:

| Sev | Weakness | Minimal fix |
|---|---|---|
| **Critical** | `confined` has **zero runtime enforcement** on any OS: `casl-host.launch` returns staged/unsupported, `host.confine` is never called in prod, and `activity.SubprocessActivity` (`activity.py:78`) spawns bodies with inherited env + full I/O. A `generated` body's `import imaplib` is not stopped. | **Fail-closed at spawn** (rule 2): refuse to run a `confined` body the host can't cage; cap grade at "declared" while unenforced. |
| **Critical** | macOS (the dev host) and Linux-without-the-runner have **no enforcement path at all** — "confined" is decorative there. | Restrict confined runs to enforcing hosts; else deny / hard-cap grade with a loud marker. |
| **High** | Static lint **not wired** (`check_imports` has no caller; no `used` extractor) and **unsound** (`__import__`, `importlib`, `eval/exec`, `getattr(os,…)`, `ctypes`, C-ext, non-Python bodies evade). | Wire as deny-only lint; never treat passing as confinement; ban dynamic-import primitives; rely on the runtime cage. |
| **High** | **Attestation fraud**: `kind`/`producer` are author-asserted free fields not bound by the signature; mislabel LLM body as `kind=verified, producer=human` to skip the rule. Re-introduces the R-H1 anti-pattern. | Trigger confinement on "no real F\* proof," not on `kind`; **bind `kind`+`producer` into the signed record**; require attestation for `verified` effect-site artifacts. |
| **High** | **Confused deputy**: no rule stops a confined LLM artifact and an `unconfined` human artifact **sharing a provider**, or — on the in-process path — **importing each other in one address space** (`conductor.py:133`, global `provider_index`). | Caller-scope grants; forbid confined+unconfined co-execution / shared provider unless attested as a unit; require real process isolation before "confined" means anything. |
| **Medium** | Grade "drop" for opt-out **has no implementation**: `floor()` has no term lowering a `verified unconfined` artifact from G0; `io_grade`'s cap-at-attested is prose only and not folded into `effective_grade`. | Add `unconfined` field; cap ambient/`unconfined`/unenforced-confined at G3 in the grade used by `effective_grade`; fold in `io_grade`. |
| **Medium** | `confined` **defaults to the unsafe value** (`project.py:210`) and is read fail-open via `getattr(...,False)` everywhere; typos (`confned=true`) fail open. | Make `confined` required+strict-bool for LLM kinds; reject `unconfined` for those kinds in the **loader**, not just the gate. |
| **Medium** | **TOCTOU** gate↔run: manifest/bodies re-read at spawn (`conductor.py:114`, `activity.py:78`); gated bytes ≠ run bytes. | Re-verify content hash at spawn, or run from an immutable snapshot. |
| **Low/Med** | **Unbound confined artifact** (no `implements`) ⇒ `required_capability`→`None` ⇒ no-ambient check **skipped** (`capability.py:76`); confinement unchecked. | Treat an unbound confined artifact as deny-by-default. |
| **Low** | `BROKER_BUILTINS={"broker"}` hardcoded allow-string an author could name for a free pass. | Make builtin-broker a typed, non-author-settable capability. |

**Residual risks even after fixes:** rung-3 host/kernel TCB; static-lint unsoundness
(why rung-3/4 matter); dishonest-human attestation (accountability anchor, not a
mechanism); non-Linux hosts have no by-construction story until WASI.

**Net:** the obligation, the lint, and the grade-cap are good ideas that are **not yet
load-bearing in code**. Ship no "confined ⇒ safe" language until the fail-closed runtime
(Critical) and the safe-by-default field (Medium) exist; everything else is hardening on
top of an open door.

## 8. Implementation plan (honest ordering)

Re-prioritized so the load-bearing, non-TCB, *testable-without-Linux* fixes land first.

- **P0 — Safe-by-default field + fail-closed spawn (CASL core).** `project.py`:
  `confined` required+strict-bool for `generated`/`oracle`; reject `unconfined` for those
  kinds at load. `activity`/`conductor`: if `confined` and the host can't enforce, **refuse
  to spawn** (typed refusal), and cap grade at "declared/attested." Pure Python, no F\*/TCB
  change. Testable on macOS (asserts confined bodies refuse to run). *This converts
  `confined` from decorative to real.*
- **P1 — Gate obligation.** Add the deny-by-default predicate (`kind∈{generated,oracle}
  ⇒ confined`) in `obligation_gate.check_project`. Now meaningful because P0 made it bite.
- **P2 — Static lint (deny-only) + wire scriptorium.** AST `used`-extractor → call
  `check_imports`; ban dynamic-import primitives in confined bodies. Refactor scriptorium:
  `imaplib`/`smtplib` move into providers; brains become `generated`+`confined`; run via
  conductor. The lint should **fail** on today's `app/mail.py` (the demonstration). No live
  effects executed (real creds present).
- **P3 — Finish rung-3 (`casl-host`).** Land the staged netns+seccomp exec on a Linux
  runner; wire `activity` to call it; only then may a confined artifact's grade rise above
  attested. Security-central → supervised, signed merge.
- **P4 — Bind provenance + close confused-deputy.** Attestation binds `kind`+`producer`;
  caller-scoped grants; forbid confined+unconfined co-execution / shared provider; TOCTOU
  hash-at-spawn. Security-central → supervised.
- **P5 — WASI rung-4 (by-construction).** The end state; per the engineering plan.

## Sources

External:
- Object-capability model — Wikipedia: https://en.wikipedia.org/wiki/Object-capability_model  `[ocap-wiki]`
- Capability Myths Demolished (summary) — the morning paper: https://blog.acolyer.org/2016/02/16/capability-myths-demolished/  `[capmyths]`
- WASI — Introduction: https://wasi.dev/  `[wasi]`
- Wasmtime — Security: https://docs.wasmtime.dev/security.html  `[wasmtime]`
- Landlock — Linux Kernel docs: https://docs.kernel.org/userspace-api/landlock.html  `[landlock]`
- Sandlock: per-tool sandboxing for AI agents — Multikernel: https://multikernel.io/2026/03/25/sandlock-mcp-per-tool-sandboxing/  `[sandlock]`
- AI Agent Sandboxing guide (OWASP ASI05, Veracode 45%, CVEs, E2B): https://beyondscale.tech/blog/ai-agent-sandboxing-enterprise-security-guide  `[llm-sandbox]`

Internal (LLang, `main`): `src/casl/obligation_gate.py`, `capability.py`, `project.py`,
`host.py`, `activity.py`, `broker.py`, `conductor.py`, `run.py`, `grade_flow.py`,
`levels.py`, `attestation.py`, `dependency.py`, `keyring.py`; `rust/casl-host/src/lib.rs`,
`rust/casl-broker/src/lib.rs`, `rust/casl-proto/src/lib.rs`.
