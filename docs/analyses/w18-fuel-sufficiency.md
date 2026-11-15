# W18 — fuel-sufficiency of the n-ary MPST merge (working document)

**Status: CLOSED — machine-proven in F\* (`merge_complete`, 0 admits), bridge 412/412, audit green.**
The winning idea: a symmetric fuel bound is provably inconsistent for the induction; an *asymmetric*
bound (charge the second argument double) closes it. Full narrative in §7 (A0/A1).

(Original working status below.) **Status:** ACTIVE (autonomous work). **Goal:** close W18 — prove that the fuel the wrapper `merge`
gives `merge_f` is always enough, i.e. `merge` never returns `None` *because it ran out of fuel* on a
pair that is actually mergeable. Equivalently: the running checker over-rejects nothing for a
fuel reason (incompleteness), so the SAFE-direction caveat becomes a theorem.

This file gathers everything, opens parallel proof strategies, evaluates them, and records every
attempt (success or failure) honestly.

---

## 1. The artefact under study (from `fstar/CASL.fst`)

```
merge_f (fuel) l1 l2 =
  if fuel=0 then None
  else if l1=l2 then Some l1
  else match opts_of l1, opts_of l2 with
       | Some (p,o1), Some (q,o2) -> if p=q then (match merge_opts_f (fuel-1) o1 o2 with
                                                   | Some o -> Some (LExtC p o) | None -> None)
                                     else None
       | _ -> None
merge_opts_f (fuel) o1 o2 =
  if fuel=0 then None
  else match o2 with
       | [] -> Some o1
       | (a,c)::t -> match assoc_lbl a o1 with
                     | None    -> merge_opts_f (fuel-1) ((a,c)::o1) t          // (None-branch)
                     | Some c0 -> match merge_f (fuel-1) c0 c with
                                  | Some c' -> merge_opts_f (fuel-1) (replace_lbl a c' o1) t  // (Some-tail)
                                  | None    -> None
merge l1 l2 = merge_f (lsize l1 + lsize l2 + 1) l1 l2          // <-- the bound B in question
```

`opts_of (LRcv p a c) = Some (p,[(a,c)])`, `opts_of (LExtC p os) = Some (p,os)`, else `None`.
`lsize` is the structural size (every node ≥ 1); `lsize_opts` sums option continuation sizes.

## 2. Already proven in F* (0 admits, on `main`, SP-3)

- **Monotonicity** `merge_f_mono`/`merge_opts_f_mono`: `merge_f n = Some r ⇒ merge_f (n+1) = Some r`
  (success is upward-stable in fuel). ⇒ a success at any fuel is a success at every larger fuel.
- **Output-size bound** `merge_f_size`/`merge_opts_f_size`: `merge_f n l1 l2 = Some r ⇒ lsize r ≤ lsize l1 + lsize l2`.
- Helpers: `opts_of_size` (`lsize_opts o + 1 = lsize l`), `assoc_size` (`assoc a os = Some c0 ⇒ lsize c0 ≤ lsize_opts os`),
  `replace_size` (`lsize_opts(replace a c' os) + lsize c0 = lsize_opts os + lsize c'`).

## 3. The target theorem

`merge_complete`: `(∃ n. merge_f n l1 l2 = Some r) ⇒ merge l1 l2 = Some r`.
By monotonicity this reduces to a **sufficiency / depth bound**: a successful computation needs at
most `B = lsize l1 + lsize l2 + 1` fuel (then monotonicity lifts any witnessing fuel ≤ B up to B,
and for a witnessing fuel > B we must show B already suffices).

## 4. The obstacle (why it is not a one-liner)

- **Structural termination is circular.** Dropping fuel needs the `Some-tail` recursion measure to
  decrease; with measure `lsize_opts o1 + lsize_opts o2` the change is `−lsize c0 + lsize c'`, which
  is `≤ 0` *only by the output-size bound* `lsize c' ≤ lsize c0 + lsize c`. But that bound is a fact
  *about `merge_f`*, provable only *after* `merge_f` is defined, whereas F\*'s termination check runs
  *at* the definition. Hence fuel. (A post-hoc completeness *Lemma* may use the size bound freely —
  not circular — so the route is a Lemma, not a structural redef.)
- **Fuel accounting is not linear.** The `None-branch` moves an element `o2 → o1` (total size
  conserved) while consuming 1 fuel, so a naive `B_opts = lsize_opts o1 + lsize_opts o2 + 1` is
  *constant* across such steps yet fuel drops — the bound must also charge for the `length(o2)`
  traversal. A hand bound `B_opts = lsize_opts o1 + 2·lsize_opts o2 + 1` makes both branches drop by
  ≥1 (using the size bound for `Some-tail`), **but** then `merge_f`'s `B−1` no longer supplies that
  `B_opts` when `lsize_opts o2 ≥ 2`.

## 5. OPEN QUESTION raised by §4 — is the code's bound `B = lsize l1 + lsize l2 + 1` even sufficient?

The §4 accounting cannot show `B` feeds the needed `merge_opts` fuel. Two possibilities:
1. **`B` is genuinely too small** for some mergeable pair ⇒ this is a real *incompleteness bug*
   (never unsoundness — deny-by-default), and the fix is to enlarge `merge`'s fuel to a
   proven-sufficient closed form, then prove it.
2. **`B` is sufficient** but needs a non-linear invariant (a `max_i (i + depth_i)` argument), and the
   loose linear bounds just fail to see it.

**Decision: settle this empirically first** (probe `merge_f` at `B` vs. at a large fuel over a big
corpus). A counterexample turns W18 into "correct the bound"; none over a wide search directs the
proof effort and suggests the tight invariant / the safe enlarged bound. (Recorded in §7.)

