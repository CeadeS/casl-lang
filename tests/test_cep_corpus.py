"""The CEP corpus guarantees, as standalone tests: schema valid, exact CEP<->spec round-trip,
and the proven-status rule (a Standards CEP is Final only if its building blocks exist)."""
from casl import cep, spec, kernel


def test_schema_valid():
    assert cep.validate() == []


def test_roundtrip_exact():
    assert cep.roundtrip_diff(spec.REQS) == []


def test_status_consistency():
    viol = cep.status_consistency(set(kernel.REGISTRY), set(spec.ACCEPTED_GAPS))
    assert viol == []


def test_every_requirement_has_a_cep():
    cep_reqs = set(cep.requirements())
    assert set(spec.REQS) == cep_reqs
