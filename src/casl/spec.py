"""
spec.py — the SINGLE SOURCE OF AUTHORITY.

Principle: "All authority derives from the specifications and the things
derived from them." (Martin, 2026-06-15)

This module is the machine-readable spine of CASL.md + docs/principles.md:
  THESES        — the five guiding theses T1–T5
  GRUNDSAETZE   — the first principles P0–P9
  REQS          — the L1 requirements (level, verif stage, thesis sources)
  ACCEPTED_GAPS — executable-verifiable requirements not yet realized (tracked)
  TENSIONS      — open contradictions/tensions under watch

Every other module (kernel, authority, audit) DERIVES from this one. Nothing
may claim authority that is not rooted here — that is what `authority.py`
enforces.
"""
from __future__ import annotations

THESES = {
    "T1": "oracle/provability/SMT",
    "T2": "agent-/session-typed, projection",
    "T3": "runtime/resilience/monitor/blame",
    "T4": "objects/capabilities/contracts/tests",
    "T5": "RE/traceability/standards",
}

GRUNDSAETZE = {
    "P0": "self-application (lived system)",
    "P1": "oracle separation (prove the hull, LLM = oracle)",
    "P2": "correctness by construction",
    "P3": "behavior is type (session type)",
    "P4": "global → local via projection",
    "P5": "least privilege (capabilities)",
    "P6": "linearity (promise/obligation)",
    "P7": "one structure proves and tests",
    "P8": "blame locality at the oracle boundary",
    "P9": "traceability & docs-as-code",
    "P10": "accountability where proof is impossible (containment + provenance + human signature)",
}

