---
cep: 72
title: Attestation key lifecycle — rotation, revocation, recovery
status: Draft
type: Informational
created: 2026-06-24
version: 0.1
requires: [57, 67]
realized-by: [obligation_gate, human_attestation]
---

# CEP-0072 — Attestation key lifecycle

The artifact-trust attestation (LH-Q-018) is a human signature by a GPG/SSH key. Keys change; the model
must say what happens to a signature when its key does. Realized by `src/casl/keyring.py` + the gate's
opt-in policy check.

## Model

A signature's authority is judged at **the time it was made**, against a keyring of identities with
validity windows (`.casl/attest_keys`):

    valid_at(t)  ≡  added ≤ t  ∧  (retired is None ∨ t ≤ retired)  ∧  (revoked is None ∨ t < revoked)

- **Rotation:** add the new key; mark the old `retired:<date>`. The retired key still validates
  attestations made on/before that date — so we **retain old public keys forever**; it just cannot make
  *new* ones.
- **Revocation (compromise):** mark the key `revoked:<date>`. Every signature **at or after** that date
  is invalid and must be re-reviewed; signatures before it stand.
- **Recovery (loss):** there is no cryptographic recovery. A lost key means out-of-band
  **re-attestation** with a new key. The model states this honestly rather than pretending.

## Mechanism (opt-in)

`keyring.authorized(project, identity, ts)` enforces the window. The gate consults it for each
otherwise-valid signature. **Opt-in:** if `.casl/attest_keys` is absent or empty, no key policy is
enforced (back-compat); `casl init` scaffolds a comment-only template, so the policy stays off until a
real identity is added. A solo repo can ignore it; a team turns it on by listing keys.

## Honest limits

- The policy binds the *recorded signer identity* + timestamp, not the raw key fingerprint — git does
  the cryptographic verification, this adds the *was-it-authorized-then* layer. Tighter fingerprint
  binding (via `git log %GK`) is a possible refinement, but it needs the public key present at
  verification time (a CI runner usually lacks it), so it lives at the local hook.
- Like every signature in CASL, this is a liability/authority record, not proof of correctness.
