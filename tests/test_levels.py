"""Tests for the CASL Assurance Levels model (CEP-0003): feature inference + deny-by-default
profile/assurance ceilings."""
from types import SimpleNamespace

from casl.core import Comm, Choice, Branch, End
from casl import levels


def _br(lbl):
    return Branch(lbl, (), End())


def test_binary_choice_is_core():
    g = Choice("C", "A", (_br("l1"), _br("l2")))
    assert levels.features_used(g) == set()
    assert levels.min_profile(set()) == "core"
    assert levels.profile_ok(g, "core") == (True, [])


def test_nary_choice_is_extended_G0():
    g = Choice("C", "A", (_br("l1"), _br("l2"), _br("l3")))
    feats = levels.features_used(g)
    assert feats == {"nary_choice"}
    assert levels.min_profile(feats) == "extended"
    assert levels.min_assurance(feats) == "G0"
    ok, over = levels.profile_ok(g, "core")
    assert not ok and over == ["nary_choice"]          # deny-by-default
    assert levels.profile_ok(g, "extended") == (True, [])


def test_async_feature_is_G1():
    proto = SimpleNamespace(gtype=Comm("C", "A", "m", (), End()), async_k=2)
    assert "async" in levels.features_used(proto)
    assert levels.min_assurance({"async"}) == "G1"


def test_oracle_and_verified_are_advisory_attested():
    assert "oracle" in levels.features_used(Comm("C", "A", "m", (), End(), from_oracle=True))
    assert "verified" in levels.features_used(Comm("C", "A", "m", (), End(), verified=True))
    assert levels.min_profile({"oracle"}) == "advisory"
    assert levels.min_assurance({"oracle"}) == "G3"


def test_assurance_floor_denies_weaker():
    proto = SimpleNamespace(gtype=Comm("C", "A", "m", (), End()), async_k=1)   # async is G1
    ok, weak = levels.assurance_ok(proto, "G0")
    assert not ok and weak == ["async"]
    assert levels.assurance_ok(proto, "G1") == (True, [])


def test_core_protocol_passes_strictest():
    g = Comm("C", "A", "m", (), Choice("A", "J", (_br("l1"), _br("l2"))))   # binary, sync
    assert levels.profile_ok(g, "core") == (True, [])
    assert levels.assurance_ok(g, "G0") == (True, [])


# --- SP-1: assurance mode + trust budget ---

def test_assurance_mode_per_grade():
    assert levels.assurance_mode("G0") == "proved"
    assert levels.assurance_mode("G1") == "bounded"
    assert levels.assurance_mode("G2") == "tested"
    assert levels.assurance_mode("G3") == "attested"


def test_feature_modes():
    assert levels.feature_mode("nary_choice") == "proved"
    assert levels.feature_mode("async") == "bounded"
    assert levels.feature_mode("oracle") == "attested"
    assert levels.feature_mode("verified") == "attested"


def test_core_protocol_has_empty_trust_budget():
    g = Comm("C", "A", "m", (), Choice("A", "J", (_br("l1"), _br("l2"))))   # binary, sync
    assert levels.trust_budget(g) == []
    assert levels.trust_budget_ok(g) is True


def test_nary_only_is_proved_so_empty_budget():
    g = Choice("C", "A", (_br("l1"), _br("l2"), _br("l3")))                 # extended but G0/proved
    assert levels.trust_budget(g) == []          # proved ⇒ contributes nothing to the budget
    assert levels.trust_budget_ok(g) is True


def test_async_and_oracle_enter_trust_budget():
    proto = SimpleNamespace(gtype=Comm("C", "A", "m", (), End(), from_oracle=True), async_k=2)
    tb = dict(levels.trust_budget(proto))
    assert tb["async"] == "bounded"
    assert tb["oracle"] == "attested"
    assert levels.trust_budget_ok(proto) is False
