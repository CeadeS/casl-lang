"""
run_all — executes every spike against the shared BudgetedQA fixture and
prints a convergence summary, plus a prompt-projection demo (LH-F-006):
the SAME projected local type drives the generated agent prompt.
"""
from __future__ import annotations
from casl import core
from casl import spike_proj_mpst as mpst
from casl import spike_proj_msc as msc
from casl import spike_smt_contract as smt
from casl import spike_monitor_test as mon
from casl.core import Field


def prompt_projection(role: str) -> str:
    """Render an agent prompt skeleton from the role's MPST local type +
    its capability set + any contracts it must honor. (LH-F-006)"""
    lt = mpst.project(core.G_OK, role)
    lines = [f"You are agent {role} ({core.ROLE_NAMES[role]}). Follow this protocol exactly:"]
    step = [1]

    def walk(l):
        if isinstance(l, mpst.LRecv):
            lines.append(f"  {step[0]}. Receive {l.label}({core.fields_str(l.fields)}) from {l.frm}.")
            step[0] += 1
            walk(l.cont)
        elif isinstance(l, mpst.LSend):
            ct = ""
            if l.label == "Draft":
                ct = f"  CONTRACT: {core.C_COST_LE_BUDGET.text} (you are blamed if violated)."
            lines.append(f"  {step[0]}. Send {l.label}({core.fields_str(l.fields)}) to {l.to}.{ct}")
            step[0] += 1
            walk(l.cont)
        elif isinstance(l, mpst.LRec):
            lines.append(f"  {step[0]}. Repeat the following (loop {l.var}) until accepted:")
            step[0] += 1
            walk(l.body)
        elif isinstance(l, mpst.LVar):
            lines.append(f"     ↺ go back to loop {l.var}.")
        elif isinstance(l, mpst.LExtChoice):
            opts = ", ".join(lbl for lbl, _, _ in l.opts)
            lines.append(f"  {step[0]}. Await one of {{{opts}}} from {l.frm}:")
            step[0] += 1
            for lbl, _flds, c in l.opts:
                if isinstance(c, mpst.LVar):
                    lines.append(f"       - {lbl}: loop again.")
                elif isinstance(c, mpst.LEnd):
                    lines.append(f"       - {lbl}: done.")
                else:
                    lines.append(f"       - {lbl}: continue.")
        elif isinstance(l, mpst.LIntChoice):
            opts = ", ".join(lbl for lbl, _, _ in l.opts)
            lines.append(f"  {step[0]}. Choose and send one of {{{opts}}} to {l.to}.")
            step[0] += 1
        # LEnd: stop

    walk(lt)
    caps = core.AGENT_CAPS.get(role, ())
    if caps:
        lines.append("Capabilities you MAY use (and nothing else):")
        for c in caps:
            lines.append(f"  - {c}")
    else:
        lines.append("You have NO tool capabilities.")
    return "\n".join(lines)


def main():
    r_mpst = mpst.run(); print()
    r_msc = msc.run(); print()
    r_smt = smt.run(); print()
    r_mon = mon.run(); print()

    print("=" * 72)
    print("PROMPT PROJECTION (LH-F-006) — generated prompt for agent A from its local type")
    print("=" * 72)
    print(prompt_projection("A"))

    print("\n" + "=" * 72)
    print("CONVERGENCE SUMMARY — do the layers fit together on BudgetedQA?")
    print("=" * 72)
    rows = [
        ("MPST: G_OK projectable",        r_mpst["G_OK_projectable"] is True),
        ("MPST: G_BAD rejected",          r_mpst["G_BAD_projectable"] is False),
        ("MSC:  G_OK realizable",         r_msc["G_OK_realizable"] is True),
        ("MSC:  G_BAD rejected",          r_msc["G_BAD_realizable"] is False),
        ("MPST & MSC agree on G_OK/G_BAD",
            r_mpst["G_OK_projectable"] == r_msc["G_OK_realizable"]
            and r_mpst["G_BAD_projectable"] == r_msc["G_BAD_realizable"]),
        ("SMT: budget-safety proven",     r_smt["budget_safety_proven"]),
        ("SMT: overspend counterexample", r_smt["overspend_counterexample"]),
        ("Monitor: blames A on violation", r_mon["blame_case_blames_A"]),
        ("Property test: 0 mismatches",   r_mon["property_failures"] == 0),
    ]
    allok = True
    for name, ok in rows:
        allok = allok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print("-" * 72)
    print(f"  RESULT: {'ALL LAYERS CONSISTENT on the shared fixture' if allok else 'MISMATCH — see above'}")


if __name__ == "__main__":
    main()
