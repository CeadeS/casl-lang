# Red-Team Re-Test — CASL v0.1.28 (Approval-Keystone hardening)

**Reviewed:** CASL repo @ v0.1.28 — commits `99364c4` (PR #18, "red-team hardening of the approval keystone"), `e6b13db`, `9b504b6` (C3 runtime enforcement)
**Date:** 2026-06-17
**Scope:** re-run the three critical attacks from `docs/reviews/redteam-review-v0.1.27.md` (C1/C2/C3) + M2, verify the fixes are real (not relabels), then adversarially probe the *new* logic.
**Finding-scheme:** `X-<sev><n>` — C = critical, H = high, M = medium, N = low/credit.

---

## 0. One-paragraph verdict

The hardening is **real and correct in structure**, not cosmetic. All three v0.1.27 criticals (C1 deny-branch, C2 untagged effect, C3 no-runtime-gate) and the M2 loop-consent issue are now closed by the right mechanisms: a *consent-branch* obligation, effect-bound-to-capability with deny-by-default, a per-encounter loop reset, and a genuine **default-deny** runtime gate. One new finding replaces the old one: the C2 fix moved the trust surface from an author-set boolean (`irreversible`) onto an author-set **free-text `scope` string**, and the classifier that reads it (`effectful()`) is both **leaky** (a normal write-naming convention is misread as read-only) and **spoofable** (any scope containing "readonly" is trusted). Two specs that should require approval are accepted with no gate. Net: the keystone went from "bypassable three ways" to "bypassable one way, via the effect classifier" — a large improvement, with one focused fix remaining.

---

## 1. Status of the v0.1.27 criticals

| ID | v0.1.27 | v0.1.28 | Mechanism that fixes it |
|----|---------|---------|--------------------------|
| **C1** — irreversible action in the *Deny* branch | accepted (unsafe) | **REJECTED ✓** | `approval_dominated`: `br_approved = True if (node.approval and b.consent) else approved` — only a `consent`-marked branch discharges the duty |
| **C2** — effectful capability, no `irreversible` tag | accepted (unsafe) | **REJECTED ✓** | `is_irreversible` = explicit tag **OR** `effectful(cap)`; `effectful` is deny-by-default (effectful unless scope is read-only) |
| **C3** — runtime never consults a human | gate resolved by structural default | **ENFORCED ✓** | `_decide_approval`: interactive callback → explicit `--approve` → **default-deny**; `_pick_approval_branch` never enters a consent/effect branch without external approval, and aborts if no deny-path exists |
| **M2** — one approval authorizes a whole loop | not reasoned about | **CLOSED ✓** | `walk(Rec)` recurses with `approved=False` — consent does not survive an iteration |

These are verified against the running system, not just the source:

```
$ ./casl check  <DenyBranchAttack.casl>   → ✗ REJECTED  (approval dominance FAIL:
        "effectful action S→K (Move) not dominated by an approval consent branch")
$ ./casl check  <SilentSend.casl>          → ✗ REJECTED  (same gate)
$ ./casl run    examples/reschedule.casl                 → approval gate ⛔ no grant → deny → Skip
$ ./casl run    examples/reschedule.casl  (approve=True) → approval gate ✅ externally granted → Move
$ ./casl check  examples/reschedule.casl   → ✓ ACCEPTED   (intended-good still passes)
```

The runtime behaviour is the important one: with no approval the interpreter takes the non-consent branch (`Skip`, no effect); only an *external* grant routes into the consent branch (`Move`, the irreversible effect). The human-in-the-loop now exists in the execution path, and it is default-deny. This was the weakest point in v0.1.27 and it is now structurally sound.

---

## 2. New finding

### R-H1 — The effect classifier is a spoofable, leaky substring test on the author's `scope` string
**Severity: high.** Closes nothing of C1/C3, but re-opens a narrow version of C2.

`spike_approval.effectful()` decides whether an action is dangerous by lower-casing the capability's `scope` and testing for the substrings `("readonly", ":read", "read-only")`. Everything keys off that classification. Two problems:

**(a) Leak — ordinary write naming is misclassified as read-only.** `:read` is a *prefix* of `:read-write` / `:readwrite`. So a genuine write scope using the common `read-write` convention is treated as non-effectful and needs no approval. This is the dangerous case because an honest author — or the NL→spec synthesizer — produces it *by accident*.

**(b) Spoof — any scope containing "readonly" is trusted regardless of the tool.** A `purge` / `delete` / `send` tool whose scope merely contains the string "readonly" escapes the gate.

Reproduced — both **ACCEPTED (exit 0), no approval gate required**:

```casl
protocol RWNaming {                       // (a) leak: plain write naming
  roles S, U, K;
  agent S caps { calendar(event) scope "cal:read-write" ttl 1 sig "s1"; }
  S -> U : Notice(detail: Str);
  S -> K : Move() uses calendar;          // writes the calendar, no tag, no approval → ACCEPTED
}

protocol DeleteReadonly {                 // (b) spoof: destructive tool, misleading scope
  roles S, U, D;
  agent S caps { purge(id) scope "db:readonly" ttl 1 sig "s1"; }
  S -> U : Notice(detail: Str);
  S -> D : Purge() uses purge;            // deletes, no tag, no approval → ACCEPTED
}
```

Unit-level confirmation (the classifier itself, independent of parsing):

```
effectful("cal:read-write") = False      ← write scope read as read-only (leak)
effectful("cal:readwrite")  = False      ← write scope read as read-only (leak)
effectful("db:readonly")    = False      ← destructive tool trusted (spoof)
```

**Root cause.** The v0.1.27→v0.1.28 fix correctly bound *effect* to *capability* (good) but inferred the effect from **free text the author controls**, matched by a greedy substring test. Trust didn't leave the artifact; it moved from the `irreversible` boolean to the `scope` string. Deny-by-default helps (an unknown scope *is* treated as effectful), but the read-only allow-list is both too greedy (`:read` ⊂ `:read-write`) and trivially spoofable (`readonly` anywhere).

**Fix (focused).** Stop inferring effect from a scope substring. Make read-only an explicit, structured, validated capability property — e.g. a `mode: read | write | admin` field (default `write`), or an `effect: none | reversible | irreversible` field — so the safe classification can only be reached by an explicit, reviewable declaration and cannot be produced by naming. If a free-text scope must be kept, match it against an exact allow-list of known read-only scopes (`== "web:readonly"`, …) rather than `in`, and treat everything else as effectful.

---

## 3. Minor

- **R-N1 — runtime consent is blanket, not per-action.** `--approve` is a single boolean that approves *every* gate in a run; the per-node `on_approval` callback exists but the CLI doesn't bind it to the disclosed message (`Conflict(detail)`). So a run is either all-deny or all-approve, and the grant isn't tied to what the human was shown. This is the residual "approve X, the branch actually does Y" gap — a structural checker cannot close it; only per-gate disclosure + per-gate consent can. Not a hole (default-deny holds), but it caps how much the approval gate can really mean. Worth wiring `on_approval` to a real per-gate prompt before the "autonomous secretary" use case.
- **N2 (credit) — the turnaround was fast and the mechanisms are the textbook-correct ones** (consent branch, capability-bound effect, default-deny runtime, loop reset). The fix tracked the report's recommended directions closely.

---

## 4. Updated safety posture

The v0.1.27 verdict was "the keystone is bypassable three independent ways; unsafe to rely on as an authorization boundary." After v0.1.28:

- The **structural** story is now genuinely strong: an effect must sit in a consent branch of an approval gate, consent doesn't leak across branches or loop iterations, and the runtime is default-deny. The class of "author forgot the gate / put it in the wrong branch / runtime ignored it" failures is closed.
- The **residual** exposure is one layer down and narrow: whether a given action *counts* as an effect is decided by a spoofable/leaky scope heuristic (R-H1). Until that classifier is hardened, the gate can still be walked past — but now only through a mislabeled or convention-named capability, not through protocol shape.

Everything outside the approval keystone from `docs/reviews/redteam-review-v0.1.27.md` still stands and is unchanged by this patch: the verified F\* core still covers only the one-step / 3-role / recursion-free head fragment (H2); the gate that runs is still unverified Python while the proof is about the F\* definitions (H1); capability containment is still a static lint with no runtime tool-mediation (H3); the oracle monitor still checks a self-reported cost number (H4). Those remain the larger structural gaps; R-H1 is the one this release newly introduced.

---

## 5. Recommendations (prioritized)

1. **[R-H1] Replace the scope-substring effect test with a structured, validated capability field** (`mode`/`effect`), default-effectful. This is the one fix that closes the keystone for real. Add `cal:read-write`, `cal:readwrite`, `db:readonly`-on-`purge` as cases that MUST be rejected.
2. **Ship `examples/attacks/` and gate CI on rejection.** A suite of specs that `casl check` must reject (deny-branch, untagged effect, approve-once-spam, read-write-naming, readonly-spoof, cost-underreport) is worth more than another green self-audit. The five specs in this report and v0.1.27 are the seed.
3. **[R-N1] Bind `on_approval` to a per-gate prompt** that shows the disclosed message and the specific action about to run; drop the blanket `--approve` for anything beyond demos.
4. **Carry the larger v0.1.27 items** (H1 single-source-of-truth, H2 proof scope vs. claims, H3 runtime tool-mediation, H4 measured-not-self-reported cost) as their own tracked work — they bound how much "safe-by-construction" can ever mean here.

---

### Appendix — reproduction

```bash
pip install z3-solver
cd <repo>

# v0.1.27 criticals — now all rejected / enforced:
./casl check  /tmp/atk/deny_branch.casl   ; echo $?      # ✗ exit 1  (C1 closed)
./casl check  /tmp/atk/untagged_send.casl ; echo $?      # ✗ exit 1  (C2 closed)
./casl run    examples/reschedule.casl                   # default-deny → Skip (C3 closed)

# R-H1 — effect classifier leak / spoof, both wrongly accepted:
./casl check  /tmp/atk/rw_naming.casl       ; echo $?    # ✓ exit 0  (leak: "cal:read-write")
./casl check  /tmp/atk/delete_readonly.casl ; echo $?    # ✓ exit 0  (spoof: "db:readonly" on purge)

# classifier, in isolation:
python3 -c "import sys;sys.path.insert(0,'prototype');import spike_approval as a,casl_core as c;\
print(a.effectful(c.Capability('x',('p',),'cal:read-write',1,'s')))"   # -> False
```

Attack specs (`RWNaming`, `DeleteReadonly`) are in §2; v0.1.27 specs (`DenyBranchAttack`, `SilentSend`) are in `docs/reviews/redteam-review-v0.1.27.md` §2.

*End re-test — CASL v0.1.28.*
