# Red-Team Review — CASL v0.1.27

**Reviewed:** CASL repo @ v0.1.27 (docs L0–L3, `prototype/`, `fstar/CASL.fst`, `engine/`, `examples/`)
**Date:** 2026-06-17
**Stance:** adversarial. The goal is to find where the system's guarantees do *not* hold, what it is actually good for, and how safe it is to rely on today.
**Finding-scheme:** `X-<sev><n>` — C = critical, H = high, M = medium, N = low/credit.

---

## 0. One-paragraph verdict

CASL is a genuinely good piece of *research engineering*: a clean two-stage idea (prove the deterministic hull, monitor the LLM as an oracle), a real — if tiny — machine-checked F\* core, a working projection/typing pipeline, and an unusually disciplined docs-as-code/traceability spine. It is **not**, today, a safety mechanism you can put in front of an autonomous agent with real side effects. The single property the whole safety story rests on — *"an irreversible action is structurally impossible without prior human approval" (LH-Q-011)* — is **demonstrably bypassable**, the effect-tagging it depends on is **unenforced and self-asserted**, and the runtime that is supposed to enforce approval **does not consult a human at all**. The proven core is real but covers a one-step, three-role, recursion-free fragment, and — critically — **the proven artifact is not the artifact that runs**. Treat the current "safe-/conform-by-construction" framing as a research aspiration, not a property the code currently delivers. The good news: every critical finding is fixable, and the fixes are mostly things the project already half-knows it needs.

---

## 1. What this actually is (and what it's good for)

Strip the framing and CASL is **a typed choreography linter + a monitored runtime harness for multi-LLM protocols**, plus a small mechanized MPST core. Concretely it does three useful things well:

1. **Protocol well-formedness for multi-agent message-passing.** Global choreography → per-role local types via MPST projection, with a real MSC cross-check. Catches non-local choice, mismatched branches, and unrealizable protocols *before* anything runs. This is the strongest, most defensible part.
2. **A structured place to hang policy.** Capabilities, contracts, crash/refusal cases, approval gates, termination measures are first-class syntax. Even where enforcement is weak, the *vocabulary* is right and the diagnostics are legible.
3. **A disciplined development methodology.** The requirement IDs → building-block registry → living audit → traceability tooling is better than what most production teams run. As a *process* artifact it is exemplary.

**Best honest positioning today:** a *design-time specification and linting language* for agent choreographies, and a *test/monitoring harness*, with a research-grade formal core. Not an authorization kernel, not a sandbox, not a runtime safety boundary.

---

## 2. Critical findings (the safety story does not hold)

### C1 — The approval-dominance keystone accepts "deny ⇒ do the irreversible thing"
`spike_approval.approval_dominated` walks the tree and sets `approved = approved or node.approval` for **every** branch under an approval `Choice`, then recurses into **all** branches. So an irreversible action placed in the **Deny** branch is considered "dominated by approval." The code's own docstring admits this ("it does not yet distinguish which branch means 'consent'"), but the consequence is not cosmetic — the gate certifies as safe a protocol whose plain reading is *"if the human refuses, perform the irreversible action."*

Reproduced (accepted, exit 0):

```casl
protocol DenyBranchAttack {
  roles S, U, K;
  agent S caps { calendar(event) scope "cal:write" ttl 1 sig "s1"; }
  S -> U : Conflict(detail: Str);
  choice approval at U -> S {
    Approve: { S -> K : Skip(); }
    Deny:    { S -> K : Move() uses calendar irreversible; }
  }
}
```

`casl check` → **✓ ACCEPTED**, "approval dominance (irreversible ⇒ approval) [PASS]". Projected local for the calendar role is literally `K: S&{ Skip(): end  Move(): end }` — the `Move` fires on the `Deny` path. The one invariant the VISION leans on ("the feared failure … becomes structurally impossible") does not hold against a one-line reordering.

**Severity rationale:** this is the marketed guarantee, and it fails on an input a confused author *or a synthesizing LLM* could easily produce.

