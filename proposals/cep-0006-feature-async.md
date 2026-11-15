---
cep: 6
title: Feature — asynchronous (buffered) sessions (profile extended, assurance G1)
status: Final
type: Informational
created: 2026-06-18
version: 1.0
authors: [Martin]
requires: [3, 24]
---

# CEP-0006 — Feature: asynchronous (buffered) sessions

**Capability profile:** `extended` · **Assurance grade:** `G1` (bounded / model-checked) ·
**Feature key:** `async` (see `levels.FEATURES`).

## What it is

Buffered, order-relaxed message passing as an *encapsulated* refinement of a synchronous
session (an `async` marker on a protocol). The `core` profile is synchronous only.

## Assurance (why G1, not G0)

Safety is established by a **bounded** buffered semantics + gate (`semantics_async.py`,
`async_safe`) and the kernel self-tests `async_bounded` / `async_enhancement` (the audit's
async checks). This is machine-checked *up to a bound*, not an unbounded F\* proof — hence `G1`
(one notch below the proven `G0`). The honest fuel/bound caveat is tracked as tension `W18`.

## Conservativity over `core`

The `async` capability is opt-in via an explicit marker; a protocol without the marker is
classified synchronous and decided exactly as before. Enabling the feature cannot change a
`core` (synchronous) protocol's verdict.

## Enforcement

`levels.features_used` flags `async` from the protocol's async marker; `casl check --profile
core` rejects it deny-by-default, and an assurance floor of `G0` also rejects it (G1 < G0).
End-to-end: safe async examples are accepted, the reorder trap is rejected (deny-by-default).

## Cross-references

CEP-0003 (assurance levels), CEP-0024 (requirement LH-F-010, the async enhancement), tension
`W18` (fuel/bound, safe-direction only).
