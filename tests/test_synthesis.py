"""CEP-0079 — the requirements → verified-project loop. The monotone gate is the SOLE arbiter of emission
(CEGIS / veto-never-vouch): an accepted proposal yields a conductable project; a rejected one yields nothing
(fail-closed). Verified offline with the deterministic mock generator. See casl.synthesis, docs/synthesis.md."""
import os

from casl import surface, synth, synthesis


def test_new_project_emits_and_conducts(tmp_path):
    # requirement → gated proposal → emitted project → conducted end-to-end through the broker
    res = synthesis.new_project("Budgeted QA with retry", str(tmp_path), synth.MockGenerator())
    assert res.accepted and res.gate.accepted                       # the gate is the arbiter
    assert (tmp_path / "casl.toml").exists()
    assert (tmp_path / "casl" / "budgetedqa.casl").exists()
    assert "draft" in res.artifacts and "search_provider" in res.artifacts
    assert res.conducted is not None and res.conducted.run.outcome == "completed"


def test_fail_closed_emits_nothing(tmp_path):
    # max_iters=1: the mock proposes only the BROKEN spec → the gate never accepts → nothing is emitted
    res = synthesis.new_project("x", str(tmp_path), synth.MockGenerator(), max_iters=1, conduct=False)
    assert not res.accepted and res.project_dir is None
    assert not (tmp_path / "casl.toml").exists()                    # fail-closed: no project on disk


def test_derive_manifest_binds_oracle_and_provider():
    proto = surface.parse(synth._FIXED)                              # the accepted BudgetedQA
    toml = synthesis.derive_manifest(proto, "R-1")
    assert "BudgetedQA:Draft" in toml and '"oracle"' in toml         # oracle site → oracle artifact
    assert "provides" in toml and '"search"' in toml                 # effect capability → single-purpose provider


def test_emitted_project_is_gate_clean_and_conductable(tmp_path):
    # re-load the emitted project independently and conduct it: the conductor gates the hull before running
    synthesis.new_project("Budgeted QA with retry", str(tmp_path), synth.MockGenerator(), conduct=False)
    from casl import conductor
    cr = conductor.Conductor(str(tmp_path)).run(scenario="ok", approve=True, env={"budget": 100})
    assert cr.run.outcome == "completed"
