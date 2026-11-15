"""CASL project model + manifest (docs/analyses/project-structure-and-modules.md)."""
import os
import pytest

from casl import project


def test_init_scaffolds_layout(tmp_path):
    d = str(tmp_path / "proj")
    man = project.init_project(d, "demo")
    assert os.path.exists(man)
    for sub in ("requirements", "casl", "artifacts", "attestations", "deps.lock", ".casl/attest.pub"):
        assert os.path.exists(os.path.join(d, sub)), sub
    m = project.load_manifest(d)
    assert m.name == "demo" and m.artifacts == []


def _write(tmp_path, body: str) -> str:
    d = tmp_path / "p"
    d.mkdir()
    (d / "casl.toml").write_text(body, encoding="utf-8")
    return str(d)


def test_manifest_parses_artifacts(tmp_path):
    d = _write(tmp_path, '''
name = "demo"
version = "0.1.0"
[attest]
pubkey = ".casl/attest.pub"
[[artifact]]
name = "smtp_send"
kind = "generated"
requirement = "LH-LOCAL-001"
grade = "G3"
body = "artifacts/smtp_send.py"
[[artifact]]
name = "requests"
kind = "external"
requirement = "LH-LOCAL-002"
grade = "G2"
''')
    m = project.load_manifest(d)
    assert m.name == "demo" and m.attest_pubkey == ".casl/attest.pub"
    a = {x.name: x for x in m.artifacts}
    assert a["smtp_send"].kind == "generated" and a["smtp_send"].trace == "full" and a["smtp_send"].owned()
    assert a["smtp_send"].floor() == "G3"           # generated ⇒ unprovable floor
    assert a["requests"].kind == "external" and a["requests"].trace == "burden" and not a["requests"].owned()


def test_unknown_kind_rejected(tmp_path):
    d = _write(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="a"\nkind="trustme"\ngrade="G0"\nbody="b.py"\n')
    with pytest.raises(project.ManifestError):
        project.load_manifest(d)


def test_trace_regime_follows_ownership_not_free_choice(tmp_path):
    # declaring an owned artifact as `burden` (the self-downgrade escape hatch) is rejected (LH-P-009)
    d = _write(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="a"\nkind="generated"\ngrade="G3"\ntrace="burden"\nbody="b.py"\n')
    with pytest.raises(project.ManifestError):
        project.load_manifest(d)


def test_generated_requires_body(tmp_path):
    d = _write(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="a"\nkind="generated"\ngrade="G3"\n')
    with pytest.raises(project.ManifestError):
        project.load_manifest(d)
