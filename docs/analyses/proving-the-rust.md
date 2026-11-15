# Proving the Rust (not just pinning it)

*Design analysis. The Rust engine is already differential-pinned to the F\* verdict (same assurance the Python
reference has). This asks the next question: can the Rust be **machine-proven**, and how? Draft → research →
variants → compare → synthesize → honest scope. Companion to docs/analyses/python-retirement-roadmap.md.*

## 1. The premise, corrected

The Python checker is **not** proven — `fstar/CASL.fst` (0 admits) is the proof of record, the F\*-extracted
(OCaml) checker is the proved *artifact* (`casl check --authoritative`), and Python is a reference
implementation **pinned** to that verdict by the conformance differential. The Rust engine gets the identical
treatment (parse-, core-, and verdict-differentials). So "prove the Rust like the Python" already holds in the
sense that matters: Rust is assured to the same F\*-anchored standard Python is. This doc is about going
*beyond* the differential to an actual machine proof of the Rust.

**Hard caveat up front:** only **well-formedness** (`wellformed_core` = contractive ∧ no_self ∧ gdistinct ∧
closed ∧ projectable{C,A,J,D}) is proven in F\* at all. The other checks (capability containment,
approval-dominance, concurrency, async-bounded, pipeline, contracts) have **no F\* proof** in either language —
they are characterization-pinned, and their grade says so. So a Rust proof can only *match an existing proof*
on the well-formedness fragment; elsewhere there is nothing to match.

## 2. Research — the 2026 landscape

- **Verus** — SMT-based verification of Rust, in-language (`spec fn`/`proof fn`/`requires`/`ensures`/
  `decreases`), aimed at "full functional correctness of low-level systems code" (OSDI'24; PLDI'26 *VerusBelt*
  gives its semantic foundation). Self-contained; uses Z3.
- **Creusot** — deductive verifier translating Rust (MIR) to WhyML; functional correctness via contracts.
- **Aeneas** — translates (a safe subset of) Rust into a **pure functional model** in F\*/Lean/Rocq, so the
  Rust can be proven *in the same prover* against the *same spec*. Frontend = Charon.
- **Eurydice** — the *other* direction: compiles verified Rust (or F\*/Low\*) **to C** (HACL\*/Kyber). "Doesn't
  currently scale much beyond small, self-contained programs"; targets machine-int/GC-free code.

## 3. Variants + compare (for proving `wellformed_core`)

| | Verus (prove Rust in-language) | Aeneas → F\* (prove Rust in the prover) | Eurydice (extract Rust ⟸ F\*) |
|---|---|---|---|
| Proves the **Rust**? | yes | yes (via a faithful functional model) | n/a (generates code *from* F\*) |
| Reuses the existing F\* spec? | no (re-state spec in Verus) | **yes** (bring Rust into F\*, reuse `CASL.fst`) | n/a |
| Toolchain on this Mac | **z3 ✓, verus installable** (prebuilt release) | needs **Charon + Lean/F\*** (absent) | needs Low\* rewrite (style mismatch, `TBD-004`) |
| Fit for CASL's core (string-labeled recursive ADT) | good | **best** (algebraic, matches F\*) | poor (wrong shape; doesn't scale) |
| Effort for a first result | **low–medium** | medium–high (install + model plumbing) | high (reformulate the core in Low\*) |

## 4. Synthesis — the plan

**Verus first** (lowest friction, runnable here once installed), then **Aeneas → F\*** as the "gold" follow-up
(it reuses `CASL.fst`, the most elegant unification). Eurydice is rejected for this core (style mismatch).

Prove the `wellformed_core` conjuncts one at a time, simplest first — **`no_self`** is the first brick:

1. a `spec fn` giving the mathematical predicate (the meaning),
2. an `exec fn` in the casl-core style, proven `ensures result == spec` (functional correctness),
3. `decreases` on the recursive structure (termination), and Verus's default panic-freedom,
4. then `closed`, `contractive`, `gdistinct` (also structural), and finally the **projectable** conjunct
   (the hard one — it calls `project`/`merge`).

**What this buys, honestly:** it proves the Rust *implementation* faithfully computes the predicate (no
panics, terminates, matches its logical definition). It does **not** re-prove the MPST metatheory
(preservation/progress) — those stay in `fstar/CASL.fst`. The win is closing the gap between the *running Rust*
and *its spec* with a machine proof, on the one fragment where a spec/proof exists.

## 5. Status — VERIFIED ✅ (n-ary)

`rust/proofs/no_self_verus.rs` is **machine-checked**: Verus (release 0.2026.06.20.911e4e7 + rustc 1.96.0)
reports **`5 verified, 0 errors`** — the `no_self` checker refines its logical spec (`ensures`), terminates
(`decreases`), is panic-free (Verus default), and the self-communication-rejection lemma discharges, over an
**n-ary** choice (arbitrary branches, recursing into every one). So **the Rust *can* be proven**, on the
fragment where a spec exists — demonstrated, not asserted.

Empirical finding (the cautious loop earned it): the *faithful* `Vec<Branch>` version **fails** Verus's
termination checker — recursing into a `Vec` of a recursive enum under `decreases g` is a documented Verus
limitation (verus-lang/verus #1195/#1222). The n-ary proof therefore models the branch list as a recursive
**cons-list** (`BList`): identical predicate meaning, arbitrary branch count, single structural recursion,
which Verus discharges cleanly. The cons-list-vs-`Vec` container and roles-as-`usize` are the remaining
faithful abstractions — neither changes the predicate's logic.

Honest scope: it proves the *implementation* faithfully computes the `no_self` predicate; it does **not**
re-prove the MPST metatheory (that stays in `fstar/CASL.fst`), and `no_self` is one of five `wellformed_core`
conjuncts. Follow-ons: `closed`/`contractive`/`gdistinct` (same cons-list shape), then the `projectable`
conjunct (`project`/`merge` — the hard one). The heavier alternative — **Aeneas → F\***, reusing `CASL.fst` —
remains the "gold" unification, and would also dissolve the `Vec` limitation since it models the real Rust.

Reproduce: install the Verus release + the matching rustup toolchain, then
`<verus-release>/verus rust/proofs/no_self_verus.rs`.
