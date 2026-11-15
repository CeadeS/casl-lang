---
cep: 57
title: Artifact-trust layer — artifacts, dependency burden, line traceability, human attestation
status: Draft
type: Informational
created: 2026-06-24
version: 0.1
requires: [3, 4, 55, 56]
realized-by: [project, dependency, traceability, attestation, obligation_gate]
---

# CEP-0057 — The artifact-trust layer

Implements P10 (accountability where proof is impossible) + containment from
`docs/artifact-trust-requirements.md`, per the synthesized design in
`docs/analyses/project-structure-and-modules.md`. This is the checker/IDE layer (rings 1–2); it does
**not** touch the verified core (`CASL.fst` stays 0 admits; `wellformed`/assurance ladder unchanged).

## Summary

A CASL **project** is manifest-driven (`casl.toml`) with a canonical layout. An **artifact** is a
first-class named unit (typed seam + body file + obligation record). Ownership splits the world:
**first-party** code we own is fully line-traced, blamed, and human-signed; **dependencies** we import
are an accepted, pinned, owned, contained **burden** — never line-traced. The Tier-0 obligation gate
binds all of this deny-by-default ("agents may veto, never vouch").

## What is implemented (this CEP's realizing modules)

- `project.py` — manifest model + canonical layout + `casl init` / `casl project`. Artifact unit with
  STRUCTURED, validated provenance kind (`external|generated|verified|oracle`, never inferred); the
  trace regime FOLLOWS OWNERSHIP, not a free choice (closes the self-downgrade hatch); unprovable kinds
  floor at G3. *(slate: LH-F-012 artifact decl, LH-F-013 provenance/kind, LH-P-009 trace regime)*
- `dependency.py` — `deps.lock` burden ledger: pinned (version+hash) + accepted-by a human; unpinned/
  unowned/undeclared blocks; a hash change expires acceptance. `casl deps`. *(slate: LH-Q-020)*
- `traceability.py` — per-line requirement + author + mechanism (`human|llm`, default human) + blame,
  over `git blame`; untraced first-party lines block; provenance summary (human-vs-llm mix).
  `casl trace` / `casl blame`. Honest limit: provenance, not justification. *(slate: LH-P-006/007)*
- `attestation.py` — content-bound (hash; edit ⇒ expires), non-self (producer ≠ attester), human-identity
  signature via a GPG/SSH-signed git commit ("humans sign as humans"); plaintext/none REJECTED as
  forgeable by a local agent. *(slate: LH-Q-016 floor, LH-Q-017 binding, LH-Q-018 human/non-self)*
- `obligation_gate.py` — the single Tier-0 opener composing manifest + deps + line-trace + attestation,
  deny-by-default; effective grade = weakest link (min-composition, laundering impossible). `casl gate`.
  *(slate: LH-G-006 gate, LH-Q-019 monotonicity)*

Tested end-to-end (`tests/test_project.py`, `test_dependency.py`, `test_traceability.py`,
`test_attestation_gate.py` — 22 tests); the verified core, bridge, and living audit stay green.

## Status / what is NOT yet authority

**Update (2026-06-24, on `feat/artifact-trust`):** the slate is now **promoted**. The 12 requirements
(`LH-F-012/013`, `LH-Q-016/017/018/019/020`, `LH-P-006/007/009`, `LH-G-005/006`) are entered in
`spec.REQS`, realized by kernel building blocks with self-tests (`artifact_manifest`,
`dependency_burden`, `line_traceability`, `trace_regime`, `human_attestation`, `obligation_gate`),
covered in the L2 sheet (`PH-AT-001..006`), and recorded as Standards **CEP-0058..0069** — `LH-G-005`
(observability capture) is **Deferred** (a tracked `ACCEPTED_GAPS` entry, not yet built). The living
audit now enforces the CEP↔`spec.REQS` round-trip and the `realized-by` "proven" rule on every run;
principle **P10** is added to `spec.GRUNDSAETZE`.

This work nonetheless **remains on the `feat/artifact-trust` branch**: merging it into `main` is the
maintainer's **CODEOWNERS sign-off** on the TCB-touching paths (`spec.py`, `kernel/`, `proposals/`) — the
human act of accepting these changes — and is **not yet done**. Until then this CEP stays a Draft record.

## Open questions (carried from the requirements draft)

- ~~Grade-per-data-flow-path vs. global minimum (LH-Q-019)~~ — **resolved (D1, CEP-0070):** grade per
  requirement reported alongside the unchanged global weakest-link headline; flow-graph / containment-
  boundary models deferred to the typed seam, under an anti-laundering invariant.
- ~~Provenance granularity: per line vs per region/function (LH-P-007)~~ — **resolved (D2):** per-line
  stays the enforced, language-agnostic ground truth; the *region* (contiguous same-provenance blame
  hunk, `traceability.regions`) is the default human-review view. Per-function (AST) rejected as it
  breaks language-agnosticism.
- ~~Rubber-stamp pressure from deny-by-default-must-sign~~ — **addressed (D3, CEP-0071):** cannot be
  mechanically prevented (honest); risk-concentration is surfaced + an optional `signers: N` second-signer
  knob exists now; observability (LH-G-005, the primary lever) stays deferred; sampling-audit is process.
- ~~Attestation-key lifecycle: rotation/recovery, retaining old public keys (LH-Q-018)~~ — **resolved
  (D4, CEP-0072):** `keyring.py` + `.casl/attest_keys` validity windows (retain retired keys; revoke
  invalidates at/after; loss ⇒ re-attest), opt-in gate policy.
- ~~Supply-chain strength beyond pin: SBOM / SLSA / Sigstore (LH-Q-020)~~ — **resolved (D5, CEP-0073):**
  `deps.lock` optional `evidence:pin|sbom|slsa|signed`, weakest-link floor surfaced, optional
  `min_evidence` policy block. Never makes a dependency "verified"; generation stays ecosystem tooling.

## Cross-references

`docs/artifact-trust-requirements.md`, `docs/analyses/project-structure-and-modules.md`,
CEP-0003 (assurance), CEP-0004 (integrity case), CEP-0055 (sound core), CEP-0056 (completeness ratchet).
