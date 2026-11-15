# CASL — How it all works together (the keystone architecture)

**Date:** 2026-06-25 · **Status:** architecture decision record (research-backed). **Supersedes** the narrow
effect-runtime framing of `docs/execution.md`. **Companions:** `docs/ide.md` (authoring loop),
`docs/analyses/forwarding-fidelity-a1.md` (the O4/enforcer-cap result), `docs/vision.md`.

> **In one sentence.** CASL is a *choreography-specified, declaratively-orchestrated, capability-confined
> supervisor*: you write a verified `.casl` blueprint; an agent fills it with polyglot code artifacts that
> CASL gates at build time; and `casl run` **conducts** those artifacts and LLM agents along the proven
> protocol — every model/tool call forced through one capability broker, every irreversible effect through a
> human gate, every step graded so a person can see exactly how much to trust the run.

CASL is the conductor, **not** the instrument: the artifacts (Python/Java/C/JS, or an LLM at an `oracle`
site) do the work; CASL specifies, verifies, conducts, confines, and supervises.

---

## 1. The problem, formalized

**Actors.** A *principal* (human, or an LLM acting as one) who starts a run; the *conductor* (CASL's verified
core); *artifacts* (polyglot code units the project ships); *agents* (LLMs at `oracle` sites); *capabilities*
(the model endpoint(s) and tools); a *human supervisor* (often the principal) who reviews and approves.

**Trust boundary.** The conductor + the broker + the `.casl` spec + the F\* core are the **trusted computing
base (TCB)**. Everything else — every artifact, every agent — is **untrusted** (artifacts are partly
LLM-written). The thesis: *prove the deterministic hull, treat each agent/artifact as a monitored oracle;
agents may veto, never vouch.*

**The unbypassable-invariant set** (what must hold on *every* run, by construction):

- **I1 — Complete mediation of capabilities.** No artifact, in any language, can reach the model or a tool
  except through CASL. (Anderson reference monitor: always-invoked, tamperproof, verifiable.)
- **I2 — No irreversible effect without disclosure + human approval**, decided per effect, bound to the
  concrete action (not a branch label).
- **I3 — Runtime conformance = what was gated at build time.** The artifact CASL dispatches is the attested,
  conformant one (content hash re-checked at the moment of call — the O4 / enforcer-cap discharge).
- **I4 — Honest, conservative grading.** Every step carries an assurance grade encoding the *kind* and
  *coverage* of its guarantee; the system never over-states (an inflated grade is worse than none).
- **I5 — Tamper-evident, complete provenance** over the mediated seam (an unmediated path is an unrecorded
  path).

**Success criteria.** (a) *Security*: I1–I3 hold by construction, not convention. (b) *Human-verifiability*:
a person can supervise with **bounded effort** — read a small `.casl` blueprint + a grade report + a trace,
and the grade calibrates trust. (c) *Polyglot*: artifacts in any language, one enforcement policy. (d)
*Natural*: authoring/operating feels like a build tool (`init` → write → `gate` → `run`).

---

## 2. The three layers (the synthesis)

### Layer 1 — Specification (choreographic / MPST): *prove the hull*

One global `.casl` protocol — roles, message order, payload contracts, effects, approval gates — **projected**
to per-role local types and checked by the verified F\* core (communication-safety, fidelity, projectability;
Honda–Yoshida–Carbone 2008/2016; Montesi 2013; the Choral line 2024). The `.casl` file plays two roles at
once: the **human blueprint** you review (Lamport, "blueprints") and the **safety policy** the run must obey
(Necula, proof-carrying code). This is where the deterministic hull is *manufactured and proven*.

### Layer 2 — Supervision (build-time gate): *keep the artifacts honest*

`casl init` scaffolds the project (folder, git, keys, layout). An agent (or human) writes the `.casl` and
**implements the artifacts** in any language. `casl gate` — run **frequently** (pre-commit / CI / `casl
watch`), like a compiler in the loop — checks the code artifacts *conform*: the **seam** binds each artifact
to a site (`implements="Proto:Label"`, kind matches the site's nature), every owned line **traces** to a
requirement, each is **attested** (content hash + human signature), deps are **pinned**, and the **grade** is
computed. It fails on drift. The grade report is the **proof-carrying certificate**; the human supervises by
reading the `.casl` + the grades, not the agent's full output. (This whole layer exists today: `project`,
`seam`, `trace`, `blame`, `gate`, `attestation`, `dependency`, `levels`.)

### Layer 3 — Execution (the conductor, `casl run`): *run it choreographed*

