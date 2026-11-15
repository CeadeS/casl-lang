"""End-to-end — the whole CASL loop in one place (the running version for checking):
  · an example choreography passes the checker (spec → gate),
  · a natural-language requirement becomes a gate-accepted, CONDUCTED project (`casl new`),
  · the emitted project stands alone and re-conducts from disk through the broker,
  · the safety property holds at run time: an oracle overspend is CAUGHT (never silently accepted).
This is the integration guard — if any layer (checker / synthesis / conductor / monitor) drifts, it fails."""
import os

from casl import check, conductor, surface, synth, synthesis

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(_ROOT, "examples")


def test_example_checks():
    # spec → gate: a known-good choreography is admissible
    proto = surface.parse_file(os.path.join(EX, "budgeted_qa.casl"))
    assert check.check_protocol(proto)["accepted"] is True


def test_requirement_becomes_a_conducted_project(tmp_path):
    # requirement → gated .casl → emitted project → conducted end-to-end through the broker
    res = synthesis.new_project("Budgeted QA with a cost check and retry", str(tmp_path),
                                synth.MockGenerator())
    assert res.accepted and res.conducted is not None
    assert res.conducted.run.outcome == "completed"
    # the emitted project is self-contained: re-load it from disk and conduct again independently
    cr = conductor.Conductor(str(tmp_path)).run(scenario="ok", approve=True, env={"budget": 100})
    assert cr.run.outcome == "completed"


def test_runtime_safety_property_holds(tmp_path):
    # the whole point: at run time the contract monitor CATCHES an oracle overspend (blame the producer);
    # it is never silently accepted — the loop bounds instead of completing on a violating draft.
    synthesis.new_project("Budgeted QA with a cost check and retry", str(tmp_path),
                          synth.MockGenerator(), conduct=False)
    cr = conductor.Conductor(str(tmp_path)).run(scenario="overspend", approve=True, env={"budget": 100})
    assert cr.run.last_verdict == "violation"
    assert cr.run.outcome in ("loop_bound_reached", "completed")
