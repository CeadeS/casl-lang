"""W19 completeness via the user/external as a completeness ORACLE (route C′): a conservative reject
can be lifted by a re-checkable certificate (oracle re-validates SAFETY + FAITHFULNESS to g), else by a
labelled G3 human attestation. The sound core keeps the safety verdict — the oracle only lifts rejects."""
from casl.core import Comm, Choice, Branch, End
from casl.spike_proj_mpst import project, LSend, LRecv, LEnd
from casl import completeness as K, semantics_sync as S

_G = Comm("C", "A", "m", (), Choice("A", "J", (Branch("l1", (), End()), Branch("l2", (), End()))))
_ROLES = S.collect_roles(_G)


def test_projection_is_a_valid_certificate():
    cert = {r: project(_G, r) for r in _ROLES}            # g's own projection implements g
    assert K.faithful(_G, cert, _ROLES) is True
    ok, _ = K.accept_with_certificate(_G, cert)
    assert ok is True


def test_unsafe_certificate_rejected():
    cert = {r: project(_G, r) for r in _ROLES}
    cert["C"] = LEnd()                                    # C bows out early → deadlock
    ok, why = K.accept_with_certificate(_G, cert)
    assert ok is False and "not safe" in why


def test_unfaithful_but_safe_certificate_rejected():
    # a perfectly safe endpoint system that does NOT implement g (wrong label) must be rejected
    g = Comm("C", "A", "m", (), End())
    cert = {"C": LSend("A", "x", (), LEnd()), "A": LRecv("C", "x", (), LEnd())}   # safe, but label x≠m
    ok, why = K.accept_with_certificate(g, cert)
    assert ok is False and "faithfully" in why


def test_attestation_fallback():
    ok, _ = K.attest(_G, "Martin", "hand-reviewed, safe")
    assert ok is True
    ok2, _ = K.attest(_G, "", "")                         # deny-by-default without a human + rationale
    assert ok2 is False