`casl run project --entry NAME args` is the **entrypoint** — a human or an LLM invokes it. CASL is a
**deterministic conductor** in the mold of a *declarative, statically-verified* workflow engine (AWS Step
Functions), **not** replayed imperative code (Temporal/Azure) — so it gets determinism *by construction and
verification* (the hull is the verified `.casl`), avoiding the versioning tax, duplicate-effect hazard, and
runtime non-determinism errors of orchestrator-replay. The conductor drives the verified choreography over
the project's **own** artifacts + LLM agents, which run as **isolated, confined participants** (§3) reachable
only through the **broker**. At each step it: dispatches to the bound artifact via the seam; lets the artifact
reach the model/tools **only** through CASL's capability connector; **monitors** the contract (a runtime
verification monitor — safety-shaped properties only); **gates** irreversible effects behind human approval
with **runtime re-attestation** (I3); follows the branch the verdict implies; and records a **tamper-evident
provenance trace**. Robustness follows the actor/OTP supervision tradition: participants are isolated behind
the message seam, the conductor holds a *declared failure-strategy table* (timeout→kill, restart-to-
checkpoint, backoff-then-escalate, stop-on-contract-violation), and the conductor holds all verdict authority
— the operational form of "veto, never vouch."

> **Honest framing (do not over-claim).** Classic choreography earns deadlock-freedom *by being
> decentralized — no conductor*. CASL re-introduces a central conductor to get a single chokepoint for
> approval + supervision of untrusted participants. The trade is explicit: liveness/progress for the
> *orchestrated* execution must be **proved or monitored at the conductor/seam**, not imported from
> endpoint-projection theorems. The specification-time guarantees (comm-safety, projectability) are
> choreographic; the run-time guarantees are earned at the seam.

---

## 3. The chokepoint — one broker, all access, made unbypassable

This is the heart of "controllable," and the answer to *"it's not easily controllable how Python talks to
the model."*

