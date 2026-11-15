"""SP-5 — the LLM-proposes / F*-decides proof loop. Integrity is fail-closed: only F* accepts,
and a candidate with any proof hole is rejected before F* even runs."""
import pytest

from casl import proof_loop as P


def test_proof_holes_detected():
    assert P.proof_holes("let x = admit ()") == ["admit"]
    assert P.proof_holes("foo (assume bar) sorry") == ["assume", "sorry"]
    assert P.proof_holes("let x = () // clean") == []


def test_fail_closed_rejects_holes_without_running_fstar():
    # no F* needed: a candidate containing `admit` is rejected outright (cannot bypass the prover)
    ok, msg = P.verify_candidate("let l (x:int) : Lemma (x == x) =", "  = admit ()")
    assert ok is False and "admit" in msg


def test_pending_goals_are_not_claimed_proved():
    # the hard residual goals are honestly open / bounded — never silently "proved"
    assert {g.status for g in P.PENDING_GOALS} <= {"open", "bounded"}
    assert all(g.status != "proved" for g in P.PENDING_GOALS)


_GOOD = """  match l with
  | LEnd | LVar _ -> ()
  | LRec _ c | LSnd _ _ c | LRcv _ _ c -> lsize_pos c
  | LIntC _ _ | LExtC _ _ -> ()"""

_HDR = "let rec lsize_pos (l:ltyp) : Lemma (ensures lsize l >= 1) (decreases l) ="


@pytest.mark.skipif(not P.toolchain_available(), reason="F* toolchain / CASL.fst absent")
def test_loop_closes_a_real_core_lemma():
    g = P.ProofGoal("lsize_pos", _HDR)
    res = P.attempt(g, P.MockGenerator(["  = ()", _GOOD]), max_iters=3)   # 1st bad, 2nd good
    assert res["verified"] is True
    assert res["iters"] == 2


@pytest.mark.skipif(not P.toolchain_available(), reason="F* toolchain / CASL.fst absent")
def test_loop_fails_closed_on_a_false_goal():
    g = P.ProofGoal("false_goal",
                    "let lsize_ge2 (l:ltyp) : Lemma (ensures lsize l >= 2) =")
    res = P.attempt(g, P.MockGenerator(["  ()"]), max_iters=1)            # false ⇒ F* rejects
    assert res["verified"] is False
