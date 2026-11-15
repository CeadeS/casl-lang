---
cep: 77
title: The conductor — `casl run` dispatches a verified project through the broker
status: Draft
type: Informational
created: 2026-06-26
version: 0.1
requires: [76]
realized-by: []
---

# CEP-0077 — The conductor (project-aware execution through the broker)

Books the **Layer 3 (Execution)** design realized by `src/casl/conductor.py` and `docs/conductor.md`:
`casl run --project` drives a **verified** choreography end-to-end, dispatching every model/tool call
through the broker (the reference monitor). Builds on the opt-in capability service of [CEP-0076].

## Summary

- **The verified `.casl` IS the state machine.** Determinism comes from the F\* proof, not from a runtime
  replay-guard (the AWS-Step-Functions-style declarative model, not the Temporal/Durable-Functions
  event-sourced-replay model — see `docs/conductor.md` §2). The interpreter (`casl.run.run_protocol`) is the
  deterministic conductor; it gates the hull (`check_protocol`) **before** executing.
- **Coordination/effect split.** The conductor decides; every effect is dispatched through the broker — the
  one reference monitor (complete mediation). Two thin seams: `BrokerBackend` (oracle sites →
  `client.oracle`, capability-gated + H4 cost) and `BrokerDispatch` (effect sites → `client.effect`,
  deny-by-default).
- **Two monitors, two policies — not redundant.** The **broker** is the *access/capability* monitor (may
  this artifact call this provider/tool? what did it cost?); the **conductor** is the *choreography/contract*
  monitor (does the measured cost satisfy this site's contract → which branch?) and holds verdict + approval
  authority.
- **Minimal, additive footprint.** `run_protocol` gains one optional `dispatch=` parameter; with
  `dispatch=None` the proven single-file interpreter path is byte-for-byte unchanged. Project awareness
  (manifest + the typed-seam bindings of [CEP-0074]) lives in `conductor.py`, outside the verified core.

## Realization

- `src/casl/conductor.py` — `Conductor(project_dir)`; `BrokerBackend`; `BrokerDispatch`; `ConductorResult`.
- `src/casl/run.py` — the additive `dispatch=` hook at effect-bearing steps.
- CLI — `casl run --project DIR [--protocol N] [--provider P]` (vs. the single-file `casl run FILE.casl`).
- Dogfood — `examples/projects/triage/` (an oracle site + an approval-gated effect site, both bound via the
  typed seam), conducted end-to-end through the broker. `tests/test_conductor.py` pins it (10 tests:
  bindings resolve; oracle + effect cross the broker; default-deny at the gate blocks the effect; tool /
  provider denial; overspend flagged at the boundary; the hull is gated before running; the in-process path
  is unchanged).

## Status

Informational decision record. Realized for the in-process / subprocess broker with the offline mock
provider — fully verified (`pytest`, audit ✓). Deferred, tracked increments: **confinement** (rung-3/4 — the
"only egress is the broker" guarantee, opt-in grade-upgrade, `docs/engineering-plan.md` P2) so the dispatched
artifact's body itself becomes a confined activity; the **live provider HTTP send** (needs a key); and
**polyglot artifact-as-subprocess activities** (Variant C in `docs/conductor.md` §4, the P2/P3 rung).
