# W19 — projection soundness & completeness (mergeability) — project setup

**Status:** OPEN (dedicated project). **Goal:** a *satisfying*, honest resolution of W19 — i.e. a
rigorous statement of what CASL's projection/merge guarantees, with the safety-critical direction
(soundness) actually proven, and the completeness gap either closed or precisely characterised.

This file frames the problem, the literature, CASL's exact current state, and candidate solution
routes with the criteria for "satisfying". Work + decisions are logged at the bottom.

## 1. Background — what projection is (the heart of MPST and of CASL)

A **global type** `G` describes a protocol from a bird's-eye view ("Client sends Request to Agent;
then Agent sends either Ok or Err to Judge; …"). To run it, each role needs its own **local type**
(its private script: what it sends/receives, in what order). **Projection** `G↾r` mechanically
derives role `r`'s local type from `G`. Projection is the bridge from the one global spec to the many
endpoint programs; well-formedness = "G projects to every role".

## 2. The hard case — the third party at a choice (where "merge" enters)

At a choice `p → q : { l_i : G_i }` (p tells q one of several labels), consider a role `r` that is
**neither p nor q**. In some branches `r` may behave differently. But `r` does *not* see which label
p chose — so `r`'s single local type must be **consistent with every branch**. **Merge** combines the
per-branch projections `G_i↾r` into one local type:
- identical behaviours merge to themselves;
- *external choices / receives from the same partner* merge by **unioning** their label sets
  (full merge, Honda–Yoshida–Carbone) — r can simply be ready to receive more labels;
- otherwise the branches are **not mergeable** ⇒ projection is undefined ⇒ G is rejected.

`merge` is exactly CASL's `merge_f`/`merge_opts_f` (the fuel-bounded function W18 was about). The
*question* of W19 is not whether `merge` terminates (W18, solved) but whether the merge-based
projection is **right**.

## 3. The two ways merge-based projection can be "wrong"

- **SOUNDNESS (the safety-critical direction):** could `wellformed(G)` accept a `G` whose projected
  endpoints actually *deadlock / mis-communicate*? If yes, the checker gives a false "safe" — the one
  thing CASL must never do. (Over-acceptance.)
