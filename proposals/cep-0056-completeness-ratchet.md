---
cep: 56
title: The completeness ratchet — drive the human residual down, never the safety verdict up
status: Accepted
type: Informational
created: 2026-06-23
version: 0.2
realized-by: [completeness_ratchet, audit "[5e]"]
authors: [Martin]
requires: [3, 4, 55]
---

# CEP-0056 — The completeness ratchet

## Summary

CASL's verdict model is asymmetric: **soundness is proven and fixed** (a well-formed protocol's
projection is safe — never delegated), while **completeness is maximised in practice and the residual
is delegated to a human/oracle behind the monitored boundary** (CEP-0055). This CEP proposes to make
that residual a *first-class, monotonically non-increasing quantity* — a **ratchet** — with an explicit
long-term goal of driving it toward (but never to) zero, while leaving soundness strictly untouched.

The crucial framing decision: **the optimisation target is the disclosed human/oracle residual, NOT
"completeness."** Targeting completeness directly would invite Goodhart pressure in the one direction
that endangers soundness (accept more); targeting the *residual* keeps the pressure on mechanisation,
where it is safe and productive.

## Motivation

Today the residual oracle (`completeness.py`, `casl check --attest`, CEP-0055) is a *static escape
hatch*: it exists, it is sound (lifts rejects only), it is disclosed in the trust budget (CEP-0003) —
but nothing says it should *shrink over time*, and nothing measures whether it does. That leaves two
gaps:

1. **No direction.** "Maximise completeness" is stated as a one-time property of the chosen merge, not
   as an ongoing engineering objective. Each new mechanisation (e.g. the CAV-2023 automata operator as
   a certificate kind, or proving more under-unfolding lemmas like W19-A (c′)) ought to *retire* part
   of the human residual — and that retirement should be recorded and never silently reversed.
2. **No accountability.** We cannot today answer "how much are we relying on humans for completeness,
   and is it going down?" The trust budget lists *that* there is a reliance; it does not trend it.

A ratchet closes both: it gives completeness a *direction* (monotone) and an *auditable metric*
(residual coverage), turning human attestation from a permanent crutch into measured, shrinking **debt**
— which matches the Zwiebelmodell (each layer mechanises more, the human covers less) and the
"agents veto, never vouch" stance.

## Specification (normative, once Accepted)

Let **A** be a fixed reference acceptance set — the natural denominator is *the set of MST-implementable
(automata-complete, Li–Stutz–Wies–Zufferey CAV 2023) global types* over CASL's fragment. Partition any
accepted protocol's provenance into:

- **M (mechanised):** accepted by the sound automatic checker (syntactic merge) or by a re-checkable
  **certificate** the trusted oracle re-validates (mode ≤ G2, *no new trust*).
- **H (human residual):** accepted only via a human Tier-3 **attestation** (mode G3, disclosed).

The ratchet is three rules:

1. **R1 — Soundness is out of scope.** This CEP places NO target, metric, or pressure on soundness.
   The hard invariant of CEP-0055 (the sound core always keeps the safety verdict; the oracle only
   lifts *rejects*) is unconditional and unaffected. No completeness goal may ever be cited to weaken a
   `wellformed` conjunct or a MUST gate.
2. **R2 — Monotone on the completeness side only.** A release MUST NOT *enlarge* the human residual H
   relative to the previous release on the shared corpus: any protocol that was mechanised (M) must
   stay mechanised. New mechanisation moves protocols H → M; nothing moves M → H. (Soundness fixes may
   move protocols *out of A* by tightening `wellformed` — that is allowed and is not an H-regression.)
3. **R3 — Residual is the target, and it is bounded below.** The optimised quantity is `|H|` (the human
   residual), reported in/alongside the trust budget with its trend. It is acknowledged that `|H|`
   **cannot reach zero**: the requirement-faithfulness gap (does the protocol mean what the human
   intended?) is inherently undecidable (W16/W17; Lahiri; IronSpec). The goal is *monotone decrease of
   the mechanisable part*, not elimination of the human.

### Why the target is H and not completeness (Goodhart)

"When a measure becomes a target, it ceases to be a good measure" (Strathern 1997; Goodhart 1975). If
"% complete" were the target, the cheapest way to move it is to accept more — directly toward
over-acceptance, the one failure soundness forbids. Targeting `|H|` (residual to retire *by
mechanisation*) can only be improved by proving/checking more, never by relaxing the gate: a protocol
leaves H only by entering M (a machine-checked path), and the sound core still independently keeps the
safety verdict. So the ratchet is **Goodhart-safe by construction**.

## Realization (status)

**Accepted + lightweight gate implemented (v0.27.x).** The policy (R1/R2/R3) is adopted, and an
honest, sound enforcement of R2 is live:
- `src/casl/completeness_ratchet.py` snapshots the **disclosed trust-budget residual** per shipped
  example (e.g. `oracle:attested`, `async:bounded`) and fails if it GROWS vs a committed baseline
  (`completeness_ratchet.baseline.json`); shrinking is always allowed; `--update` re-baselines.
