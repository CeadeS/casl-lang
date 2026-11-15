"""Confinement-by-default for LLM-authored artifacts (docs/analyses/confinement-by-default-llm-artifacts.md).

Pins the three load-bearing properties:
  · LOADER  — an LLM-authored kind (generated/oracle) cannot opt out of confinement, and the flag is
              parsed strictly (no truthy-string fail-open).
  · GATE    — an un-confined generated/oracle artifact is DENIED (confinement-by-default at admission).
  · RUNTIME — a confined activity FAILS CLOSED (refuses) where the host cannot enforce confinement,
              instead of running the body with full ambient authority.
  · CAPABILITY — a confined *read* brain (broker-mediated oracle boundary) passes no-ambient; only an
              EFFECT capability needs a signed single-purpose provider.
"""
import os
import sys

import pytest

from casl import activity
from casl import capability as cap
from casl import host
from casl import obligation_gate as og
from casl import project
from casl.project import Artifact, Manifest


def _load(tmp_path, toml_body):
    (tmp_path / "casl.toml").write_text(f'name = "t"\nversion = "0.1.0"\n{toml_body}\n')
    return project.load_manifest(os.path.join(str(tmp_path), "casl.toml"))


_GEN = '[[artifact]]\nname = "b"\nkind = "generated"\nrequirement = "R"\ngrade = "G3"\nbody = "a/b.py"\n'


# -- LOADER: opt-out impossible for LLM kinds, strict bool --------------------
def test_generated_cannot_opt_out_unconfined(tmp_path):
    with pytest.raises(project.ManifestError):
        _load(tmp_path, _GEN + "unconfined = true")


def test_generated_native_alias_rejected(tmp_path):
    with pytest.raises(project.ManifestError):
        _load(tmp_path, _GEN + "native = true")


def test_generated_cannot_set_confined_false(tmp_path):
    with pytest.raises(project.ManifestError):
        _load(tmp_path, _GEN + "confined = false")


def test_confined_must_be_strict_bool(tmp_path):
    # bool("false") is True — a mistyped security flag must be a hard error, never fail open
    with pytest.raises(project.ManifestError):
        _load(tmp_path, '[[artifact]]\nname = "b"\nkind = "verified"\nrequirement = "R"\n'
                        'grade = "G0"\nbody = "a/b.py"\nconfined = "false"')


def test_human_kind_opt_out_not_yet_available(tmp_path):
    # a human-authored kind may eventually opt out (P4) — until the graded obligation exists, claiming it
    # FAILS CLOSED rather than silently granting ambient authority
    with pytest.raises(project.ManifestError):
        _load(tmp_path, '[[artifact]]\nname = "b"\nkind = "verified"\nrequirement = "R"\n'
                        'grade = "G0"\nbody = "a/b.py"\nunconfined = true')


def test_generated_confined_omitted_loads_but_false(tmp_path):
    # omission still LOADS (backward compatible) — but the gate denies it (default-on at admission)
    m = _load(tmp_path, _GEN)
    assert m.artifacts[0].confined is False


# -- GATE: un-confined LLM kind is denied ------------------------------------
def _man(*arts):
    return Manifest(name="t", version="0.1.0", attest_pubkey=None, artifacts=list(arts), root=".")


def test_gate_denies_unconfined_generated(tmp_path):
    # build the project on disk; a generated artifact with confined omitted must be DENIED for confinement
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl" / "x.casl").write_text(
        'protocol X {\n  roles A, B;\n'
        '  agent A caps { compose(x) scope "llm" mode read ttl 1 sig "s"; }\n'
        '  A -> B : Triage() uses compose;\n}\n')
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "b.py").write_text("# brain\n")
    (tmp_path / "casl.toml").write_text(
        'name = "t"\nversion = "0.1.0"\n'
        '[[artifact]]\nname = "brain"\nkind = "generated"\nrequirement = "R"\ngrade = "G3"\n'
        'body = "artifacts/b.py"\nimplements = "X:Triage"\n')          # confined omitted
    ok, lines = og.check_project(str(tmp_path), repo=None)
    assert not ok
    assert any("must be `confined`" in ln for ln in lines)


# -- CAPABILITY: a confined READ brain passes no-ambient (broker-mediated) ----
def test_confined_read_brain_passes_no_ambient(tmp_path):
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl" / "x.casl").write_text(
        'protocol X {\n  roles A, B;\n'
        '  agent A caps { compose(x) scope "llm" mode read ttl 1 sig "s"; }\n'
        '  A -> B : Triage() uses compose;\n}\n')
    (tmp_path / "casl.toml").write_text(
        'name = "t"\nversion = "0.1.0"\n'
        '[[artifact]]\nname = "brain"\nkind = "generated"\nrequirement = "R"\ngrade = "G3"\n'
        'body = "a/b.py"\nimplements = "X:Triage"\nconfined = true\n')
    m = project.load_manifest(os.path.join(str(tmp_path), "casl.toml"))
    ok, viol = cap.check_no_ambient_authority(m, str(tmp_path))
    assert ok and not viol                                    # a read cap needs no provider


# -- RUNTIME: a confined activity fails closed where it can't be enforced -----
def test_can_enforce_is_false_off_linux():
    if not sys.platform.startswith("linux"):
        assert host.can_enforce() is False


def test_confined_activity_fails_closed(monkeypatch):
    # where the host cannot enforce, a confined activity REFUSES rather than running unconfined
    monkeypatch.setattr(activity._host, "can_enforce", lambda: False)
    act = activity.SubprocessActivity(command=[sys.executable, "-c", "print('{}')"],
                                      confined=True, name="brain")
    out = act.generate("q", 100)
    assert out.refused is True and "cannot enforce" in out.raw


def test_unconfined_activity_still_runs(monkeypatch):
    # a NON-confined activity is unaffected — it runs even when can_enforce() is False
    monkeypatch.setattr(activity._host, "can_enforce", lambda: False)
    src = ("import json,sys; json.loads(sys.stdin.readline());"
           "print(json.dumps({'answer': 'ok', 'cost': 1}))")
    act = activity.SubprocessActivity(command=[sys.executable, "-c", src], confined=False, name="x")
    out = act.generate("q", 100)
    assert not out.refused and out.answer == "ok"
