# A1 — Forwarding fidelity: lifting the forwarding re-base from G2 to a proof (G0)

**Date:** 2026-06-25 · **Status:** realized (CERT-FID proved; grade path + runtime enforcement shipped).
**Code:** `fstar/Forwarding.fst` (the F\* lemma, 0 admits), `src/casl/grade_flow.py`
(`cert_fid_verified`, G0 grant), `src/casl/run.py` (interpreter-enforced forwarding), `scripts/check_admits.sh`
(non-vacuity gate extended), `tests/test_forwarding_fidelity.py`, `tests/test_grade_flow.py`.
**Predecessors:** `docs/analyses/data-lineage.md` (A1/A2 split), `docs/analyses/grade-rebase.md` (Model-C),
`proposals/cep-0070-grade-per-flow-path.md`.

This closes the headline item of the research frontier left open after the data-lineage work: turning the
**capped G2** forwarding re-base into a **proof-backed G0**. It follows the project method — research with
references → formalize → competing designs → rate → synthesize → red-team → verify → implement.

---

## 1. The exact gap (what G0 needs that G2 did not)

A2 (shipped) grants **G2** to a site `S` whose payload field is *forwarded* from a `verified` boundary `B`
(`S.f = B.f`) when `B`'s proved contract SMT-entails `S`'s. The cap was **G2**, with the honest reason: the
"lineage" was a *structural* forwarding read off the surface syntax, sound only under CASL's standing
**spec-conformance assumption** — nothing *proved* that a forwarded value is actually delivered unchanged,
and nothing in the runtime *enforced* it. The frontier question:

> What licenses raising that site to **G0** (proved), and what exactly remains assumed?

The answer requires three things to become *proofs* rather than assumptions: (i) **value identity** — the
forwarded value really is the source's, preserved by the reduction; (ii) **property transfer** — that
identity carries the source's proved contract to the destination; (iii) **runtime realization** — the
running interpreter honors the forward rather than letting an independent (oracle) value stand in.

---

## 2. Research synthesis (with references)

Three literature threads were run and adversarially cross-checked. Full briefs distilled here; see the
consolidated references in §9.

### 2.1 Provenance — identity transfers *for free*; transform does not

The database-provenance literature draws the decisive line. **Where-provenance** (a value *copied* from a
source) is *defined* so the source and copied values are **equal**: "all the values that reside in the
source locations of the where-provenance of `l` are equal to the value that resides at `l`"
(Cheney, Chiticariu & Tan 2009; Buneman, Khanna & Tan 2001). Value-equality transports *any* value-predicate
verbatim — so for **identity forwarding** the source's proved refinement holds of the destination with **no
new obligation** (in Liquid-Types terms, the reflexive VC `p ⇒ p`). By contrast **how-provenance**
(a *computed* value) is a semiring polynomial over the inputs (Green, Karvounarakis & Tannen 2007): the
output is a different object, and a predicate transfers only by discharging a function-specific obligation
`(φ_src ∧ sem(f)) ⇒ φ_dst` that references `f`'s **actual semantics**, not a tag (Liquid Types — Rondon,
Kawaguchi & Jhala 2008; Refinement Reflection — Vazou et al. 2018). Provenance is the same machinery as
dependency/information-flow analysis (Cheney, Ahmed & Acar 2007), and dynamic taint is structurally
*incomplete* (undertainting via implicit flows, path-coverage bound — Schwartz, Avgerinos & Brumley 2010;
DTA++ — Kang et al. 2011), so a **static, all-runs forwarding** guarantee strictly beats per-run lineage.

**Consequence for A1:** scope the proof to **identity forwarding** (`S.f = B.f`, verbatim). That is exactly
the case that transfers a refinement *by value-equality*, and exactly the case dynamic taint cannot match.

### 2.2 MPST / F\* — the fidelity lemma is *light*

