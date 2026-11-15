"""Typed .casl↔artifact seam — manifest `implements` binds an artifact to a site (LH-F-012 full / CEP-0074)."""
from casl import project, seam

CASL = ("protocol P {\n  roles A, B;\n  A -> B : Ask(q: Str);\n"
        "  B -> A : Answer(a: Str) oracle;\n  B -> A : Send() uses mail irreversible;\n}\n")


def _proj(tmp_path, manifest):
    d = tmp_path / "p"
    project.init_project(str(d))
    (d / "casl.toml").write_text(manifest, encoding="utf-8")
    (d / "casl" / "P.casl").write_text(CASL, encoding="utf-8")
    return d


def test_binding_resolves(tmp_path):
    d = _proj(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="cls"\nkind="oracle"\n'
                        'requirement="R1"\ngrade="G3"\nimplements="P:Answer"\n')
    ok, _v, binds = seam.check_seam(project.load_manifest(str(d)), str(d))
    assert ok and binds["cls"][1] == "Answer" and binds["cls"][2] == "oracle"


def test_kind_mismatch_rejected(tmp_path):
    d = _proj(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="bc"\nkind="verified"\n'
                        'requirement="R"\ngrade="G0"\nbody="b.py"\nimplements="P:Answer"\n')
    ok, viol, _ = seam.check_seam(project.load_manifest(str(d)), str(d))
    assert not ok and any("cannot realize" in v for v in viol)


def test_unknown_site_rejected(tmp_path):
    d = _proj(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="cls"\nkind="oracle"\n'
                        'requirement="R"\ngrade="G3"\nimplements="P:Nope"\n')
    ok, viol, _ = seam.check_seam(project.load_manifest(str(d)), str(d))
    assert not ok and any("no site" in v for v in viol)


def test_site_requirements_and_unbound(tmp_path):
    d = _proj(tmp_path, 'name="x"\nversion="1"\n[[artifact]]\nname="cls"\nkind="oracle"\n'
                        'requirement="LH-LOCAL-9"\ngrade="G3"\nimplements="P:Answer"\n')
    man = project.load_manifest(str(d))
    assert seam.site_requirements(man, str(d)) == {("P", "Answer"): "LH-LOCAL-9"}
    assert any("Send" in u for u in seam.unbound_sites(man, str(d)))   # the effect site is unbound
