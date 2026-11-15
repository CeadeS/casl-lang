---
cep: 79
title: Requirements → verified project — the authoring loop (LLM proposes, the gate decides)
status: Draft
type: Informational
created: 2026-06-26
version: 0.1
requires: [77, 78]
realized-by: []
---

# CEP-0079 — Requirements → verified project (the authoring front door)

Books the loop realized by `src/casl/synthesis.py` (`casl new`): a requirement in natural language → an
**untrusted** generator proposes a `.casl` choreography → the **monotone gate** (`ide.synthesize_gated`,
Tier‑0 `check_protocol` the sole opener; "agents veto, never vouch") decides → on acceptance, emit a
complete, **conductable** project (manifest + choreography + artifacts bound to sites) → conduct it through
the broker ([CEP‑0077]) under the capability/confinement model ([CEP‑0078]). Closes the loop from intent to
a running, verified system.

## The loop (CEGIS-shaped)

Counterexample‑guided inductive synthesis (Solar‑Lezama) / the LLM‑Modulo pattern (Kambhampati et al.):
a proposer and a *sound verifier* in a feedback loop, **soundness from the verifier, never the proposer**.

1. **Propose** — `generator.propose(wish, feedback)` (mock | Ollama | local coder) emits `.casl`.
2. **Gate** — `synth.synthesize` runs `check_protocol` (Tier‑0, the MUST hull) to convergence, then the full
   monotone gate (Tier‑1 mock run · Tier‑2 review, clamped to PASS/VETO/ESCALATE · Tier‑3 human attestation
   for effect‑bearing / `verified` artifacts).
3. **Feedback** — on rejection the specific MUST violations go back to the proposer (counterexample‑style);
   bounded iterations.
4. **Emit — only on acceptance** — `project.init_project` + a derived manifest (`derive_manifest`: one
   `oracle` artifact per oracle site bound via the typed seam, one single‑purpose `external` provider per
   effect capability).
5. **Conduct** — `conductor.Conductor(dir).run(...)` runs the emitted project through the broker.

## Soundness guarantee (crisp)

Let the gate `G` be a *sound* decision procedure for the safety property `S` (`G` accepts `a` ⟹ `a ⊨ S`),
and the *sole* gate on emission. Then **every emitted project satisfies `S`, irrespective of how the
proposer produced it** — one line: emission requires `G(a)=accept`, soundness of `G` gives `a ⊨ S`, and the
proposer never appears in the implication. The untrusted generator can only affect *whether/how fast* an
accepted spec is found (completeness/throughput), never *what passes*. **Fail‑closed:** if `G` never accepts
within the iteration bound, nothing is emitted (no downgraded artifact).

## Residual risks (disclosed honestly — validation ≠ verification)

- **Requirement↔spec fidelity (dominant).** `G` certifies `a ⊨ S`, not that `S`/the `.casl` is *what the
  user meant*. The LLM‑produced formalization is an unverified trusted root; a perfectly verified project can
  faithfully implement the *wrong* choreography. This is *validation*, structurally outside `G`. The emitted
  project's unprovable artifacts therefore carry **human‑attestation obligations** (the loop produces the
  obligation; the human discharges it) and the formalization is graded **below "proved"** until evidenced.
- **Vacuity** — a trivially‑satisfiable spec verifies and proves nothing (mitigation: the SP‑4 anti‑vacuity
  gate). **Over‑restriction** — an over‑constrained gate rejects valid intent (surfaces as non‑convergence).
  **Reward‑hacking** — a capable proposer may satisfy `S` while subverting intent (the adversarial face of the
  fidelity gap). **TCB integrity** — the whole guarantee rests on the soundness of the F\*‑backed checker and
  the gate being the sole chokepoint.

## Realization

`src/casl/synthesis.py` (`new_project`, `derive_manifest`, `format_new`); CLI `casl new DIR "wish"`
(`check.cmd_new`); reuses `ide.synthesize_gated` + `synth.synthesize` + `project.init_project` +
`conductor.Conductor`. `tests/test_synthesis.py` pins it: a sound requirement → accepted project that
conducts to completion; a rejected proposal → **nothing emitted** (fail‑closed); the derived manifest binds
the oracle site + a single‑purpose provider; the emitted project re‑gates + conducts independently.

## Status

Informational decision record. Verified **offline with the deterministic mock generator** (the loop, the
fail‑closed property, the emit + conduct). The **live generator** (`synth.ChatGenerator` over Ollama /
`CoderBackend`) is wired but its real run needs a model (deferred, like the broker's live HTTP send).
Tracked refinement: richer manifest derivation (confined callers, multi‑protocol projects) and a
round‑trip/back‑translation **validation** step for requirement↔spec fidelity.
