"""
Spike A — MPST-style projection  [TBD-003 alternative 1]   (v2: + recursion)

Projects a (now possibly recursive) global type onto each role's local
session type. A choice by p sent to q must be learnable by every other role
via a distinguishing receive (the merge operation), else projection fails.
Recursion is handled with mu-binders; the Retry branch loops back.

Demonstrates: LH-F-006 (projection), LH-Q-001a/b/c (static guarantees),
LH-F-002 (type = session type), and now recursive (looping) protocols.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, List
from casl import core
from casl.core import G, Comm, Choice, Branch, Rec, TVar, End, Field, fields_str


# ---- Local (endpoint) type AST ----
class L:
    pass


@dataclass(frozen=True)
class LSend(L):
    to: str
    label: str
    fields: Tuple[Field, ...]
    cont: L


@dataclass(frozen=True)
class LRecv(L):
    frm: str
    label: str
    fields: Tuple[Field, ...]
    cont: L


@dataclass(frozen=True)
class LIntChoice(L):       # internal choice (we decide & send)
    to: str
    opts: Tuple[Tuple[str, Tuple[Field, ...], L], ...]


@dataclass(frozen=True)
class LExtChoice(L):       # external choice (we branch on received label)
    frm: str
    opts: Tuple[Tuple[str, Tuple[Field, ...], L], ...]


@dataclass(frozen=True)
class LRec(L):
    var: str
    body: L


@dataclass(frozen=True)
class LVar(L):
    var: str


@dataclass(frozen=True)
class LEnd(L):
    pass


class NonProjectable(Exception):
    pass


def _as_options(t: L):
    """View a receive / external choice as (partner, {label: (fields, cont)})."""
    if isinstance(t, LRecv):
        return (t.frm, {t.label: (t.fields, t.cont)})
    if isinstance(t, LExtChoice):
        return (t.frm, {lbl: (flds, c) for lbl, flds, c in t.opts})
    return None


def merge_pair(a: L, b: L) -> L:
    """Full MPST merge (hardened, W2): identical types merge to themselves;
    receives / external choices from the SAME partner merge by unioning labels
    and recursively merging the continuations of SHARED labels (so a common
    prefix that is later distinguished is fine). Anything else — e.g. a send at
    the point of divergence — is non-mergeable."""
    if a == b:
        return a
    oa, ob = _as_options(a), _as_options(b)
    if oa is not None and ob is not None and oa[0] == ob[0]:
        partner = oa[0]
        out = dict(oa[1])
        for lbl, (flds, c) in ob[1].items():
            if lbl in out:
                out[lbl] = (flds, merge_pair(out[lbl][1], c))   # shared → recurse
            else:
                out[lbl] = (flds, c)                            # disjoint → keep both
        return LExtChoice(partner, tuple((l, f, c) for l, (f, c) in out.items()))
    raise NonProjectable(
        "branches not mergeable (role cannot locally determine which branch was taken)")


def merge(types: List[L]) -> L:
    """Merge the projections of a non-participating role across branches."""
    result = types[0]
    for t in types[1:]:
        result = merge_pair(result, t)
    return result


def project(g: G, r: str) -> L:
    if isinstance(g, End):
        return LEnd()
    if isinstance(g, TVar):
        return LVar(g.var)
    if isinstance(g, Rec):
        return LRec(g.var, project(g.body, r))
    if isinstance(g, Comm):
        cont = project(g.cont, r)
        if r == g.sender:
            return LSend(g.receiver, g.label, g.fields, cont)
        if r == g.receiver:
            return LRecv(g.sender, g.label, g.fields, cont)
        return cont
    if isinstance(g, Choice):
        if r == g.sender:
            return LIntChoice(g.receiver,
                              tuple((b.label, b.fields, project(b.cont, r)) for b in g.branches))
        if r == g.receiver:
            return LExtChoice(g.sender,
                              tuple((b.label, b.fields, project(b.cont, r)) for b in g.branches))
        return merge([project(b.cont, r) for b in g.branches])
    raise TypeError(type(g))


def local_pretty(l: L) -> str:
    if isinstance(l, LEnd):
        return "end"
    if isinstance(l, LVar):
        return l.var
    if isinstance(l, LRec):
        return f"μ{l.var}. {local_pretty(l.body)}"
    if isinstance(l, LSend):
        return f"{l.to}!{l.label}({fields_str(l.fields)}) . {local_pretty(l.cont)}"
    if isinstance(l, LRecv):
        return f"{l.frm}?{l.label}({fields_str(l.fields)}) . {local_pretty(l.cont)}"
    if isinstance(l, LIntChoice):
        inner = "  ".join(f"{lbl}({fields_str(flds)}): {local_pretty(c)}" for lbl, flds, c in l.opts)
        return f"{l.to}⊕{{ {inner} }}"
    if isinstance(l, LExtChoice):
        inner = "  ".join(f"{lbl}({fields_str(flds)}): {local_pretty(c)}" for lbl, flds, c in l.opts)
        return f"{l.frm}&{{ {inner} }}"
    raise TypeError(type(l))


def project_all(g: G, name: str):
    print(f"  MPST projection of {name}:")
    ok = True
    for r in core.ROLES:
        try:
            lt = project(g, r)
            print(f"    {r}: {local_pretty(lt)}")
        except NonProjectable as e:
            ok = False
            print(f"    {r}: ✗ NON-PROJECTABLE — {e}")
    print(f"  => {name} is {'projectable (well-formed)' if ok else 'REJECTED by MPST'}")
    return ok


def run():
    print("=" * 72)
    print("SPIKE A — MPST projection (recursive)")
    print("=" * 72)
    ok1 = project_all(core.G_OK, "G_OK")
    print()
    ok2 = project_all(core.G_BAD, "G_BAD")
    return {"G_OK_projectable": ok1, "G_BAD_projectable": ok2}


if __name__ == "__main__":
    run()
