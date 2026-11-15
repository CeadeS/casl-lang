---
cep: 80
title: The activity executor + the live transport — running a real program / agent / model as a monitored producer
status: Draft
type: Informational
created: 2026-06-26
version: 0.1
requires: [76, 77, 78]
realized-by: []
---

# CEP-0080 — The activity executor + the live transport

Books the two execution drivers realized by `src/casl/activity.py` and `providers.UrllibTransport`: the
coarse **activity executor** (run the project's own program / agent as a monitored producer) and the fine
**live transport** (a real HTTPS POST so the oracle can be a live local/hosted model). Together they take
the conductor ([CEP‑0077]) from *conducting a mock* to *conducting real programs and a real model* — with no
new architecture and no new trust. Full design + literature in `docs/analyses/activity-executor.md`.

## The one seam, two drivers

The conductor asks a single seam — `backend.generate(question, budget) → OracleResult` — and the broker
([CEP‑0076]) runs whatever `backend` it holds through the **monitored oracle boundary** (contract + the
out‑of‑band H4 cost measure + blame). "Run a program", "run an agent loop", and "call a live model" are
therefore the *same call with a different object plugged into the existing seam*. Neither driver adds a
verdict path; the trusted monitor still decides.

## A — the activity executor (coarse)

An **activity** is an untrusted, out‑of‑process *producer* bound to an oracle site — the durable‑execution
orchestrator/activity split (Temporal, AWS Step Functions), except CASL's determinism is the F\* proof of
the hull, not a replay guard, so the verified `.casl` *is* the orchestrator and only the activity was
missing. The agent's "loop" is the choreography's **verified recursion** (the monitor verdict drives retry),
not an unconstrained agent — the safe inversion of PFI's *trusted orchestrator + restricted untrusted agent*.

`SubprocessActivity` is a `backend` drop‑in that runs the artifact body out of process over a one‑line JSON
contract identical to the LLM oracle's (`{"question","budget"}` → `{"answer","cost"}`, parsed by the reused
`oracle.parse_oracle_output`). The conductor auto‑selects it when an oracle site is bound (typed seam) to an
**executable** artifact (kind `oracle` with a runnable `body`); otherwise it keeps the mock/provider backend
(the proven default path is untouched). Polyglot, no key, cross‑platform.

Five properties (each pinned by `tests/test_activity.py`):

1. **Fail‑closed** — crash / non‑zero exit / timeout / no output / unparseable / missing cost ⇒ a *typed
   refusal*, never a fabricated "ok"; the hull stays safe.
2. **Veto‑never‑vouch** — the activity emits no verdict; the trusted monitor computes it from the (claimed)
   cost. An overspending activity is blamed even if it self‑asserts `"verdict":"ok"`.
3. **No authority widening** — the activity has only stdin/stdout; tools/effects still cross the broker and
   approval stays external (PFI: restrict the untrusted agent).
4. **Determinism preserved** — the orchestrator is unchanged; the activity is the single non‑deterministic
   leaf, *recorded + monitored* (LH‑G‑005).
5. **Bounded** — a deadline kills a hung activity → refusal.

## B — the live transport (fine)

`providers.UrllibTransport` performs the real HTTPS POST (stdlib `urllib`, zero new deps — the same `urllib`
already in `oracle.OllamaBackend`) behind the existing, tested `build_request`/`parse_response`. **Fail to a
typed refusal:** a non‑2xx returns its body so the parser yields a refusal; a transport error (DNS / refused
/ timeout) is caught by `ProviderBackend.generate` → refusal. `live_backend_from_env` builds it from the
broker's environment; the **no‑key local path** is `openai`‑shape + `http://localhost:11434` (Ollama). The
`api_key` is injected by the broker from its env — **never embedded in code or the manifest, never sent by
the client/artifact**. Pinned end‑to‑end against a localhost stub by `tests/test_live_transport.py`.

## What this does and does not change

- **Grade.** A spawned activity runs at **attested** grade (kind `oracle`/`generated` floors at G3) — trusted
  by human signature, not yet confined. rung‑3 confinement ([CEP‑0078]) later wraps the *same* subprocess to
  upgrade it to enforced grade; the executor is confinement‑ready by construction, but does not itself confine.
- **Effects.** The coarse executor runs *producer / compute / agent* activities only. An activity that
  performs a real side effect needs the broker's real effect dispatch + the human approval gate (deliberately
  left behind the approval boundary).
- **Honest residuals.** Single‑turn JSON contract (multi‑turn / streaming + per‑site routing are the next
  increment). For an opaque subprocess there is no out‑of‑band cost meter, so the attested claim is what the
  monitor checks (a metered substrate — a live LLM's usage tokens — sets `measured_cost`). The live transport
  is "modulo TLS/endpoint trust"; egress from a *confined* caller is still cut (the transport is broker‑side).
