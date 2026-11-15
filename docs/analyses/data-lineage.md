# Data lineage — turning a re-base *candidate* into a sound *grant*

**Date:** 2026-06-24 · **Reference:** `docs/analyses/grade-rebase.md` (Model-C, the candidate/grant gap),
`src/casl/grade_flow.py`, `src/casl/observability.py` (runtime capture), `src/casl/core.py` (`Comm.fields`),
`src/casl/seam.py`. **Status:** design decision (pre-CEP). **No code until the approach is chosen.**

## The exact gap

Model-C surfaces a re-base CANDIDATE when a verified boundary B's proved contract entails a downstream
site S's contract, but cannot APPLY it: in MPST each message payload is a **fresh binding**, so "B proves
`[n≥0]`" and "S requires `[n≥0]`" are about *different* values unless we know **S's value is B's value,
carried unchanged**. That fact is **lineage** — and a sound grant needs it.

## What lineage is, in the literature

- **Where-provenance** (Cheney, Chiticariu & Tan, *Provenance in Databases: Why, How, and Where*, FnT
  Databases 2009): exactly "this output value came from *that* source." Our lineage is where-provenance of
  a payload field.
- **Provenance as dependency analysis** (Cheney, Ahmed & Acar, DBPL 2007): provenance is the *same*
  dependency/lattice machinery as information flow — so lineage rides the dependency graph the grade
  flow-graph already walks, refined to payload-field granularity.
- **IFC for multiparty sessions** (Capecchi, Castellani & Dezani-Ciancaglini, *Session Types for Access and
  Information Flow Control*, CONCUR 2010; *Information Flow Safety in Multiparty Sessions*, 2016): attach
  **security levels to messages** and track them through the session; a **monitored semantics** blocks
  leaks and permits **controlled declassification**. This is our grades-on-sites + robust re-base, with a
  precedent for the monitored (runtime) flavor.

## Three approaches (the decision)

**A — static forwarding in the surface/IR.** A message field may *reference* an earlier field:
`S -> R : Move(slot = Proposal.slot)`. Lineage becomes explicit + statically checkable (the reference
resolves to a real earlier field of matching sort), enabling a **sound static** per-site grade re-base —
exactly what Model-C wanted. *Cost:* it changes `core.py`'s `Comm` (a field is no longer just `name:sort`
but may be a reference) — i.e. it **touches the verified core IR** and the F\* bridge/projection. Against
our standing discipline (the proven hull stays small + untouched; the artifact-trust layer sits above it).
Principled, strongest, most invasive.

**B — attested lineage (manifest/governance layer).** An artifact *declares* a forwarding
(`forwards = {"Move.slot": "Proposal.slot"}`) and a **human signs** that it holds. No core change. But the
declaration is author-asserted with nothing in the `.casl` to check it against → by R-H1 it cannot be
trusted as a proof; it is an **attestation**. So it yields a **G3** re-base (a human vouches the lineage),
never a G0 grant. Cheap, honest, weak — the same liability-anchor pattern as the rest of the layer.

