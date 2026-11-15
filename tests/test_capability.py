"""CEP-0078 — the capability-provider gate (rung-2, by construction). No ambient I/O authority: providers
are single-purpose + unambiguous; a confined artifact's used capabilities must each resolve to a granted
provider; the I/O grade is the provider's floor. The human-signature requirement is enforced by the
obligation gate. See docs/confinement.md."""
import os

from casl import capability as cap
from casl import obligation_gate as og
from casl import project
from casl.project import Artifact, Manifest


def _man(*arts):
    return Manifest(name="t", version="0.1.0", attest_pubkey=None, artifacts=list(arts), root=".")


def _art(name, kind="external", grade="G3", **kw):
    return Artifact(name=name, kind=kind, requirement="R", grade=grade,
                    trace=("burden" if kind == "external" else "full"),
                    body=kw.pop("body", None), **kw)


# -- pure provider checks --------------------------------------------------
def test_single_purpose_unambiguous_ok():
    m = _man(_art("mailer", provides="mail"), _art("httpx", provides="http:api"))
    ok, viol = cap.check_providers(m)
    assert ok and not viol
    assert set(cap.provider_index(m)) == {"mail", "http:api"}


def test_duplicate_provider_rejected():
    m = _man(_art("mailer1", provides="mail"), _art("mailer2", provides="mail"))
    ok, viol = cap.check_providers(m)
    assert not ok and any("provided by >1" in v for v in viol)


def test_provider_cannot_be_confined():
    m = _man(_art("mailer", kind="generated", body="a/m.py", provides="mail", confined=True))
    ok, viol = cap.check_providers(m)
    assert not ok and any("cannot itself be `confined`" in v for v in viol)


# -- no ambient authority (needs a choreography with an effect site) -------
_CASL = ('protocol X {\n  roles A, B;\n'
         '  agent A caps { widget(x) scope "w" mode write ttl 1 sig "s"; }\n'
         '  A -> B : Go() uses widget;\n}\n')


def _project(tmp_path, *artifact_tomls):
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl" / "x.casl").write_text(_CASL)
    body = "\n".join(artifact_tomls)
    (tmp_path / "casl.toml").write_text(f'name = "t"\nversion = "0.1.0"\n{body}\n')
    return str(tmp_path)


_CALLER = ('[[artifact]]\nname = "caller"\nkind = "generated"\nrequirement = "R1"\n'
           'grade = "G3"\nbody = "artifacts/caller.py"\nimplements = "X:Go"\nconfined = true')
_PROVIDER = ('[[artifact]]\nname = "widget_provider"\nkind = "external"\nrequirement = "R2"\n'
             'grade = "G3"\nprovides = "widget"')


def test_confined_caller_with_provider_ok(tmp_path):
    d = _project(tmp_path, _CALLER, _PROVIDER)
    m = project.load_manifest(os.path.join(d, "casl.toml"))
    ok, viol = cap.check_no_ambient_authority(m, d)
    assert ok and not viol


def test_confined_caller_without_provider_rejected(tmp_path):
    d = _project(tmp_path, _CALLER)                       # no provider for `widget`
    m = project.load_manifest(os.path.join(d, "casl.toml"))
    ok, viol = cap.check_no_ambient_authority(m, d)
    assert not ok and any("no ambient authority" in v and "widget" in v for v in viol)


def test_io_grade_is_provider_floor(tmp_path):
    d = _project(tmp_path, _CALLER, _PROVIDER)
    m = project.load_manifest(os.path.join(d, "casl.toml"))
    assert cap.io_grade(m, d) == {"caller": "G3"}          # external provider floors at G3


def test_unconfined_caller_is_not_gated(tmp_path):
    # a HUMAN-authored (verified) caller, NOT confined, may do its own I/O — no ambient-authority check
    # applies. (An LLM-authored generated/oracle caller may NOT be unconfined — see test_confinement_default.)
    caller = (_CALLER.replace('kind = "generated"', 'kind = "verified"')
                     .replace("confined = true", "confined = false"))
    d = _project(tmp_path, caller)
    m = project.load_manifest(os.path.join(d, "casl.toml"))
    ok, _ = cap.check_no_ambient_authority(m, d)
    assert ok


# -- the signature requirement is enforced by the obligation gate ----------
def test_provider_requires_human_signature(tmp_path):
    # a `verified` provider would normally be discharged by proof, but granting I/O is an unprovable trust
    # act ⇒ the obligation gate now requires a human attestation (CEP-0078). No record ⇒ gate fails.
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl" / "x.casl").write_text(_CASL)
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "io.py").write_text("# single-purpose widget provider\n")
    (tmp_path / "casl.toml").write_text(
        'name = "t"\nversion = "0.1.0"\n'
        '[[artifact]]\nname = "io"\nkind = "verified"\nrequirement = "R"\ngrade = "G0"\n'
        'body = "artifacts/io.py"\nprovides = "widget"\n')
    ok, lines = og.check_project(str(tmp_path), repo=None)
    assert not ok
    assert any("io" in ln and "attestation" in ln.lower() for ln in lines)


def test_no_providers_is_backward_compatible(tmp_path):
    # a manifest with no providers / no confined artifacts is inert under the new gate
    (tmp_path / "casl").mkdir()
    (tmp_path / "casl.toml").write_text('name = "t"\nversion = "0.1.0"\n')
    m = project.load_manifest(os.path.join(tmp_path, "casl.toml"))
    assert cap.check(m, str(tmp_path)) == (True, [])
