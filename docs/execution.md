# R1 — Execution: making the cage hold on one real effect

**Date:** 2026-06-25 · **Status:** roadmap (pre-implementation). **Owner direction:** R1 (the running system).
**Companion:** `docs/ide.md` (the requirement-driven front end), `docs/analyses/forwarding-fidelity-a1.md`
(the O4 / calculus↔runtime gap this slice first tests in earnest), `examples/projects/secretariat/`.

## Why this, why now

Every recent round has deepened the **governance/trust** model (provenance, attestation, grade-flow,
re-base, lifecycle, supply-chain, observability). It is now remarkably deep — and **nothing has ever
executed a real effect**. `casl run` is a *structural simulator*: it walks the global type, calls the LLM
oracle, monitors contracts, and *traces* `Move`/`Notify` — but no side effect is performed, even with
`--live` (only the oracle answer is real). The central thesis — *prove the hull, monitor the oracle, agents
veto never vouch* — has therefore been tested against a model, never against the world.

The honest risk is **governance perfectionism**: an exquisite trust model that never runs. More trust depth
(e.g. A1's G2→G0) now buys *less* real-world assurance than the first running effect would. So the next
round runs the real thing — **small, once, all the way through** — and either validates the model or shows
what is missing.

**Thesis of this slice:** the value of executing a real effect is exactly proportional to its danger, so the
success criterion is **not "an email was sent"** but **"an email could be sent *only* through the gate, and
a tampered / unattested / contract-violating / unapproved path was provably *refused*."** The negative tests
are the result; the positive send is the easy part.

## Scope discipline (the three guardrails from the strategy review)

1. **R2 stays at zero.** The slice anchors on the existing **secretariat** choreography, whose only contract
   is `Proposal(slot, conflicts) [conflicts <= 0]` — already inside the decidable `le/ge/len` DSL. No new
   value types (List/Record/refinements) are introduced. If a future app needs them, that is a *separate*
   R2 decision, not smuggled in here.
2. **The first handler is human-vetted + attested, not LLM-generated.** Running a *generated* handler that
   performs an irreversible effect means executing LLM-written code behind only a *logical* lint (the broker
   is a capability check, not an execution sandbox). For slice-1 the handler is hand-written, committed,
   line-traced and human-signed (`kind = generated`, owned). The generated-handler path + real isolation is
   the **next** increment (M2), not this one.
3. **R4 only to "watchable".** Enough cockpit to see each gated call happen (`casl observe` already captures
   prompt→response; extend it to effect dispatch). No LSP, no UI build-out in this slice.

R3 (more mechanized proof) and R5 (multi-signer, team keys, CI/CD, OS-level sandboxing beyond the minimum)
are **explicit non-goals here** — valuable, but only after one instance actually runs.

## What exists vs. what is missing

| Capability | State today | Needed for the slice |
|---|---|---|
| Static check / projection / safety | ✓ (F\* core + checker) | — |
| Typed seam artifact↔site (`implements`) | ✓ `seam.py` (binding + kind-match) | **wire the secretariat manifest** (no `implements` yet) |
| Obligation gate (manifest+deps+trace+attestation) | ✓ `obligation_gate.py` (static, pre-run) | reuse at **dispatch time** (re-attest) |
| Attestation (content-hash + human sig) | ✓ `attestation.py` | re-check at dispatch (deny on hash drift) |
| Capability broker (runtime) | ✓ `run.py` `_tool_allowed` | already interposes; keep |
| Approval gate (runtime, disclosure-bound) | ✓ `run.py` `_decide_approval` | already there; keep |
| Observability (prompt→response capture) | ✓ `observability.py` | **extend to effect calls** |
| **Project-aware run** | ✗ `run_protocol` takes a bare gtype | **M0** |
| **Effect dispatch to a handler** | ✗ effect sites are trace lines | **M1** |
| **Runtime re-attestation at dispatch** | ✗ | **M1** |
| **A real effect (SMTP send)** | ✗ | **M1** (to a local sink) |
| **Handler isolation** | ✗ (broker is a lint) | minimal in M1 (vetted handler), real in M2 |

The seam already gives the missing link: `check_seam` returns `{artifact: (proto, label, nature)}` and
`_site_nature` classifies a `Comm` as `oracle | verified | effect | plain`. **Dispatch = at an `effect`
site, resolve the bound artifact and invoke it — through the gate.** Nothing in the verified core changes;
this is ring-1/2 runtime wiring.

## The Handler ABI (the seam from spec to real code)

A handler is a vetted Python module bound to an effect site via the manifest (`implements`). One entry point,
total and explicit:

```python
# artifacts/mail_send.py  (kind=generated, owned, line-traced, human-attested)
def handle(ctx: EffectContext) -> EffectResult:
    """Perform the effect named by Secretariat:Notify. May ONLY use capabilities in ctx.caps.
    Must be deterministic given ctx; no ambient I/O beyond the declared capability."""
```

- `EffectContext` carries: the site (`proto:label`), the message fields (values bound so far, incl.
  forwarded ones), the granted capability object (attenuated — only what the spec declared), and the
  transport config (the SMTP sink). It carries **no** secrets and **no** capability the spec did not grant.
- `EffectResult` is `{ok|refused|error, measured_cost, evidence}` — `evidence` (e.g. the SMTP server's
  250-response + message-id) is captured into the observation, so the effect is auditable after the fact.
- The handler is invoked **only** by the dispatcher, **only** after the gate passes (below). It never sees
  the approval decision or the attestation — it just does the one effect.

## The dispatch gate (deny-by-default, re-checked at the moment of effect)

At an `effect` site during a run, before any side effect:

1. **Bind** — resolve the artifact implementing `proto:label` via `seam.check_seam`. No binding ⇒ **refuse**
   (an effect site with no owned handler cannot fire).
2. **Re-attest** — recompute the handler's content hash and check it against `attestations/<name>.json`:
   signature present, hash matches (no drift since signing), grade acceptable for the site. Any failure ⇒
   **refuse** (this is the TOCTOU-safe core: hash-then-load the *same* bytes; never attest one file and run
   another).
3. **Broker** — the acting role must carry the capability at runtime (`_tool_allowed`); revoked/undeclared ⇒
   **refuse** (existing).
4. **Approve** — the effect is inside the approval gate's consent branch; without external consent bound to
   the disclosure, **deny-by-default** (existing).
5. **Invoke** — only now call `handle(ctx)`, with the attenuated capability and the local transport.
6. **Monitor + capture** — check `measured_cost`/result against the contract; record an `OracleObservation`-
   style effect record (prompt/effect → evidence + verdict) for the cockpit.

Re-attestation at step 2 is the runtime realization of the static grade — the first real test of the **O4 /
enforcer-cap** gap named in the A1 analysis: the running system must enforce the same grade the model
computed, or the guarantee is theatre.

## Milestones

**M0 — project-aware run.** `casl run` (and `run_protocol`) learn to take a *project* (manifest +
choreography + seam bindings), not just a bare `.casl`. Resolve the global type from the project, load the
manifest, compute seam bindings once. *No behavior change yet* — pure plumbing. Existing bare-file `casl
run` stays working (back-compat). Success: `casl run <projectdir>` walks the secretariat exactly as today,
plus a `--dispatch` flag (off by default) that will turn on M1.

**M1 — the gated real effect (the heart of the slice).** Implement the Handler ABI + the dispatch gate.
Add a hand-written, attested `mail_send` handler bound to `Secretariat:Notify`, sending via a **local SMTP
sink** (e.g. Python's `aiosmtpd`/`DebuggingServer` or a file "outbox"); real internet SMTP is opt-in behind
explicit config. Wire `implements` into the secretariat manifest. Success = the **negative-test matrix**
(below) all hold, and only the all-green path delivers to the sink. This is the milestone that validates or
falsifies the governance model.

**M2 — generated handler + minimal isolation.** Allow an *LLM-generated* handler (the `draft_reply` path)
to run, but only inside real confinement: a subprocess with a wall-clock timeout and no network except the
configured sink (the minimal honest version of R5's OS-sandboxing, pulled forward because a generated effect
*forces* it). Re-attestation + the generated-artifact grade (G3) gate it; the human still signs.

**M3 — thin intake.** A minimal trigger that starts a run from an incoming event (a single function /
one-shot CLI "process this message", not a server). Just enough to drive the loop from a real input. Full
event/HTTP/async server is out of scope.

**M4 — cockpit to "watchable".** Extend `casl observe` to render effect dispatches (site, re-attest verdict,
approval, capability, evidence) alongside oracle calls, so the maintainer watches each gated call live. No
UI framework — the existing report + a static HTML view at most.

## The negative-test matrix (M1 success criterion)

Each row must **refuse the real send**; only the last delivers. These are the actual deliverable.

| # | Tamper | Expected | Mechanism |
|---|---|---|---|
| 1 | Edit `mail_send.py` after attestation | refuse (hash drift) | re-attest step 2 |
| 2 | Remove/expire the attestation | refuse (no valid sig) | re-attest step 2 |
| 3 | `Proposal` with `conflicts = 1` (contract violated upstream) | never reach the gate | static check + monitor |
| 4 | Approval denied (Deny branch) | no send (Keep/Hold) | approval gate |
| 5 | Revoke / undeclare `mail` capability | refuse (broker) | `_tool_allowed` |
| 6 | No artifact bound to `Notify` | refuse (unbound effect) | seam step 1 |
| 7 | All green (attested, approved, capability carried, contract holds) | **deliver to the local sink** | full path |

A passing matrix is the proof that the cage holds on a real animal. A *failing* row is the more valuable
outcome — it shows exactly where the model leaks under execution.

## What the slice will likely expose (and that is the point)

- **Capability cage ≠ containment for arbitrary code.** A real handler runs real code; the broker only
  *checks a list*. M1 keeps this safe by vetting the handler; M2 must add real isolation. Expect this to be
  the first honest crack — the lint was never a sandbox.
- **TOCTOU at re-attestation.** Attesting one byte-string and executing another must be impossible; the
  dispatcher must hash-and-run the same bytes. The slice forces this to be gotten right.
- **Approval UX is load-bearing.** Default-deny without a TTY means an unattended run never sends — correct,
  but the slice will show how a human actually approves in practice.
- **The O4 gap becomes concrete.** Re-attestation is where the static grade either does or does not bind the
  running effect. This is the first real measurement of the calculus↔runtime distance.

## Requirements & process

Proposed new requirements (created via the CEP flow at implementation, not yet in `spec.REQS`):
`LH-F-014` *seam dispatch / gated effect execution* and `LH-Q-021` *runtime re-attestation at dispatch
(deny-by-default)*. M1 lands behind a CEP (decision record) like every feature; the obligation gate and the
attack-corpus discipline extend to a runtime negative-test suite (`tests/test_dispatch_*`). The verified
F\* core is **untouched** throughout — this is execution wiring above the proven hull.

## Sequencing

M0 → M1 is the spine and the whole point; do them first and stop to evaluate. M2–M4 are demand-driven by
what M1 reveals. R2 (value types), R3 (mechanization), R5 (team/compliance/OS-sandbox beyond the M2 minimum)
wait until one instance runs end-to-end and the negative-test matrix is green.