- The living **audit `[5e]`** runs the ratchet as a hard gate (so CI's `python` job enforces it).
- Baseline today: 14 disclosed reliances over 12 protocols; `tests/test_completeness_ratchet.py`
  checks the gate actually bites (growth flagged) and that shrinking never violates.

This ratchets the *disclosed trust budget* — concrete and sound today — NOT a completeness
percentage. The QUANTITATIVE `|H|/|A|` coverage metric remains future work because the denominator
needs a projection-INDEPENDENT safety oracle (the semantic oracle `semantics_sync` itself projects,
so it cannot judge rejected/non-projectable protocols) — i.e. the CAV-2023 automata operator. See
Open questions.

## Realization (future work)

- A **completeness-coverage report**: over a curated corpus (extend the existing differential/bridge
  corpus), classify each accepted protocol as M or H and emit `|H|`, `|M|`, and the delta vs. the last
  tagged release. Wire into `levels.trust_budget` reporting and the audit.
- A **ratchet gate** (CI): fail if any corpus protocol regressed M → H since the baseline (R2).
- New mechanisations land as **M-expanding** changes: e.g. (a) integrate the proven W19-A (c′)
  under-unfolding result into the core (`fstar/W19ProjSubst.fst`, already 0 admits) so recursive
  protocols leave H; (b) add the CAV-2023 automata operator as a re-checkable certificate kind
  (CEP-0055 names this) so the automata-complete frontier becomes M, not H.
- Honest reporting: the report always states the irreducible-H caveat (R3 / W16/W17).

## Open questions / tensions

- **Denominator well-definedness.** `A` (MST-implementable types) must be pinned precisely or `|H|/|A|`
  is vacuous; the CAV-2023 operator is the intended yardstick but is PSPACE — the *report* may need to
  sample or restrict to a bounded fragment. (Tracks W19.)
- **Corpus representativeness.** A ratchet over a corpus only ratchets *that corpus*; protocols outside
  it can still regress. Mitigate with corpus growth as a separate, monotone obligation.
- **Interaction with soundness tightening.** Tightening `wellformed` (e.g. adding `gdistinct`, or the
  earlier `contractive`/`no_self`) removes protocols from `A` — must be accounted as a soundness change,
  not an H-regression, to avoid a perverse incentive against safety fixes (R2 carve-out).
- Relates to: CEP-0003 (assurance grades / trust budget), CEP-0004 (integrity case), CEP-0055 (the
  sound-core + completeness-oracle split this builds on), W16/W17 (inherent undecidability),
  W19 (projection completeness).

## References / sources (to resolve this CEP later)

MPST completeness frontier (the denominator and the mechanisation targets):
- Scalas & Yoshida, *Less is More: Multiparty Session Types Revisited*, POPL 2019 — soundness-first,
  semantic safety; why mergeability ⇒ safety is not free. https://doi.org/10.1145/3290343
- Li, Stutz, Wies, Zufferey, *Complete Multiparty Session Type Projection with Automata*, CAV 2023 —
  sound+complete+decidable (PSPACE) projection; the natural completeness yardstick `A`.
  https://doi.org/10.1007/978-3-031-37709-9_18 (https://cs.nyu.edu/~wies/publ/cav23_mst.pdf)
- Tirore, Bengtson & Carbone, *A Sound and Complete Projection for Global Types*, ITP 2023 —
  computable projection sound+complete vs. a coinductive relation. https://doi.org/10.4230/LIPIcs.ITP.2023.28
- Honda, Yoshida, Carbone, *Multiparty Asynchronous Session Types*, JACM 2016 — the full
  label-unioning merge CASL already uses. https://doi.org/10.1145/2827695

Metric design / the Goodhart hazard (why target the residual, not completeness):
- Goodhart, *Problems of Monetary Management: the UK Experience*, 1975 — original formulation.
- Strathern, *'Improving Ratings': Audit in the British University System*, European Review 5 (1997),
  305–321 — the canonical "when a measure becomes a target…" phrasing.
- Goodhart's law overview: https://en.wikipedia.org/wiki/Goodhart%27s_law

Assurance-case / faithfulness framing (residual is irreducible, must be disclosed):
- ISO/IEC/IEEE 15026-3 — assurance levels / integrity levels (anchors CEP-0003).
- Lahiri et al. on specification correctness; IronSpec (spec-bug finding in verified systems) — the
  requirement-faithfulness gap that keeps `|H| > 0` (anchors W16/W17, SP-4).

Internal:
- `proposals/cep-0055-projection-soundness-completeness.md`, `proposals/cep-0003-assurance-levels.md`,
  `proposals/cep-0004-integrity-assurance-case.md`
- `docs/analyses/w19-projection-completeness.md` (§8c — W19-A (c′) proven, 0 admits)
- `src/casl/completeness.py`, `src/casl/levels.py` (trust budget), `fstar/W19ProjSubst.fst`
