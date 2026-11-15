# Closing W11: Variant A (n-ary core) vs Variant B (additive merge) — head-to-head

Both variants were implemented in full and machine-verified, on parallel branches:

- **B** — branch `feat/tcb-merge` (commit f8269d2)
- **A** — branch `feat/tcb-merge-A`

## The problem (recap)

The exhaustive TCB differential bridge (`src/casl/tcb_corpus.py`, single-sourced, 412 bounded
protocols, also generates `fstar/ocaml/driver.ml`) found 4 protocols where the Python checker
(full MPST merge) accepted external-choice merges the F\*-verified kernel rejected — the running
checker exceeding the proof (concrete W11 / LH-C-004).

## Variant B — additive `LExtN`, merge-only

Keep the global type and direct projection **binary**; add an n-ary external choice `LExtN`
used *only* by `merge`; implement the full MPST merge (mirroring `spike_proj_mpst.merge_pair`).
Because the F\* metatheorems are **head-scoped** (they never inspect `merge`'s output), no
metatheorem needed re-proving.

- `CASL.fst` diff: small (one constructor + ~40 lines of merge; `project` unchanged).
- F\* **0 admits** (no proof re-derivation).
- Bridge: **412/412** on the binary corpus.
- Expressiveness: unchanged (binary global choices only).

## Variant A — full n-ary refactor

Replace binary `GCh`/`LIntC`/`LExtC` with **n-ary** label-lists (`GCh p q [(l,G);…]`,
`LIntC p [(l,L);…]`, `LExtC p [(l,L);…]`); generalize `project` (+`project_opts`), the full
`merge` (n-ary `LExtC` directly), `subst_g`, and the step relations `gstep`/`cstep` to n-ary
(index-based selection); **re-prove all three metatheorems** for the n-ary calculus.

- New proof obligations that had to be discharged (all 0 admits): `project_opts_index` (the
  i-th projected option = projection of the i-th branch), `project_opts_len`, `cget_init`
  (`cget (init_config g) r == proj g r`), `proj_chooser` (the chooser projects a choice to an
  internal choice over the projected options). With these, `fidelity_complete`, `fidelity_sound`
  (the inversion direction — the hard one), and `deadlock_free` all re-verify.
- `CASL.fst` diff: large (types, 4 functions, 2 step relations, 3 metatheorems + 4 lemmas).
- F\* **0 admits**.
- Bridge: **412/412** on the binary corpus **plus** n-ary (≥3-label) choices — `nary3_ok`,
  `nary3_merge` (a third role merges three distinct receives → a 3-label external choice),
  `nary4_end` — all verified and agreeing. B's binary core cannot even *represent* these.

## Comparison

| Criterion | B (additive merge) | A (n-ary core) |
|---|---|---|
| Closes the 4-case W11 gap | ✓ | ✓ (subsumed: `LExtC` is n-ary) |
| F\* 0 admits | ✓ | ✓ |
| Bridge agreement | 412/412 (binary) | 412/412 (binary) **+ n-ary choices** |
| Expressiveness | binary choices | **n-ary choices** (strictly more) |
| `CASL.fst` change | small, additive | large, structural |
| Metatheorem re-proof | **none** (head-scoped) | **full** (4 new lemmas + 3 re-proofs) |
| Trusted/checked surface | minimal | larger (but fully proven) |
| Risk / maintenance | lowest | higher (bigger proven core) |

**Empirical power gap:** `nary3_merge = GCh C→A {l1:C→D x, l2:C→D y, l3:C→D z}` — role D merges
three receives into a 3-label external choice. A: projectable + F\*-verified. B: the binary
core cannot encode the 3-way global choice at all (`b1,b2 = branches` raises `too many values
to unpack`).

## Recommendation — and a decision to confirm

Both work and both are 0-admits. **A is strictly more powerful** (n-ary choices) at the cost of
a much larger proven core and a real metatheorem re-derivation; **B is minimal** — it closes the
actual W11 gap with a tiny, head-scoped-safe change and the smallest trusted surface.

The stated rule ("if A works and is more powerful than B, then we take **B**") is ambiguous —
it reads two ways:
- *take the more powerful* → **A** (n-ary expressiveness, the maximal core);
- *take the minimal* → **B** (smallest proven core; A's power isn't needed unless protocols use
  n-ary choices), which also fits the project's "prove the hull, keep the TCB small" ethos.

Engineering view: if n-ary choices are on the roadmap, **A** is the better long-term core (clean,
unified, and now proven). If the priority is the smallest verified trusted base and B already
closes the real gap, **B**. This is your call — both branches are ready to merge.
