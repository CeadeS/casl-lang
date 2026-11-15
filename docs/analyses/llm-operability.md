# Probe: Is CASL operable by an LLM? (Finding)

**Date:** 2026-06-19 · **Reviewer:** Claude (as design oracle) · **Toolchain:** `casl check/run/synth`, F\* core untouched
**Question:** Can an LLM operate the language? Is it usable and meaningful?
**Method:** 5 new choreographies for classic assistance cases written by hand, iterated against `casl check`, executed in the mock and **live against Gemma** (`google/gemma-4-31b-it`, vLLM on betty1); additionally the `casl synth` loop tested live.

---

## 1. What was built (`examples/`)

| File | Case | Constructs | Verdict |
|---|---|---|---|
| `expense_approval.casl` | Expense approval | 3 roles, read+write cap, data contract, approval gated irreversible booking | ✓ accepted |
| `email_assistant.casl` | Email assistant | `stream`, 4 roles, tool draft, approval gated sending | ✓ accepted |
| `meeting_scheduler.casl` | Meeting finding | `rec` + `measure`, retry, approval in the accept branch | ✓ accepted (1 SHOULD) |
| `travel_booking.casl` | Travel booking | 4 roles, ONE approval gating TWO irreversible effects, mergeability | ✓ accepted |
| `auto_reply_unsafe.casl` | Anti-pattern | Auto-send without approval | ✗ **correctly rejected** (approval dominance) |

Regression check: the entire attack corpus (`examples/attacks/`, 8 files) is still rejected; my 4 positive examples accepted, the 1 negative example rejected. No verdict shifted.

## 2. Runtime (live against Gemma)

- `casl run budgeted_qa --live`: the oracle (Gemma) answered, the monitor measured **out-of-band** `cost=13 ≤ budget=100` → ok. Noteworthy: Gemma reported a **wrong** self-cost (`Claim 5 ≠ measured 13`); the monitor took the measured number — `H4` hardening holds against a real model.
- `casl run` (mock) of all 4 positive examples: run through cleanly. The approval gate exposes the concrete irreversible action **before** consent, e.g. travel: "*Consent executes: BookFlight() [irreversible]; BookHotel() [irreversible]*". This is the safety promise in action.

## 3. Core finding — can an LLM operate the language?

**Strong model (Claude): yes, with the checker in the loop.** I produced 4 well-formed + 1 deliberately unsafe protocol and hit the safety model correctly. But even I ran into 3 language edges on the **first** draft and needed the checker diagnosis to fix them (see §4). The `casl check` feedback loop is good enough to get to green quickly — the diagnostics are precise and name the violated requirement.

**Medium model (Gemma 31B) via `casl synth --live`: no — no convergence.** 4/4 iterations failed at the **parser**, every time at the same spot. Gemma's raw output was *structurally plausible* but syntactically wrong in several places:

```casl
agent A caps {
  tool(oracle) scope "drafting" write ttl 3600 sig "sha256";   // 'mode' missing → "Expected 'ttl', found 'write'"
}
A -> J : ProposeDraft(cost: Int, content: Str)
  uses tool(oracle)            // 'uses tool' expected — NO arguments
  oracle
  contract [cost <= budget];   // keyword 'contract' does not exist; attribute order wrong
```

Three different errors in one block; the repair feedback names only the **first** parser error per round, and Gemma did not correct even that one over 4 rounds. Conclusion: the **surface syntax** has sharp edges on which a 31B model gets stuck, and the current repair feedback (raw parser error, one per round) is too thin to lead it out.

## 4. Friction points (real language edges I ran into)

1. **The contract DSL is tiny.** The grammar allows **only** `[Id <= Id]` or `[len(Id) > 0]`. No literals (`[size <= 500]` → parse error), no `>=`, `<`, `==`, `+`. Every bound must be threaded through as a payload variable.
2. **`oracle` promise + `stream` clash.** An `oracle` promise must be discharged **exactly once** per loop iteration (promise linearity). In a dispatch `stream` (mail/quit) the quit branch does not draft → 0 times → rejection. Solution: model the LLM draft in the stream as pure tool use (`uses compose`, without `oracle`).
3. **No statement after `rec`.** `rec {…} <more>` is a parse error. An action "after the loop" has to go into the terminating branch *inside* the `rec` — and each bystander (e.g. calendar) then needs a distinguishing message in **every** branch, otherwise not projectable.

None of these three are stated clearly in the guide; but the diagnostics led reliably to the solution.

## 5. Assessment

- **Meaningful?** Yes. The throughline — effectful action only behind approval, least-privilege capabilities, mergeability — bites exactly at the places where agents become dangerous, and the gate exposes the irreversible action before consent. The anti-pattern was structurally rejected.
- **Operable?** For a strong model with `casl check` as arbiter: yes. For auto-synthesis by a medium local model: not today — it fails on the surface syntax, not the semantics.
- **Biggest lever:** (a) extend the contract DSL (literals, more operators) or add the 3 edges to guide §4; (b) enrich the repair feedback (all errors + a concrete counterexample/fix snippet instead of only the first parser token), so the `synth` loop converges with smaller models too.

---

## 6. Rework + live re-test (2026-06-19)

Both levers from §5 were implemented and re-measured live on betty. What changed:

- **Contract DSL:** `>=` added (parser normalizes `a >= b` → `b <= a`); **integer literals** supported (`[size <= 500]`, monitor with operand resolver). Strict `>`/`<`/`==` still deliberately absent — the guide (§4) now documents all three language edges.
- **synth robustness:** `casl synth --live` crashed on every betty error with a traceback (unlike `casl run`). Now typed: `oracle.OracleUnavailable` (endpoint/timeout/HTTP/response) → clean abort.
- **synth ergonomics:** full example in the system prompt; **error-specific** repair hints (parser error → concrete correction); **accumulation** of the hints across iterations (the fail-fast parser names only 1 error/round); temp schedule (0 → 0.3); live budget 4 → 6 iterations.

**Re-test result (refines §3):**

- **QA wish (close to the prompt example): now converges in iteration 1** (previously 4/4 failure). The ergonomics fixes work.
- **New wish (expense approval, *not* resembling the example):** with accumulated feedback Gemma crosses the **syntax threshold** and reaches **parser-valid, semantically sensible** drafts in iter. 3/5 — the rejections are then the deep modeling rules (non-local choice: role `E` cannot distinguish branches; capability containment: `M` uses `ledger` undeclared). But the model **oscillates** (capability brackets ↔ strict `>`) and does not hold the full fix set across 6 iterations.

**Refined verdict:** the original finding "Gemma: no" was **confounded** by the synth ergonomics. After the rework the boundary shifts markedly back — from "fails at the first syntax token" to "reaches semantically sensible drafts, but does not hold ~5 simultaneous constraints across a full regeneration". The remaining deficit is now clearly a **capacity limit of the 31B model** (full regeneration at temp>0 reintroduces fixed errors), no longer prompt/DSL. The next real lever lies beyond this PR: **patch-/diff-based editing** instead of full regeneration, so that fixes accumulate structurally — or a stronger generator model. The safety architecture stays intact in all cases: the verifier rejected every faulty draft.