### C2 — Safety depends entirely on untrusted, unenforced self-tagging
`irreversible` and `approval` are author-set booleans on AST nodes. **Nothing binds an externally-effectful capability to the `irreversible` flag.** A protocol that invokes a `mail:send` / `cal:write` / `delete` capability without the tag requires no approval and passes every MUST-gate. The threat model is exactly that the artifact behind a tool-call is opaque/LLM-written (VISION §2) — yet the safety check trusts that same artifact to honestly label its own dangerous actions.

Reproduced (accepted, exit 0):

```casl
protocol SilentSend {
  roles S, U, M;
  agent S caps { mail(to) scope "mail:send" ttl 1 sig "s1"; }
  S -> U : Notice(detail: Str);
  S -> M : SendEmail() uses mail;          // no `irreversible`, no approval anywhere
}
```

`casl check` → **✓ ACCEPTED**. For the motivating "autonomous secretary," this is the whole ballgame: the synthesizer omits one keyword (or never emits it) and the gate waves through unattended mail-send. The danger lives in the *capability* (`mail:send`), but the safety check keys off an unrelated, optional annotation.

### C3 — The runtime never asks a human; the "approval gate" has no operational meaning
`casl run` is presented as enforcing the two-stage semantics. But `casl_run._pick_branch` selects a branch purely from the **monitor verdict and tree structure** (`ok → a terminating branch`, else `a looping branch`). It does not read `Choice.approval`, does not pause, does not solicit consent. Running the *good* `reschedule.casl`:

```
• S→U: Conflict(detail:Str)
• U→S: ⊕ picks »Deny« (default; verdict=None)   ← chosen by the interpreter, no human
• S→K: Skip()
```

The approval node is resolved by a structural default. So even where the static checker is right, **at runtime the human-in-the-loop does not exist** — the gate is decorative once executing. The "the human approves the irreversible" pillar is currently unimplemented in the execution path.

---

## 3. High findings (the proof/engineering gap)

### H1 — The verified artifact is not the artifact that runs (TCB inversion)
There are **three** implementations of the core: F\* (`CASL.fst`, proven), Rust (`engine/`, *hand-written*, explicitly "No machine extraction"), and Python (`prototype/`, what `casl check`/`casl run` actually execute). The proof discharges properties about the F\* definitions; the **gate that decides real `.casl` files is the unverified Python.** Nothing mechanically ties the Python checker to the F\* core — `cargo test` "pins" Rust to Python/F\* by hand-written fixtures, not by extraction or refinement. The trusted computing base is the least-verified of the three, and divergence between them is a matter of human discipline, not proof. The OCaml extraction (`fstar/out/CASL.ml`) exists but sits off to the side, invoked by nothing in the user-facing flow.

### H2 — "Deadlock-free / fidelity, machine-proven (0 admits)" is true but covers far less than it sounds
The three F\* theorems (`fidelity_complete`, `fidelity_sound`, `deadlock_free`) are real and admit-free, but every one is guarded by `head_ok g`, which holds **only when the top node is a single `GMsg`/`GCh`** (binary choice, 3 fixed roles RC/RA/RJ, recursion explicitly excluded — `head_ok (GRec _ _) = false`). `deadlock_free` proves *"the first step can be taken,"* not *"no reachable configuration deadlocks."* There is no induction over execution, no recursion, no n-ary choice, no ≥4 roles. The file says so honestly ("Full reachability incl. recursion is covered by-test in `metatheory.py`"), but `README`/`CASL.md` advertise "progress + operational correspondence" and `LH-Q-001b` claims *"deadlock freedom MUST be statically guaranteed"* — a whole-protocol reading the proof does not support. **The proof is a one-step preservation/progress lemma for a toy calculus, dressed in the language of full metatheory.** `LH-Q-009` termination has the same shape: it checks that a `measure`/`bound` annotation is *present*, not that the measure actually decreases.

### H3 — Capability containment is a spec lint, not confinement
`spike_capability.capability_check` walks the AST and compares `uses_capability` strings to a declared set. There is no runtime: tools are never actually invoked or mediated (the "oracle step" only asks the LLM for an answer+cost). VISION admits the "real tool layer" is still missing. So "least privilege … privilege escalation structurally prevented" (P5) holds only over a *self-declared* spec; against a live LLM with real connectors there is zero enforcement that the agent calls only tools in its set. The property proven is "the spec doesn't *mention* an undeclared tool," not "the agent *cannot use* one."

