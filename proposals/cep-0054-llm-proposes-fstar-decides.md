---
cep: 54
title: LLM-proposes / F*-decides proof loop (SP-5; targets W18 depth bound, W19 completeness)
status: Draft
type: Informational
created: 2026-06-18
version: 0.1
authors: [Martin]
requires: [4]
---

# CEP-0010 — LLM-proposes / F\*-decides proof loop

**SP-5.** Dogfoods CASL's own validated pattern to discharge CASL's own hardest open obligations:
an LLM is an **untrusted proposer**, F\* is the **sole acceptor**, the search is **fail-closed**.

## Mechanism (`src/casl/proof_loop.py`)

A `ProofGoal` is an F\* lemma signature; a `Generator` (LLM or `MockGenerator`) proposes a proof
body; `verify_candidate` writes `module CASLProof; open CASL; <header><body>` and runs `fstar.exe`.
A candidate is **accepted iff** (1) it contains **no proof hole** (`admit`/`assume`/`sorry`/`magic`
— rejected *before* F\* even runs) **and** (2) F\* discharges all VCs (RC=0). `attempt` iterates a
bounded number of times, feeding each error back; on exhaustion the goal stays **open**, never
"assumed". This mirrors `scripts/check_admits.sh`, so the loop cannot manufacture a verdict.

## Why this shape (research-grounded)

LLM-proposes / kernel-decides is the empirically robust pattern (COPRA; Draft-Sketch-Prove;
DeepSeek-Prover-V2), and the 4/δ result bounds the search loop's termination *if a proof exists*.
The LLM is never an accept authority (self-preference / position bias make it a biased judge);
F\* is. See `docs/analyses/verification-mode-and-tcb-unification.md` §SP-5.

## Targets (honestly open)

`PENDING_GOALS` records the hard residuals the loop aims at, **not yet proved**:

- `merge_fuel_depth_bound` — the recursion-DEPTH half of fuel-sufficiency (W18); monotonicity +
  output-size are already proven (SP-3), this is the remaining piece. Status: **open**.
- `merge_projection_completeness` — projection/merge completeness à la Scalas–Yoshida (W19);
  genuinely hard, may stay a tracked bounded result. Status: **bounded**.

Expectation set honestly: the loop *infrastructure* is in place and verified (it closes real core
lemmas against F\*, and is fail-closed on holes and on false goals — `tests/test_proof_loop.py`).
Whether it closes W18/W19 is an empirical, possibly-open question; whatever it does not prove
remains a tracked tension, **never** silently assumed.

## Cross-references

CEP-0004 (C5/C6 — untrusted producer, no vacuity), CEP-0009 (extracted checker authoritative),
tensions W18/W19, `docs/analyses/verification-mode-and-tcb-unification.md`.
