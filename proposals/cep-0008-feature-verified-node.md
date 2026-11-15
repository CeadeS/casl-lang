---
cep: 8
title: Feature — verified (deterministic) pipeline node (profile advisory, assurance G3)
status: Final
type: Informational
created: 2026-06-18
version: 1.0
authors: [Martin]
requires: [3, 25]
---

# CEP-0008 — Feature: verified (deterministic) pipeline node

**Capability profile:** `advisory` · **Assurance grade:** `G3` (human-attested) ·
**Feature key:** `verified` (see `levels.FEATURES`).

## What it is

A pipeline node carrying an external deterministic program asserted to meet its contract. It is
the exclusive twin of `oracle`: a node is either an opaque oracle or an attested verified
program, never both.

## Assurance (why G3)

CASL does not re-derive the external program's correctness; the claim that it meets its contract
is discharged by a **human Tier-3 attestation** (`ide.py`), not by an internal proof. Trust thus
rests on a disclosed, specific, reviewable human sign-off (CEP-0004 C8, "no self-attestation") —
grade `G3`. A future option is to admit machine-checked evidence (a checkable certificate) to
raise a node to a stronger grade.

## Conservativity over inner rings

`verified` is an outer-ring (`advisory`) construct; protocols not using it are unaffected, and
the layering guard (CEP-0003 step 5) keeps inner-ring modules free of it at load time.

## Enforcement

`levels.features_used` flags `verified` from `Comm.verified`; `casl check --profile core` and
`--profile extended` reject it deny-by-default; `pipeline_safe` (LH-F-011, CEP-0025) enforces the
`oracle ⊕ verified` exclusivity, and the IDE requires a Tier-3 attestation before a `verified`
node is admitted.

## Cross-references

CEP-0003 (assurance levels), CEP-0004 (C8, human attestation is the irreducible root),
CEP-0025 (requirement LH-F-011), CEP-0007 (`oracle`, the exclusive twin).
