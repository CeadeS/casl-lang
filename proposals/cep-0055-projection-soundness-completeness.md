---
cep: 55
title: Projection soundness & completeness — the W19 resolution (sound core + completeness oracle)
status: Draft
type: Informational
created: 2026-06-19
version: 0.1
authors: [Martin]
requires: [3, 4]
---

# CEP-0055 — Projection soundness & completeness (W19)

Mergeability-based projection is sound-but-subtle (Scalas–Yoshida, *Less is More*, POPL 2019) and
incomplete vs. the automata-complete operator (Li–Stutz–Wies–Zufferey, CAV 2023). CASL's resolution
keeps the two directions strictly separate, matching the assurance grades.

## Soundness — machine-held, never delegated (the bar)

`wellformed(G) ⇒ the projected synchronous endpoint system is safe` (deadlock-free, no reception error).
**Proven in F\* (0 admits) — now for the FULL fragment incl. recursion (v0.27.0):** `global_progress` (a well-formed head can
always step), `preservation` (subject reduction over `GS_Msg`/`GS_Ch`), `progress_invariant` (a
well-formed rec-free protocol is `GEnd` or a head communication) — together with the head `fidelity`
metatheorems and `deadlock_free`, this gives deadlock-freedom along every run. Building it surfaced and
**closed two real over-acceptances** of `wellformed`: non-contractive recursion (`μt.t`) and
self-communication (`p→p`), now conjuncts of `wellformed` (`contractive`, `no_self`), mirrored in the
TCB bridge + `casl check` gates. The **recursion** case is now PROVEN: `subst_g_wf` (unfolding preserves all four wellformed conjuncts) feeds `preservation_full`, full subject reduction over GS_Msg/GS_Ch/GS_Rec. This required adding `gdistinct` (distinct branch labels) + `closed` (no free type vars) to `wellformed` and the keystone `subst_opts_inj` (substitution-injectivity of the n-ary merge, via the `merge_opts_lookup` assoc-characterisation). All 0 admits; bridge 412/412. The semantic safety oracle
(`semantics_sync`) cross-checks soundness by test (39 k+ guarded protocols, 0 counterexamples).

## Completeness — maximised automatically + recovered on demand (never proven)

CASL already uses the maximal STANDARD syntactic merge (full label-unioning Honda–Yoshida–Carbone), so
the automatic checker accepts as much as a syntactic merger can. The residual — protocols only the
automata-complete operator would accept — is recovered behind the **monitored boundary** by the
**user/external as a completeness ORACLE** (`completeness.py`), which can only lift a conservative
*reject* to an *accept*, never touch soundness:
- **strong (no new trust):** a user/tool supplies a local-type **certificate**; the trusted oracle
  re-validates it is **safe** and **faithful** to `G` (bisimilar to `G`'s global reduction) ⇒ admit at
  mode `tested`/G2. (Proof-carrying / the SP-5 propose⇒check shape.)
- **weak (bounded trust):** a human Tier-3 **attestation** ⇒ mode `attested`/G3, disclosed, reviewable;
  deny-by-default if absent.

## Status

Soundness = **proved** (G0, FULL fragment incl. recursion as of v0.27.0). Completeness = **maximised + test/certificate**
(≈G2), residual **human-attested** (G3). The hard invariant — *the sound core always keeps the safety
verdict; the oracle only lifts rejects* — means no human or tool can ever turn an unsafe protocol into an
accepted one. Remaining (optional): the PSPACE automata operator as one more certificate kind; the completeness ratchet (CEP-0056).

## Cross-references

CEP-0003 (assurance levels / modes), CEP-0004 (integrity case), CEP-0054 (SP-5 proof loop),
`docs/analyses/w19-projection-completeness.md`; Scalas–Yoshida POPL 2019; Li–Stutz–Wies–Zufferey CAV 2023.