# requirement id -> (stufe, verif stage, [thesis sources])
REQS = {
    "LH-G-001": ("MUST", "—",   ["T1", "T2", "T3", "T4"]),
    "LH-G-002": ("MUST", "B/M", ["T1"]),
    "LH-G-003": ("SHOULD", "B",   ["T4"]),
    "LH-G-004": ("SHOULD", "T",   ["T1", "T2"]),
    # Artifact-trust layer (CEP-0057): the obligation gate + artifact observability
    "LH-G-005": ("SHOULD", "M",  ["T3"]),        # artifact observability: structured prompt→response capture (realized: observability)
    "LH-G-006": ("MUST", "M",   ["T4"]),         # Tier-0 obligation gate (deny-by-default: manifest+deps+trace+attestation)
    "LH-F-001": ("MUST", "B",   ["T2"]),
    "LH-F-002": ("MUST", "B",   ["T2"]),
    "LH-F-003": ("MUST", "B",   ["T2"]),
    "LH-F-004": ("MUST", "B",   ["T4"]),
    "LH-F-005": ("MUST", "B",   ["T4"]),
    "LH-F-006": ("MUST", "B",   ["T2", "T3"]),
    "LH-F-007a": ("SHOULD", "B",  ["T3"]),
    "LH-F-007b": ("SHOULD", "M",  ["T3"]),
    # Expressiveness toward the target picture (secretariat, VISION §3/§6)
    "LH-F-008": ("SHOULD", "T",   ["T2"]),       # multiparty ≥4 roles (prototype generic + by-test; proof head fragment, W9)
    "LH-F-009": ("SHOULD", "T",   ["T2", "T3"]), # event-driven, long-running sessions (stream) — tracked, PR #25
    "LH-F-010": ("SHOULD", "T",   ["T2", "T3"]), # async/buffered — boundedly certifiable (bounded+orphan-free+deadlock-free), deny-by-default, encapsulated (W16, PR #33)
    "LH-F-011": ("SHOULD", "T",   ["T2", "T4"]), # pipeline node trichotomy (program|LLM-box|verified); oracle monitored, oracle⊕verified exclusive; verified trust human-attested (W17, CASL-IDE Phase 4)
    # Artifact-trust layer (CEP-0057): a project's artifacts as first-class governed units
    "LH-F-012": ("SHOULD", "T",  ["T4"]),        # artifact as a declared unit (typed seam + body + obligation)
    "LH-F-013": ("SHOULD", "T",  ["T4"]),        # provenance kind structured + validated (external|generated|verified|oracle); never inferred
    "LH-Q-001a": ("MUST", "B",  ["T2"]),
    "LH-Q-001b": ("MUST", "B",  ["T2"]),
    "LH-Q-001c": ("MUST", "B",  ["T2"]),
    "LH-Q-001d": ("MUST", "B",  ["T2"]),       # correspondence under concurrency (swap/confluence); the non-certifiable is rejected

    "LH-Q-002": ("MUST", "B/T", ["T4"]),
    "LH-Q-003a": ("MUST", "B",  ["T4"]),
    "LH-Q-003b": ("MUST", "B",  ["T4"]),
    "LH-Q-004": ("MUST", "S",   ["T1", "T4"]),
    "LH-Q-005": ("MUST", "M",   ["T3"]),
    "LH-Q-006": ("MUST", "T",   ["T4"]),
    "LH-Q-007": ("SHOULD", "T",   ["T4"]),
    "LH-Q-008": ("MAY", "M",   ["T4"]),
    "LH-Q-009": ("SHOULD", "S",   ["T1", "T2"]),
    "LH-Q-010": ("SHOULD", "B",   ["T4"]),
    "LH-Q-011": ("MUST", "B",   ["T3", "T4"]),
    # Red-team follow-up requirements (v0.1.28 re-test) — issues with traceability,
    # until the respective fix PR realizes them (then out of ACCEPTED_GAPS).
    "LH-Q-012": ("MUST", "B",   ["T4"]),       # R-H1: effect classification structured/validated
    "LH-Q-013": ("SHOULD", "M",   ["T3"]),       # R-N1: per-gate disclosure + specific consent
    "LH-Q-014": ("SHOULD", "M",   ["T4"]),       # H3: runtime tool mediation (confinement)
    "LH-Q-015": ("SHOULD", "M",   ["T3"]),       # H4: out-of-band cost metering
    # Artifact-trust layer (CEP-0057): human attestation + grade monotonicity + dependency burden
    "LH-Q-016": ("MUST", "M",   ["T4"]),         # attestation floor: unprovable kinds need a human act (G3 floor)
    "LH-Q-017": ("MUST", "M",   ["T4"]),         # attestation content-binding: bound to body sha256; an edit EXPIRES it
    "LH-Q-018": ("MUST", "M",   ["T4"]),         # humans sign AS humans: non-self + GPG/SSH-signed commit; plaintext rejected
    "LH-Q-019": ("MUST", "T",   ["T4"]),         # effective grade = weakest link (min-composition); laundering impossible
    "LH-Q-020": ("MUST", "M",   ["T4"]),         # dependency burden ledger: pinned + owned, deny-by-default
    "LH-P-001": ("MUST", "T",   ["T5"]),
    "LH-P-002": ("MUST", "T",   ["T5"]),
    "LH-P-003": ("MUST", "T",   ["T5"]),
    "LH-P-004": ("SHOULD", "T",   ["T5"]),
    "LH-P-005": ("MUST", "T",   ["T5"]),
    # Artifact-trust layer (CEP-0057): project-wide line traceability + blame + ownership-fixed regime
    "LH-P-006": ("MUST", "T",   ["T5"]),         # every owned line → a requirement; an untraced first-party line BLOCKS
    "LH-P-007": ("SHOULD", "T",  ["T5"]),        # every owned line → author + mechanism (human|llm); a bug blames the human
    "LH-P-009": ("MUST", "T",   ["T5"]),         # trace regime follows OWNERSHIP (owned⇒full, external⇒burden); no self-downgrade
    "LH-C-001": ("MUST", "T",   ["T5"]),
    "LH-C-002": ("MUST", "T",   ["T5"]),
    "LH-C-003": ("SHOULD", "T",   ["T5"]),
    "LH-C-004": ("MAY", "T",   ["T1", "T5"]),  # H1: unity of proven artifact ↔ running checker (TCB)
}

# executable-verifiable requirements knowingly not yet realized by a building block.
# These are tracked OPEN ISSUES (each also a W tension); the named PR realizes it,
# at which point it leaves this dict and a building block covers it.
ACCEPTED_GAPS = {
    "LH-C-004": "OPEN/MAY — H1 (red-team v0.1.27); TCB unity; krml/Eurydice mismatch, TBD-004 [W11]. PARTIAL STEP: TCB differential bridge (make -C fstar tcb-bridge) — F*-extracted kernel ↔ Python checker agree on a projectability corpus (offline); full unification remains blocked",
}

