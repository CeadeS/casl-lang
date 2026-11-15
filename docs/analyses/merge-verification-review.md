# Deep verification review — n-ary merge work (Variants A & B), with references

Scope: a critical correctness review of the F\* changes that close the W11 merge gap, on both
branches (`feat/tcb-merge` = B, `feat/tcb-merge-A` = A). Goal: go beyond "F\* reports 0 admits"
and check that the theorems are (i) actually verified, (ii) non-vacuous, (iii) correctly scoped
and not overclaimed, and (iv) consistent with the MPST literature.

## 1. Mechanical re-verification

- **A** (`feat/tcb-merge-A`): `fstar.exe CASL.fst` → *All verification conditions discharged*
  (0 admits), **including** the new non-vacuity lemmas. `make -C fstar tcb-bridge` → extracted
  n-ary kernel agrees with the Python checker on all 412 + n-ary cases.
- **B** (`feat/tcb-merge`): `fstar.exe CASL.fst` → 0 admits; `make -C fstar tcb-bridge` → 412/412.

## 2. Non-vacuity (are the theorems trivially true?)

A real risk with machine-checked `exists`-lemmas is vacuity (true because the premise is
unsatisfiable, or the conclusion is trivially witnessed). Checked:

- Added (and verified) `_ex_msg`, `_ex_ch`: `wellformed g /\ head_ok g` is **satisfiable** for
  a concrete message and a concrete 3-way choice — so `fidelity_complete`/`deadlock_free` have a
  non-empty domain.
- Added (and verified) `_fid_demo`: `fidelity_complete` is **instantiated** on a concrete 3-way
  choice and yields a real `cstep` — the lemma is not vacuously true.
- Degenerate inputs are correctly rejected, not silently accepted: an **empty** choice
  `GCh p q []` is *not* wellformed (a third role projects via `merge_all [] = None`); a
  self-communication is excluded from the head metatheorems by `head_ok` (`p <> q`).

## 3. What is proven — and what is not (scope honesty)

The metatheorems are **single-head-step**: `fidelity_complete` (global→config), `fidelity_sound`
(config→global, the inversion), and `deadlock_free` are about *one* step of the head construct;
`diamond_indep`/`cstep_diamond` (W9) prove commutation of two independent actions at both levels.
**Full, inductive session fidelity over arbitrary traces is NOT machine-proven here** — it is
validated by-test in `metatheory.py` (exhaustive state enumeration). This is stated in the
`CASL.fst` header and tracked as W9; the comparison/claims do not overclaim it. Review verdict:
the scope is honestly represented.

## 4. The merge / projection vs. the literature

The merge implemented in both variants — *receives / external choices from the **same partner**
union their labels; shared labels merge their continuations recursively; anything else is
non-mergeable* — is exactly the classic MPST **mergeability** projection of Honda–Yoshida–Carbone
(POPL 2008 / JACM 2016): the literature describes merging "the branches of non-local choices as
long as they all are receives from the same participants." Our `merge`/`opts_of` match this.

**Caveat worth tracking (referenced):** Scalas & Yoshida, *Less is More: MPST Revisited*
(POPL 2019), showed that **type-safety proofs built on mergeability projection were subtly
flawed** in the general (full π-calculus, async) setting, and that *complete* projection is
delicate — later addressed with automata-based projection (Wies et al., *Complete MST Projection
with Automata*, CAV 2023). Implication for us: our guarantees are scoped to **synchronous,
head-step fidelity + a bounded differential bridge**, which does **not** rely on the general
mergeability type-safety claim that was found flawed. But the merge approach's known limits
(completeness; async) should remain a tracked tension, and automata-based projection is the
state-of-the-art path if/when full completeness is needed.

## 5. Fuel-bounded merge (identified caveat — safe direction only)

`merge l1 l2 = merge_f (lsize l1 + lsize l2 + 1) l1 l2`. Termination is machine-proven (the fuel
strictly decreases). What is **not** machine-proven is that this fuel is always *sufficient*
(i.e. equals the unbounded merge for every input). Analysis:

- If fuel were ever exhausted, `merge` returns `None` → `wellformed` returns *false* → the checker
  **rejects** a protocol. That is **incompleteness, never unsoundness** (deny-by-default): it can
  never make the checker *accept* something invalid.
- The exhaustive bridge would **catch** any such case as a Python/F\* divergence; none occurred on
  412 + n-ary protocols. Combined with the size-based bound, fuel is sufficient in practice.
- Recommendation (cheap follow-up, applies to A and B equally): add a fuel-monotonicity lemma
  (`merge_f (n+1) ≡ merge_f n` above the size bound) to retire the caveat entirely.

## 6. The `is_head_event` weakening in A (assessed sound)

A changed `is_head_event (GCh p q opts) e` from label-membership to a sender/receiver **role
check**. This is only a *precondition filter* on `fidelity_sound`; the `cstep` derivation `d`
already pins `e` to a concrete selection event, and `_fid_demo` shows the companion direction is
non-vacuous. The weakening makes the premise *broader* (the theorem holds for more `e`), and the
proof still reconstructs the matching `GS_Ch`. No soundness loss.

## 7. Bridge scope (honest)

The differential is **exhaustive over a bounded corpus** (depth ≤ 2, capped, plus named/n-ary/
recursion cases), not a proof of full Python≡F\* equivalence. Agreement on 412 + n-ary is strong
empirical evidence within that bound, and is described as such (not as total equivalence).

## Verdict

No correctness defect was found that affects the A-vs-B decision. Both variants:
are genuinely verified (0 admits), **non-vacuous**, **honestly scoped** (head-step + by-test
remainder), and use a merge that **matches the classic MPST literature**. The identified
limitations are **pre-existing and shared** (head-scoping; mergeability-projection's known
general-setting subtleties; bounded bridge) or **safe-direction only** (fuel ⇒ incompleteness,
never unsoundness). Two cheap, variant-independent follow-ups are recommended regardless of which
branch is merged: (a) a fuel-monotonicity lemma; (b) track the Scalas–Yoshida projection-
completeness caveat as an explicit tension (with the CAV-2023 automata approach as the resolution
path).

## References

- Honda, Yoshida, Carbone. *Multiparty Asynchronous Session Types.* POPL 2008; JACM 2016.
  https://mrg.cs.ox.ac.uk/publications/multiparty-asynchronous-session-types-jacm/jacm.pdf
- Scalas, Yoshida. *Less is More: Multiparty Session Types Revisited.* POPL 2019.
  https://mrg.cs.ox.ac.uk/publications/less-is-more-multiparty-session-types-revisited/DTRS18-6.pdf
- Majumdar, Yoshida, Wies, et al. *Complete Multiparty Session Type Projection with Automata.*
  CAV 2023. https://cs.nyu.edu/~wies/publ/cav23_mst.pdf
- *Generalising Projection in Asynchronous Multiparty Session Types.* 2021.
  https://arxiv.org/pdf/2107.03984
