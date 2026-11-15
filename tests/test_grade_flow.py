"""Grade flow-graph — per-site grade along the typed-seam edges (D1-B / CEP-0070)."""
from casl import grade_flow as gf
from casl import project

CASL = ("protocol P {\n  roles A, B;\n  A -> B : Check(n: Int) [n >= 0] verified;\n"
        "  B -> A : Draft(t: Str) [len(t) > 0] oracle;\n  B -> A : Send() uses mail irreversible;\n}\n")

MAN = ('name="x"\nversion="1"\n'
       '[[artifact]]\nname="chk"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="c.py"\nimplements="P:Check"\n'
       '[[artifact]]\nname="dr"\nkind="oracle"\nrequirement="R2"\ngrade="G3"\nimplements="P:Draft"\n')


def _proj(tmp_path):
    d = tmp_path / "p"
    project.init_project(str(d))
    (d / "casl.toml").write_text(MAN, encoding="utf-8")
    (d / "casl" / "P.casl").write_text(CASL, encoding="utf-8")
    return d


def test_upstream_keeps_strong_grade(tmp_path):
    d = _proj(tmp_path)
    fg = gf.flow_grades(project.load_manifest(str(d)), str(d))
    assert fg[("P", "Check")] == "G0"     # verified, nothing weak upstream
    assert fg[("P", "Draft")] == "G3"     # the oracle downstream degrades — but Check stayed G0


def test_boundaries_detected(tmp_path):
    d = _proj(tmp_path)
    bn = gf.containment_boundaries(project.load_manifest(str(d)), str(d))
    assert any("Check" in b and "verified" in b for b in bn)
    assert any("Draft" in b and "monitored" in b for b in bn)


def test_rebase_candidate_detected_but_not_applied(tmp_path):
    # Model-C: a verified Check proves [n>=0]; a downstream oracle Draft requires the SAME [n>=0] over n.
    # SMT entailment detects the candidate, but it is NOT applied (no verified data lineage in MPST).
    casl = ("protocol Q {\n  roles A, B;\n  A -> B : Check(n: Int) [n >= 0] verified;\n"
            "  B -> A : Draft(n: Int) [n >= 0] oracle;\n}\n")
    man = ('name="x"\nversion="1"\n'
           '[[artifact]]\nname="chk"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="c.py"\nimplements="Q:Check"\n'
           '[[artifact]]\nname="dr"\nkind="oracle"\nrequirement="R2"\ngrade="G3"\nimplements="Q:Draft"\n')
    d = tmp_path / "q"
    project.init_project(str(d))
    (d / "casl.toml").write_text(man, encoding="utf-8")
    (d / "casl" / "Q.casl").write_text(casl, encoding="utf-8")
    m = project.load_manifest(str(d))
    assert ("Q:Check", "Q:Draft") in gf.rebase_candidates(m, str(d))   # entailment finds the candidate
    assert gf.flow_grades(m, str(d))[("Q", "Draft")] == "G3"           # but NOT applied — stays conservative


_FWD_CASL = ("protocol P {\n  roles A, B;\n  A -> B : Check(n: Int) [n >= 0] verified;\n"
             "  B -> A : Relay(n: Int = Check.n) [n >= 0];\n}\n")
_FWD_MAN = ('name="x"\nversion="1"\n'
            '[[artifact]]\nname="chk"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="c.py"\nimplements="P:Check"\n'
            '[[artifact]]\nname="rl"\nkind="generated"\nrequirement="R2"\ngrade="G3"\nbody="r.py"\nimplements="P:Relay"\n')


def _fwd_proj(tmp_path):
    d = tmp_path / "p"
    project.init_project(str(d))
    (d / "casl.toml").write_text(_FWD_MAN, encoding="utf-8")
    (d / "casl" / "P.casl").write_text(_FWD_CASL, encoding="utf-8")
    return d


def test_a1_forwarding_rebase_g0_with_cert(tmp_path):
    # Relay.n is FORWARDED from the verified Check (proves [n>=0]); Relay also requires [n>=0].
    # With CERT-FID (fstar/Forwarding.fst) present, the re-base is PROVED → G0.
    assert gf.cert_fid_verified()                                       # the lemma ships in this repo
    d = _fwd_proj(tmp_path)
    m = project.load_manifest(str(d))
    assert gf.flow_grades(m, str(d), apply_rebase=False)[("P", "Relay")] == "G3"   # conservative
    assert gf.applied_rebases(m, str(d)) == {("P", "Relay"): "G0"}                 # CERT-FID → G0 grant
    assert gf.flow_grades(m, str(d))[("P", "Relay")] == "G0"                       # applied


def test_a2_forwarding_rebase_falls_back_to_g2_without_cert(tmp_path, monkeypatch):
    # Without CERT-FID (lemma absent / holed), the SAME forward is still SOUND but capped at the
    # structural G2 (A2) — never over-claims. (Models a checkout where Forwarding.fst is missing.)
    monkeypatch.setattr(gf, "cert_fid_verified", lambda: False)
    d = _fwd_proj(tmp_path)
    m = project.load_manifest(str(d))
    assert gf.applied_rebases(m, str(d)) == {("P", "Relay"): "G2"}
    assert gf.flow_grades(m, str(d))[("P", "Relay")] == "G2"