TENSIONS = [
    ("W1", "high",    "capability containment claimed but unchecked", "resolved (block capabilities)"),
    ("W2", "high",    "MPST⇔MSC equivalence (adversarial battery, 10 cases)", "hardened — merge made recursive + realizability sharpened on first divergence"),
    ("W3", "high",    "crash/refusal (LH-F-007a/b) prototyped", "resolved (blocks crash_tolerance/refusal_monitor)"),
    ("W4", "medium",  "capability ttl vs. retry loop", "resolved (ttl_safety, composed with the W5 bound; revocation as fallback)"),
    ("W5", "medium",  "loop termination", "resolved (termination: SMT ranking + loop measure)"),
    ("W6", "medium",  "promise linearity under recursion", "resolved (linearity: static usage check)"),
    ("W7", "low",     "branch contract len(reason)>0 wired up", "resolved (branch_contracts: nonempty monitor synthesized + property-checked, in the audit)"),
    ("W8", "low",     "σ (provenance) unused", "RESOLVED (intentionally reserved): σ is a documented field of the §3 capability tuple (LH-F-005) — provenance/signature reserved for future delegation-provenance integrity. NOT dead code; deliberately not consumed by a check (economy of mechanism — no unmotivated gate added). Annotated reserved in core.py Capability."),
    ("W9", "low",     "op. correspondence soundness / concurrency ≥4 roles", "prototype: swap rule + by-test (`LH-Q-001d`, soundness global⊆config without exception). F\*: `cgstep` (permutation) + `diamond_indep` (global) + `proj_skip` + `cstep_diamond` (endpoint level) PROVE mechanically (0 admits) that independent actions commute on BOTH levels; `fidelity_sound` scoped to the head event. Remainder (Direction C): fully general inductive fidelity under permutation for ARBITRARY protocols + cross-recursion concurrency — by-test"),
    # Red-team v0.1.27 residual risks — registered as first-class, tracked tensions
    # (instead of only in prose), so the living audit makes them visible on every run.
    ("W10", "high",    "C3: approval only statically checked (lint); casl_run picked a structural default at the gate, never asked a human", "resolved (casl_run: default-deny at the approval gate, --approve/callback, consent branch, re-evaluated per encounter; block runtime_approval)"),
    ("W11", "medium",  "H1: TCB inversion — the running Python checker is not the artifact proven in F*", "RESOLVED in-fragment (SP-2 / CEP-0009): `casl check --authoritative` runs the F*-EXTRACTED, verified `wellformed` as THE core verdict for in-fragment protocols (GMsg/GCh/GRec/GVar/GEnd over {C,A,J,D}); Python is demoted to an untrusted client whose projection is cross-checked, a divergence is a hard error. TCB of that verdict = F*+Z3+extraction, NOT Python. The differential bridge (412 protocols incl. n-ary, src/casl/tcb_corpus.py) is demoted from the trust story to a REGRESSION guard. Residual (tracked, not on the in-fragment path): Python's out-of-fragment MSC layer, and the general cross-language unification (`LH-C-004`, krml/Eurydice-Low* mismatch, TBD-004). See proposals/cep-0009-extracted-checker-authoritative.md, docs/analyses/verification-mode-and-tcb-unification.md"),
    ("W12", "medium",  "H3: capability check was a lint, not runtime confinement (no tool broker interposed)", "resolved (`LH-Q-014`): `casl_run._tool_allowed` interposes on every tool use against the runtime capmap (`tool_denied`); block `tool_broker`"),
    ("W13", "low",     "H4: the oracle reported the very costs it is evaluated on", "resolved (`LH-Q-015`): the monitor checks against the out-of-band measurement (`OracleResult.measured_cost`, server usage); the oracle `cost` is only a claim; block `cost_metering`"),
    # Red-team v0.1.28 re-test
    ("W14", "high",    "R-H1: the effect classifier `effectful()` was a leaky/spoofable substring test on the free-text `scope` (e.g. `cal:read-write`→read-only, `db:readonly` on purge)", "resolved (`LH-Q-012`): effect follows from a structured, validated `mode` field (default `write`); block `effect_classification`; attacks `rw_naming`/`delete_readonly` in the corpus"),
    ("W15", "low",     "R-N1: runtime consent was blanket (`--approve` approves every gate), not bound to the disclosed gate message", "resolved (`LH-Q-013`): `GateDisclosure` (disclosed message + concrete effect-bearing action), `on_approval(disclosure)` per gate, interactive CLI prompt; block `gate_disclosure`"),
    # async enhancement (PR #33)
    ("W17", "medium",  "pipeline `verified` nodes claim a deterministic program lies inside the proven hull — but the machine cannot prove an ARBITRARY external program; a blindly trusted `verified` marker would be an escalation path (effect principle R-H1: never derive trust from author free-text)", "mitigated (`LH-F-011`): Tier 0 (`pipeline_safe`) checks only the STRUCTURE (oracle monitored/`oracle⊕verified` exclusive); the TRUST of `verified` is NOT granted but ATTESTED by a human in the IDE (Tier 3, `casl_ide`), exactly like an effect. A machine-checkable backing (compositional verification of the sub-artifact) remains future work"),
    ("W16", "medium",  "async subtyping is UNDECIDABLE in general (Bravetti–Carbone–Zavattaro 2017, Lange–Yoshida) — a complete, terminating async-safety checker cannot exist; unbounded FIFO buffers encode a Turing-powerful counter", "mitigated (`LH-F-010`): ENCAPSULATED enhancement `semantics_async` (one inbox/receiver, non-blocking send, FIFO recv). The deny-by-default gate `async_bounded` enumerates the k-bounded state space and certifies bounded + orphan-free + deadlock-free; reports sync-equivalence (≤1 message in flight ⇒ inherits the proven core guarantees). The non-certifiable (reorder/deadlock, orphan, buffer>k, state explosion) is REJECTED. Full unbounded async deliberately stays out of scope (hard barrier, docs/analyses/async.md); F\* mechanization of bounded async = tracked MAY future. WITHOUT the `async` marker untouched — the proven synchronous core stays the default"),
    ("W18", "low",     "the n-ary `merge` uses a structural FUEL (= input size) for termination; fuel-sufficiency (that the wrapper never returns a spurious None for lack of fuel) was the open question", "RESOLVED (machine-proven, 0 admits): `merge_complete` in CASL.fst proves `(exists n. merge_f n l1 l2 = Some r) ==> merge l1 l2 = Some r` — the wrapper `merge` (fuel `2*(lsize l1+lsize l2)`) reproduces every reachable success, so it NEVER returns a spurious None. Built from fuel MONOTONICITY (`merge_f_mono`/`_mono_le`), the OUTPUT-SIZE bound (`merge_f_size`), and the SUFFICIENCY lemmas `suff_f`/`suff_opts` (strong induction on the witnessing fuel; an ASYMMETRIC size bound — charge the 2nd arg double — closes the induction where a symmetric one is provably inconsistent). Empirically pre-validated over 360k+ pairs incl. adversarial (0 insufficiencies). See docs/analyses/w18-fuel-sufficiency.md"),
    ("W19", "medium",  "mergeability-based projection (used by both the Python checker and the F* core) was shown by Scalas–Yoshida (`Less is More`, POPL 2019) to make general pi-calculus type-safety proofs subtle/flawed; complete projection in general needs automata (Majumdar–Yoshida–Wies et al., CAV 2023)", "tracked: CASL's mechanized guarantees are scoped to SYNCHRONOUS head-step fidelity + a bounded differential bridge, which do NOT rely on the general mergeability type-safety claim. W19-A PROGRESS (machine-proven, 0 admits): two real over-acceptances of `wellformed` found via the semantic safety oracle and CLOSED — non-contractive recursion (μt.t) and self-communication (p→p), now conjuncts of `wellformed` (contractive/no_self). SOUNDNESS for the RECURSION-FREE fragment is proven: `global_progress` (Q) + `preservation` (P, subject reduction) + `progress_invariant`, which with head fidelity + `deadlock_free` give deadlock-freedom along every run. Remaining: the GS_Rec/substitution-preservation lemma to extend to recursion; completeness via the automata engine (by-test) + the user-as-completeness-oracle residual (C′), now IMPLEMENTED (`casl/completeness.py`, CEP-0055): CASL uses the maximal syntactic merge (full Honda-Yoshida-Carbone); a conservative reject can be lifted only via a re-checkable certificate (oracle re-validates safety + faithfulness-to-G, mode tested/G2) or a labelled human attestation (attested/G3) — the sound core always keeps the safety verdict. Resolution path if full automatic completeness is wanted: automata-based projection (CAV 2023), one more certificate kind, pursued via the SP-5 loop (`casl/proof_loop.py`). See docs/analyses/w19-projection-completeness.md and CEP-0055"),
]


def is_executable(verif: str) -> bool:
    """A requirement is realizable by a building block iff it has a B/S/M/T stage."""
    return verif not in ("—",)
