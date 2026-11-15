# The Conductor — `casl run` dispatches the project through the broker

*Design note for Layer 3 (Execution). Companion to `docs/architecture.md` §"Layer 3 — Execution" and
`docs/engineering-plan.md`. Status: design + first slice (this branch).*

## 1. The gap

Two halves exist but do not talk to each other:

- **`src/casl/run.py` — the interpreter.** `run_protocol(g, backend, …)` walks the *verified-shape* global
  type and is, already, the **deterministic conductor**: projection/types/contracts are fixed and proved,
  only the payload is non-deterministic. But its effect plane is in-process: oracle sites call
  `backend.generate(question, bound)` on a Python object, and effect sites are checked by the in-process
  `_tool_allowed`. No real artifact is dispatched; nothing crosses the broker.
- **`src/casl/broker.py` + the Rust broker — the reference monitor.** A separate process that gates
  `oracle`/`effect` (capability-negotiated, deny-by-default, `-32011`), holds the connector, and measures
  cost (H4). But nothing drives a choreography *through* it.

The **conductor** closes the gap: make `casl run` *project-aware* (resolve each site to its bound artifact
via the typed seam) and dispatch every model/tool call **through the one broker**, while the interpreter
retains verdict + approval authority over the choreography.

## 2. What the literature says (and where we diverge)

A focused read of durable/deterministic workflow engines (Temporal, Azure Durable Functions, AWS Step
Functions) and the reference-monitor line (Anderson; Schneider; Jaeger; NIST SP 800-204B PEP/PDP) gives a
clear verdict:

- **Coordination/effect split** (all four engines): the orchestrator decides; *activities* perform all
  non-deterministic, side-effecting work, **outside** the trusted core. → Our conductor decides; every
  effect is an activity reaching the world **only** through the broker.
- **The spec IS the interpreted state machine** (AWS Step Functions / Amazon States Language — *no user-code
  replay*). Temporal/Durable Functions instead **replay** event-sourced orchestrator code, and their long
  determinism rule-lists (no clocks, no RNG, no I/O…) exist *only because of replay*, enforced at runtime by
  a guard their own docs admit "won't catch all violations." Our verified `.casl` **already is** that static
  state machine, so we would pay replay's costs (fragile determinism contract, versioning hazards) to
  re-derive a guarantee we get **by construction**.
- **A single mediation chokepoint requires a central orchestrator** (orchestration vs. choreography): only a
  central conductor admits one place to attach policy/approval. Decentralized choreography structurally
  precludes it.

**So we diverge from Temporal/Step-Functions in exactly two places:**

1. **Determinism by ahead-of-time F\* proof, not runtime replay-discipline.** The choreography is the
   theorem; the runtime needs no replay, no command-vs-event matching, no `NonDeterministicException` guard.
2. **The mediated effect is a capability-gated, *graded*, vetoable call** — not connectivity-RPC. None of the
   four engines attach a verifiable trust grade to the mediated effect. Our broker does ("agents veto, never
   vouch").

## 3. The monitor separation (the key insight)

Routing the oracle through the broker is **not** double-monitoring, because the two layers enforce
*different* policies:

| Layer | Question it answers | Mechanism |
|------|--------------------|-----------|
| **Broker** = access / capability monitor | *May this artifact call this provider/tool? What did it cost?* | `llm:<provider>` + tool capability (deny-by-default, `-32011`); the connector; the **H4 out-of-band cost measurement** |
| **Conductor** = choreography / contract monitor | *Does the measured cost satisfy this site's contract → which branch?* | `_oracle_step` + `synth_refusal_monitor` over the broker's **measured** cost → verdict → `_pick_branch`; the approval gate |

The broker says *"you may call `claude`, and it cost 18 tokens."* The conductor says *"this site requires
`cost ≤ budget`; 18 ≤ 100 → ok → terminating branch."* Complete mediation lives at the broker; **verdict and
approval authority live at the conductor**. Together they are the reference-monitor picture
(`docs/architecture.md` §3): complete mediation + a small verifiable core + a single approval chokepoint.

## 4. Variants considered (rated: security + understandability + feasibility — *not* speed)

| Variant | Mediation | Understandability | Feasible now (no keys/Linux) | Verdict |
|--------|-----------|-------------------|------------------------------|---------|
| **A — broker-as-backend only** (oracle through broker; effects stay in-process `_tool_allowed`) | model access only | highest (no interpreter change) | yes | partial — tools not mediated |
| **B — broker for BOTH oracle + effect** via one additive `dispatch=` hook | model **and** tool access through the one monitor (complete mediation at the conductor seam) | high (a single, default-off hook; the proved interpreter path is byte-identical when `dispatch=None`) | yes (mock provider + in-process broker) | **Adopt now** |
| **C — full polyglot subprocess "activities"** (each artifact becomes a confined, broker-speaking process) | strongest (confinement-ready, language-agnostic) | lower (a whole new subsystem) | no (needs artifacts-as-processes = the P2 confinement rung) | **Defer to P2** |

**Decision: B.** It maximizes the two weighted axes — *security* (both model and tool access cross the one
reference monitor → complete mediation at the conductor↔broker seam) and *understandability* (a single
additive hook; the F\*-shaped interpreter is untouched on the default path) — and is fully verifiable today
with the mock provider and the in-process broker, no API key and no Linux sandbox. It consciously defers
**C** — the polyglot, confined, subprocess "activity" dispatch — to the P2 confinement rung, where
artifacts-as-processes belongs ("only egress is the broker", the bypass-fails negative test). B is the rung
that makes CASL a *runtime*; C is the rung that makes that runtime *containment-enforced*.

## 5. The slice (this branch)

- **`run.py`:** one additive parameter `dispatch=None`. At an effect-bearing `Comm` (`uses_capability`), if
  `dispatch` is set, the capability check + record route through `dispatch.effect(node)` (the broker); else
  the in-process `_tool_allowed` (unchanged). `dispatch=None` ⇒ the proved path is byte-for-byte the same.
- **`conductor.py`:** the project-aware conductor — `Conductor(project_dir)` loads the manifest +
  choreographies + seam bindings; `run(protocol, …)` gates the hull (`check_protocol`), stands up the broker
  (granted tools = the choreography's declared agent caps), builds `BrokerBackend` (oracle → broker) +
  `BrokerDispatch` (effect → broker), runs `run_protocol`, and returns the `RunResult` + a per-site
  binding/grade summary.
- **CLI:** `casl run --project DIR [--protocol NAME] [--provider P] [--live]` — conduct a whole project, vs.
  the existing `casl run FILE.casl` (single-file, in-process).
- **Dogfood:** `examples/projects/secretariat/` gains an oracle `Classify` site + `implements` bindings, so a
  real artifact realizes each site and the run crosses the broker end-to-end.

Non-goals for this slice (tracked): C's confined subprocess activities (P2); live provider HTTP (needs a key);
multi-language stubs (P3).