- **COMPLETENESS:** could `wellformed(G)` *reject* a `G` that is in fact perfectly safe (some role's
  branches aren't syntactically mergeable, but the protocol is fine)? If yes, the checker is overly
  conservative — annoying, not dangerous. (Under-acceptance / false rejects.)

## 4. Why this is a *known* subtle area (the literature)

- **Scalas & Yoshida, "Less is More: Multiparty Session Types Revisited", POPL 2019.** Showed that
  the *classic* top-down MPST theory (global type + syntactic projection + mergeability) has a
  **limited subject-reduction property**, and that several published systems' type-safety proofs were
  consequently **flawed**. Their fix: drop the heavy syntactic machinery; type processes against a
  context and require a **single general behavioural safety property** (checked semantically, e.g. by
  model-checking the bounded state space). "Less is More" = less syntax, more generality + actual
  soundness. → This is *the* warning that "mergeability ⇒ safety" is not free, and the template for a
  soundness-first fix.
- **Li, Stutz, Wies, Zufferey, "Complete Multiparty Session Type Projection with Automata", CAV 2023.**
  The first projection operator that is **sound, complete, and efficient**: it represents each role's
  local behaviour as an automaton (communicating state machine) and decides implementability;
  MST implementability shown **PSPACE-complete**. → This is *the* route to closing the **completeness**
  gap (syntactic mergeability is incomplete; automata are complete).
- (Related: Majumdar–Mukund–Stutz–Zufferey, CONCUR 2021, generalising async projection; Stutz et al.,
  ECOOP 2023, async MST implementability decidable.)

## 5. CASL's exact current state (what is proven vs. assumed)

- CASL uses **syntactic mergeability** projection in BOTH the Python checker and the F\* core
  (`project`/`merge_f`).
- **Proven in F\* (0 admits), but HEAD-SCOPED (single step):** `fidelity_complete`/`fidelity_sound`
  (a global head step ↔ a configuration step) and `deadlock_free` (a head choice/comm can always
  step). W18 closed: `merge` never spuriously fails.
- **NOT yet proven:** a *global, multi-step* safety theorem (deadlock-freedom / fidelity for the whole
  protocol run, composing the head-step results), and any statement that merge-based projection is
  **sound** in the Scalas–Yoshida sense. Completeness vs. the automata-complete operator is also open.
- **Honest scope today (the W19 tension text):** CASL's mechanized guarantees are deliberately scoped
  to synchronous head-step fidelity + the bounded differential bridge, which do *not* rely on the
  general mergeability-type-safety claim. W19 = make this rigorous, not just scoped.

## 6. What a "satisfying solution" must deliver (acceptance criteria)

1. **Soundness first (non-negotiable):** a machine-checked theorem that `wellformed(G)` ⇒ the
   projected endpoint system is safe (no deadlock / orphan / reception error) for the synchronous
   semantics — i.e. CASL never accepts an unsafe protocol. This is the safety-critical half and the
   real content of W19 for our "no unsound accepts" ethos.
2. **Completeness: MAXIMISED in practice + test-evidenced (NOT proven).** Build the strongest
   practical automatic checker (full Honda–Yoshida–Carbone merge; target the sound+complete
   automata operator, CAV 2023) so it accepts as much *safe* G as feasible — and *demonstrate* that
   completeness empirically (differential vs. a semantic safety oracle over a large corpus, like the
   TCB bridge), without demanding an F\* completeness theorem. The user/oracle (criterion-bridging
   C′) covers only the genuinely-undecidable residual, as labelled G3. (Soundness proved, completeness
   maximised-by-test, residual attested — the three assurance grades.)
3. **No regression / no new TCB:** stays 0-admits; the TCB bridge still agrees; the level model and
   the existing metatheorems remain valid.

## 7. Candidate solution routes (to compare & synthesise)

- **A. Soundness theorem for the synchronous core (extend the head-scoped metatheorems to multi-step).**
  Prove global deadlock-freedom/fidelity by induction over the reduction, reusing W9 (confluence/swap)
  + the head-step lemmas. Closes criterion 1 within CASL's existing calculus. Most aligned with what we
  have; F\*-providable; **primary candidate**.
- **B. Semantic safety à la Scalas–Yoshida (bounded model-check the projected system).** Replace/augment
  "trust syntactic mergeability" with a direct safety check over the bounded synchronous state space
  (CASL already does this for async, `semantics_async`/`async_bounded`). Gives soundness by construction
  for the bounded fragment and side-steps the mergeability pitfalls. Synergises with B-for-async.
- **C. Automata-complete projection (CAV 2023) for the completeness half.** Implement/port the
  automata-based projectability decision to characterise/close completeness; heavier, PSPACE, likely a
  separate decision oracle cross-checked against `merge`. Targets criterion 2.
- **C′ (CHOSEN for completeness) — the user/external as a COMPLETENESS ORACLE behind the monitored
  boundary.** Key insight (Martin): completeness is ultimately the user's concern, supplied from
  OUTSIDE. So treat it exactly like CASL treats the LLM/oracle: the sound, fast, syntactic checker
  decides by default (deny-by-default); when it *rejects* a borderline `G`, an external oracle may
  supply COMPLETENESS — but NEVER soundness. Two grades, monotone & labelled:
  - **strong (default, no new trust):** the user/tool ships a re-checkable CERTIFICATE (explicit local
    types / a bounded bisimulation witness / the CAV-2023 automata projection / even an F\* proof);
    CASL's TRUSTED sound checker (route A/B) re-validates it. Accept iff it verifies. Pure PCC / the
    SP-5 "propose ⇒ F\* decides" pattern — soundness preserved, grade up to the certificate's strength.
  - **weak (fallback):** when no machine witness exists, a human Tier-3 ATTESTATION admits `G` at mode
    `attested`/G3, disclosed & reviewable, deny-by-default if absent. New trust = the human (bounded,
    labelled — never confused with the G0 proved core).
  HARD INVARIANT: the oracle can only lift a conservative REJECT to an ACCEPT; the sound core always
  retains the safety verdict, so no oracle (human or tool) can ever turn an unsafe `G` into an
  accepted one.

  CLARIFICATION (Martin): C′ is the RESIDUAL fallback, NOT an excuse to keep the automatic checker
  weak. We still want **maximal completeness in practice** — just not a completeness *proof*. So
  route C (the strong / automata-complete checker) stays IN, as the completeness ENGINE, but its
  completeness is established **by test** (differential vs. a semantic safety oracle over a large
  corpus), not by an F\* theorem. The user oracle handles only what even the strong checker cannot
  decide. Mapping to the assurance grades: soundness = **proved** (G0); completeness = **maximised &
  test-evidenced** (≈G2), not proven; residual = **human-attested** (G3).
- **D. Empirical certificate first (as in W18).** Before proving, exhaustively/randomly search for a
  SOUNDNESS counterexample (a `wellformed` G whose endpoints deadlock) and for completeness gaps
  (safe G that we reject), to learn which theorem is even true and to guide A/B/C.

## 8. Plan (updated)
D (empirical, settles which soundness theorem is true) → A (soundness theorem + a sound semantic
safety check, the must-have) → **C′ for completeness** (user/external as completeness oracle behind the
monitored boundary: re-checkable certificate by default, labelled G3 human attestation as fallback;
deny-by-default; the sound core keeps the safety verdict) → synthesise, integrate (0 admits, bridge
green), update tension/CEP. Soundness is the bar (machine, never delegated); completeness is **maximised
in practice and test-evidenced** (a strong checker — full merge, target the CAV-2023 automata operator
— validated by differential against a semantic safety oracle), NOT proven-complete; the oracle boundary
covers only the residual the strong checker cannot decide. Route C (automata) stays IN as the
completeness ENGINE (by-test), not optional and not a proof obligation.

## Log

### W19-A — progress + recursion-free subject reduction PROVEN (F*, 0 admits)
- Side-findings (both real over-acceptances of `wellformed`, found via the oracle, now fixed): contractive
  recursion (μt.t) [bc97d74] and no self-communication (p→p) [862460e].
- **(Q) global progress** `global_progress` — a well-formed head communication/choice can always take a
  global step (global counterpart of `deadlock_free`).
- **(P) subject reduction** `preservation` — `wellformed g ∧ rec_free g ∧ gstep g e g' ⇒ wellformed g'
  ∧ rec_free g'`, for the RECURSION-FREE fragment (GS_Msg/GS_Ch cases; GS_Rec is vacuous here). Helpers
  `contractive_opts_index`/`no_self_opts_index`/`rec_free_opts_index`.
- **progress invariant** `progress_invariant` — a well-formed recursion-free protocol is `GEnd` or a head
  communication (so progress/deadlock-freedom apply).
⇒ Together with head **fidelity** + `deadlock_free`, this is **machine-checked deadlock-freedom along every
run for the recursion-free fragment** — the soundness bar (criterion 1) met there. **Remaining for full
W19-A:** the `GS_Rec` case, i.e. a substitution-preservation lemma `wellformed (GRec t g0) ⇒ wellformed
(subst_g g0 t (GRec t g0))` (contractive/no_self/projection under substitution) — the fiddly recursion
step, tracked; candidate for the SP-5 loop.

#### Full-soundness (GS_Rec) progress + honest stop
Decomposed `subst_g_wf` into three preservation facts about substitution:
- **(a) no_self under subst — PROVEN** (`no_self_subst`/`no_self_subst_opts`, 0 admits).
- **(b) contractive under subst — OPEN (research-grade).** Needs the bound-set tracking of `contractive_chk`
  to commute with substituting a closed contractive recursion; provable but multi-lemma (closedness +
  "a communication clears the bound set" arguments). Not attempted to completion (risk of an unbounded
  grind).
- **(c) projection under subst — OPEN (the hard one).** Projection must commute with substitution, AND
  that commutation must go through the n-ary **merge** (third-role case) — the classic page-long part of
  MPST mechanizations.
**Honest status:** soundness is PROVEN for the recursion-free fragment (a real theorem); full soundness
with recursion reduces to (b)+(c), which are research-grade and explicitly tracked as the SP-5
LLM-proposes/F\*-decides target. Not faking it: recursion soundness is NOT claimed, only the rec-free
theorem + the `no_self_subst` building block.

### W19-D — empirical certificate + safety oracle built — DONE
Built the **synchronous safety oracle** `src/casl/semantics_sync.py` (formalisation of §2/§3: project to all
roles; explore the reachable synchronous configuration space; verdicts SAFE / DEADLOCK / RECV_ERROR /
DIVERGENT / UNKNOWN). Controls confirm it has teeth (detects a mutual-wait deadlock and a label-mismatch
reception error; accepts a good config) — `tests/test_semantics_sync.py`.

Process honesty: a first oracle version had a **too-eager** reception-error check (fired whenever a
partner's *current* head couldn't take a label, even if the partner was merely busy with another
communication first) → 12 false positives on the corpus. Fixed to fire only **in rendezvous** (the
partner's head is actually receiving from the sender). After the fix:

- **Corpus (412):** all 65 projectable protocols are SAFE — **0 soundness counterexamples.**
- **Random GUARDED fragment (60 000 generated; 39 281 projectable & checked, incl. recursion / choices /
  4 roles):** **0 soundness counterexamples** (projectable ⇒ safe).

⇒ **Soundness (projectable ⇒ safe) holds empirically and robustly.** This strongly suggests the W19-A
soundness theorem is TRUE and provable, and matches classic MPST theory (a *sequential* well-formed
global type projects to a deadlock-free endpoint system).

**Separate minor finding (NOT a mergeability hole):** the only "unsafe-but-projectable" cases were
**non-contractive recursion** (`μt.t` and friends) — silent divergence, not a communication deadlock.
CASL's checker does not currently enforce **guardedness/contractiveness**. That is a cheap, orthogonal
soundness-hardening item (add a contractiveness check; `semantics_sync.contractive` already decides it),
tracked separately from W19's projection/merge core.

**Completeness measurement (next):** a "completeness gap" = a *safe* `G` that CASL *rejects*. Since a
rejected `G` has no projection, the yardstick must be either (i) `G`'s own global synchronous reduction
(deadlock-free at the global level yet not mergeability-projectable), or (ii) the automata-complete
operator (CAV 2023). This is exactly the W19-Completeness engine task.

**Synthesis from D:** soundness is real and provable (→ W19-A, primary). Completeness is to be maximised
by-test against the oracle/global-semantics yardstick (→ W19-Completeness, route C engine), with the
user/oracle (C′) for the residual. Plus a small bonus: a guardedness check closes the non-contractive gap.

### Side-finding CLOSED (bc97d74): contractiveness enforced
`wellformed` (F\*) now includes `contractive` (every μ-variable guarded by a communication since its
binder); mirrored in the TCB bridge + a `casl check` MUST gate. `μt.t` is rejected everywhere. 0 admits,
bridge 412/412. This also gives W19-A a cleaner hypothesis (no silent-divergence corner case).

### W19-A — formalisation, decomposition, routes

**Theorem to prove (global, multi-step soundness):** `wellformed(G)` ⇒ the projected synchronous endpoint
system is SAFE — every configuration reachable from `init_config(G)` is either final (all `LEnd`) or can
take a step (deadlock-free), and no reception error ever occurs.

**Key decomposition (the real insight): the multi-step theorem reduces to two single-level lemmas plus
the head-scoped fidelity we already proved.** With `corr(G, C)` = "C is G's per-role projection":
- **(P) Preservation:** `wellformed G ∧ gstep G e G' ⇒ wellformed G' ∧ corr(G', C')` where `C'` is the
  config after the matching `cstep`. (Projection commutes with reduction.) — the substantive lemma.
- **(Q) Global progress:** `wellformed G ∧ G ≠ GEnd ⇒ ∃ e G'. gstep G e G'`. (A non-final well-formed
  global type can always make a global step.)
- **(F) Fidelity (HAVE, head-scoped):** a global head step ↔ a configuration step.
Then global safety follows by induction over the run: every reachable `C` corresponds to a reachable
well-formed `G'` (by P); if `G' = End`, `C` is final; else `G'` steps (Q) ⇒ `C` steps (F). No stuck
non-final config ⇒ deadlock-free; fidelity-soundness rules out reception errors.

**Extra well-formedness conditions surfaced by (Q)** (the generator/corpus satisfy them implicitly; they
must become explicit conjuncts of `wellformed`, like `contractive` did):
- **non-empty choice** — `GCh p q []` is projectable but cannot step (Q fails); require `opts ≠ []`.
- **no self-communication** — `GMsg p p` / `GCh p p` (need `p ≠ q`, i.e. `head_ok`); require it
  structurally everywhere, not just at the head.
(Each is a tiny `wellformed` tightening + bridge mirror, validated by the oracle.)

**Routes (compare):**
- **A. Subject-reduction + progress (inductive)** — prove (P) and (Q), reuse (F); standard MPST safety,
  aligned with the head lemmas we have. Recursion (`GS_Rec` + a substitution↔projection lemma) is the
  fiddly part. **CHOSEN** (the F\*-provable general theorem).
- **B. Bisimulation global↔config LTS** — elegant but heavy in F\*; (P)+(Q) subsume what it needs.
- **C. Bounded semantic safety (the oracle) as the F\* statement** — not a general theorem (by-test only);
  already have it empirically (39k+). Keep as the cross-check, not the proof.

**Plan for A:** (1) tighten `wellformed` (+ non-empty choice, + no self-comm; bridge mirror; re-verify);
(2) prove (Q) global progress; (3) prove (P) preservation — first for the recursion-free fragment, then
the `GS_Rec`/substitution case; (4) assemble the multi-step safety theorem; (5) cross-check vs the
semantic oracle. Honest expectation: (P) with recursion is the hard step and may take several iterations;
the recursion-free safety theorem is a real partial result if the full one resists.

### W19-Completeness — C′ implemented (the user/external as completeness oracle)
`src/casl/completeness.py` + `tests/test_completeness.py` (4): CASL already uses the maximal STANDARD
syntactic merge (full label-unioning Honda–Yoshida–Carbone), so automatic completeness is maximised; the
residual (what only the automata operator would accept) is recovered behind the monitored boundary:
- `accept_with_certificate(g, endpoints)` — lift a conservative reject iff the user-supplied local-type
  certificate is **safe** (semantics_sync) AND **faithful** to `g` (bisimilar to `g`'s global reduction),
  both re-validated by the trusted oracle ⇒ admit at mode `tested`/G2. No new trust (PCC / SP-5 shape).
- `attest(g, who, rationale)` — human Tier-3 fallback, mode `attested`/G3, disclosed; deny-by-default.
HARD INVARIANT upheld: only a reject can be lifted; the sound core keeps the safety verdict.

## 8b. Full recursion soundness (GS_Rec) — progress log

Extending `preservation` to the recursion (unfolding) step `GRec t g0 --> subst_g g0 t (GRec t g0)`
reduces to `subst_g_wf`: unfolding preserves each well-formedness conjunct. Status:

- **(a′) no-self-communication — PROVEN** (`unfold_no_self`, immediate from `no_self_subst`).
- **(b′) contractiveness — PROVEN** (`unfold_contractive`, 0 admits) for CLOSED protocols. The clean
  formulation: the unfold lemma's precondition is `contractive_chk bnd g` at the SAME running set (not
  `t::bnd`) — a guard (`GMsg`/`GCh`) resets the since-guard set to `[]`, which is exactly where the
  substituted closed recursion must be contractive. Supporting lemmas (all 0 admits): `ctr_mono`
  (smaller running set = weaker), `unfold_ctr`/`unfold_ctr_opts`, `cl`/`cl_opts` (lexical closedness,
  never resets), `ctr_agree` (for a lexically-closed `g`, `contractive_chk` depends on the running set
  only via its `lex` restriction), `rec_all_ctr` (a closed contractive recursion is contractive under
  EVERY running set). Closedness is genuinely needed: an open body could carry a stray free var that
  `forall b. contractive_chk b (GRec t g0)` would otherwise break on. Real protocols are closed, so this
  is the natural side condition (candidate to fold into `wellformed`).
- **(c′) projectability-under-unfolding — OPEN, research-grade (SP-5 goal).** Needs `project` to commute
  with substitution THROUGH the n-ary `merge`. Sharp finding: the standalone merge-commutation equality
  `merge (subst l1) (subst l2) = subst (merge l1 l2)` is **FALSE**. Counter-corner: distinct branch
  projections `l1 = LVar t` and `l2 = LRec t c` are NOT mergeable (`merge l1 l2 = None`), yet both
  collapse to `LRec t c` under `[t := LRec t c]`, so the substituted merge succeeds — the two sides
  disagree. The lemma is only true **intertwined with projection-DEFINEDNESS**: in that very corner
  `project g0 r = None`, so any theorem hypothesising `project g0 r = Some _` is vacuous there. This
  intertwining (prove `project`-commutes-with-`subst` and definedness simultaneously, threading the
  fuel like W18) is what makes it multi-hour; routed to the proof loop, NOT faked. Soundness stays
  machine-held: nothing is admitted, and the recursion-free subject-reduction theorem is untouched.

## 8c. Projectability-under-unfolding (c') — literature review, synthesis, and the reduction

A focused literature pass and an F* proof campaign (artifact: `fstar/W19ProjSubst.fst`, machine-checked
modulo ONE admit) turned the open (c') into a single crisp lemma.

**Concepts extracted from the literature.**
- *Scalas & Yoshida, "Less is More", POPL 2019.* Don't reason by raw syntactic equality; reason in the
  semantic/success world. This reframes our task: for soundness we need projection-DEFINEDNESS to be
  preserved, i.e. only the EASY direction `merge l1 l2 = Some m ⟹ merge (subst l1)(subst l2) = Some (subst m)`.
  The earlier "the merge-subst equality is FALSE" obstruction (the `LVar t`/`LRec t c` collapse) lives
  entirely in the failure world (`merge = None`) and is excluded once we hypothesise success.
- *Tirore, Bengtson & Carbone, "A Sound and Complete Projection for Global Types", ITP 2023 / JAR 2025.*
  Define projection coinductively over the infinite unfolding tree; a computable function is proved
  sound+complete to it. Under this view unfolding is definitionally transparent, so (c') is almost free —
  at the cost of re-basing projection on a coinductive relation (a larger redesign). Our fallback.
- *Scalas et al., "Iso-Recursive Multiparty Sessions", arXiv 2501.17778.* Make `μX.T` and its unfolding
  isomorphic-not-equal (finite), and compute deadlock-freedom semantically on the environment LTS — no
  syntactic projection/substitution lemma at all. Matches CASL's existing semantic safety oracle.

**Synthesised proof (Strategy A), tested in F* — all of it verifies except one lemma:**
`subst_l` (local-type substitution) → `opts_of_subst`, `assoc_subst`, `replace_subst` (helper
commutations) → `merge_subst`/`merge_opts_subst` (success-world merge/subst commutation) →
`merge_wrap_subst` (lift to the fuel-wrapper via `lsize_subst_ge` + `merge_f_mono_le`) →
`merge_all_subst` (the n-ary fold) → `proj_subst`/`proj_opts_subst` (projection commutes with subst)
→ `unfold_projectable` (`Some? (project (GRec t g0) r) ⟹ Some? (project (subst_g g0 t (GRec t g0)) r)`).
The keystone `subst_inj` (substitution is injective on the success world — distinct mergeable types
never collapse, because a collapse forces a sub-merge of `LVar` against a non-variable = `None`) is
proven at the continuation level; it rules out `merge_f`'s `l1 = l2` short-circuit firing spuriously
on substituted arguments.

**`subst_opts_inj` is now PROVEN (zero admits).** Substitution-injectivity of the n-ary merge at the
OPTIONS level: `merge_opts_f n o1 o2 = Some o ⟹ (subst o1 = subst o2 ⟹ o1 = o2)`. The breakthrough was
NOT to follow `merge_opts_f`'s accumulator-rewriting recursion (prepend/`replace_lbl`) — which defeats
list-position induction — but to characterise it via `merge_opts_lookup`: stated about ASSOC LOOKUPS,
`merge_opts_f n acc o2 = Some o` determines `assoc a o` from `assoc a acc` / `assoc a o2`, and where
both are present the conts were merged (a `merge_f` witness exists). Assoc lookups transform
predictably under prepend (`(b,_)::acc`) and `replace_lbl`, so THIS induction generalises over the
rewritten accumulator. From it: for subst-equal lists (same label sequence), every shared label yields
a merge witness ⟹ cont-level `subst_inj` ⟹ equal conts ⟹ `o1 = o2`. The keystone `subst_inj` /
`subst_opts_inj` are mutually recursive on a lexicographic TYPE-SIZE measure (fuel cannot decrease
across the cross-calls; the merge witness is taken existentially, any sufficient fuel by monotonicity).
Distinct branch labels (`nodup`/`ldistinct`/`gdistinct`) is the natural side condition — true of every
real protocol, and proven preserved by both merge (`merge_ldistinct`) and projection
(`project_ldistinct`). Tirore et al.'s coinductive route and the iso-recursive route were the
documented fallbacks; not needed.

**Net (v0.27.0): FULL recursion soundness is now in the proven core.** The (c′) lemmas were ported into
`CASL.fst`; `gdistinct` (distinct branch labels) + `closed` (no free type vars) were added to
`wellformed`; `subst_g_wf` assembles (a′)no-self + (b′)contractive + gdistinct + closed + (c′)projectable;
and `preservation_full` is full subject reduction over GS_Msg/GS_Ch/GS_Rec. Mirrored in the TCB bridge
(`projectable`, 412/412) and the `casl check` MUST-gate. Core 0 admits. `fstar/W19ProjSubst.fst` remains
as the standalone exposition of (c′).

## 9. Synthesis — the W19 "satisfying solution" (status)
- **Soundness (the bar):** PROVEN for the recursion-free fragment (`global_progress` + `preservation` +
  `progress_invariant`, with head fidelity + `deadlock_free`); two real over-acceptances (`μt.t`, `p→p`)
  found + closed; the recursion case reduces to `subst_g_wf` — (a′) no-self + (b′) contractive PROVEN
  (§8b, 0 admits, for closed protocols), (c′) projection-under-subst OPEN/research-grade (SP-5; the
  merge-commutation is only true intertwined with projection-definedness — see §8b). Soundness is
  machine-held throughout; never delegated.
- **Completeness:** maximised automatically (full syntactic merge), and the residual is recovered on
  demand via the C′ oracle boundary — re-checkable certificate (no new trust, up to G2) or labelled G3
  attestation — never proven-complete, by design.
- **Three assurance grades realised:** soundness = proved (G0), completeness = maximised + test/cert
  (≈G2), residual = human-attested (G3). The empirical safety oracle cross-checks all of it.

## References
- Scalas & Yoshida, *Less is More: MPST Revisited*, POPL 2019 — https://www.doc.ic.ac.uk/research/technicalreports/2018/DTRS18-6.pdf
- Li, Stutz, Wies, Zufferey, *Complete MST Projection with Automata*, CAV 2023 — https://cs.nyu.edu/~wies/publ/cav23_mst.pdf
- Majumdar, Mukund, Stutz, Zufferey, *Generalising Projection in Asynchronous MST*, CONCUR 2021.
- Honda, Yoshida, Carbone, *Multiparty Asynchronous Session Types* (full merge), JACM 2016.
