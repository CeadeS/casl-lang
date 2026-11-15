# Verification-mode-as-type, proof-faithfulness, and TCB unification — design synthesis (C & D)

**Date:** 2026-06-18
**Method:** fan-out web research (5 angles, ~50 sources, adversarial extraction), synthesized against the CASL core.
**Scope:** resolves the open problems **C** (TCB unification — the running Python checker is not the proven F\* artifact) and **D** (remaining F\* proof obligations: merge fuel-sufficiency; projection/merge completeness), and turns Martin's "verification-mode-as-a-type" idea into a concrete construct.

---

## 0. Framing (the Torvalds point)

If AI is the new compiler, correctness moves out of hand-written code into the **validating layer** — and that layer must itself be trustworthy. CASL *is* that layer. C and D are about the layer's own floor: the verdict-giving core. The prior pipeline report validated the orchestration that sits *on* the verifier; this note is about the verifier itself.

Martin's proposal: make *the kind of verification a call requires* a first-class construct — e.g. `human-verified`, `LLM-proposed + human-confirmed`, or `proof-required` (an LLM may supply the proof). And the sharp follow-up: when a proof is supplied, **how do we know it proves the requirement and not something vacuous?** — which seems to need LLM-pre + human-post again. The research says: the construct is exactly right and has strong prior art; and there *is* a better way than pure human review for the faithfulness question — front it with mechanical anti-vacuity checks so the human reviews a smaller, sharper residual.

---

## 1. What the research establishes

**Verification-mode-as-a-type is established prior art.** Mature systems already record, per term, whether an obligation is *machine-discharged* or *trusted/assumed*, as a checkable, named token: F\* `Lemma`/`Tot` (proof required) vs `assume`/`assume val` (axiom) [1]; Coq proof body vs `Axiom`/`Admitted` (surfaced by `Print Assumptions`); Lean a real proof term vs `sorry`/`axiom`, with **`#print axioms` making the trusted set machine-queryable per theorem** [2]; Dafny **refuses to compile** a bare `assume` unless annotated `{:axiom}` — a hard build gate distinguishing proved from trusted [3]. Effect lattices / graded monads classify the assurance regime of a term in its type [1]. Proof-carrying code transmits the obligation *and* its machine-checkable discharge, validated by a small trusted checker [4].

**The proof-faithfulness gap is real, central, and has no algorithmic closure.** A machine-checked proof guarantees only that the code meets the *written* spec, never that the spec matches *intent*; the spec is the unverified trust anchor. Concretely: vacuous truth (a property holding for a trivial reason, e.g. an unsatisfiable antecedent) is a classic failure, detectable by mutating a subformula and requiring an "interesting witness" [5]. **IronSpec found ten genuine specification bugs across six already-*verified* real-world systems** — spec bugs that survived into deployed verified code and were caught only by spec-level testing [6]. MutDafny shows mutation testing finds specs that verify but fail to detect injected implementation faults (≈1 weak spec per 241 LOC) [7]. LLM-generated Dafny specs collapse to near-zero on compositional tasks, dominant failure "specification fragility" — verifies locally, doesn't constrain behavior [8]. Lahiri: there is "no algorithmic way of ensuring the correctness of user-intent formalization," so judge generated specs by *soundness* (don't reject valid impls) and *completeness* (do reject wrong ones) [9]. Clover reframes this as **consistency-triangulation** among code, NL docstring, and formal spec (87% accept of correct, 100% reject of incorrect on its bench — approximate, not a guarantee) [10].

**LLM-proposes / kernel-decides is the validated robust pattern.** LLM as untrusted proposer inside a search whose every step the proof engine adjudicates: COPRA [11], Draft-Sketch-Prove (39.9% miniF2F via Sledgehammer-filled sketches) [12], DeepSeek-Prover-V2 (up to 88.9% miniF2F-test) — in every case the LLM proposes, the trusted checker decides. The kernel never grows: in Lean, arbitrarily complex tactics "do not need to be trusted at all" because they must emit a kernel-checkable term [2]. **But F\* does *not* satisfy the de Bruijn criterion**: it discharges goals by encoding to SMT and asking Z3, builds no independent proof term, so "F\* implicitly trusts its encoding to SMT logic and the correctness of Z3" — Z3 + the encoding are in the TCB [13]. Kernel/soundness bugs are real and recurring (Coq tracks ≈one critical bug/year) [14], and verifying the kernel itself (Lean4Lean) has found genuine kernel bugs [15].

