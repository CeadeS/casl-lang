# Grade per data-flow path (D1)

**Date:** 2026-06-24 · **Reference:** `src/casl/obligation_gate.py` (`effective_grade`, LH-Q-019),
`src/casl/project.py` (`Artifact.floor`, `by_requirement`), CEP-0057, CEP-0068 (LH-Q-019), `docs/cockpit.md`.
**Status:** decision record (realised by CEP-0070).

## Problem

The project's effective grade is the **weakest link** across *all* artifacts (`effective_grade`,
min-composition, LH-Q-019). That is sound and un-launderable, but **coarse**: a single unprovable unit
(`external`/`generated`/`oracle`, floor G3) flattens the *whole* project to G3 — even outputs that never
depend on it. The `examples/projects/secretariat` project shows it: one proved **G0** predicate
(`conflict_check`), yet the project reports ≥G3 because the reply drafter and the classifier are G3.

## The laundering trap

The obvious fix — "grade each output by only the artifacts on its dependency path" — **reintroduces the
exact escalation that weakest-link prevents**, *if* the dependency edges are author-declared free text.
This is the R-H1 / W14 lesson: never derive trust from a marker. A project could simply declare "the G3
oracle is not consumed by the G0 path" and launder a high grade. So per-path grading is sound only if:

1. the flow graph comes from a **checkable source**, not an author "contained"/"independent" marker; and
2. a low-grade unit's floor **propagates to everything downstream of it**, *unless* a real, **checked
   containment boundary** sits between.

## Three models

- **A — per-requirement.** Weakest floor *within each requirement's* artifacts (`by_requirement()` —
  already structured + validated). No graph, no new laundering surface. Finer than one global scalar;
  the honest first step. *Limit:* a requirement that legitimately mixes a contained G3 call with a G0
  core still reads G3 (no intra-requirement flow modelled).
- **B — flow-graph.** Edges derived from the choreography's message flow (`.casl`) and/or a verified
  import scan; a grade is computed for each exposed output as the weakest floor on its dependency cone.
  Sound **iff** edges are *derived*, not declared. Needs the typed `.casl`↔artifact **seam binding**
  (LH-F-012 full), which is still deferred.
- **C — containment boundary.** A monitored-contract / approval point is a grade **firewall**: downstream
  re-bases to the *boundary's* checked assurance (the contract's grade), never G0 for free. Matches
  CASL's oracle-boundary philosophy (a contract-checked oracle output is trusted at the contract's
  assurance, not the oracle's). Strongest model; the most to build; also needs B's graph.

## Anti-laundering invariant (binds B and C)

1. Flow edges MUST be derived from a checkable artifact (the choreography graph or a verified import
   scan) — never from an author marker.
2. A unit's floor propagates to **every** downstream node on its cone.
3. The **only** way to raise a downstream grade above an upstream floor is to interpose a **checked**
   boundary (a monitored contract or an approval gate); downstream then inherits the **boundary's**
   assurance (≤ the contract's grade), not G0.
4. The project **headline stays the global weakest link** (the conservative, un-launderable number).
   Per-path grades are an *additional, finer* view — never a replacement that could only ever raise the
   reported number.

## Decision (2026-06-24)

- **Now (model A):** `obligation_gate` reports a grade **per requirement** alongside the global
  weakest-link headline. The grouping is structured (the manifest's `requirement` field), so there is no
  laundering surface. The headline `effective_grade` (LH-Q-019) is **unchanged**.
- **Deferred (models B/C):** the flow-graph + containment-boundary grading, governed by the
  anti-laundering invariant above, lands **after** the typed `.casl`↔artifact seam (LH-F-012 full) — B/C
  structurally depend on it. Tracked as an open item (CEP-0057 open questions, CEP-0070).

## Why not build B/C now

B and C both require a *derived* flow graph, whose only sound source today would be the `.casl`
choreography's message flow bound to artifacts — but that binding (the typed seam) is exactly the piece
still listed as deferred. Building B/C on a declared graph would be a laundering hole; building it on a
not-yet-existing seam would be premature. Model A is the part that is both safe and available now.