No mainstream MPST result proves *value identity* across hops; every subject-reduction / session-fidelity
theorem is **type-preservation** or **predicate-preservation** (Honda, Yoshida & Carbone 2016 — the value
**substitution lemma** `Γ,x:S ⊢ P ∧ Γ ⊢ v:S ⟹ Γ ⊢ P{v/x}`; Scalas & Yoshida 2019; the refinement-MPST line
Zhou, Ferreira, Hu, Neykova & Yoshida 2020 and Toninho & Yoshida 2016 carry a *predicate* forward, never the
identity of a value). So a forwarding-fidelity lemma is a **genuine new statement** — but a cheap one:
value forwarding is the **easy, non-linear** case of session-type metatheory. It is a **first-order equality
invariant over the reduction relation**, provable by the same induction as subject reduction — explicitly
**not** a logical relation (overkill — POPLMark Reloaded) and **not** delegation/linearity (delegation
repeatedly broke SR and needs ownership transfer; a base value is non-linear, copyable, and its preservation
is the routine reduction case — confirmed in the ECOOP 2025 mechanisation, Tirore, Bengtson & Carbone).
**Gotchas, in severity order:** asynchrony (queues) — avoided by a synchronous model; recursion — re-examine
unfolding (ITP 2025 found a recursive structural rule that broke SR); choice — fidelity must hold *per
branch* with a vacuity guard; "unchanged" must be defined precisely (identity vs transform).

### 2.3 IFC endorsement + secure compilation — the soundness conditions and the *cap*

Raising an integrity grade is an **endorsement** (the integrity-dual of declassification). It is sound iff
(Askarov & Myers 2010; Myers, Sabelfeld & Zdancewic 2006; Zdancewic & Myers 2001): **(1)** the endorsed
value is not derived from data weaker than the target grade (no adversary-controlled transform on the path),
and **(2)** the *endorsement decision* itself rests only on high-integrity data — their type system rejects
`t := u` and `if (u1) then t := endorse(u2)` precisely because the decision `u1` is attacker-controlled. Plus
Sabelfeld & Sands' **non-occlusion**: the endorsement must not become a laundering side channel. Finally,
the achievable grade is **capped by the enforcement mechanism**:

> `rebased_grade ≤ min( boundary_grade, enforcer_assurance )`

This is not one named theorem but a robust synthesis: a *runtime monitor* sees one trace and cannot soundly
decide a 2-safety hyperproperty (Finkbeiner et al., monitoring hyperproperties), so a monitored enforcer caps
at G2; a human signature discharges nothing mechanically (G3); only a **static machine-checked** discharge of
(1)+(2) reaches the top. Transferring the calculus proof to the running interpreter is a **robust-compilation**
obligation — target **Robust Safety Preservation** (Abate et al. 2019), the cheapest rung (back-translation of
finite prefixes); full abstraction (Patrignani, Ahmed & Clarke 2019) suffices but is stronger than needed.
Session-typed IFC with a monitored semantics and typed declassification is the closest precedent
(Capecchi, Castellani & Dezani-Ciancaglini 2010/2016), with the warning that *leaks hide in the control
constructs* (branch/route), so the routing decision must be high-integrity too.

**Consequence for A1:** CASL satisfies (1)+(2) **by construction** — the forward edge, the `verified` marker,
and the entailment all come from the *parsed protocol* and the *proof*, never from oracle data. So the
endorsement decision is adversary-independent. The cap then says: prove fidelity statically and the *calculus*
grade is G0; the *running* grade is bounded by how faithfully the interpreter realizes forwarding — which is
the **same calculus↔runtime TCB gap** (H1/W11) the whole proven core already carries, not a new blocker.

---

## 3. Formalization

**Payload layer.** A *slot* is a payload field of a site (each a fresh MPST binding ⇒ **write-once / SSA**).
A *store* maps slots to optional values (the contract-DSL integer domain). Reduction events:
`Produce d v` (an ordinary/oracle production `d := v`) and `Forward d src` (`d := store[src]`, the carried
value). `wf bound es` requires every produced slot **fresh** and every `Forward`'s source **already bound**.

**Forwarding fidelity (CERT-FID).** For a `wf` run from the empty store that contains `Forward d src`:
> `run` delivers `Some? (store src)` and `store d == store src` — the destination holds the source's value.

