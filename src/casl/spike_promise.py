"""
Spike J — Promise/Future as a first-class type  [LH-F-003; stage B]

A result produced by the oracle is a **first-class Promise[T]**: a typed
future over the payload sort that carries a *resolve-once* obligation (write-once,
linearity — the guarantee already established under W6). With this, "Promise" is no longer just
an implicit `from_oracle` marker, but a named type with an obligation:

    A -> J : Draft(answer:Str, cost:Int)  ⟨oracle⟩      ⇒  A produces Promise[Str/Int],
                                                            which is resolved exactly once.

`promise_discipline` checks: every promise is resolved exactly once on every path
(min==max==1). This connects the first-class Promise type with the proven linearity.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
from casl import core
from casl import spike_hardening as hard


@dataclass(frozen=True)
class Promise:
    """First-class future type over a payload sort."""
    sort: str

    def __str__(self) -> str:
        return f"Promise[{self.sort}]"


def promises_of(g: core.G) -> List[Tuple[str, str, Promise]]:
    """(producer, label, Promise[sort]) for each oracle-produced message."""
    out: List[Tuple[str, str, Promise]] = []

    def walk(n):
        if isinstance(n, core.Comm):
            if n.from_oracle:
                sort = "·".join(f.sort for f in n.fields) if n.fields else "Unit"
                out.append((n.sender, n.label, Promise(sort)))
            walk(n.cont)
            if n.on_crash is not None:
                walk(n.on_crash)
        elif isinstance(n, core.Choice):
            for b in n.branches:
                walk(b.cont)
        elif isinstance(n, core.Rec):
            walk(n.body)
    walk(g)
    return out


def promise_discipline(g: core.G):
    """(ok, violations, promises): every first-class promise is resolved exactly once
    (write-once / resolve-once). Uses the linearity guarantee (W6)."""
    ok, viol = hard.linearity_check(g)
    return ok, viol, promises_of(g)


def run():
    print("=" * 72)
    print("SPIKE J — Promise[T] as a first-class type + resolve-once")
    print("=" * 72)
    ok, _, proms = promise_discipline(core.G_OK)
    print(f"  G_OK Promises: {[(s, l, str(p)) for s, l, p in proms]}")
    print(f"  G_OK resolve-once: {ok}")
    dup_ok, dup_viol, _ = promise_discipline(hard.G_DUP)
    print(f"  G_DUP resolve-once: {dup_ok}  (violation {dup_viol})")
    return {"G_OK_ok": ok, "G_OK_has_promise": len(proms) == 1, "G_DUP_flagged": dup_ok is False}


if __name__ == "__main__":
    run()
