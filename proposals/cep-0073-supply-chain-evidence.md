---
cep: 73
title: Supply-chain evidence beyond pin — SBOM / SLSA / signatures
status: Draft
type: Informational
created: 2026-06-24
version: 0.1
requires: [57, 69]
realized-by: [dependency_burden, obligation_gate]
---

# CEP-0073 — Supply-chain evidence beyond pin

Strengthens the *evidence* recorded about a dependency burden (LH-Q-020) without ever claiming the
dependency is verified. Realized by `dependency.py` (evidence level + floor + policy) + the gate.

## The evidence ladder

A dependency is an accepted, unowned burden — we never verify its body. What we *can* vary is the
**evidence about its provenance/integrity**, escalating:

| level | what it adds | detects |
|---|---|---|
| `pin` | version + sha256 (current) | substitution / drift of the pinned artifact |
| `sbom` | the full transitive set enumerated | the burden is **complete**, not just top-level |
| `slsa` | build provenance attestation | built from the claimed source by a trusted builder |
| `signed` | publisher signature (e.g. Sigstore) | bound to a publisher **identity** |

`pin < sbom < slsa < signed`. The honest invariant: **none make the dependency "verified"** — the body
stays unproven, unowned code. They make the *trust decision* better-informed and harder to subvert.

## Mechanism

`deps.lock` gains an optional `evidence:<level>` per line (default `pin`, so existing ledgers are
unchanged). `dependency.supply_chain_floor` reports the **weakest** evidence across all deps (the gate
surfaces it, like the grade weakest-link), and an optional manifest `min_evidence = "<level>"` makes the
gate **block** any dependency below it (`check_min_evidence`; off by default).

## Scope boundary (what CASL does NOT do)

**Generating** SBOMs, SLSA provenance, or signatures is ecosystem tooling (pip/cargo, `cosign`, SLSA
generators) — outside CASL. CASL is the **ledger of trust decisions + the policy gate**: it records the
evidence each dependency carries, surfaces the weakest, and enforces a declared minimum. Verifying the
attestations themselves cryptographically is a possible future refinement; today the ledger records the
human's assessment of the available evidence.