**Differential testing is evidence, not proof; a refinement proof is the upgrade.** "Testing shows the presence, never the absence, of bugs" (Dijkstra); differential testing is additionally blind to bugs *shared* by all implementations compared [16]. Csmith found ~120 compiler bugs by differential testing but **none in CompCert's verified middle-end** — illustrating proof > testing [17]. The qualitative upgrade is a machine-checked **refinement** of the running implementation against the spec model (seL4 [18], Cogent emits a per-compilation refinement proof [19]). But every such path *relocates* trust: extraction/compilation joins the TCB unless itself verified — Coq's standard extraction is trusted and even inserts `Obj.magic` [20]; MetaCoq/CertiCoq give a *verified* erasure [21]; CompCert proves source→asm behavior preservation but its TCB still includes Coq, extraction, and the C front end [22]; F\*'s Low\*→C via KaRaMeL is proven trace-preserving to Clight [23]; translation validation verifies each run instead of the compiler once [24]; PCC shrinks the consumer's trust to a small validator [4].

**Human sign-off is the irreducible root — and automation bias makes it fragile.** Verification bottoms out in a TCB the system cannot verify about itself ("the integrity of lower layers is treated as axiomatic by higher layers"; seL4 holds "assuming the proof is free from error") [25]. The EU AI Act Art. 14 makes human *override* a binding requirement and explicitly names automation bias as a risk to counter [26]; automation bias is empirically documented (humans rubber-stamp aided decisions) [27]; an LLM is a biased accept-authority (self-preference [28], position bias across ~150k instances [29]) — hence restrictive-only, cross-model, fail-closed. ISO/IEC/IEEE 15026-3 / DO-178C codify *tiered* assurance: criticality determines required evidence strength [30].

---

## 2. The construct: verification-mode as a first-class, auditable field

Synthesizing Martin's idea with the prior art [1][2][3], CASL should make the **assurance mode** of every call/node a first-class, machine-queryable token — which CASL already half-has via the G0–G3 grades and `oracle`/`verified` markers. The refinement:

| Mode | Meaning | Discharged by | Grade |
|---|---|---|---|
| `proved` | obligation is a real F\* proof | F\* (+Z3) | G0 |
| `bounded` | safe up to a model-checked bound | bounded checker | G1 |
| `tested` | property/conformance evidence | test corpus | G2 |
| `attested` | human Tier-3 sign-off (LLM may pre-screen) | human | G3 |
| `assumed` | explicitly trusted axiom | nothing — trusted | (counts against budget) |

Two mechanisms from the research make this enforceable rather than decorative:

1. **An auditable trust budget** (Dafny `{:axiom}` gate [3] + Lean `#print axioms` [2]): the audit reports, per accepted artifact, exactly which `assumed`/axiom tokens it depends on, and the profile caps it deny-by-default — **`core` admits zero assumptions beyond the kernel**. This is "the assurance mode is machine-queryable and budgeted," directly mirroring `#print axioms`.
2. **A `proof-required` call mode**: a node may *demand* that a supplier (LLM or human) furnish an F\* obligation, and the node does not gate-pass until F\* discharges it — the PCC pattern [4] at the CASL surface.

---

## 3. The "better way" for proof-faithfulness (the heart of Martin's worry)

The literature is unanimous that proof↔intent has **no algorithmic guarantee** [9][25] — so the root is human attestation. But pure "LLM-pre + human-post" wastes the human on failures that mechanical proxies catch. Insert a **mechanical anti-vacuity front-line** before the human, so the human attests only the irreducible residual (statement ↔ intent):

1. **Mandatory non-vacuity / witness** per `proved` obligation [5] — CASL already does this ad hoc (`_ex_*`, `_conserv_demo`); make it a *gate*: a proof whose preconditions are unsatisfiable, or that has no firing witness, **fails**.
2. **Spec mutation testing** [6][7]: mutate the implementation; the spec must *reject* the mutant. A spec that still passes is too weak → fail.
3. **Consistency triangulation** [10]: the requirement (NL), the formal statement, and the witness must agree; back-translation of the formal statement to NL is a SHOULD-level cross-check.
4. **Human Tier-3 attestation** of the residual only — disclosed, specific, reviewable, cross-model-screened, never an LLM accept [26][28][29].

