"""SP-4 — proof-faithfulness anti-vacuity front-line."""
from casl.core import Comm, Choice, Branch, End
from casl import faithfulness as F


def test_witnesses_present():
    assert F.missing_witnesses() == []          # the F* non-vacuity witnesses still exist


def test_must_die_mutants_are_rejected():
    assert F.mutation_survivors() == []         # discriminating power: none wrongly accepted


def test_mutation_test_is_not_vacuous():
    # positive control: a WELL-FORMED protocol must be accepted, else _projectable is trivially False
    g = Comm("C", "A", "m", (), Choice("A", "J", (Branch("l1", (), End()), Branch("l2", (), End()))))
    assert F._projectable(g) is True


def test_each_must_die_is_actually_illformed():
    for name, g in F.must_die():
        assert F._projectable(g) is False, name


def test_cep_levels_consistency():
    assert F.cep_feature_consistency() == []    # per-feature CEPs agree with levels.FEATURES


def test_overall_ok():
    assert F.ok() is True
