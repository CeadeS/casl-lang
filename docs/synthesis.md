# Requirements → verified project (`casl new`)

*The authoring front door. Companion to CEP-0079, `docs/conductor.md`, `docs/confinement.md`.*

```
casl new my-project "Budgeted question-answering with a cost check and retry"
```

A requirement in natural language goes in; a complete, **gate-accepted, conducted** project comes out — or
nothing. The loop (`src/casl/synthesis.py`):

1. **Propose.** An *untrusted* generator (deterministic mock by default; `--live`/`--coder` for a real LLM)
   writes a `.casl` choreography.
2. **Gate.** The monotone gate decides — Tier-0 `check_protocol` (the MUST hull: projectable, guarded,
   no-self, distinct, closed, approval-dominance, capability containment) is the *sole opener*; Tier-1 a
   deterministic mock run; Tier-2 review (clamped to PASS/VETO/ESCALATE — a reviewer can never release);
   Tier-3 human attestation for effect-bearing / `verified` artifacts. **Agents may veto, never vouch.**
3. **Iterate.** On rejection the specific violations go back to the proposer (counterexample-style), bounded.
4. **Emit — only on acceptance.** A real project: `casl.toml` (one `oracle` artifact per oracle site bound
   via the typed seam; one single-purpose `external` provider per effect capability), `casl/<name>.casl`,
   the requirement trace.
5. **Conduct.** The emitted project is run through the broker (the conductor), confined per CEP-0078.

## What you get — and what you don't

**Guarantee (CEGIS / LLM-Modulo):** the gate is the *sole arbiter of emission*, so **every emitted project
satisfies the safety property regardless of how the generator produced it** — the proposer can only be
rejected, never vouch. If the gate never accepts within the budget, **nothing is emitted** (fail-closed) —
never a downgraded artifact.

**What it does NOT guarantee (validation ≠ verification):** the gate certifies *spec ⊨ safety*, not
*spec ≅ your intent*. A perfectly verified project can faithfully implement the *wrong* choreography. So the
emitted project's unprovable artifacts come with **human-attestation obligations** — the loop produces the
obligation; **you sign it**. Read the proposed `.casl` before adopting. (Residual risks — fidelity, vacuity,
over-restriction, reward-hacking, TCB integrity — are enumerated in CEP-0079.)

## Status

Verified offline with the deterministic mock generator. The live generator (Ollama / local coder) is wired
(`--live`, `--coder`) but its real run needs a model. A round-trip **validation** step for requirement↔spec
fidelity is the tracked next refinement.
