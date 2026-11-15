"""
Hardening W2 — does MPST-projectability ⇔ MSC-realizability really hold?

The convergence claim (Grundsaetze, Konvergenzkriterium 1) was only checked on
G_OK / G_BAD. Here we throw an adversarial battery at it: choreographies with a
shared message prefix, send-divergences, irrelevant third roles, and recursion —
each labelled with its TRUE well-formedness. We then compare:

    MPST projectable?   vs.   MSC realizable?   vs.   expected

A divergence (or a disagreement with `expected`) is a real finding: it means one
of the two checks is too strict or too lax and must be hardened.
"""
from __future__ import annotations
import io
from contextlib import redirect_stdout

from casl import core
from casl.core import Comm, Choice, Branch, End
from casl import spike_proj_mpst as mpst
from casl import spike_proj_msc as msc


def choice(*branches) -> core.G:
    """C->A:Req . A->J:Draft . J->C:{branches}  (A is the 'third role')."""
    return Comm("C", "A", "Req", tuple(),
                Comm("A", "J", "Draft", tuple(), Choice("J", "C", tuple(branches))))


def b(label, cont):
    return Branch(label, tuple(), cont)


def JtoA(lbl, cont):
    return Comm("J", "A", lbl, tuple(), cont)


def AtoJ(lbl, cont):
    return Comm("A", "J", lbl, tuple(), cont)


BATTERY = [
    ("ok_distinct", choice(b("Accept", JtoA("Done", End())),
                           b("Reject", JtoA("Retry", End()))), True,
     "A is informed in both branches with distinct labels"),
    ("bad_uninformed", choice(b("Accept", End()),
                              b("Reject", JtoA("Retry", End()))), False,
     "A learns nothing in the Accept branch"),
    ("ok_shared_prefix_distinct_later",
     choice(b("Accept", JtoA("Go", JtoA("X", End()))),
            b("Reject", JtoA("Go", JtoA("Y", End())))), True,
     "shared Go, then X/Y → A distinguishes later (tricky!)"),
    ("bad_shared_prefix_then_send",
     choice(b("Accept", JtoA("Go", AtoJ("P", End()))),
            b("Reject", JtoA("Go", AtoJ("Q", End())))), False,
     "shared Go, then A must SEND P/Q without knowing the branch"),
    ("bad_send_divergence", choice(b("Accept", AtoJ("P", End())),
                                   b("Reject", AtoJ("Q", End()))), False,
     "A immediately sends different things without being informed"),
    ("ok_irrelevant_third", choice(b("Accept", Comm("J", "C", "Bye", tuple(), End())),
                                   b("Reject", Comm("J", "C", "Bye", tuple(), End()))), True,
     "A is uninvolved in both branches → does not matter"),
    ("bad_one_sends_one_silent", choice(b("Accept", AtoJ("P", End())),
                                        b("Reject", End())), False,
     "A sends in one branch, stays silent in the other, uninformed"),
    ("ok_recursive", core.G_OK, True, "recursive canonical example"),
    ("bad_recursive", core.G_BAD, False, "recursive counterexample"),
    ("ok_recursive_crash", core.G_OK_CRASH, True, "crash-tolerant variant"),
]


def mpst_ok(g) -> bool:
    for r in core.ROLES:
        try:
            mpst.project(g, r)
        except mpst.NonProjectable:
            return False
    return True


def msc_ok(g) -> bool:
    with redirect_stdout(io.StringIO()):
        return msc.realizability(g, "")


def run():
    print("=" * 78)
    print("HARDENING W2 — MPST projectability  vs  MSC realizability  vs  expected")
    print("=" * 78)
    print(f"  {'case':<30} {'MPST':<6} {'MSC':<6} {'exp':<5} verdict")
    divergences, mismatches = [], []
    for name, g, expected, _desc in BATTERY:
        m = mpst_ok(g)
        s = msc_ok(g)
        agree = (m == s)
        correct = (m == expected and s == expected)
        verdict = "ok" if (agree and correct) else ("DIVERGENCE" if not agree else "WRONG")
        if not agree:
            divergences.append(name)
        if not correct:
            mismatches.append(name)
        print(f"  {name:<30} {str(m):<6} {str(s):<6} {str(expected):<5} {verdict}")
    print("-" * 78)
    print(f"  Divergences (MPST≠MSC): {divergences or 'none'}")
    print(f"  Deviations from the expected verdict: {mismatches or 'none'}")
    ok = not divergences and not mismatches
    print(f"  RESULT: {'✓ equivalence hardened — all cases agree' if ok else '✗ hardening reveals weaknesses (see above)'}")
    return {"divergences": divergences, "mismatches": mismatches, "ok": ok,
            "n_cases": len(BATTERY)}


if __name__ == "__main__":
    run()