This is strictly stronger than LLM-pre + human-post: steps 1–3 mechanically kill the documented common failure modes (vacuity, weak spec, mis-formalization) *before* the human, who then faces a small, sharp question. It cannot reach a *guarantee* — every proxy compares the spec to another unverified artifact — but it minimizes and surfaces the residual trust, which is exactly the CASL ethos.

---

## 4. Problem C — TCB unification (candidates compared)

| Candidate | Trust removed | Resulting TCB | Effort | Stays human-attested |
|---|---|---|---|---|
| **C1 — extraction-as-authoritative** (extract the F\* core `project/merge/wellformed` to OCaml; make it THE checker; Python becomes an untrusted client) | the **parallel Python reimplementation** leaves the TCB entirely | F\* typechecker + Z3 + F\* extraction (trusted) + OCaml | medium (F\* already extracts; reroute the CLI's core judgment) | the F\* spec matches the requirements |
| C2 — strengthen the differential bridge (more protocols, property-based) | little — evidence not proof; blind to shared bugs [16][17] | unchanged (Python still authoritative) | low | everything the bridge doesn't cover |
| C3 — prove the Python checker ≡ F\* spec | strong in principle | would need a formal semantics of Python | very high / impractical | — |

**Recommendation C = C1**, with C2 retained *only* as a regression guard (not the trust story), and an honest TCB statement. Per the scope-honesty finding [9][30], unify **only the core judgment**, not the whole CLI. Note the irreducible: F\* extraction is itself trusted [20] and Z3 stays in the TCB [13]; a later TCB-shrink is Low\*/KaRaMeL (proven trace-preserving [23]) or MetaCoq-style verified erasure [21] — flagged, not required now.

---

## 5. Problem D — discharging the F\* obligations (candidates compared)

| Obligation | Candidate | Approach | Risk |
|---|---|---|---|
| **D1 fuel-sufficiency** (merge terminates *and* a size-based fuel never spuriously hits 0 on mergeable inputs — currently safe-direction-only, `W18`) | **direct F\* proof** | prove `lsize l1 + lsize l2 + 1` fuel suffices: a structural decreasing-measure lemma | low–medium — finite structural argument, likely closable directly |
| **D2 merge/projection completeness** (à la Scalas–Yoshida, `W19`) | **LLM-assisted proof loop, F\* fail-closed gate** | LLM proposes lemmas/scripts (COPRA/DSP pattern [11][12]); F\* decides; 4/δ bounds the search loop | medium–high — may be genuinely hard/partly open; keep `bounded`/documented if not closable |

**Recommendation D:** attempt **D1 directly** first (it is a self-contained termination/sufficiency argument, not Scalas–Yoshida-hard). Use the **LLM-proposes / F\*-decides** loop [11][12] for D2 and for any D1 residual — the LLM never accepts, F\* (and a human for the *statement*) does. Honest caveat: F\*'s "proof" is Z3-discharged, not kernel-checked [13]; that is the same TCB as the rest of the core, so D adds no new trust. If D2 resists, it stays an explicitly tracked bounded result — surfacing the gap, per ethos.

---

## 6. Synthesized starting points (for actual implementation)

**SP-1 (construct, enables everything).** Add the assurance-mode token + auditable **trust budget** to the level model: extend `levels.py`/`profiles.py` so every node carries a mode (`proved`/`bounded`/`tested`/`attested`/`assumed`), the audit reports the per-verdict axiom/assumption set (à la `#print axioms` [2]), and the profile caps it deny-by-default (`core` = 0 assumptions). Pure governance + Python; no F\* change. *First, smallest, unblocks SP-4.*

**SP-2 (C1).** Route the CLI's **core judgment** through the OCaml extracted from `fstar/CASL.fst` (the `tcb_bridge`/`driver.ml` extraction path already exists). The Python `project/merge/wellformed` becomes a non-trusted convenience wrapper that defers to the extracted checker; the differential bridge is demoted to a regression test. Land with an updated honest TCB statement in CEP-0004 and a new CEP for "extracted-checker-authoritative."

**SP-3 (D1).** Prove merge fuel-sufficiency directly in F\* (decreasing measure on `lsize`), removing the safe-direction-only caveat `W18`. Self-contained; do before D2.

**SP-4 (faithfulness front-line).** Implement the anti-vacuity gate: mandatory witness per `proved` obligation [5], spec **mutation testing** [6][7], and consistency triangulation [10], with the human Tier-3 attestation reduced to the residual. Wire into the audit. Depends on SP-1.

**SP-5 (D2, last).** Stand up the LLM-proposes / F\*-decides proof loop [11][12] (reuse CASL's Tier-2 cross-model, fail-closed machinery) and aim it at completeness; if unclosable, record as a bounded result. Largest effort, do last.

**Recommended order:** SP-1 → SP-3 → SP-2 → SP-4 → SP-5. (SP-1/SP-3 are low-risk and unblock the rest; SP-2 is the big trust win; SP-4 closes the faithfulness worry; SP-5 is the open-ended research item.)

---

## 7. Irreducible roots (stated honestly)

No path removes all trust [25]. After all of the above, the residual is: (a) the F\* typechecker + Z3 + extraction [13][20]; (b) that the F\* **statements** match the **requirements** — human-attested, now front-lined by mechanical anti-vacuity [5][6][10] but never algorithmically closed [9]; (c) the human attestor (automation bias [27], mitigated by restrictive-only, disclosed, cross-model review [26]). Surfacing these *is* the safeguard.

---

## References

[1] Dijkstra Monads for All — https://arxiv.org/pdf/1903.01237 · [2] Lean, Validating Proofs / `#print axioms`; Lean trust model — https://lean-lang.org/doc/reference/latest/ValidatingProofs/ , https://ammkrn.github.io/type_checking_in_lean4/trust/trust.html · [3] Dafny Reference (`assume`/`{:axiom}`) — https://dafny.org/dafny/DafnyRef/DafnyRef · [4] Proof-Carrying Code (Necula–Lee) — https://people.eecs.berkeley.edu/~necula/pcc.html · [5] Beer et al., Efficient Detection of Vacuity — https://www.cs.toronto.edu/~chechik/courses05/csc2108/beer01.pdf · [6] IronSpec (OSDI'24) — https://www.usenix.org/conference/osdi24/presentation/goldweber · [7] MutDafny — https://arxiv.org/abs/2511.15403 · [8] DafnyCOMP — https://arxiv.org/abs/2509.23061 · [9] Lahiri, User-Intent Formalization — https://arxiv.org/abs/2406.09757 · [10] Clover — https://arxiv.org/abs/2310.17807 · [11] COPRA — https://arxiv.org/html/2310.04353 · [12] Draft-Sketch-Prove — https://arxiv.org/pdf/2210.12283 ; LeanDojo/ReProver — https://arxiv.org/pdf/2306.15626 · [13] F\* trusts Z3/SMT — https://fstar-lang.org/tutorial/book/part1/part1_prop_assertions.html · [14] Coq critical bugs — https://github.com/coq/coq/blob/master/dev/doc/critical-bugs.md · [15] Lean4Lean — https://arxiv.org/abs/2403.14064 · [16] differential testing is blind to shared bugs — https://arxiv.org/html/2504.04321v1 ; Dijkstra — https://en.wikiquote.org/wiki/Edsger_W._Dijkstra · [17] Csmith (PLDI'11) — https://users.cs.utah.edu/~regehr/papers/pldi11-preprint.pdf · [18] seL4 — https://cacm.acm.org/research/sel4-formal-verification-of-an-operating-system-kernel/ · [19] Cogent — https://arxiv.org/pdf/2112.05964 · [20] Coq extraction is trusted / `Obj.magic` — https://arxiv.org/pdf/2012.09138 · [21] MetaCoq verified erasure — https://dl.acm.org/doi/10.1145/3656379 · [22] CompCert manual; TCB — https://compcert.org/man/manual001.html , https://arxiv.org/pdf/2201.10280 · [23] F\* Low\*/KaRaMeL — https://fstarlang.github.io/lowstar/html/Introduction.html · [24] Translation validation (Pnueli) — https://link.springer.com/chapter/10.1007/BFb0054170 · [25] Trusted computing base / seL4 axioms — https://en.wikipedia.org/wiki/Trusted_computing_base · [26] EU AI Act Art. 14 — https://artificialintelligenceact.eu/article/14/ · [27] Automation bias review — https://pmc.ncbi.nlm.nih.gov/articles/PMC3240751/ · [28] Self-preference bias — https://arxiv.org/abs/2410.21819 · [29] Position bias (~150k instances) — https://arxiv.org/abs/2406.07791 · [30] ISO/IEC/IEEE 15026-3 — https://www.iso.org/standard/84444.html ; DO-178C DAL — https://arxiv.org/pdf/2511.14215
