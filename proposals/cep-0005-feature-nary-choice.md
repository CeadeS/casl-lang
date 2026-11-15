---
cep: 5
title: Feature — n-ary choice (profile extended, assurance G0)
status: Final
type: Informational
created: 2026-06-18
version: 1.0
authors: [Martin]
requires: [3]
---

# CEP-0005 — Feature: n-ary choice

**Capability profile:** `extended` · **Assurance grade:** `G0` (F\*-proven, 0 admits) ·
**Feature key:** `nary_choice` (see `levels.FEATURES`).

## What it is

A choice with more than two branches: `p->q : {l1:G1, … , ln:Gn}` (Variant A). The `core`
profile admits only binary choice; n-ary choice is the first `extended` feature.

## Assurance (why G0)

The full n-ary calculus — projection, the MPST merge, substitution, the global/configuration
step relations, and the metatheorems (`fidelity_complete`/`sound`, `deadlock_free`) — is
machine-checked in `fstar/CASL.fst` with **0 admits** (admits=0 CI gate, CEP-0004 C6). Hence the
strongest grade, `G0`.

## Conservativity over `core` (CEP-0003 C9)

Proven in F\*: `conserv` shows `project g r == project_bin g r` on the binary fragment
(`is_bin_frag`), with corollary `conserv_wf` (identical well-formedness verdict). Enabling this
feature therefore never changes a binary-only (`core`) protocol's verdict — the gradual
guarantee holds.

## Enforcement

`levels.features_used` flags a protocol as using `nary_choice` when any `Choice` carries >2
branches; `casl check --profile core` then rejects it deny-by-default (the protocol is still
*well-formed*, but exceeds the requested capability ceiling). The TCB differential bridge
(`tcb_corpus.py`) exercises n-ary cases and the F\*-extracted checker agrees with the Python
checker on all of them.

## Cross-references

CEP-0003 (assurance levels), CEP-0004 (integrity assurance case, C9), and the projection
requirement LH-F-006.