### H4 — The oracle monitor checks a self-reported number; "SMT data-contracts" collapse at runtime
`LH-Q-004` advertises SMT-discharged data contracts. At runtime (`casl_run._oracle_step` / `oracle.oracle_step`) this reduces to: the oracle returns its own `cost` integer, and the monitor checks `cost <= budget` with `<=`. The agent **self-reports the quantity it is being judged on**; nothing measures real token/cost/effect. Blame ("blame A") is therefore gameable by the very component it is meant to police — an oracle that under-reports cost is "ok." The only contract forms the runtime understands are `le` and `nonempty`; everything richer in the contract vocabulary is unenforced at runtime.

---

## 4. Medium / low

- **M1 — Green self-audit ≠ external validation.** "26 building blocks, all MUST+SHOULD satisfied" is measured by the project's *own* `audit.py` against its *own* fixtures (essentially one canonical example + a couple of reschedule cases). `metatheory.py`'s "250+ protocols" live inside the same 3-role fragment. The audit can only catch regressions against properties someone already thought to encode; it is not evidence of coverage.
- **M2 — Consent is per-session, not per-action, and unbounded.** Even with C1 fixed, one `approval` dominates arbitrarily many irreversible actions, including inside a loop ("approve once → send forever"). My loop variant was only rejected *incidentally* (projection failure), not by the approval logic — confirming the approval check does not reason about multiplicity. `TBD-V-002 = strict` is noted but unimplemented.
- **M3 — Parser/encoding sharp edges.** `parse_contract` only supports `a <= b` and `len(x) > 0`; `>=` is tokenized but unused; string payloads are quote-delimited with no escaping; recursion variables aren't scope-checked (`continue X` to an unbound `X` would `KeyError` at run). Minor, but a synthesizing LLM will hit these.
- **M4 — `σ` (provenance/signature) is dead weight.** The capability tuple's whole point of difference from prior art is the provenance field; it is parsed and ignored (`W8`, open). The "unforgeable" in the Capability definition is currently aspirational.
- **N1 (credit) — Citations check out.** I independently verified the two load-bearing 2026 arXiv references: **2604.17612** (Bollig/Függer/Nowak, MSC coordination) and **2604.05969** (Acharya, MCP security / MCPShield) both exist and match. The repo's own `docs/reviews/casl-review-v0.1.0.md` correctly caught and corrected the one misattribution (the `(tool,params,scope,ttl,σ)` tuple is CASL's own model, now labeled as such). Intellectual honesty here is above average.
- **N2 (credit) — The docs are unusually candid about limits.** VISION §5 ("safe-/conform-by-construction, *not* content-correct") and the per-spike "honest limit" notes are accurate and rare. The problem is mainly that the top-level marketing language (README, LH-Q-001b/011) over-reaches past these honest caveats.

---

## 5. How unsafe is it, really?

Framed by use:

- **As a research prototype / thinking tool:** safe and, frankly, good. Nothing here is dangerous to explore; the ideas are sound and the honest caveats are present if you read inward.
- **As a *linter* in a human-driven workflow:** mostly safe and useful *if* you read its verdicts as advisory. The risk is **false confidence**: a "✓ ACCEPTED — approval dominance [PASS]" badge that a developer reasonably reads as "this cannot send/cancel without consent," when C1/C2/C3 show it can.
- **As an actual safety boundary for an autonomous agent with side effects (the motivating secretary):** **unsafe to rely on today.** The exact failure the system advertises preventing — unattended irreversible action — is reachable three independent ways (deny-branch placement, missing tag, no runtime gate), each demonstrated above. The gap between claim ("structurally impossible") and behavior (one keyword away) is the dangerous part, because the stronger the safety language, the more weight a user puts on it.

The honest one-liner: **CASL today proves the shell of a shell.** The mechanized core is a one-step fragment; the enforcement that reaches real `.casl` files is unverified Python; and the headline invariant fails on trivial adversarial inputs. None of that makes the *project* bad — it makes the *current claims* outrun the *current code*.

