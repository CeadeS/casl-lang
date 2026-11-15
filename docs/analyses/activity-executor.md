# The activity executor — running a real program / agent as a monitored producer

*Design analysis. Coarse structural seam for Layer 3 (Execution). Formalize → literature → variants →
synthesis → properties → residuals. Companion to docs/conductor.md and docs/architecture.md §"Layer 3".*

## 1. The problem, framed

Today the conductor (`casl run --project`) drives a **verified** choreography through the broker, but the
oracle payload always comes from a `MockBackend` — the conductor never runs the *project's own program* (or
a real agent loop). The gap is not architecture: the conductor already asks one seam,
`backend.generate(question, budget) → OracleResult` (`conductor.py:33`), and the broker holds *a* backend
(`broker.py:48`) and runs it through the monitored oracle boundary (contract + H4 measured cost + blame).

So "run a program" and "run an LLM agent loop" are **the same call with a different object plugged into the
existing monitored seam**. What is missing is one such object: an **activity** — an out-of-process,
untrusted *producer* bound to a site, whose output is monitored, never trusted.

## 2. Literature

- **Durable-execution orchestrator/activity split** (Temporal, AWS Step Functions). The *workflow* is a
  deterministic orchestration; *activities* are the "safe zone" for non-deterministic, failure-prone,
  side-effecting work; an activity's result is **recorded and checked**, not trusted, and (in Temporal)
  activities are *not replayed*. CASL's twist: determinism comes from the **F\* proof of the hull**, not from
  a runtime event-history replay — so the verified `.casl` already *is* the deterministic orchestrator
  (docs/conductor.md §2, "Step-Functions, not Temporal-replay"). We need only the activity.
- **Prompt-Flow-Integrity / least-privilege LLM agents** (PFI; LPLM). Split into a *trusted* party and an
  *untrusted* agent; restrict the untrusted agent to the smallest capability set by policy; monitor its
  flows. Maps directly onto CASL: the orchestrator + broker are trusted; the activity is the untrusted
  agent, and it gets **no ambient authority** — tools/effects still cross the broker, approval stays
  external.
- **Runtime enforcement over agent behavior** (AgentSpec): rules with conditions + enforcement actions
  govern the agent's output. CASL's per-site **contract monitor** is exactly this — the activity proposes a
  payload + a *claimed* cost; the monitor (with the H4 out-of-band measure) decides the verdict and assigns
  blame. The activity cannot certify itself.
- **Circuit breakers / timeouts** (multi-agent reliability): isolate a misbehaving agent before it
  contaminates the run. Here: an activity that hangs or crashes is bounded to a **typed refusal**, cleanly
  classified (not silently retried, not mistaken for success).

## 3. Formalization

**Orchestrator.** The verified global type `g` (proved well-formed, projectable) interpreted by
`run_protocol` — deterministic by construction. It owns sequencing, the choice/branch policy, the approval
gate, forwarding, the loop bound. *Unchanged.*

**Activity.** A function `A : (question, budget) → OracleResult` realizing one bound site, executed
**out of process**, treated as an **untrusted proposer**. Its result flows into the existing monitored
oracle step (`run._oracle_step`), so the trusted boundary — not the activity — decides `ok | violation |
refusal` and blames the producer.

An activity must satisfy five properties (each testable):

1. **Fail-closed.** Any failure — non-zero exit, crash, timeout, empty/garbled output, missing fields,
   unparseable JSON — yields a *typed refusal* (`OracleResult(refused=True)`), never a fabricated "ok".
   The hull stays safe because a refusal drives the monitor to a non-`ok` verdict (retry/loop/abort).
2. **Veto-never-vouch.** The activity's self-reported `cost` is only a *claim*. The monitor checks the
   out-of-band `measured_cost` (H4). An activity cannot pass its own contract by lying.