**Re-base soundness (the licence).** With `entails φ_src φ_dst ≜ ∀v. φ_src v ⇒ φ_dst v`:
> `wf` ∧ contains `Forward d src` ∧ `entails φ_src φ_dst` ∧ `φ_src (store src)`  ⟹  `φ_dst (store d)`.

i.e. **identity forwarding + entailment ⇒ the destination satisfies its contract by proof.** This is the
where-provenance "free transfer" made machine-checked: no monitor re-checks `φ_dst`.

**Obligation ledger for a G0 forwarding re-base** (what must be discharged, and how):

| # | obligation | discharged by | residual |
|---|---|---|---|
| O1 | value identity `S.f = B.f` preserved by reduction | **CERT-FID** (`fstar/Forwarding.fst`, F\* 0 admits) | — |
| O2 | property transfer (identity + entailment ⇒ φ_dst) | **CERT-FID** `rebase_sound` + SMT `_entails` (z3) | decidable contract DSL only |
| O3 | endorsement decision adversary-independent | structural: edge + `verified` + entailment come from the parsed protocol, never oracle data | — |
| O4 | runtime realizes the forward | **interpreter-enforced forwarding** (`run.py`): source must be produced upstream; edge honored | calculus↔runtime TCB (H1/W11), shared with the whole core |

O1–O3 are now **proofs**; O4 is enforced by the runner and bounded by the *standing* TCB-unity item — so a
forwarded+entailed site is graded **G0 with the same caveat the rest of the F\*-proved core carries**.

---

## 4. Competing designs

- **D1 — extend the core IR (`CASL.fst`) with payload values + a fidelity lemma in-core.** Strongest
  coupling. *Rejected:* `GMsg` is field-blind by design; adding values perturbs the 0-admits metatheorems and
  the field-blind differential bridge — high cost, high regression risk, against the "small proven hull" rule.
- **D2 — companion F\* module modelling the payload layer + fidelity/`rebase_sound`; checker gates the grade
  on the proof.** Self-contained (mirrors `W19ProjSubst.fst`), core untouched, bridge untouched. *Chosen.*
- **D3 — dynamic provenance / taint at runtime only.** Per-run, no static guarantee; structurally incomplete
  (implicit flows; path coverage). *Rejected as the G0 vehicle* (kept as a complementary observability idea).
- **D4 — human-attested lineage.** A signature → G3, never G0; rubber-stamp risk. *Rejected* (it is the
  existing honest stopgap, already available).

**Rating** (5 = best):

| criterion | D1 in-core | **D2 companion (chosen)** | D3 dynamic | D4 attested |
|---|---|---|---|---|
| soundness of G0 | 5 | **5** | 2 (per-run) | 1 (G3 only) |
| proven-hull untouched | 1 | **5** | 5 | 5 |
| coverage (all runs) | 5 | **5** | 2 | 5 |
| mechanization cost | 1 | **4** | 5 | 5 |
| fit with onion model / R-H1 | 2 | **5** | 4 | 3 |
| honesty about residual | 3 | **5** | 3 | 4 |

---

## 5. Synthesized design (D2)

1. **CERT-FID** — `fstar/Forwarding.fst`: the write-once payload model, `fidelity`/`fidelity_gen` (value
   identity preserved by reduction), and `rebase_sound` (identity + entailment ⇒ φ_dst by proof). Verifies at
   **0 admits**; the admits gate (`scripts/check_admits.sh`) now scans it too, so a future weakening cannot
   pass silently. `CASL.fst` is untouched.
2. **Grade gate** — `grade_flow.cert_fid_verified()` checks the module is present and hole-free (same
   non-vacuity test as the core). `applied_rebases` grants `_rebase_grade()` = **G0 when CERT-FID is proved,
   else G2** (the conservative A2 cap). The three structural conditions (forward edge, `verified` source, SMT
   entailment) are unchanged — they discharge O3 by reading only the parsed protocol.
3. **Interpreter-enforced forwarding** — `run.py` maintains the produced-field set; a forwarded field's
   source must be produced upstream (the runtime analogue of `wf`), the edge is **honored** and recorded, and
   an unbound source aborts the run (`forward_violation`). This discharges O4 to the level of the running
   toolchain (residual = the standing TCB-unity item).

