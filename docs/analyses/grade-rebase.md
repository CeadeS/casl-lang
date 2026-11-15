# Model-C — boundary re-base as robust, entailment-gated endorsement

**Date:** 2026-06-24 · **Reference:** `docs/analyses/grade-per-flow-path.md` (D1-A/B), `src/casl/grade_flow.py`
(per-site grade + boundary detection), `src/casl/seam.py` (artifact↔site), `src/casl/spike_smt_contract.py`
(contract SMT), `src/casl/levels.py` (G0–G3). **Status:** design decision (pre-CEP).

## The problem

The grade flow-graph (D1-B) only ever DEGRADES: a site's grade is the weakest bound artifact at-or-upstream.
Model-C is the missing piece — soundly **raising** a downstream grade *past* an upstream floor when a
**containment boundary** re-establishes the property. The danger is laundering: an unsound re-base would
let a G3 oracle "become" G0 for free. So Model-C must state precisely *when a raise is sound*.

## The right frame: this is endorsement on an integrity lattice

Grades `G0 < G1 < G2 < G3` are an **integrity lattice** (G0 = highest integrity / proved; G3 = lowest /
attested). A weak artifact is a low-integrity source; a boundary that lifts downstream integrity is an
**endorsement** (the integrity-dual of declassification). The information-flow literature gives the exact
soundness condition:

- **Robust declassification / endorsement** (Myers, Sabelfeld, Zdancewic, *Enforcing Robust
  Declassification and Qualified Robustness*, JCS 2006; Askarov & Myers, *A Semantic Framework for
  Declassification and Endorsement*, ESOP 2010): an endorsement is sound only if it **cannot be influenced
  by the adversary** — here, by the untrusted oracle/LLM data. The decision *to* endorse, and the property
  it endorses, must rest on **trusted** inputs only.
- **Declassification dimensions** (Sabelfeld & Sands, *Declassification: Dimensions and Principles*, JCS
  2009): *what* is released/endorsed, *where*, *by whom*. Our boundary fixes all three: the *where* is the
  site, the *by whom* is the boundary's trusted mechanism, the *what* is the boundary's contract.

This is **the same R-H1 / anti-laundering rule** we already hold ("never derive trust from author free-text"),
now with a name and a soundness theorem from the literature: **the re-base must be robust** — independent of
the weak upstream's content.

## Why CASL's boundaries are robust by construction

The three boundary kinds endorse via a **trusted, upstream-independent** mechanism, so each is robust:

| boundary | mechanism | endorses to | robust because |
|---|---|---|---|
| `verified` site | a proof discharges its postcondition | **G0** | the proof holds unconditionally — independent of any input |
| `oracle`+contract site | a runtime monitor enforces the contract, blame on violation | **G2** (tested) | the monitor checks the value regardless of what the oracle produced |
| approval gate | a human consents to the disclosed effect | **G3** (attested) | the human decides; the oracle cannot forge consent |

So robustness is satisfied by the *kind* of boundary. What is **not** automatic is whether the boundary
actually re-establishes *the property the downstream relies on*.

## The entailment gate (the SMT part)

A boundary B re-bases a downstream consumer C only **for the property C depends on**. Soundness requires
B's enforced contract to **entail** C's precondition — a **verification condition** dischargeable by SMT
(Rondon–Kawaguchi–Jhala, *Liquid Types*, PLDI 2008; Vazou et al., *Refinement Reflection*, POPL 2018).
CASL already has this: `spike_smt_contract` decides the tiny contract DSL (`le`/`ge`/`len`, literals). So:

> **Re-base rule (sound).** On the dataflow, C's grade may be raised to boundary B's grade iff
> (1) B is a robust boundary (kind ∈ {verified, oracle+contract, approval}),
> (2) B **dominates** every dataflow path from a weak upstream W to C (B is on all of them), and
> (3) B's contract **SMT-entails** C's precondition (the property C relies on).
> Otherwise C keeps the weakest-upstream floor (D1-B, conservative).

Decidability ceiling: the entailment must stay in the decidable contract fragment (no quantifiers) — which
matches CASL's DSL. Anything outside ⇒ no re-base (conservative), never an unsound raise.

## Dataflow precision (the honest over-approximation)

The dataflow edges come from the **parsed protocol** (checkable, not free-text — the anti-laundering source).
v1 uses the **causal** approximation: C depends on everything before it in protocol order. This
**over-approximates** dependency (it may think C depends on W when it doesn't) → it only ever **withholds**
a re-base, never grants an unsound one. Sound, conservative. Payload-precise lineage (which field flows
where) is a later refinement that grants *more* (sound) re-bases.

## Implementable subset — options for now

- **C1 — verified-only re-base, entailment-gated.** Only a `verified` boundary (→ G0) re-bases, and only
  when its contract SMT-entails the downstream precondition. The clearest sound case (proof). Smallest,
  safest. Covers the secretariat's no-double-booking shape (a verified check upstream of an effect).
- **C2 — verified + monitored (G2).** Add the `oracle`+contract boundary (→ G2). Doubles the coverage;
  needs the monitor-assurance argument in the doc but no new SMT.
- **C3 — all three (+ approval → G3).** Full boundary set. Most coverage; approval→G3 rarely *raises*
  (G3 is the floor anyway), so low marginal value now.

Across all: the **global weakest-link headline stays authoritative** (Model-C only refines the per-site
flow view, never the headline), and an un-entailed / non-dominated boundary never raises (conservative).

## Recommendation

**C1 now** (verified-only, SMT-entailment-gated, causal dataflow) — it is the one case that is *provably*
sound with machinery we already have, it exercises the whole pipeline (dominator + entailment + re-base),
and it lands the robustness+entailment discipline. C2/C3 and payload-precise lineage are follow-ups, each
its own sound increment. Mechanized robustness (an F\* proof of the re-base rule) stays the long-horizon item.

## Implementation finding (2026-06-24) — the grant needs lineage, so v1 surfaces *candidates*

Building C1 revealed that SMT entailment **alone is not sound to APPLY** a re-base. In MPST every message
payload is a **fresh binding**: a contract `[conflicts ≤ 0]` *proved* at a verified site B and a
same-named `[conflicts ≤ 0]` *required* at a downstream site S are predicates over **different values**.
Name-based entailment (`φ_B ⇒ φ_S`) therefore does **not** establish that S's value *is* the proved one —
a downstream oracle could produce a fresh `conflicts` B never saw. Granting the raise on entailment alone
would be exactly the laundering we forbid (and would violate robustness: the "endorsement" would depend on
untrusted downstream data).

A sound grant needs **verified data lineage** — a checkable fact that S's value is B's output carried
unchanged, not merely that the predicates match by name. The choreography does not yet express payload
forwarding, so lineage is the genuine blocker (the research step).

**So v1 (`grade_flow.rebase_candidates`) surfaces re-base CANDIDATES, never applies them:** for each
downstream site whose (non-G0) flow grade has a contract entailed by a dominating `verified` boundary's
proved contract, it emits `B ⇒ S (would re-base to G0 if lineage holds)`. The applied flow grade stays the
conservative D1-B weakest-link — **zero** unsound claims. Applying a candidate awaits either (a) a
payload-flow lineage analysis over the choreography (sound; the next research step), or (b) a
human-attested lineage declaration (a G3 attestation, not a G0 grant).