## 6. Parallel proof strategies (to evaluate)

- **A. Post-hoc completeness Lemma by strong induction on the witnessing fuel `n`**, using
  monotonicity + size/assoc/replace lemmas; choose a *sufficient* (possibly enlarged) closed-form
  bound for `merge` so the arithmetic closes. Most likely to land; non-circular.
- **B. Saturation/fixpoint**: `merge_f n = merge_f (n+1)` for `n ≥ B`. Same depth core.
- **C/D. Distinct-labels invariant**: in a well-formed choice the option labels are distinct, so the
  `Some-tail` `replace` continuation never re-merges `a` (no later element has label `a`); the
  recursion is then effectively structural on `o2` and the size-bound circularity disappears. Either
  redefine merge under that invariant (invasive; risks the 412-bridge + metatheorems) or prove
  completeness scoped to distinct labels (sufficient for all real protocols).
- **E. Enlarge the fuel to a manifestly-sufficient closed form** (e.g. quadratic
  `(lsize l1 + lsize l2)² + 1`, or `2·(lsize l1+lsize l2)+1`) chosen so the §4 accounting closes,
  then prove sufficiency for that bound. Trades a tight bound for a provable one — fully acceptable
  (the wrapper just uses more fuel; merge is still terminating and the verdict identical).

## 7. Attempt log

### A0 — empirical sufficiency probe (settles §5) — DONE
Faithful Python mirror of `merge_f` (`/tmp/w18/probe*.py`). Compared `merge_f(B)` vs fuel-saturated
`merge_f(BIG)`:
- 300 000 random pairs (depth ≤ 5, incl. **duplicate-label** stress): **0 mismatches; 0 pairs needed
  fuel > B.**
- targeted adversarial (long disjoint external choices forcing long None-traversals; long shared-label
  lists forcing deep Some-tail merges; random depth ≤ 8): **0 insufficiencies; max `needed/B` ratio
  = 0.80.**
⇒ **§5 resolved: the code's bound `B = lsize l1 + lsize l2 + 1` IS sufficient** (Possibility 2), with
~20 % headroom even adversarially. Actual depth is ~linear in the size sum. The statement is TRUE;
the difficulty is purely the proof's accounting.

### Refined plan
Prove a **sufficiency / saturation lemma by strong induction on the witnessing fuel `n`** (Strategy A),
using monotonicity (have) + size/assoc/replace (have). Hand-algebra shows a per-step bound closes with a
**2× constant** via monotonicity in the None-branch (`Δ = lsize c − 1 ≥ 0`) — but the *leaf* Some-tail
case (`t=[]`, `o1={(a,c0)}`) is off-by-one at exactly 2×. ⇒ use a **generous, provable bound**
`Bsuff = 2·(lsize l1 + lsize l2) + 1` (Strategy E): prove `merge_f n l1 l2 = Some r ⇒ merge_f Bsuff l1 l2
= Some r`, then point the wrapper `merge` at `Bsuff` (harmless by monotonicity; re-run the 412-bridge to
confirm identical verdicts). Iterate the exact constant in F\* (fast) until it closes. (If the tight `B`
proof is wanted later, it needs the `max_i(i+depth_i)` invariant — deferred; `Bsuff` closes W18 now.)

### A1 — SOLVED in F* (0 admits)
The symmetric linear bound is provably **inconsistent** (the four inductive inequalities force
`c2 > c1` on the opts side via the None-branch, yet equality via the symmetric merge_f→opts transfer).
The resolution is an **asymmetric** bound charging the second argument double:
`target_f(l1,l2) = lsize l1 + 2*lsize l2`, `target_opts(o1,o2) = lsize_opts o1 + 2*lsize_opts o2 + 1`.
All four inequalities then close using `opts_of_size` / `assoc_size` / `replace_size` / `merge_f_size`.
Proven: `merge_f_mono_le` + `merge_opts_f_mono_le` (lift a success across any larger fuel) and
`suff_f` / `suff_opts` (strong induction on the witnessing fuel `n`). Verified standalone against the
real `open CASL` core. Integration: wrapper `merge` re-pointed at fuel `2*(lsize l1 + lsize l2)`
(≥ target_f; ≥ old bound, so monotone-safe) + theorem `merge_complete`:
`(∃ n. merge_f n l1 l2 = Some r) ⇒ merge l1 l2 = Some r` — **the wrapper never returns a spurious
`None`.** W18 closed.

## 8. Reusable lessons + why we STOP here (not over-running into W19)

- **Lesson (transferable):** when a fuel/measure induction over an *accumulating* recursion stalls,
  the obstruction is often a hidden *asymmetry* (one argument grows, the other shrinks). A symmetric
  bound cannot see it; solving the per-branch inequality system for the *coefficients* (and finding
  the symmetric system inconsistent) hands you the right asymmetric bound directly. This is a clean,
  reusable recipe — record it for future fuel proofs (e.g. any future `merge`-like fold).
- **Empirics-first paid off:** the 360k-pair probe converted "is this even true?" into a fact before
  any proof effort, and the `needed/B ≤ 0.8` headroom told us a generous bound would be provable.
- **W19 (projection/merge completeness, Scalas–Yoshida) is deliberately NOT attempted here.** It is a
  genuinely research-grade problem (general mergeability completeness needs *automata-based*
  projection, Majumdar–Yoshida–Wies et al., CAV 2023) and — crucially — it is **not blocking**: CASL's
  mechanized guarantees are scoped to synchronous head-step fidelity + the bounded differential
  bridge, which do not depend on general mergeability type-safety. Grinding on it would be exactly the
  "don't get stuck" the task warned against. It stays a tracked, honest, non-blocking tension (W19),
  targeted by the SP-5 loop if/when pursued as dedicated research.


