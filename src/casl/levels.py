"""
levels.py — CASL Assurance Levels (CEP-0003): the capability/assurance level model.

Two orthogonal axes:
  · CAPABILITY  — which constructs a protocol uses (binary choice = core; n-ary choice, async =
                  extended; oracle / verified pipeline nodes = advisory).
  · ASSURANCE   — how strongly a feature is backed: G0 F*-proven · G1 bounded-checked ·
                  G2 by-test · G3 human-attested.

Named, cumulative PROFILES (core ⊂ extended ⊂ advisory) are presets over a FEATURE set. The
checker INFERS the minimum profile a protocol needs, and a ceiling REJECTS anything above it
(deny-by-default). See proposals/cep-0003-assurance-levels.md and docs/language-spec.md
(ISO/IEC/IEEE 15026-3 system integrity levels).
"""
from __future__ import annotations
from typing import List, Set, Tuple

from casl.core import Comm, Choice, Rec

# Assurance grades, strongest first. Lower index = stronger guarantee.
ASSURANCE = ["G0", "G1", "G2", "G3"]
ASSURANCE_RANK = {g: i for i, g in enumerate(ASSURANCE)}

# Cumulative capability profiles, innermost first.
PROFILES = ["core", "extended", "advisory"]
PROFILE_RANK = {p: i for i, p in enumerate(PROFILES)}

# feature name -> (profile it belongs to, assurance grade). Unknown features are treated as the
# outermost/weakest (advisory, G3) — deny-by-default.
FEATURES = {
    "nary_choice": ("extended", "G0"),   # Variant A: n-ary choice; F*-proven (0 admits)
    "async":       ("extended", "G1"),   # buffered/async; bounded model-checked
    "oracle":      ("advisory", "G3"),   # LLM box; attested monitored boundary
    "verified":    ("advisory", "G3"),   # deterministic program; human-attested (Tier 3)
}

# Assurance MODE (how an obligation is discharged) as a first-class, machine-queryable token —
# mirroring F* `Lemma`/`assume`, Lean proof/`sorry` (+`#print axioms`), Dafny `assume`/`{:axiom}`.
# Each grade maps to a mode; `assumed` is the explicit-trust escape hatch (no current feature uses
# it — reserved so the trust budget can name it). See docs/analyses/verification-mode-and-tcb-unification.md.
MODE_OF_GRADE = {
    "G0": "proved",     # machine-proved (F* + Z3)
    "G1": "bounded",    # safe up to a model-checked bound
    "G2": "tested",     # property / conformance evidence
    "G3": "attested",   # human Tier-3 sign-off (LLM may pre-screen)
}
MODES = ["proved", "bounded", "tested", "attested", "assumed"]
# Modes that rest on something other than a machine proof — these are what the trust budget counts.
TRUSTED_MODES = {"bounded", "tested", "attested", "assumed"}


def _feature_meta(f: str) -> Tuple[str, str]:
    return FEATURES.get(f, ("advisory", "G3"))


def assurance_mode(grade: str) -> str:
    """The discharge mode for an assurance grade (G0->proved … G3->attested)."""
    return MODE_OF_GRADE.get(grade, "attested")


def feature_mode(f: str) -> str:
    """The discharge mode a feature relies on."""
    return assurance_mode(_feature_meta(f)[1])


def trust_budget(proto) -> List[Tuple[str, str]]:
    """The protocol's TRUST BUDGET: the (feature, mode) pairs it relies on that are NOT a machine
    proof — i.e. everything resting on a bound, a test, human attestation, or an explicit axiom.
    A `core` (binary-only, G0) protocol has an EMPTY budget. This is the `#print axioms` analogue
    at the protocol level: it names exactly what an accepted verdict trusts beyond the proven kernel."""
    return sorted((f, feature_mode(f)) for f in features_used(proto)
                  if feature_mode(f) in TRUSTED_MODES)


def trust_budget_ok(proto) -> bool:
    """True iff the protocol rests on no non-proof trust (empty budget) — the `core` requirement."""
    return not trust_budget(proto)


def _gtype_of(proto):
    return getattr(proto, "gtype", proto)


def _walk(g):
    yield g
    if isinstance(g, Comm):
        yield from _walk(g.cont)
        if g.on_crash is not None:
            yield from _walk(g.on_crash)
    elif isinstance(g, Choice):
        for b in g.branches:
            yield from _walk(b.cont)
    elif isinstance(g, Rec):
        yield from _walk(g.body)


def features_used(proto) -> Set[str]:
    """The set of level-gated features a (parsed) protocol uses. Accepts a surface Protocol
    (with .gtype / .async_k) or a bare global type."""
    feats: Set[str] = set()
    if getattr(proto, "async_k", None) is not None:
        feats.add("async")
    for n in _walk(_gtype_of(proto)):
        if isinstance(n, Choice) and len(n.branches) > 2:
            feats.add("nary_choice")
        if isinstance(n, Comm):
            if getattr(n, "from_oracle", False):
                feats.add("oracle")
            if getattr(n, "verified", False):
                feats.add("verified")
    return feats


def min_profile(feats: Set[str]) -> str:
    """Smallest cumulative profile admitting all used features (`core` if none)."""
    rank = max((PROFILE_RANK[_feature_meta(f)[0]] for f in feats), default=0)
    return PROFILES[rank]


def min_assurance(feats: Set[str]) -> str:
    """Weakest assurance grade among used features — the effective grade (G0 if none)."""
    rank = max((ASSURANCE_RANK[_feature_meta(f)[1]] for f in feats), default=0)
    return ASSURANCE[rank]


def profile_ok(proto, ceiling: str = "core") -> Tuple[bool, List[str]]:
    """(ok, over): admit the protocol iff every used feature is within `ceiling`
    (deny-by-default). `over` lists features exceeding the ceiling."""
    cap = PROFILE_RANK.get(ceiling, 0)
    over = sorted(f for f in features_used(proto)
                  if PROFILE_RANK[_feature_meta(f)[0]] > cap)
    return (not over, over)


def assurance_ok(proto, floor: str = "G3") -> Tuple[bool, List[str]]:
    """(ok, weak): every used feature must be at least as strongly assured as `floor`
    (G0 strongest). `weak` lists features below the floor."""
    flr = ASSURANCE_RANK.get(floor, len(ASSURANCE) - 1)
    weak = sorted(f for f in features_used(proto)
                  if ASSURANCE_RANK[_feature_meta(f)[1]] > flr)
    return (not weak, weak)
