---
cep: 9
title: Extracted F* checker as the authoritative core judgment (C1 / W11)
status: Accepted
type: Informational
created: 2026-06-18
version: 0.1
authors: [Martin]
requires: [4]
---

# CEP-0009 — Extracted F\* checker as the authoritative core judgment

**SP-2 / C1.** Closes — for the core MPST projection judgment — the W11/LH-C-004 gap: the *running*
checker was Python while the *proof* was F\*, with only an empirical differential bridge between them.

## What changes

`casl check --authoritative` (or `$CASL_AUTHORITATIVE`) takes the core well-formedness (MPST
projection) verdict from the **F\*-extracted, machine-verified `wellformed`** (`src/casl/authoritative.py`
→ `fstar/ocaml/wf_one.exe`), not from the Python checker. The Python projection is cross-checked and a
disagreement is a **hard error** (`TCB DIVERGENCE`), never a silent fallback. The differential bridge
(`tcb_bridge.py`, 412 + n-ary protocols) is thereby demoted from *the trust story* to a **regression guard**.

## Why this is the right shape (research-grounded)

A finite differential corpus shows the *presence* of divergence, not its absence (Dijkstra), and is blind
to bugs shared by both sides — so it is evidence, not proof. The principled upgrade is to make the *proven*
artifact authoritative (proof-carrying-code shape: a small trusted checker decides). See
`docs/analyses/verification-mode-and-tcb-unification.md` (C-comparison; refs CompCert, seL4, Cogent, PCC).

## Scope (honest)

Authority is claimed **only for protocols in the F\* core fragment**: `GMsg/GCh/GRec/GVar/GEnd` over roles
{C,A,J,D}, with no oracle/verified/crash annotations (`in_core_fragment`). Out-of-fragment protocols fall
back to the Python verdict with an explicit notice — the F\* core does not model those constructs, so its
verdict would not be applicable. Python's extra MSC-realizability layer likewise stays Python (a separate,
smaller trust item).

## Trusted base of the authoritative verdict

F\* typechecker + Z3 + F\* extraction (OCaml) + OCaml toolchain — **not** the Python checker. Honest
residual: F\* discharges via SMT and does **not** emit independently-checkable proof terms, so Z3 and the
extraction are trusted (it does not satisfy the de Bruijn criterion); the recursion-DEPTH half of merge
fuel-sufficiency (W18) and MSC realizability remain as tracked items. The default `casl check` stays
Python-only for portability (no toolchain needed); `--authoritative` is opt-in and CI-exercised.

## Cross-references

CEP-0004 (integrity assurance case; this discharges part of C5/W11), CEP-0003 (the `proved` mode),
`docs/analyses/verification-mode-and-tcb-unification.md` (SP-2).
