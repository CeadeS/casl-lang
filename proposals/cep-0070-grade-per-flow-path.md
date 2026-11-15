---
cep: 70
title: Grade per data-flow path — finer grades without laundering
status: Draft
type: Informational
created: 2026-06-24
version: 0.1
requires: [57, 68]
realized-by: [obligation_gate, grade_flow]
---

# CEP-0070 — Grade per data-flow path

Refines how the artifact-trust **effective grade** (LH-Q-019, CEP-0068) is *reported*, without weakening
the sound headline. Full analysis: `docs/analyses/grade-per-flow-path.md`.

## Summary

`effective_grade` is the global **weakest link** across all artifacts — sound and un-launderable, but
coarse (one G3 unit flattens the whole project, even outputs that never depend on it). The naive per-path
fix reintroduces laundering when dependency edges are author-declared (the R-H1 lesson). The resolution:

- **Now (model A):** report a grade **per requirement** (`obligation_gate.grade_by_requirement`,
  weakest floor within each requirement's artifacts) alongside the unchanged global headline. The
  requirement grouping is structured, so there is no laundering surface.
- **Now (model B, conservative):** with the typed seam (LH-F-012 full) in place,
  `grade_flow.flow_grades` computes a grade **per site** from the parsed-protocol edges — a site upstream
  of a weak artifact keeps its strong grade. Sound + un-launderable (edges come from the protocol, not
  free text). `casl flow` reports it; kernel block `grade_flow`.
- **Model C (re-base) — candidates + APPLIED via forwarding (A2):** `grade_flow.rebase_candidates` detects
  via SMT entailment where a `verified` boundary's *proved* contract entails a downstream contract. When the
  downstream value is also **forwarded** from that boundary (surface `field = Src.field`, the data-lineage
  A2), the re-base is **APPLIED** — `grade_flow.applied_rebases` raises the site to **G2** (capped:
  statically-checked structural lineage under CASL's spec-conformance assumption; G0 needs an F\*
  forwarding-fidelity proof, A1). Entailment *without* forwarding stays a candidate (no lineage), never
  applied. Framed by robust declassification (Myers–Sabelfeld–Zdancewic 2006), refinement-type entailment
  (Liquid types, SMT VC), and where-provenance (Cheney et al.). See `docs/analyses/data-lineage.md`,
  `grade-rebase.md`.

## Invariant (for the deferred models)

The project headline remains the global weakest link; per-path grades are an additional finer view that
can never *raise* the reported number on their own. A downstream grade exceeds an upstream floor only via
a checked containment boundary (a monitored contract / approval gate), inheriting the boundary's
assurance — never G0 for free.

## Status

Informational decision record. Model A is realised now by `obligation_gate.grade_by_requirement` + the
gate report breakdown; B/C are tracked open items (see CEP-0057 open questions).