**Grade outcome:** a forwarded+entailed site from a `verified` boundary is **G0** (`casl flow` reports the A1
re-base), advisory as before (the obligation gate and the global weakest-link headline are untouched). Absent
the certificate, the same site stays **G2** — never over-claims.

---

## 6. Red-team / iteration

- **Entailment without a forward edge.** Stays a *candidate*, never applied — proven by the model's
  `no_transfer_without_forward` (two runs differing only in a `Produce`d value give different destination
  values, so no transfer is derivable). Guards against name-based laundering (the original Model-C finding).
- **Oracle-in-the-middle.** A re-base only fires when the *source* is a `verified` boundary; an oracle source
  is never the lineage root, so O3 (adversary-independence) holds. The runtime additionally refuses to let an
  oracle value stand in for a forwarded field (it is bound from the source).
- **Choice / branching.** Fidelity is stated over the linear event list of an executed path; the runtime
  produced-set is path-local, so a forward is honored only on a branch where its source actually executed —
  no cross-branch vacuity. (The grade view over the parsed protocol remains the conservative weakest-floor.)
- **Recursion.** Write-once/SSA means a slot is produced once; the stability lemma shows a bound slot's value
  never changes under later steps, so re-entry cannot silently rebind a forwarded source. (The grade view does
  not raise across a loop back-edge.)
- **Transitivity (d ← s1 ← s0).** The runtime produced-set and the F\* model already support chains (a
  forwarded field becomes produced and may be forwarded again; `==` composes). The *grade* gate still checks a
  **1-hop** verified source, so transitive G0 is a small, sound follow-up increment (left as frontier).
- **Transform forwarding (`S.x = f(B.y)`).** Deliberately **out of scope** for G0: it is how-provenance and
  needs the function-specific obligation `(φ_src ∧ sem(f)) ⇒ φ_dst` (Liquid Types / Refinement Reflection).
  Surfaced as the next frontier; never silently granted.

---

## 7. What shipped (verification)

- `fstar/Forwarding.fst` — **`fstar.exe Forwarding.fst` → "All verification conditions discharged
  successfully", RC=0, 0 admits** (F\* 2026.03.24, Z3 4.16.0).
- `scripts/check_admits.sh` — extended to scan `CASL.fst` **and** `Forwarding.fst` (0 holes).
- `grade_flow.py` — `cert_fid_verified`, `_rebase_grade`, G0 grant in `applied_rebases`, A1 report text.
- `run.py` — `_forward_step` interpreter-enforced forwarding; `RunResult.forwards`; `forward_violation`.
- Tests — `test_forwarding_fidelity.py` (cert gate + runtime honor/violation), `test_grade_flow.py`
  (G0 with CERT-FID; G2 fallback without). Full suite **green**; living audit **green**.

---

## 8. Limitations (honest)

- **G0 carries the standing calculus↔runtime caveat (H1/W11).** CERT-FID proves the *calculus*; the running
  interpreter is the Python toolchain, not the extracted artifact. This is the *same* residual the whole
  proven core has (bounded by the differential bridge / the krml–Eurydice TCB-unity blocker), not a new one.
  A future increment proves the interpreter **robustly preserves** forwarding (RSP, Abate et al.) and/or
  unifies the TCB — only then is the runtime residual itself discharged.
- **Identity only.** Transform/how-provenance forwarding is future (§6).
- **1-hop grade.** Transitive forwarding is proved/enforced but not yet *graded* G0 (§6).
- **Decidable contract DSL.** Entailment stays in the quantifier-free fragment z3 decides; anything outside ⇒
  no re-base (conservative).

---

## 9. References