3. **No authority widening.** The activity is a *producer*, not a grantor. It receives `(question, budget)`
   and returns a payload. It does **not** grant tools, approve effects, or hold a model endpoint — those
   stay with the broker/human. (PFI: the untrusted agent's privilege is restricted by policy.)
4. **Determinism preserved.** The orchestrator stays deterministic (proved); the activity is the single
   non-deterministic leaf, and its output is *recorded + monitored* (LH-G-005 observation), mirroring the
   Temporal "record, don't replay" rule — except our determinism is a proof, not a replay guard.
5. **Bounded.** An activity is killed at a deadline; the timeout maps to a refusal (property 1), so a hung
   program cannot stall the run.

## 4. Variants

| | V1 — activity *as backend* (callee) | V2 — artifact *as client* (driver) | V3 — long-lived co-process |
|---|---|---|---|
| Who drives | the proven orchestrator calls the activity per oracle site | the artifact runs its own loop, calling the broker | a persistent artifact process holds a session |
| Determinism | preserved (orchestrator unchanged) | at risk — an autonomous loop is the thing CASL exists to *tame* | preserved, but lifecycle state to manage |
| Fits existing seam | **yes** — drop-in `backend.generate`, like `ProviderBackend` | no — inverts control; new wire | partial — needs session protocol |
| Monitoring | reuses `oracle_step` (contract + H4 + blame) verbatim | must re-establish monitoring around an autonomous agent | reuses, plus session bookkeeping |
| Confinement-ready | yes — wrap the subprocess in rung-3 later, no redesign | yes, but the trust story is harder | yes |
| Simplicity | **highest** | lowest | medium |

**Rating** (security + understandability weighted over speed, per the standing methodology): V1 ≫ V3 > V2.
V2's "autonomous agent driving" is precisely the unconstrained loop CASL is built to constrain; realizing
the agent *as a monitored activity behind the verified orchestrator* is the safe inversion. The "agent loop"
is then expressed as the **choreography's verified recursion** (the monitor verdict drives retry —
`run._pick_branch`/`TVar`, already proven), with each iteration's payload produced by the activity. V3 is a
pure performance optimization (avoid per-call process spawn) and is deferred.

## 5. Synthesis

Implement V1: **an `Activity` is a `backend` drop-in**, and `SubprocessActivity` runs the artifact body out
of process over a tiny JSON-over-stdio contract:

```
conductor → broker(backend = SubprocessActivity(cmd)) → oracle_step(monitor) → verdict
                         │  stdin:  {"question": ..., "budget": ...}
                         ▼  stdout: {"answer": "...", "cost": <int|null>}   (one JSON line)
                    artifact program (any language: reads stdin, writes stdout)
```

- The activity lives **in the broker** (broker-only backend), so "the model/agent lives only in the broker;
  the conductor merely asks" still holds. The conductor *selects* a `SubprocessActivity` backend when the
  protocol's oracle site is bound (via the typed seam) to an **executable** artifact; otherwise it keeps the
  mock/provider backend. The proven single-file path (`dispatch=None`, mock backend) is untouched.
- The artifact is **polyglot**: any program that reads a JSON request on stdin and writes a JSON line on
  stdout. No key, cross-platform. It runs at **attested** grade today (kind `oracle`/`generated` floors at
  G3); rung-3 confinement later wraps the *same* subprocess to upgrade it to enforced grade — no redesign.
- **Per-site routing** (a different program per oracle site) needs `site` threaded into the backend seam;
  it is a documented refinement, not built now (coarse → fine). V3 (long-lived co-process) likewise.

This is the uniform realization of the user's observation: *the conductor can run a program or an LLM agent
loop* — both are a monitored `backend` behind the broker's oracle boundary, and the "loop" is the verified
choreography's recursion, not an unconstrained agent.

## 6. What is enforced, and where

| Property | Enforced by | Test |
|---|---|---|
| fail-closed | `SubprocessActivity.generate` normalizes every failure to refusal | crash / timeout / non-JSON / missing-field → `refused` |
| veto-never-vouch | existing `oracle_step` checks H4 `measured_cost`, not the claim | an activity that *claims* under budget but measures over → `violation`, blame producer |
| no authority widening | activity has only stdin/stdout; tools/effects still cross the broker; approval external | effect step still routed through `BrokerDispatch`; activity cannot grant |
| determinism preserved | orchestrator (`run_protocol`) unchanged; activity is the only non-deterministic leaf | the existing proven-path tests stay green |
| bounded | subprocess deadline → kill → refusal | a sleeping activity returns refusal within the deadline |

## 7. Residuals (honest)

- An activity at **attested** grade is *trusted by human attestation*, not confined — until rung-3 wraps the
  subprocess, "the program only does what it claims" rests on the human signature, not enforcement. This is
  the existing opt-in posture (CEP-0078); the activity executor is *confinement-ready* but does not itself
  confine.
- The JSON-over-stdio contract is single-turn (one request → one answer). Multi-turn / streaming activities
  and per-site routing are the next increment.
- An activity that performs a real **side effect** (not just produces a payload) is out of scope here — that
  needs the broker's real effect dispatch + the human approval gate (P2), which deliberately stays behind
  the approval boundary. The coarse executor runs *producer / compute / agent* activities only.
