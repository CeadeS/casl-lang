"""
Spike D — monitor + dual-mock + property test  [LH-Q-005, LH-Q-006; stages M, T]

From the SAME local type + contract (BudgetedQA Draft, cost <= budget) we
synthesize, mechanically:
  (1) a runtime MONITOR for the A->J Draft boundary that assigns BLAME on a
      contract violation (the payload is from the oracle, so blame falls on
      the producing agent A) — verification stage M, LH-Q-005;
  (2) a DUAL-MOCK of A so J can be tested in isolation — LH-Q-006(a);
  (3) a PROPERTY generator/test asserting the monitor verdict matches the
      contract on random inputs — LH-Q-006(b), verification stage T.

Everything here is derived from the structural spec in casl_core, which is
the point: the same types that the proofs use also generate the tests.
"""
from __future__ import annotations
import random
from dataclasses import dataclass
from typing import Optional, Tuple
from casl import core


@dataclass(frozen=True)
class Draft:
    answer: str
    cost: int


@dataclass(frozen=True)
class Verdict:
    ok: bool
    blame: Optional[str]   # role to blame on violation, else None
    reason: str


def synth_monitor(contract: core.Contract, producer: core.Role):
    """Build a monitor from a contract relation. Supported forms:
       ('le', x, y)       — numeric: holds iff val(x) <= val(y); each operand is either a
                            variable (env[name]) OR an integer literal (used directly).
       ('nonempty', x, _) — string : holds iff len(env[x]) > 0   (W7: branch contracts)
    Violation always carries blame on the producing agent."""
    kind, lhs, rhs = contract.relation

    def _resolve(o, env):
        return o if isinstance(o, int) else env[o]

    def _show(o, env):
        return str(o) if isinstance(o, int) else f"{o}={env[o]}"

    def monitor(env: dict) -> Verdict:
        if kind == "le":
            l, r = _resolve(lhs, env), _resolve(rhs, env)
            if l <= r:
                return Verdict(True, None, f"{contract.text} holds ({_show(lhs, env)} <= {_show(rhs, env)})")
            return Verdict(False, producer,
                           f"{contract.text} VIOLATED ({_show(lhs, env)} > {_show(rhs, env)}) → blame {producer}")
        if kind == "nonempty":
            v = env.get(lhs, "")
            if len(str(v)) > 0:
                return Verdict(True, None, f"{contract.text} holds (len({lhs})>0)")
            return Verdict(False, producer,
                           f"{contract.text} VIOLATED (len({lhs})=0) → blame {producer}")
        return Verdict(False, producer, f"unsupported Contract relation {kind!r}")
    return monitor


def _collect_branch_contracts(g):
    """(producer, label, contract) for each choice branch carrying a contract."""
    out = []

    def walk(n):
        if isinstance(n, core.Comm):
            walk(n.cont)
            if n.on_crash is not None:
                walk(n.on_crash)
        elif isinstance(n, core.Choice):
            for b in n.branches:
                if b.contract is not None:
                    out.append((n.sender, b.label, b.contract))
                walk(b.cont)
        elif isinstance(n, core.Rec):
            walk(n.body)
    walk(g)
    return out


def branch_contract_monitors_sound(g):
    """W7: each branch contract is synthesized into a monitor that agrees with the
    contract on representative inputs (otherwise it is not enforceable)."""
    bad = []
    for producer, label, c in _collect_branch_contracts(g):
        m = synth_monitor(c, producer)
        kind = c.relation[0]
        lhs = c.relation[1]
        if kind == "nonempty":
            ok = (m({lhs: "x"}).ok is True) and (m({lhs: ""}).ok is False)
        elif kind == "le":
            rhs = c.relation[2]
            li, ri = isinstance(lhs, int), isinstance(rhs, int)
            if li and ri:                       # both literals: monitor must hit the fixed truth
                ok = (m({}).ok is (lhs <= rhs))
            elif ri:                            # lhs variable, rhs literal: boundary at rhs
                ok = (m({lhs: rhs}).ok is True) and (m({lhs: rhs + 1}).ok is False)
            elif li:                            # rhs variable, lhs literal: boundary at lhs
                ok = (m({rhs: lhs}).ok is True) and (m({rhs: lhs - 1}).ok is False)
            else:                               # both variables (previous behaviour)
                ok = (m({lhs: 0, rhs: 0}).ok is True) and (m({lhs: 1, rhs: 0}).ok is False)
        else:
            ok = False
        if not ok:
            bad.append((label, c.text))
    return (not bad), bad


def dual_mock_A(budget: int, overspend: int = 0) -> Draft:
    """A dual-mock standing in for agent A; lets us test J in isolation.
    Honest mock keeps cost within budget; overspend>0 simulates an oracle
    that breaks the contract."""
    return Draft(answer="(mock answer)", cost=budget + overspend)


def property_test(monitor, n: int = 2000, seed: int = 7) -> Tuple[int, int]:
    """The monitor verdict MUST agree with the contract on random inputs."""
    rng = random.Random(seed)
    failures = 0
    for _ in range(n):
        budget = rng.randint(0, 1000)
        cost = rng.randint(0, 1000)
        v = monitor({"cost": cost, "budget": budget})
        expected_ok = cost <= budget
        if v.ok != expected_ok:
            failures += 1
    return n, failures


def run():
    print("=" * 72)
    print("SPIKE D — monitor (blame) + dual-mock + property test")
    print("=" * 72)
    mon = synth_monitor(core.C_COST_LE_BUDGET, producer="A")

    # passing case
    d_ok = dual_mock_A(budget=100, overspend=0)
    v_ok = mon({"cost": d_ok.cost, "budget": 100})
    print(f"  pass-case  Draft(cost={d_ok.cost}, budget=100): "
          f"{'OK' if v_ok.ok else 'BLAME'} — {v_ok.reason}")

    # blaming case (oracle overspends)
    d_bad = dual_mock_A(budget=100, overspend=25)
    v_bad = mon({"cost": d_bad.cost, "budget": 100})
    print(f"  blame-case Draft(cost={d_bad.cost}, budget=100): "
          f"{'OK' if v_bad.ok else 'BLAME ' + str(v_bad.blame)} — {v_bad.reason}")

    n, fails = property_test(mon)
    print(f"  property test: {n} random cases, monitor vs contract mismatches = {fails} "
          f"=> {'PASS' if fails == 0 else 'FAIL'}")

    return {"pass_case_ok": v_ok.ok,
            "blame_case_blames_A": (not v_bad.ok and v_bad.blame == "A"),
            "property_failures": fails}


if __name__ == "__main__":
    run()
