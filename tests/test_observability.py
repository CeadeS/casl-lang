"""Artifact observability — structured oracle-call capture (LH-G-005 / CEP-0060)."""
from casl import core, oracle
from casl import observability as obs
from casl import run as casl_run


def test_run_captures_observations():
    r = casl_run.run_protocol(core.G_OK, oracle.MockBackend("ok"), {"budget": 100, "question": "q"},
                              max_loops=3, caps=core.AGENT_CAPS)
    assert r.observations, "expected at least one oracle observation"
    o = r.observations[0]
    assert o.prompt and o.response                      # prompt→response captured as data, not prose
    assert o.verdict in ("ok", "violation", "refusal")
    assert ":" in o.step                                # "Sender→Receiver:Label"


def test_persist_and_load_roundtrip(tmp_path):
    r = casl_run.run_protocol(core.G_OK, oracle.MockBackend("ok"), {"budget": 100, "question": "q"},
                              max_loops=3, caps=core.AGENT_CAPS)
    path = obs.persist(r.observations, str(tmp_path), "run1")
    assert path and path.endswith("run1.jsonl")
    back = obs.load(path)
    assert [o.step for o in back] == [o.step for o in r.observations]
    assert "oracle observations" in obs.report(back)
