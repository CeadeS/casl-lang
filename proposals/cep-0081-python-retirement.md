---
cep: 81
title: Retiring Python — the strangler-fig roadmap (Rust authoritative, F* stays the proof)
status: Draft
type: Informational
created: 2026-06-26
version: 0.1
requires: [76, 77]
realized-by: []
---

# CEP-0081 — Retiring Python (the strangler-fig roadmap)

Books the program that retires CASL's Python reference component-by-component in favour of the Rust
implementation. Full analysis: `docs/analyses/python-retirement-roadmap.md`.

## What "retire" means

A component's Rust twin becomes the **authoritative implementation** and the Python one is **deleted** —
*after* a conformance differential proves they agree. It does **not** retire the **proof**: F\* stays the
spec/proof of record (only F\*→extraction, P7, unifies the running and proved artifacts), and it is **not** a
big-bang — Python is removed one component at a time, reversibly, behind the frozen contract.

## Retire-criteria (a component is eligible iff)

1. **Frozen contract** — a stable, versioned boundary (the JSON-RPC wire; the canonical AST/IR; a manifest schema).
2. **Conformance differential** — a single-sourced corpus `X` + oracle `O` with `∀x. Rust(x)=Python(x)=O(x)`;
   anchored to F\* where a proof exists, to the Python reference by **characterization** otherwise.
3. **No second unpinned impl** — exactly one authoritative impl after the cut; the other deleted or demoted to
   a regression guard.
4. **Reversible until cut** — Python stays runnable behind a flag until the Rust twin has soaked.

This is the established discipline (the broker via `tests/test_conformance.py`; well-formedness via the
412-protocol differential), extended to the rest.

## Order (bottom-up; rationale in the roadmap §5)

**parser → checker → project/trust → conductor → CLI.** Parser strategy = **hand-written recursive descent,
zero-dependency**, mirroring `surface.py` 1:1 (no new burden-ledger entry; trivially differential-pinnable).

## This increment

`casl-surface` (the parser) starts the program: the Python parse-differential **oracle**
(`src/casl/surface_corpus.py` — a single-sourced corpus of `.casl` text + canonical AST JSON) is verified
locally; the Rust `casl-surface` crate parses to the same canonical AST and is pinned by the differential in
CI. Retires `surface.py` on parity.

## Honest residuals

The proof is untouched (retire ≠ close the TCB gap); the non-core checks (stage 2) have **no** F\* proof —
they are characterization-pinned, and their grade reflects "tested, not proved"; the parser sits **outside**
the proved hull, so its differential is backed by **fuzzing** (random `.casl` ⇒ Python-AST == Rust-AST); and
this environment has no Rust toolchain, so ports are CI-verified (write-blind) — a local Rust+Linux dev loop
is the right investment before the heavier stages.
