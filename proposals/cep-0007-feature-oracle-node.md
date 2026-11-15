---
cep: 7
title: Feature — oracle (LLM) pipeline node (profile advisory, assurance G3)
status: Final
type: Informational
created: 2026-06-18
version: 1.0
authors: [Martin]
requires: [3, 25]
---

# CEP-0007 — Feature: oracle (LLM) pipeline node

**Capability profile:** `advisory` · **Assurance grade:** `G3` (attested / monitored) ·
**Feature key:** `oracle` (see `levels.FEATURES`).

## What it is

A pipeline node whose behavior is produced by an opaque oracle (an LLM box). Neither `core`
nor `extended` admit it; it is an `advisory` capability.

## Assurance (why G3)

An oracle's output cannot be proven correct; trust rests on a **monitored boundary**, not a
proof — the weakest grade, `G3`. The monitor is the reference-monitor of CEP-0004 (C5/C8): the
MCP boundary (`mcp.py`) reports `needs-human` and **never releases** on the oracle's word, and
`pipeline_safe` (LH-F-011, CEP-0025) requires every oracle node to be wrapped by a checkable
**contract** and forbids combining `oracle` with `verified` on the same node.

## Conservativity over inner rings

`oracle` is a strictly outer-ring construct; a protocol that does not use it is unaffected.
Because no inner-ring module imports the oracle module at load time (CEP-0003 step 5 layering
guard, audit `[5b]`), an oracle-free build is sound.

## Enforcement

`levels.features_used` flags `oracle` from `Comm.from_oracle`; `casl check --profile core`
(and `--profile extended`) reject it deny-by-default; `pipeline_safe` enforces the
contract-wrapping and exclusivity at check time.

## Cross-references

CEP-0003 (assurance levels), CEP-0004 (C5/C8, reference monitor + no self-attestation),
CEP-0025 (requirement LH-F-011, pipeline trichotomy), CEP-0008 (`verified`, the exclusive twin).
