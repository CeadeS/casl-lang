"""Layer 3 — the project-aware conductor (`casl.conductor`). Drives the `triage` dogfood project END-TO-END
through the broker (the reference monitor), in-process + offline (MockBackend). Pins: the typed-seam
bindings resolve; the oracle + effect both cross the broker; the contract monitor + approval gate +
deny-by-default + provider-gating all hold at the conductor↔broker seam; and the proven single-file
interpreter path (`dispatch=None`) is unchanged. See docs/conductor.md."""
import argparse
import os
import shutil

from casl import conductor, core, oracle
from casl import run as _run
from casl.broker import Broker
from casl.client import Client

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIAGE = os.path.join(_ROOT, "examples", "projects", "triage")


def _cond():
    return conductor.Conductor(TRIAGE)


def test_seam_bindings_resolve():
    c = _cond()
    assert c.seam_ok and not c.seam_violations
    assert c.bindings == {"classify": ("Triage", "Classify", "oracle"),
                          "notify": ("Triage", "Notify", "effect")}


def test_conduct_ok_crosses_the_broker():
    cr = _cond().run(scenario="ok", approve=True, env={"budget": 100, "question": "classify"})
    assert cr.run.outcome == "completed" and cr.run.last_verdict == "ok"
    t = "\n".join(cr.run.trace)
    assert "⟨oracle⟩" in t                       # oracle dispatched through the broker
    assert "broker granted »mail«" in t          # effect dispatched through the broker
    assert "served by provider 'notify'" in t    # CEP-0078 runtime: effect routed through its signed provider
    assert "»mail«⟵notify" in cr.summary          # the provider is surfaced in the conductor summary
    assert cr.site_artifact == {"Triage:Classify": "classify", "Triage:Notify": "notify"}


def test_default_deny_at_approval_gate_blocks_the_effect():
    cr = _cond().run(scenario="ok", approve=False, env={"budget": 100})
    t = "\n".join(cr.run.trace)
    assert "broker granted »mail«" not in t      # no effect dispatched
    assert cr.run.outcome == "completed"          # Hold branch → Done → end


def test_tool_denied_when_capability_not_granted():
    # a broker that grants NO tools → the mail effect is denied at the broker (deny-by-default),
    # even though the human approved. The conductor halts.
    broker = Broker(backend=oracle.MockBackend("ok"), granted_tools=set())
    client = Client(broker=broker, capabilities=["oracle", "effect"])
    cr = _cond().run(client=client, approve=True, env={"budget": 100})
    assert cr.run.outcome == "tool_denied"


def test_provider_denied_when_capability_not_declared():
    # the client declares no llm:claude, but we request provider=claude → broker -32011 → the
    # conductor surfaces a clean broker_denied (no crash).
    broker = Broker(backend=oracle.MockBackend("ok"), granted_tools={"mail"})
    client = Client(broker=broker, capabilities=["oracle", "effect"])
    cr = _cond().run(client=client, provider="claude", approve=True, env={"budget": 100})
    assert cr.run.outcome == "broker_denied"


def test_provider_allowed_when_declared():
    broker = Broker(backend=oracle.MockBackend("ok"), granted_tools={"mail"})
    client = Client(broker=broker, capabilities=["oracle", "effect", "llm:claude"])
    cr = _cond().run(client=client, provider="claude", approve=True, env={"budget": 100})
    assert cr.run.outcome == "completed"


def test_overspend_is_flagged_at_the_broker_boundary():
    # H4: the contract monitor flags the oracle overspend (measured > budget) even though the human
    # approved the send — the monitor verdict is recorded regardless.
    cr = _cond().run(scenario="overspend", approve=True, env={"budget": 100})
    assert cr.run.last_verdict == "violation"


def test_conductor_gates_an_inadmissible_hull(tmp_path):
    # the conductor proves the hull BEFORE executing; an inadmissible spec is aborted, never run.
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl.toml").write_text('name = "bad"\nversion = "0.1.0"\n')
    # an un-dominated effect (no approval gate) ⇒ LH-Q-011 MUST violation
    (tmp_path / "casl" / "bad.casl").write_text(
        "protocol Bad {\n  roles A, B;\n  agent A caps { mail(to) scope \"m\" mode write ttl 1 sig \"x\"; }\n"
        "  A -> B : Go() uses mail;\n}\n")
    cr = conductor.Conductor(str(tmp_path)).run(approve=True)
    assert cr.run.outcome == "not_admissible"


def test_inprocess_interpreter_path_unchanged():
    # run_protocol WITHOUT a dispatch is byte-for-byte the proven single-file interpreter.
    r = _run.run_protocol(core.G_OK, oracle.MockBackend("ok"), {"budget": 100, "question": "q"})
    assert r.outcome == "completed"


def test_cli_run_project(capsys):
    args = argparse.Namespace(project=TRIAGE, file=None, protocol=None, provider=None, live=False,
                              scenario="ok", budget=100, question="q", max_loops=5, approve=True,
                              model=None, endpoint=None)
    from casl import check
    rc = check.cmd_run(args)
    out = capsys.readouterr().out
    assert rc == 0 and "conductor: triage" in out and "COMPLETED" in out


# -- CEP-0078 runtime side: a confined caller delegates to its provider, or is refused ---------------
def _triage_variant(tmp_path, toml_body):
    """A tmp project reusing the real (admissible, approval-gated) triage.casl with a custom manifest —
    exercises the runtime provider routing without authoring a new choreography."""
    (tmp_path / "casl").mkdir()
    shutil.copy(os.path.join(TRIAGE, "casl", "triage.casl"), tmp_path / "casl" / "triage.casl")
    (tmp_path / "casl.toml").write_text('name = "t"\nversion = "0.1.0"\n' + toml_body)
    return str(tmp_path)


_CONFINED_SECRETARY = ('[[artifact]]\nname = "secretary"\nkind = "generated"\nrequirement = "R"\n'
                       'grade = "G3"\nbody = "artifacts/secretary.py"\nimplements = "Triage:Notify"\n'
                       'confined = true\n')
_MAILER = ('[[artifact]]\nname = "mailer"\nkind = "external"\nrequirement = "R"\ngrade = "G3"\n'
           'provides = "mail"\n')


def test_confined_caller_delegates_to_provider(tmp_path):
    # a confined artifact realizing the mail effect site delegates to the signed mail provider at run time
    d = _triage_variant(tmp_path, _CONFINED_SECRETARY + _MAILER)
    cr = conductor.Conductor(d).run(scenario="ok", approve=True, env={"budget": 100})
    assert cr.run.outcome == "completed"
    assert "delegated to provider 'mailer'" in "\n".join(cr.run.trace)


def test_confined_caller_denied_without_provider_at_runtime(tmp_path):
    # the run-time twin of no-ambient-authority: a confined caller with no provider for its capability is
    # refused at dispatch (before the broker is even asked)
    d = _triage_variant(tmp_path, _CONFINED_SECRETARY)        # no mailer ⇒ no provider for `mail`
    cr = conductor.Conductor(d).run(scenario="ok", approve=True, env={"budget": 100})
    assert cr.run.outcome == "tool_denied"
    assert "no ambient authority" in "\n".join(cr.run.trace)