---

## 6. What I would do with it (prioritized)

**If the goal is the safety story (highest leverage first):**

1. **Bind effects to capabilities; stop trusting self-tagging (fixes C2).** Make "irreversible" a property of the *capability/tool declaration*, not an optional per-message boolean. `scope "mail:send"` / `cal:write` ⇒ the message that uses it is irreversible by construction. Then "irreversible ⇒ approval-dominated" keys off something the author can't forget to write.
2. **Make approval-dominance branch-aware and per-action (fixes C1, M2).** Only the *consenting* branch may discharge the obligation; the irreversible action must be dominated by an approval whose *taken* branch authorizes *that specific action*. Add multiplicity: an approval authorizes one action unless explicitly scoped to a loop with a bound.
3. **Wire approval into the runtime (fixes C3).** `casl run` must *block* at an `approval` node and require an external decision before entering a branch that contains an irreversible action — and refuse to proceed otherwise. Until then, drop "the human approves the irreversible" from the runtime claims.
4. **Add a real tool-mediation layer (fixes H3).** A capability check is only a safety property if the runtime *interposes* on tool calls and denies out-of-set ones. Even a thin broker that refuses undeclared tools would turn a lint into an enforcement point.

**If the goal is the verification story:**

5. **Collapse to one source of truth (fixes H1).** Either extract the Python/Rust checker *from* F\*, or make F\* the spec and generate the others, or at minimum add differential/fuzz testing that mechanically pins all three to each other. As long as the gate is hand-written Python, the proof is decoration.
6. **Either extend the proof or downgrade the words (fixes H2).** Prove progress/preservation *inductively over reduction* (with recursion, n-ary choice, parametric roles), or relabel the current theorems as "head-step lemmas" and stop claiming whole-protocol deadlock-freedom in the requirements. Make `termination` actually prove the measure decreases (SMT), not merely that an annotation exists.
7. **Measure what you monitor (fixes H4).** The oracle must not self-report the quantity it's judged on. Have the harness measure cost/effects out-of-band; treat oracle-supplied numbers as untrusted claims to be checked, not as ground truth.

**If the goal is credibility:**

8. **Build an adversarial corpus (fixes M1).** Ship a `examples/attacks/` directory of specs that *must* be rejected (deny-branch, untagged effect, approve-once-spam, cost-underreport) and gate CI on their rejection. A red-team suite is worth more than another green self-audit. (My three probe specs are a starting seed.)
9. **Align the top-level prose with the honest inner caveats.** The VISION-§5 voice should be the *front-page* voice. Today the README/LH headlines promise more than VISION admits.

---

## 7. Bottom line

Keep building this — the bones are good and the discipline is rare. But right now CASL **specifies and lints** agent choreographies and **harnesses** their execution; it does not yet **enforce** the safety property it leads with. The most valuable next commit is not another building block — it is an `examples/attacks/` suite that makes `casl check` *fail*, plus the four C-fixes that make it pass those attacks for real. Until effects are bound to capabilities, approval is branch-aware and runtime-blocking, and the gate that runs is the gate that's proven, the right claim is **"safe-by-lint, with a verified toy core"** — not "safe-by-construction."

---

### Appendix — reproduction

```
pip install z3-solver
python3 prototype/audit.py                       # baseline green
./casl check examples/reschedule.casl            # ✓ (intended-good)
./casl check examples/reschedule_bad.casl ; echo $?   # ✗ exit 1 (intended-bad)

# C1 — irreversible in the Deny branch → wrongly ACCEPTED:
./casl check /path/DenyBranchAttack.casl ; echo $?    # ✓ exit 0
# C2 — effectful capability, no tag, no approval → wrongly ACCEPTED:
./casl check /path/SilentSend.casl ; echo $?          # ✓ exit 0
# C3 — runtime resolves the approval gate with no human:
./casl run examples/reschedule.casl                   # "picks »Deny« (default; verdict=None)"
```

(Attack specs are in §2. F\* coverage claims: read `head_ok` and the `requires head_ok g` on all three theorems in `fstar/CASL.fst`.)
