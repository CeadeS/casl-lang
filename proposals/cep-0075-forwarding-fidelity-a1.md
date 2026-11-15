---
cep: 75
title: Forwarding fidelity (A1) — a proof-backed G0 forwarding re-base
status: Draft
type: Informational
created: 2026-06-25
version: 0.1
requires: [70]
realized-by: [grade_flow]
---

# CEP-0075 — Forwarding fidelity (A1)

Refines the forwarding re-base of CEP-0070 (Model-C / A2) from the conservative **G2** structural cap to a
**proof-backed G0**. Full analysis + literature: `docs/analyses/forwarding-fidelity-a1.md`.

## Summary

A2 (CEP-0070) re-bases a site `S` whose payload field is forwarded from a `verified` boundary `B`
(`S.f = B.f`) to **G2**, sound only under CASL's spec-conformance assumption — nothing *proved* that the
forwarded value is delivered unchanged. A1 supplies that proof.

- **CERT-FID** (`fstar/Forwarding.fst`, F\* 0 admits, `CASL.fst` untouched — a standalone companion like
  `W19ProjSubst.fst`): a write-once payload-store model with forward edges, proving **fidelity** (a forwarded
  value is delivered unchanged) and **`rebase_sound`** (identity forwarding + contract entailment ⇒ the
  destination satisfies its contract *by proof*). The where-provenance "free transfer" (value-equality
  transports the predicate — Cheney, Chiticariu & Tan 2009) made machine-checked. The admits gate
  (`scripts/check_admits.sh`) scans it, so a weakening cannot pass silently.
- **Grade gate** (`grade_flow.cert_fid_verified` + `_rebase_grade`): when CERT-FID is present and hole-free,
  `applied_rebases` grants **G0**; absent/holed it falls back to the **G2** A2 cap (never over-claims). The
  three structural conditions (forward edge, `verified` source, SMT entailment) are unchanged and read only
  the parsed protocol — so the endorsement decision is adversary-independent (Askarov–Myers 2010).
- **Interpreter-enforced forwarding** (`run.py`): a forwarded field's source must be produced upstream; the
  runner honors the edge and aborts (`forward_violation`) on an unbound source — the runtime realization the
  enforcer-assurance cap requires.

## Soundness frame

Raising an integrity grade is an **endorsement**; it is sound iff the endorsed value is not adversary-derived
and the endorsement decision rests on high-integrity data only (Askarov–Myers ESOP 2010; Myers–Sabelfeld–
Zdancewic 2006), with the grade capped by the enforcer's assurance,
`rebased ≤ min(boundary, enforcer)`. CERT-FID discharges value-identity + property-transfer statically (so
the *calculus* grade is G0); the running interpreter realizes the forward, with the residual being the
**standing calculus↔runtime TCB item (H1/W11)** shared with the whole proven core — not a new blocker.

## Invariant (unchanged)

The global weakest-link headline stays authoritative; per-site grades (incl. the A1 re-base) are an
additional finer view and never loosen `casl gate`. A re-base fires only via a checked forward edge from a
`verified` boundary whose proved contract SMT-entails the consumer's — never G0 for free.

## Status

Informational decision record. **Realized:** CERT-FID proved (F\* 2026.03.24, 0 admits); `grade_flow` G0
grant + `run.py` enforcement shipped; tests + living audit green. **Frontier (not in this CEP):** transform /
how-provenance forwarding (needs `(φ_src ∧ sem(f)) ⇒ φ_dst`); transitive (multi-hop) *grade* re-base;
mechanized Robust Safety Preservation for the interpreter / TCB unification (discharges the O4 residual).