**The broker is the one reference monitor.** Every model/tool/messaging call from any artifact goes through a
single CASL **broker** process that holds all policy + config (the connector to ollama/vLLM/endpoints; the
tool registry). It must meet Anderson's triad — **always-invoked, tamperproof, small-enough-to-verify** — and
Saltzer–Schroeder **complete mediation** + **economy of mechanism**. As a runtime monitor it is an *execution
monitor* (Schneider): it can **enforce any safety-shaped policy** at the call ("capability present + approval
present + contract holds + re-attestation matches"), and with edit-automata power do **deny-and-substitute**
(refuse and hand back a typed refusal) without killing the run.

**Thin polyglot stubs, dumb couriers.** Each language (C/Python/Java/JS) gets a *thin* client stub that only
marshals `(site, request)` over **JSON-RPC 2.0 on stdio** (socket optional) to the broker and reads a typed
result — modelled on LSP/DAP and MCP, which independently solved "one server, N language clients" this way,
with **capability negotiation** for versioning (unknown fields ignored; absence = unsupported). The stub is
**not** security-critical (OWASP "never trust the client"); all trust/config lives in the broker; the stubs
are code-generated from one neutral schema, so the per-language surface is tiny and the TCB stays in one
place. (Out-of-process by design: a process boundary gives fault *and* security isolation that in-process FFI
throws away.)

**Making "the only path is the broker" real, not a promise.** Offering a connector is only a *convention*
until the artifact *cannot* reach the model any other way. The confinement ladder (weakest → strongest):

| Rung | Mechanism | Guarantee | Grade it can support |
|---|---|---|---|
| 0 | Convention ("please call via CASL") | none | — |
| 1 | Attestation + audit (sign artifact, log calls) | accountability *after* the fact | attested (G3) |
| 2 | `casl gate` import/dep lint (ban direct LLM/HTTP clients) | catches honest cases, not airtight | tested (G2)-ish |
| 3 | **OS sandbox + broker** (network namespace: only egress = broker socket; seccomp allow-list) | the *only* egress is CASL; coarse but real | bounded (G1) |
| 4 | **WASM/WASI component** (CASL is the host; the *only* imports are CASL capabilities) | complete mediation *by construction*, language-agnostic | bounded → proved (G1→G0) |

Rung 4 (WebAssembly Component Model + WASI) is the strongest: a module has **no ambient authority** and can
only call its host-granted imports, so restricting imports to a few typed capabilities makes mediation
structural and polyglot in one move. The recommended build is **rung 3 now** (subprocess + network namespace +
seccomp + broker — available today, language-agnostic) **with rung 4 (WASI components) as the hardening
target** — exactly mirroring CASL's own "bounded now, proved later" discipline. Belt-and-braces: rung 4 inside
rung 3 inside rung 1.

---

## 4. The grade — the human-verifiability yardstick

A person supervises by reading the `.casl` (small, legible) + the **grade report**. The grade is the
proof-carrying certificate; the CASL checker is the small proof-checker. For this to be *genuine* and not
nominal, two rules from the human-factors + runtime-verification literature are mandatory:

**(a) The grade encodes *kind* and *coverage*, conservatively** — never a flat score:

> **proved** (F\* hull; all runs) > **gated/enforced** (this run; safety properties only; mediated seam only;
> isolated monitor) > **monitored** (this run watched; for a non-safety contract "no violation" = *inconclusive*,
> not satisfied) > **tested** (some runs sampled) > **attested** (a human's word).

Every "monitored/gated" badge shows the contract's *monitorability class* and the *observation coverage*. A
three-valued monitor's `?` must **never** render as ✓. Hyperproperties (non-leakage/noninterference) and
liveness are **not** dispatch-enforceable (Schneider) — they must drop to bounded/tested/attested or be
discharged by static analysis. The grade also naturally **measures how much of the agent was governed**: a
fully-choreographed flow (oracle sites monitored, contracts checked) scores higher than a big opaque agent
loop that merely promises to use the connector (G3). That is a feature — it tells the human how much of the
run was actually supervised.

**(b) Engineer the human gate against automation bias** (the top failure mode — see §6). The grade is, in
trust-calibration terms, the instrument that makes the supervisor's trust *co-vary with real capability*
instead of collapsing to "the AI did it, looks fine" — but only if it is honest. An inflated grade
manufactures the over-trust that causes rubber-stamping.

---

## 5. Competing architectures considered (and the verdict)

| Architecture | Mediation/security | Human-verifiability | Polyglot | DX/maturity | Verdict |
|---|---|---|---|---|---|
| **A1 — in-process FFI SDK** (conductor links artifacts) | weak (TCB blended; a crash/native call escapes) | low | yes | fast now | **Reject** — unsound for untrusted code |
| **A2 — subprocess + broker (JSON-RPC/stdio) + OS confinement** | strong at syscall layer (only egress = broker) | good | yes (any lang w/ stdio+JSON) | **available today** | **Adopt now** |
| **A3 — WASM/WASI components, CASL as host** | strongest (complete mediation by construction) | good | yes (Rust/C prod; Py/Java pre-1.0) | maturing | **Hardening target** |
| **A4 — projected endpoints + distributed monitor (no conductor)** | mediation distributed | weaker (no single approval chokepoint) | yes | complex | **Reject** for the control requirement |

**Synthesis:** the deterministic *declarative-verified* conductor (Step-Functions-style, from the durable-
execution split) + **A2 now, A3 as the target**, with the grade reflecting which confinement rung a run used.
A1 is rejected outright; A4 loses the single chokepoint that I1/I2 require.

---

## 6. Red-team / honest residuals

- **Top failure mode — the honest-grade / rubber-stamp collapse.** An inflated grade (an inconclusive monitor
  shown as ✓, a non-monitorable contract, an unmediated effect) *manufactures* over-trust; automation bias
  (reliability paradox: vigilance *drops* as reliability rises; first-failure effect; back-end decision aids
  worse than front-end) *consumes* it. **Defenses (designed in):** present *evidence*, not a pre-formed
  "Approve?" verdict; force engagement with the concrete effect (target, data, blast radius) for high-risk
  actions; **friction proportional to risk** (not uniform — uniform friction trains habituation); named,
  single-owner, internalized accountability bound to the effect; make refusal as easy as approval + a stop-to-
  safe-state; keep raw evidence one click from any green grade; treat a *grade drop* as a salient event.
- **The "safe set" is the effect/irreversibility classification = R-H1.** Runtime assurance guarantees the
  envelope only as well as the model of "what is dangerous." If an artifact smuggles a mis-declared effect
  past the typed seam, that is a *spoofed sensor* and the guarantee fails silently. The classification must be
  structured + validated, never inferred from author free-text. This is the technical crux.
- **A fallible human replaces the verified backup.** In Simplex/RTA the backup controller is itself verified;
  here the ultimate authority on an irreversible effect is a human — so the guarantee is *conditional on the
  gate behaving correctly*, which is why §4(b) is not optional.
- **Confidentiality is not free.** WASM/sandbox isolation is architectural, not microarchitectural; Spectre /
  timing / covert channels cross the boundary. Mediation + integrity (I1–I3) are solid; *confidentiality*
  between mutually-distrusting co-resident artifacts needs extra hardening (process/VM isolation or
  Swivel-style mitigations) and must not be over-claimed.
- **The broker + runtime are now the whole TCB.** Keep imports narrow and typed, audit the capability
  implementations, keep the core small (seL4 is the existence proof that a capability monitor can be
  machine-checked), and patch the runtime.
- **Egress mediation ≠ containment by itself.** "Only egress is the broker" is sound *only* when backed by
  something the artifact cannot reconfigure (namespace/sandbox), not by the convention that it calls the
  broker (Istio itself says transparent interception "cannot securely enforce" this).

---

## 7. Worked example — the PDF / 3-agent app, end to end

The user's scenario: a manager agent coordinates a PDF-viewer agent and a project-built extractor; the goal is
to extract the target images from every page and store them in a DB with caption metadata.

**Choreographed form (`.casl`, roles M=Manager, V=Viewer, E=Extractor, D=DB):**

```
protocol PdfHarvest {
  roles M, V, E, D;
  agent M caps { db(row) scope "db:write" mode write; }
  M -> V : Open(path: Str);
  V -> M : Pages(n: Int) [n >= 0];
  // per page (bounded loop): extract, classify caption, store
  M -> E : Extract(page: Int) [page >= 1, page <= n];          // effect: project-built extractor
  E -> M : Figures(count: Int, caption: Str) [count >= 0] oracle;  // caption text via the model = oracle
  choice approval at M -> M {                                    // gate the irreversible DB write
    Store consent: { M -> D : Write(caption = Figures.caption) uses db irreversible; D -> M : Ok(); }
    Skip: { M -> D : Noop(); D -> M : Ok(); }
  }
}
```

Mapping to the architecture: each **model call** (the manager's reasoning, caption extraction) is an `oracle`
site, routed through the broker (I1); the **PDF-viewer tool** and the **extractor** are `effect`/tool sites,
also brokered; the extractor is project-developed code → a `generated` artifact, line-traced + attested
(Layer 2). The `[page>=1, page<=n]` contract is monitored at the seam; the **DB write is irreversible** →
human-approval gate + runtime re-attestation of the `db` handler (I2, I3); the forwarded `caption =
Figures.caption` carries lineage (A1 forwarding-fidelity). The whole run produces a tamper-evident trace (I5).
The human supervises by reading `PdfHarvest` + the grade report.

**Python-entrypoint form (the realistic, agentic variant).** A `main.py` reads PDFs and loops, calling the
model to extract info. Here the loop lives in Python — *opaque* to the conductor. Control reduces to: every
model/tool call goes through the CASL connector stub, and the artifact is **confined** (rung 3: no network
except the broker socket; or rung 4: a WASI component whose only imports are CASL capabilities). So *"how
Python talks to the model"* is no longer uncontrollable — it is **the only thing it can do is ask CASL**, and
the OS/WASM confinement makes that an *enforced* guarantee, not a convention. The grade is honest about the
difference: the choreographed form scores higher (more of it monitored/contract-checked); the opaque Python
loop is **G3 for the loop logic** but still carries the hard I1 guarantee "no ungoverned model/tool access."
**Same program, two assurance levels — and the grade says which you got.** This is exactly the
verifiability-vs-flexibility dial the project wants.

---

## 8. What exists vs. what is new, and the roadmap

**Exists today** (reuse): the monitored **oracle boundary** (`oracle.py`, `OllamaBackend`); the runtime
**capability broker** check (`run.py` `_tool_allowed`); the disclosure-bound **approval gate**; the **seam**
(`implements`, `_site_nature`); the build-time **gate** (manifest/deps/trace/attestation); **grades/levels**;
**observability/provenance**; **runtime re-attestation** groundwork (A1).

**New** (to build): (1) the **broker as a separate process** with thin per-language JSON-RPC/stdio stubs
(capability-negotiated, schema-generated); (2) **confinement** of dispatched artifacts (rung 3: namespace +
seccomp; then rung 4: WASI components); (3) the **conductor** that makes `casl run` project-aware and
dispatches to polyglot artifacts (generalizing the Python-only interpreter); (4) **risk-proportional approval
UX** engineered against automation bias; (5) the **grade report** rendered as the human-verification surface.

**Phased roadmap (each its own CEP + verification):**

- **P1 — Broker + one-language stub + rung-3 confinement.** Stand up the JSON-RPC broker; route the existing
  oracle/tool boundary through it; confine a Python artifact (namespace+seccomp) so its only egress is the
  broker. Negative tests: a direct model/network call from the artifact *fails*.
- **P2 — Conductor dispatch + runtime re-attestation.** `casl run project --entry` dispatches to bound
  artifacts; re-attest at the moment of effect; the secretariat/PDF example runs end to end with the
  negative-test matrix (tamper/unattested/unapproved/unbound ⇒ refuse). (This is the reframed `execution.md`.)
- **P3 — Second + third language stubs** (C/JS) from the shared schema; prove one policy across languages.
- **P4 — WASI-component substrate (rung 4)** as the hardening target for complete-mediation-by-construction.
- **P5 — Approval UX + grade-report cockpit** (over `observe`), engineered for calibrated trust.

R3 (more mechanized proof) and team/compliance scale (multi-signer, CI/CD, full OS-sandbox beyond P1/P4) come
*after* one real instance runs end to end.

---

## 9. References (load-bearing, consolidated)

**Choreography / orchestration / supervision.** Montesi, *Choreographic Programming* (PhD, 2013);
Honda, Yoshida, Carbone, *Multiparty Asynchronous Session Types* (POPL 2008 / JACM 63(1):9, 2016);
Giallorenzo, Montesi, Peressotti, *Choral* (TOPLAS 46(1), 2024); Temporal *Workflow Definition* docs
(deterministic workflow / activity split; LLM calls as activities); AWS *Step Functions* developer guide
(declarative state machine; `.waitForTaskToken` human-in-loop; exactly-once for non-idempotent actions);
Ericsson, *OTP Supervisor Behaviour*; Armstrong, *Making Reliable Distributed Systems…* (PhD, 2003);
Cemri et al., *Why Do Multi-Agent LLM Systems Fail?* (MAST, NeurIPS 2025).

**Capability security / confinement / enforcement.** Saltzer & Schroeder, *The Protection of Information in
Computer Systems* (Proc. IEEE 63(9), 1975); Anderson, *Computer Security Technology Planning Study* (ESD-TR-
73-51, 1972, reference monitor); Miller, *Robust Composition* (PhD, 2006, object capabilities / POLA);
Lampson, *A Note on the Confinement Problem* (CACM 16(10), 1973); Klein et al., *seL4* (SOSP 2009);
Haas et al., *Bringing the Web up to Speed with WebAssembly* (PLDI 2017); WASI 0.2 Component Model
(Bytecode Alliance, 2024) / WASI 0.3 (2026); Schneider, *Enforceable Security Policies* (TISSEC 3(1), 2000);
Ligatti, Bauer, Walker, *Run-Time Enforcement of Nonsafety Policies* (TISSEC 12(3), 2009);
Bloem et al., *Shield Synthesis* (TACAS 2015).

**Polyglot interop / broker.** Microsoft, *Language Server Protocol* + *Debug Adapter Protocol* specs
(JSON-RPC, capability negotiation); *Model Context Protocol* (JSON-RPC over stdio subprocess); Wahbe et al.,
*Efficient Software-Based Fault Isolation* (SOSP 1993); Chromium *Multi-process Architecture* / *Sandbox*
(broker/target); Burns & Oppenheimer, *Design Patterns for Container-based Distributed Systems* (HotCloud
2016, ambassador); *JSON-RPC 2.0* spec; OWASP *Authorization / Input Validation* cheat sheets.

**Human verifiability / runtime assurance / auditability.** Sha, *Using Simplicity to Control Complexity*
(IEEE Software, 2001, Simplex); Hobbs et al., *Runtime Assurance for Safety-Critical Systems* (IEEE CSM,
2023); Bauer, Leucker, Schallhart, *Runtime Verification for LTL and TLTL* (TOSEM 20(4), 2011, three-valued);
Regulation (EU) 2024/1689 (AI Act), Art. 14 (human oversight; names automation bias); Santoni de Sio & van
den Hoven, *Meaningful Human Control* (Frontiers Robotics AI, 2018); Parasuraman & Manzey, *Complacency and
Bias in Human Use of Automation* (Human Factors 52(3), 2010); Lee & See, *Trust in Automation* (Human Factors
46(1), 2004); W3C *PROV-DM/PROV-O* (2013); Schneier & Kelsey, *Secure Audit Logs* (1999); Lamport, *Who
Builds a House Without Drawing Blueprints?* (CACM 58(4), 2015); Necula, *Proof-Carrying Code* (POPL 1997).
