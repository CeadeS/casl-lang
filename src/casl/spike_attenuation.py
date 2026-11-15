"""
Spike I — object = attenuated subtype of an agent kind  [LH-F-004, LH-G-003; stage B]

An agent kind has an upper bound on capabilities (`core.AGENT_CAPS`). An OBJECT
is an *attenuated* instance of that kind: it may carry only capabilities of the kind, and
**no stronger** — a subset of tools, `ttl` no larger, scope no broader. This makes the
subtype relation "object <: kind" hold structurally, with guaranteed least-privilege
preservation: an object NEVER has more authority than its kind.

Soundness rule (checked): for every object capability `o` there exists a kind capability `k`
with the same tool, the same scope, and `o.ttl <= k.ttl`. Fewer tools / smaller ttl = ok
(attenuation); a tool outside the kind or a larger ttl = authority escalation.
"""
from __future__ import annotations
from typing import List, Tuple
from casl import core
from casl.core import Capability


def attenuates(o: Capability, k: Capability) -> bool:
    """Object capability `o` is a permissible weakening of the kind capability `k`."""
    return (o.tool == k.tool
            and o.scope == k.scope          # scope narrowing: later refinement
            and o.ttl <= k.ttl)             # not longer-lived


def attenuation_sound(obj_caps, kind_caps) -> Tuple[bool, List[str]]:
    """(ok, escalations). Every object capability must weaken a kind capability;
    otherwise the object carries more/stronger authority than its kind (subtype violation)."""
    escalations: List[str] = []
    for o in obj_caps:
        if not any(attenuates(o, k) for k in kind_caps):
            escalations.append(o.tool)
    return (not escalations), escalations


# --------------------------------------------------------------------------
# Fixtures — objects of agent kind A (kind capability: search/web:readonly/ttl3)
# --------------------------------------------------------------------------
A_KIND = core.AGENT_CAPS["A"]

# sound: same tool/scope, but shorter-lived (ttl 1 <= 3) → genuine attenuation
OBJ_OK = (Capability("search", ("query",), "web:readonly", ttl=1, sigma="obj-ok"),)
# sound: no capability at all (maximal attenuation)
OBJ_EMPTY = tuple()
# escalation: ttl 9 > 3 (longer-lived than the kind allows)
OBJ_BAD_TTL = (Capability("search", ("query",), "web:readonly", ttl=9, sigma="obj-ttl"),)
# escalation: tool outside the kind
OBJ_BAD_TOOL = (Capability("delete", ("id",), "db:write", ttl=1, sigma="obj-del"),)


def run():
    print("=" * 72)
    print("SPIKE I — Objekt = attenuierter Subtyp (Least Privilege unter Attenuierung)")
    print("=" * 72)
    cases = [("OBJ_OK", OBJ_OK, True), ("OBJ_EMPTY", OBJ_EMPTY, True),
             ("OBJ_BAD_TTL", OBJ_BAD_TTL, False), ("OBJ_BAD_TOOL", OBJ_BAD_TOOL, False)]
    out = {}
    for name, caps, expect in cases:
        ok, esc = attenuation_sound(caps, A_KIND)
        mark = "ok" if ok else f"ESCALATION {esc}"
        print(f"  {name:13} → {mark}   (expected {'sound' if expect else 'violation'})")
        out[name] = (ok is expect)
    return out


if __name__ == "__main__":
    run()
