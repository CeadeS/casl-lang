"""Human-identity attestation (LH-Q-016/017/018) + Tier-0 obligation gate (LH-G-006, LH-Q-019)."""
import json
import os

from casl import attestation as att
from casl import obligation_gate as gate
from casl import project


# ---- attestation.verify layers ----
def _rec(**kw):
    base = dict(artifact="a", sha256="sha256:x", requirement="LH-LOCAL-1",
                producer="llm", signer="Alice", sig_kind="git")
    base.update(kw)
    return att.AttRecord(**base)


def test_hash_mismatch_expires(tmp_path):
    body = tmp_path / "a.py"; body.write_text("real\n")
    ok, why = att.verify(_rec(sha256="sha256:stale"), str(body))
    assert not ok and "EXPIRED" in why


def test_self_attestation_forbidden(tmp_path):
    body = tmp_path / "a.py"; body.write_text("x\n")
    h = att.content_hash(str(body))
    ok, why = att.verify(_rec(sha256=h, producer="agent", signer="agent"), str(body))
    assert not ok and "self-attestation" in why


def test_plaintext_sig_insufficient(tmp_path):
    body = tmp_path / "a.py"; body.write_text("x\n")
    h = att.content_hash(str(body))
    ok, why = att.verify(_rec(sha256=h, producer="human", signer="Alice", sig_kind="env-plaintext"), str(body))
    assert not ok and "INSUFFICIENT" in why


def test_llm_needs_git_signature(tmp_path):
    body = tmp_path / "a.py"; body.write_text("x\n")
    h = att.content_hash(str(body))
    ok, why = att.verify(_rec(sha256=h, producer="llm", signer="Alice", sig_kind="none"), str(body))
    assert not ok  # llm-produced without a git-identity signature is denied


# ---- obligation gate composition ----
def _project(tmp_path, manifest: str):
    d = tmp_path / "proj"
    project.init_project(str(d))
    (d / "casl.toml").write_text(manifest, encoding="utf-8")
    return d


def test_gate_passes_verified_artifact(tmp_path):
    # a `verified` (decidable) artifact is discharged by proof — needs body+requirement, NO signature
    d = _project(tmp_path, 'name="p"\nversion="1"\n[[artifact]]\nname="bc"\nkind="verified"\n'
                           'requirement="LH-LOCAL-1"\ngrade="G0"\nbody="artifacts/bc.py"\n')
    (d / "artifacts" / "bc.py").write_text("def bc():\n    return True\n")
    ok, lines = gate.check_project(str(d), repo=None)   # no git ⇒ trace unchecked, but verified needs no sig
    assert ok, lines


def test_gate_denies_generated_without_attestation(tmp_path):
    d = _project(tmp_path, 'name="p"\nversion="1"\n[[artifact]]\nname="smtp"\nkind="generated"\n'
                           'requirement="LH-LOCAL-1"\ngrade="G3"\nbody="artifacts/smtp.py"\n')
    (d / "artifacts" / "smtp.py").write_text("def smtp():\n    pass\n")
    ok, lines = gate.check_project(str(d), repo=None)
    assert not ok and any("no attestation record" in l for l in lines)


def test_gate_denies_unpinned_dependency(tmp_path):
    d = _project(tmp_path, 'name="p"\nversion="1"\n')
    (d / "deps.lock").write_text("requests 2.32.3 accepted-by:Alice\n")   # no sha256 pin
    ok, lines = gate.check_project(str(d), repo=None)
    assert not ok and any("dependency burden" in l for l in lines)


def test_effective_grade_is_weakest_link(tmp_path):
    d = _project(tmp_path, 'name="p"\nversion="1"\n'
                           '[[artifact]]\nname="bc"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="artifacts/bc.py"\n'
                           '[[artifact]]\nname="smtp"\nkind="generated"\nrequirement="R2"\ngrade="G3"\nbody="artifacts/smtp.py"\n')
    man = project.load_manifest(str(d))
    assert gate.effective_grade(man) == "G3"            # weakest link (generated ⇒ G3) dominates


def test_grade_by_requirement_is_finer_than_global(tmp_path):
    # CEP-0070 model A: the per-requirement view keeps R1 at G0 though the global weakest link is G3
    d = _project(tmp_path, 'name="p"\nversion="1"\n'
                           '[[artifact]]\nname="bc"\nkind="verified"\nrequirement="R1"\ngrade="G0"\nbody="artifacts/bc.py"\n'
                           '[[artifact]]\nname="smtp"\nkind="generated"\nrequirement="R2"\ngrade="G3"\nbody="artifacts/smtp.py"\n')
    man = project.load_manifest(str(d))
    assert gate.grade_by_requirement(man) == {"R1": "G0", "R2": "G3"}
    assert gate.effective_grade(man) == "G3"            # headline unchanged (still the weakest link)


def test_second_signer_requires_n_distinct_valid(tmp_path):
    # D3 second-signer: signers=2 ⇒ a single (here git-unverifiable) record is not enough
    d = _project(tmp_path, 'name="p"\nversion="1"\n[[artifact]]\nname="smtp"\nkind="generated"\n'
                           'requirement="R"\ngrade="G3"\nbody="artifacts/smtp.py"\nsigners=2\n')
    (d / "artifacts" / "smtp.py").write_text("x = 1\n")
    h = att.content_hash(str(d / "artifacts" / "smtp.py"))
    (d / "attestations" / "smtp.json").write_text(json.dumps(
        {"artifact": "smtp", "sha256": h, "requirement": "R",
         "producer": "llm", "signer": "Alice", "sig_kind": "git"}))
    ok, lines = gate.check_project(str(d), repo=None)
    assert not ok and any("needs 2 distinct" in l for l in lines)


def test_signature_concentration_surfaces_per_signer(tmp_path):
    # D3 risk-surfacing: one signer vouching for several unprovable artifacts is made visible
    d = _project(tmp_path, 'name="p"\nversion="1"\n'
                 '[[artifact]]\nname="a1"\nkind="generated"\nrequirement="R1"\ngrade="G3"\nbody="artifacts/a1.py"\n'
                 '[[artifact]]\nname="a2"\nkind="oracle"\nrequirement="R2"\ngrade="G3"\nbody="artifacts/a2.py"\n')
    for n in ("a1", "a2"):
        (d / "artifacts" / f"{n}.py").write_text("x = 1\n")
        (d / "attestations" / f"{n}.json").write_text(json.dumps(
            {"artifact": n, "sha256": "sha256:x", "requirement": "R",
             "producer": "llm", "signer": "Martin", "sig_kind": "git"}))
    man = project.load_manifest(str(d))
    assert gate.signature_concentration(str(d), man) == {"Martin": ["a1", "a2"]}
