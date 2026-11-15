---
cep: 4
title: Integrity Assurance Case — requirements and guarantees cannot be bypassed or weakened
status: Draft
type: Informational
created: 2026-06-22
version: 0.1
authors: [Martin]
requires: [1, 3]
---

# CEP-0004 — Integrity Assurance Case

(Working title "Integrity Assurance Case"; alternatives considered: *Inviolability Argument*,
*Bypass-Resistance Case*.)

## Top claim

> A user — **including an AI agent** — using CASL to orchestrate AIs or to write programs cannot
> develop *past* the requirements, nor *weaken* the guarantees: the only way to obtain an
> "accepted / proven / level-L" verdict is to **actually satisfy** the corresponding obligation.

This is an **assurance case** in the sense of ISO/IEC/IEEE 15026: the claim is supported by an
argument and by **evidence that is itself machine-checked on every run** (the living audit + CI).
The argument rests on two classical results:

- the **reference-monitor** concept (Anderson 1972) — a policy enforcer that is **N**on-bypassable,
  **E**valuable/verifiable, **A**lways-invoked (complete mediation), **T**amperproof (NEAT); with
  Saltzer–Schroeder (1975) *fail-safe defaults*, *economy of mechanism*, *complete mediation*,
  *open design*; and
- **proof-carrying code** (Necula–Lee 1996) — an *untrusted producer* ships code **plus** a proof;
  a *small trusted checker* only **verifies**; trust never rests on the producer's word.

## Argument → evidence (each sub-claim bound to a concrete check)

| # | Sub-claim (property) | Mechanism | Evidence / check |
|---|---|---|---|
| C1 | **Non-bypassable + complete mediation** — the only path to a PASS is the deterministic Tier-0 checker; every actor else can only shrink the permitted set | monotone gate, "agents may veto, never vouch" | `casl/ide.py` (`Tier2 ∈ {PASS,VETO,ESCALATE}`, no APPROVE); `kernel.ide_monotone_gate`, `ide_tier2_review` (audit) |
| C2 | **Fail-safe defaults** — unknown/missing ⇒ reject | deny-by-default everywhere | `casl/run.py` approval default-deny; `levels.profile_ok/assurance_ok`; `kernel.runtime_approval` |
| C3 | **Assurance is computed, not claimed** — the level/grade a program earns is computed by the trusted checker, not asserted | `casl/levels.py` min-over-features; CEP proven-status | `levels.min_profile/min_assurance`; `cep.status_consistency`; `tests/test_levels.py` |
| C4 | **Traceability enforced, drift impossible** — every artifact cites a real requirement; every `Final` requirement has a green realizing block / discharged proof | authority chain + CEP round-trip | `authority.validate_blocks`/`uncovered_requirements`; `cep.validate` + `roundtrip_diff`; living audit exit≠0 on any gap |
| C5 | **The AI is an untrusted producer (PCC)** — its code/proofs/plans are re-checked, never trusted | F\*/Z3 re-checks proofs; checker re-checks projection/contracts/capabilities | `casl check --authoritative` runs the **F\*-extracted** `wellformed` as the core verdict (CEP-0009, in-fragment; TCB = F\*+Z3+extraction, not Python); `make -C fstar tcb-bridge` (412 + n-ary agree) as regression guard; the oracle boundary in `casl/mcp.py` (advisory, releases nothing) |
| C6 | **Proofs are non-vacuous + hole-free** — a sneaked `admit`/`assume` would make F\* verify vacuously | admits=0 gate | `scripts/check_admits.sh` (CI-enforced); non-vacuity lemmas in `CASL.fst` (`_ex_*`, `_fid_demo`) |
| C7 | **Tamperproof trust base** — the checker, requirements/CEPs, proofs, level model cannot be silently changed; an AI may *propose*, a human must *attest* | trust-base manifest + human review | `.github/CODEOWNERS` (trust base requires owner review); CI runs audit + admits-gate + round-trip on **every** change |
| C8 | **No self-attestation** — trust for the unprovable (oracle / external `verified` programs / irreversible effects) is **human**, specific, disclosed, reviewable; and the human attests only the *residual* after a mechanical anti-vacuity front-line | Tier-3 human attestation; per-gate disclosure; SP-4 front-line | `casl/ide.py` Tier-3; `GateDisclosure` / `on_approval` (per-gate consent, `kernel.gate_disclosure`); Tier-2 clamp forbids APPROVE; `casl/faithfulness.py` + audit `[5d]` (non-vacuity witnesses, must-die mutants, CEP↔levels consistency) |
| C9 | **Conservative layering** — enabling an outer level never changes the verdict of protocols that don't use it (gradual guarantee) | per-feature conservativity | CEP-0003; F\* **proven** `nary↾binary ≡ binary` (`CASL.conserv` / `conserv_wf`, 0 admits); `async` already conservative |
| C10 | **Evaluable / small TCB** — the trusted base is small enough to verify and can be shrunk (compile-out) | economy of mechanism; CEP-0003 build profiles | F\* 0-admits core; CEP-0003 `core` build excludes outer rings |

The audit being green is therefore not a formality: it *is* the continuously-rechecked evidence
for C1–C8/C10 (P0 self-application). CI adds the cross-tool gates (C6 admits=0; F\* + cargo).

## The irreducible roots of trust (stated honestly)

Non-circumvention cannot be made *absolute* — "who checks the checker?" bottoms out somewhere.
The roots are, explicitly:

1. **F\* + Z3 + the extraction** — `casl check --authoritative` now makes the F\*-extracted core
   the *running* verdict for in-fragment protocols (CEP-0009, SP-2), so W11/LH-C-004 is closed
   there; the residual is the trust in F\*+Z3+extraction itself (no de-Bruijn-checkable proof term)
   and Python's out-of-fragment MSC layer (the bridge bounds, does not erase, that part).
2. **Human attestations** — a human can rubber-stamp. Mitigation: keep them *minimal* (only the
   genuinely unprovable), *specific*, *disclosed*, *reviewable*; never blanket (`W15` resolved).
3. **The correctness of the requirement *statements*** — a wrong requirement is faithfully met,
   yielding a wrong guarantee. No tool removes this; the CEP corpus + human review surface it.

Per *open design*, these are **tracked, not hidden** (`spec.TENSIONS`, this CEP). Surfacing the
trust is itself the safeguard against the worst shortcut: pretending none exists.

## Meta-gap closed by this CEP

Before this CEP the gate protected *protocols* but not the *meta level* (the requirements/proofs/
checker themselves). Closed here: (a) **admits=0 gate** (`scripts/check_admits.sh`, CI) — proof
weakening cannot pass; (b) **trust-base manifest** (`.github/CODEOWNERS`) — trust-base changes
require human attestation; (c) CI runs audit + round-trip + admits-gate on **every** change, so a
weakening (a hole, a `Final` CEP without proof, a block citing a non-existent requirement) fails
loudly. The C9 conservativity obligation is now discharged in F\* (`conserv`/`conserv_wf`).
Remaining hardening tracked: `W11` (TCB unification).
