"""A1 — forwarding fidelity (CERT-FID) + interpreter-enforced forwarding.

CERT-FID is the F* lemma `fstar/Forwarding.fst` (machine-checked, 0 admits): a forwarded payload is
delivered UNCHANGED, so identity forwarding + contract entailment ⇒ the destination satisfies its
contract BY PROOF. When present, `grade_flow` re-bases a forwarded+entailed site to G0 (tested in
test_grade_flow.py). Here we test the certificate gate itself and the runtime half (run.py honoring
the forward edge). See docs/analyses/forwarding-fidelity-a1.md.
"""
import os
import re

from casl import core
from casl import grade_flow as gf
from casl import oracle
from casl import run as casl_run

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FID = os.path.join(_ROOT, "fstar", "Forwarding.fst")


def test_cert_fid_module_present_and_hole_free():
    assert os.path.exists(_FID), "CERT-FID module fstar/Forwarding.fst must ship with the repo"
    src = open(_FID, encoding="utf-8").read()
    body = re.sub(r"//[^\n]*", "", re.sub(r"\(\*.*?\*\)", "", src, flags=re.S))
    assert re.search(r"\b(admit|assume|magic|sorry)\b", body) is None, "CERT-FID must be hole-free"
    # the load-bearing theorems are present
    assert "let rebase_sound" in src and "fidelity" in src and "let rec fidelity_gen" in src


def test_cert_fid_verified_predicate_true():
    assert gf.cert_fid_verified() is True


def test_runtime_forward_honored():
    # C->A: Check(n) ; A->C: Relay(n = Check.n) ; end.  The source is produced upstream, so the
    # runner HONORS the forward edge.
    n = core.Field("n", "Int")
    n_fwd = core.Field("n", "Int", source="Check.n")
    g = core.Comm("C", "A", "Check", (n,),
                  core.Comm("A", "C", "Relay", (n_fwd,), core.End()))
    r = casl_run.run_protocol(g, oracle.MockBackend("ok"), {}, max_loops=3)
    assert r.outcome == "completed"
    assert r.forwards == ["Relay.n = Check.n"]


def test_runtime_forward_violation_when_source_unbound():
    # Relay forwards from Missing.x, which is never produced → interpreter-enforced forwarding aborts.
    n_fwd = core.Field("n", "Int", source="Missing.x")
    g = core.Comm("A", "C", "Relay", (n_fwd,), core.End())
    r = casl_run.run_protocol(g, oracle.MockBackend("ok"), {}, max_loops=3)
    assert r.outcome == "forward_violation"
    assert r.forwards == []
