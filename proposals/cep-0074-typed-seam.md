---
cep: 74
title: Typed .casl↔artifact seam (LH-F-012 full)
status: Draft
type: Informational
created: 2026-06-24
version: 0.1
requires: [57, 58]
realized-by: [typed_seam]
---

# CEP-0074 — Typed `.casl`↔artifact seam

Promotes LH-F-012 to *full*: a manifest binding from an artifact to a choreography **site**, with a
boundary check. Full analysis: `docs/analyses/typed-seam.md`. Realized by `src/casl/seam.py` + the kernel
block `typed_seam`; enforced in the obligation gate; surfaced by `casl seam`.

## Summary

An artifact declares the site it realizes: `implements = "<protocol>:<Label>"` in `casl.toml`. The seam
checker resolves the site in `casl/<protocol>.casl`, then checks the **binding + the boundary** (NOT the
body, W17):

- the **site exists**;
- the artifact **kind matches the site's nature** (`oracle`→oracle, `verified`→verified,
  effect (`irreversible`/`uses`)→generated|external) — structured, never name-inferred (the R-H1 rule);
- the site **contract is the artifact's obligation** (proven for `verified`, monitored for `oracle`).

The binding lives in the **manifest**, so the verified core IR and the parser stay **untouched** and a
`.casl` file remains a pure, reusable protocol (decision B in the analysis; A would have coupled the
proven core to governance artifact names).

## What it unblocks

- **Observability requirement-link (LH-G-005):** an oracle call → its site → the bound artifact → its
  `requirement`. `casl run` now fills `OracleObservation.requirement`.
- **Grade flow-graph (D1-B/C):** the choreography's message edges are the *derived, checkable*
  dependency graph (no author free-text → no laundering); each site's bound artifact gives its grade; an
  approval / monitored-contract site is a containment boundary. (Propagation itself is the next step.)

## Enforcement + honesty

`casl gate` denies an `implements` that names an unknown protocol/site or a kind that cannot realize the
site's nature. Unbound effect/oracle sites are *reported* (a gap), not a hard deny — the seam is opt-in:
only artifacts that declare `implements` are bound-checked, so pure projects are unaffected. The seam
makes the artifact↔site↔requirement triangle explicit and typed at the boundary; it does not verify the
body — that stays contained + attested, exactly as P10 states.