1. J. Cheney, L. Chiticariu, W.-C. Tan. *Provenance in Databases: Why, How, and Where.* Foundations and Trends in Databases 1(4), 2009. https://homepages.inf.ed.ac.uk/jcheney/publications/provdbsurvey.pdf
2. P. Buneman, S. Khanna, W.-C. Tan. *Why and Where: A Characterization of Data Provenance.* ICDT 2001, LNCS 1973. https://doi.org/10.1007/3-540-44503-X_20
3. T. J. Green, G. Karvounarakis, V. Tannen. *Provenance Semirings.* PODS 2007. https://web.cs.ucdavis.edu/~green/papers/pods07.pdf
4. J. Cheney, A. Ahmed, U. A. Acar. *Provenance as Dependency Analysis.* DBPL 2007 / MSCS 21(6), 2011. https://doi.org/10.1017/S0960129511000211
5. P. Rondon, M. Kawaguchi, R. Jhala. *Liquid Types.* PLDI 2008. https://doi.org/10.1145/1375581.1375602
6. N. Vazou, A. Tondwalkar, V. Choudhury, R. G. Scott, R. R. Newton, P. Wadler, R. Jhala. *Refinement Reflection: Complete Verification with SMT.* POPL 2018. https://doi.org/10.1145/3158141
7. K. Honda, N. Yoshida, M. Carbone. *Multiparty Asynchronous Session Types.* JACM 63(1), 2016 (POPL 2008). https://doi.org/10.1145/2827695
8. F. Zhou, F. Ferreira, R. Hu, R. Neykova, N. Yoshida. *Statically Verified Refinements for Multiparty Protocols.* OOPSLA 2020. https://doi.org/10.1145/3428216 · arXiv:2009.06541
9. B. Toninho, N. Yoshida. *Certifying Data in Multiparty Session Types.* JLAMP 90, 2017 (LNCS 9600, 2016). https://mrg.cs.ox.ac.uk/publications/certifying-data-in-multiparty-session-types/
10. A. Scalas, N. Yoshida. *Less is More: Multiparty Session Types Revisited.* POPL 2019. https://doi.org/10.1145/3290343
11. D. Tirore, J. Bengtson, M. Carbone. *MPST: A Mechanised Proof of Subject Reduction.* ECOOP 2025, LIPIcs 333. https://doi.org/10.4230/LIPIcs.ECOOP.2025.31
12. S. Zdancewic, A. C. Myers. *Robust Declassification.* CSFW 2001. https://www.cis.upenn.edu/~stevez/papers/ZM01b.pdf
13. A. C. Myers, A. Sabelfeld, S. Zdancewic. *Enforcing Robust Declassification and Qualified Robustness.* JCS 14(2), 2006. https://www.cs.cornell.edu/andru/papers/robdecl-jcs/robdecl-jcs.pdf
14. A. Askarov, A. C. Myers. *A Semantic Framework for Declassification and Endorsement.* ESOP 2010 (LMCS 7(3), 2011). https://askarov.net/askarov-myers-esop10.pdf
15. A. Sabelfeld, D. Sands. *Declassification: Dimensions and Principles.* JCS 17(5), 2009. https://doi.org/10.3233/JCS-2009-0352
16. C. Abate, R. Blanco, D. Garg, C. Hriţcu, M. Patrignani, J. Thibault. *Journey Beyond Full Abstraction: Robust Property Preservation for Secure Compilation.* CSF 2019. https://arxiv.org/abs/1710.07309
17. M. Patrignani, A. Ahmed, D. Clarke. *Formal Approaches to Secure Compilation.* ACM Computing Surveys 51(6), 2019. https://doi.org/10.1145/3280984
18. S. Capecchi, I. Castellani, M. Dezani-Ciancaglini, T. Rezk. *Session Types for Access and Information Flow Control.* CONCUR 2010 / *Information Flow Safety in Multiparty Sessions*, MSCS 26(8), 2016. https://arxiv.org/pdf/1108.4465
19. E. J. Schwartz, T. Avgerinos, D. Brumley. *All You Ever Wanted to Know About Dynamic Taint Analysis and Forward Symbolic Execution…* IEEE S&P 2010. https://doi.org/10.1109/SP.2010.26
20. M. G. Kang, S. McCamant, P. Poosankam, D. Song. *DTA++: Dynamic Taint Analysis with Targeted Control-Flow Propagation.* NDSS 2011. http://bitblaze.cs.berkeley.edu/papers/dta++-ndss11.pdf
21. B. Finkbeiner, C. Hahn, M. Stenger, L. Tentrup. *Monitoring Hyperproperties.* RV 2017 / FMSD 2019. https://arxiv.org/pdf/1807.00758
