"""
Spike C — data contracts via SMT (Z3)  [LH-Q-004, verification stage S]

Shows the "S" stage of the provability tetrad: discharge a decidable
data-plane contract statically with Z3 (QF_LIA fragment), with no runtime cost.

We use the budget split that arises in the Reject/Retry branch of BudgetedQA:
  draft 1 costs c1, retry draft costs c2.
  Contract on each Draft: cost <= remaining budget.

  Lemma (budget safety): if  c1 <= b  and  c2 <= b - c1   then  c1 + c2 <= b.
     -> we prove it by checking the NEGATION is UNSAT.

  Counterexample (why the per-step contract is necessary): if we only require
  c1 <= b  and  c2 <= b   (naive), then c1 + c2 <= b can FAIL.
     -> Z3 returns a SAT model (a concrete overspend), i.e. a violation trace.
"""
from __future__ import annotations
from z3 import Int, Solver, sat, unsat, Not, And, Implies


def prove_budget_safety():
    b, c1, c2 = Int("b"), Int("c1"), Int("c2")
    dom = [b >= 0, c1 >= 0, c2 >= 0]
    # contracts (per-step, budget-aware)
    contracts = And(c1 <= b, c2 <= b - c1)
    goal = c1 + c2 <= b
    s = Solver()
    s.add(dom)
    s.add(Not(Implies(contracts, goal)))   # negation of the lemma
    res = s.check()
    return res  # expect unsat -> lemma holds


def find_overspend_without_stepwise_contract():
    b, c1, c2 = Int("b"), Int("c1"), Int("c2")
    s = Solver()
    s.add(b >= 0, c1 >= 0, c2 >= 0)
    s.add(c1 <= b, c2 <= b)            # naive contract (NOT budget-aware)
    s.add(c1 + c2 > b)                 # overspend
    res = s.check()
    model = s.model() if res == sat else None
    return res, model


def run():
    print("=" * 72)
    print("SPIKE C — SMT data contracts (Z3, QF_LIA)")
    print("=" * 72)

    res = prove_budget_safety()
    proven = (res == unsat)
    print("  Lemma  (c1<=b ∧ c2<=b-c1) → c1+c2<=b")
    print(f"    negation check: {res}  =>  {'PROVEN (contract enforces budget safety)' if proven else 'NOT proven'}")

    res2, model = find_overspend_without_stepwise_contract()
    print("  Necessity of the step-wise contract (naive c1<=b ∧ c2<=b):")
    if res2 == sat:
        b = model.eval(Int("b")); c1 = model.eval(Int("c1")); c2 = model.eval(Int("c2"))
        print(f"    counterexample found: b={b}, c1={c1}, c2={c2}  -> c1+c2 > b (overspend)")
    else:
        print(f"    {res2} (no counterexample)")

    return {"budget_safety_proven": proven, "overspend_counterexample": res2 == sat}


if __name__ == "__main__":
    run()