**C — dynamic provenance / taint at runtime.** Tag each value at run time with its origin site; the runner
threads the tag; the `OracleObservation` records "this value's provenance = site B (verified)." Then **for
an observed run**, the re-base is justified — the value *did* come from B. No core change (runtime +
observability, both ring-1/2); it extends the LH-G-005 layer we already built. *Soundness:* per-run
(dynamic), not a static guarantee — but CASL already treats the LLM as a **runtime-monitored** oracle, so
runtime lineage is philosophically consistent (Castellani et al.'s monitored semantics is the precedent).
Enables a re-base in the **observed trace** (`casl observe`/`run`), not in the static `casl flow` grade.

## What each enables, and the honest trade

| | static flow re-base (`casl flow`) | runtime re-base (`casl run`/`observe`) | core IR change | soundness |
|---|---|---|---|---|
| **A** forwarding | **yes (G0)** | — | **yes** (invasive) | static, strongest |
| **B** attested | yes (**G3** only) | — | no | human-attested |
| **C** dynamic provenance | — | **yes (per run)** | no | per-run, monitored |

The three are **complementary**, not exclusive: B is the cheap honest stopgap; C extends observability and
fits the runtime-oracle philosophy; A is the long-horizon static guarantee (with an F\* soundness angle).

## Recommendation

Pursue **C (dynamic provenance) next**: it is sound (per-run), needs **no core change** (it lives in
`run.py` + `observability.py`, the layer we just built), directly extends LH-G-005, and matches CASL's
"monitor the oracle at runtime" stance — so the re-base becomes *real* in the observed trace (the value
provably came from the verified boundary). Keep **B** as a one-commit honest fallback for the static view
(attested→G3). Treat **A** as a future, deliberately-scoped core extension (its own design + F\* proof),
since it is the only one that touches the proven hull and must clear the highest bar.

This is the genuine fork — which kind of lineage/re-base to build — and it is the user's call.

## Deeper comparison (rev. 2 — supersedes the recommendation above)

Three findings from a closer look reshape the choice.

### Finding 1 — the re-base grade is *capped by the lineage enforcer*, not by the boundary

A re-base raises a downstream grade to the boundary's grade **only if the lineage that connects them is at
least as trustworthy**. Formally:

> `rebased_grade(S) ≤ min( boundary_grade(B), lineage_assurance(B→S) )`

Lineage is **not free G0**. If a G0 proof sits behind a lineage we only know by a human's word, the honest
re-base is G3 (the human link is the weakest hop). This single inequality orders everything below.

### Finding 2 — approach A *splits*, and the cheap half avoids the core

- **A1 — forwarding proved.** The value-identity `S.slot = B.slot` is part of the semantics and **proved in
  F\***. Lineage assurance G0 ⇒ re-base **G0**. Touches the verified core IR + the proof — the highest bar.
- **A2 — forwarding interpreter-enforced.** A surface field *reference* (`Move(slot = Proposal.slot)`) that
  the **runner honors** (it binds `Move.slot := Proposal.slot`). The F\* core proves communication safety as
  before and never inspects field *values*, so the reference is a ring-1/2 annotation, **not a proof-core
  change**. Lineage assurance = the runner's = **G2** ⇒ re-base **G2**, statically, for *all* runs.

A2 is the part I conflated into "A is invasive." It is not: it is a static, all-runs G2 re-base with the
proven hull **untouched** — competitive with C, and *stronger in coverage* (all runs vs per-run).

### Finding 3 — dynamic taint (C) is inherently incomplete

Classic dynamic taint analysis (Schwartz–Avgerinos–Brumley 2010; DTA++, Kang–McCamant et al. NDSS 2011)
**ignores implicit / control-flow flows** (the *undertainting* problem) and is **bounded by exercised
paths**. For CASL this is *milder* than in general programs — our contracts are data-level and control is
the protocol's explicit `choice` structure — but it is real: C's per-run claim can miss a value whose
influence flowed through a branch condition, and says nothing about unexercised runs.

### The comparison, with limitations

| approach | re-base grade | coverage | proof-core touched | lineage enforcer | key limitation |
|---|---|---|---|---|---|
| **A1** forwarding, proved | **G0** | static, all runs | **yes** (IR + F\*) | F\* proof | invasive, highest bar; identity-forwarding only |
| **A2** forwarding, interpreter | **G2** | static, all runs | no (annotation) | the runner (`run.py`) | needs surface refs; grade ≤ runner assurance; identity only |
| **B** attested | **G3** | static, all runs | no | a human signature | rubber-stamp risk (D3); weakest grade; decays on edit |
| **C** dynamic provenance | **G2** | **per run only** | no | runner + tags | undertainting (implicit flows); coverage-bound; not static |

Cross-cutting limit for **all four**: they establish **identity** lineage ("carried unchanged"). A value
that is *transformed* (`S.x = f(B.y)`) is **how-provenance** (Cheney et al.) — sound re-base then needs the
transform to *preserve* the property, a strictly harder frontier none of A/B/C addresses. And throughout,
the flow grade stays **advisory** (it never loosens `casl gate`), so the blast radius of any of these is a
mis-stated *report*, not an unsafe admission — which lets us prefer the cheaper, sound G2 options.

### Revised recommendation

**A2 next** (interpreter-enforced static forwarding, G2). It delivers the *static* re-base Model-C set out
to get, for *all* runs, with the **proven hull untouched**; it adds genuine choreography expressiveness
(data forwarding, which `.casl` cannot currently express); and its "limitation" (only explicit, identity
forwarding) is exactly what keeps it sound — no undertainting. **C** is a complementary later enrichment of
the runtime/observability view (per-run provenance in `casl observe`). **B** is the one-commit honest
stopgap (attested → G3). **A1** (G0) remains the long-horizon, gated on an F\* forwarding-fidelity proof.
Caveat to confirm before A2: that a value-reference annotation on `core.Comm` fields does **not** perturb
the F\* differential bridge (it should not — the bridge is over roles/labels/sorts, not field values).

## Implementation (A2 v1 — 2026-06-24, feat/data-lineage)

Built as a vertical slice, **proof-hull untouched** (the bridge being field-blind was confirmed):

- **Surface:** a message field may forward — `Label(field = Src.field)` or `field: Sort = Src.field`
  (stored on `core.Field.source`; lexer needed no change — `=`/`.` are existing op tokens).
- **Grade:** `grade_flow.applied_rebases` RAISES a site to **G2** when a forwarded field carries a value
  from a `verified` boundary whose proved contract SMT-entails the site's contract;
  `flow_grades(apply_rebase=True)` reflects it and `casl flow` shows it (`✓ P:Relay → ≥G2`). Entailment
  *without* forwarding stays a **candidate** (no lineage).
- **Cap = G2, not G0:** the lineage is a statically-checked *structural* forwarding resting on CASL's
  standing spec-conformance assumption; G0 would need an F\* forwarding-fidelity proof (A1). Advisory
  throughout — the obligation gate is untouched.
- **Limits (open):** identity-forwarding only (a *transform* `S.x = f(B.y)` is how-provenance — future);
  1-hop source in v1 (transitive forwarding is a small extension); and *interpreter-enforced* honoring of
  the forward (which would harden the G2 basis from "assumed conformance" to "observed/enforced") is a
  further increment.
