"""
Spike H — approval dominance  [LH-Q-011; stage B]   (hardened after red-team v0.1.27: C1/C2/M2)

Safety invariant: every IRREVERSIBLE/effectful action must be dominated on every path by
an APPROVAL gate, and specifically via its **consent branch**.

Hardenings relative to the first version:
  · **C2 — effect bound to capability (deny-by-default):** an action is irreversible
    if it is explicitly `irreversible` OR uses a capability whose **`mode`** is not
    `read`. This way no effect can escape through missing tagging.
  · **R-H1 (red-team v0.1.28) — structured effect field:** the effect follows from the
    validated `mode` field (read|write|admin, default `write`), NOT from a substring test
    over the author-controlled free-text `scope` (which was leaky: `cal:read-write`→read-only,
    and spoofable: `db:readonly` on purge). Trust no longer resides in freely chosen text.
  · **C1 — consent branch:** only a branch marked `consent` of an `approval` choice
    discharges the obligation. An irreversible action in the deny / non-consent branch remains
    undominated → rejection.
  · **M2 — no consent across loops:** `approved` is reset at a recursion;
    an irreversible action in a loop needs consent WITHIN the iteration
    (no "approve once → forever").
"""
from __future__ import annotations
from typing import List, Tuple
from casl import core
from casl.core import Comm, Choice, Branch, Rec, End, Capability

def effectful(cap: Capability) -> bool:
    """R-H1 (LH-Q-012): the effect follows from the structured, validated `mode` field, NOT
    from the free-text `scope`. Only `mode == "read"` is non-effectful; everything else
    (write/admin, unknown, missing) is effectful — **deny-by-default**. This way a
    dangerous action no longer escapes through a merely read-only *named* capability."""
    return (getattr(cap, "mode", "write") or "write").strip().lower() != "read"


def is_irreversible(node: Comm, capmap) -> bool:
    """Explicitly tagged OR uses an effectful capability (effect bound to capability)."""
    if node.irreversible:
        return True
    if node.uses_capability:
        for c in capmap.get(node.sender, ()):
            if c.tool == node.uses_capability and effectful(c):
                return True
    return False


def approval_dominated(g: core.G, capmap=None) -> Tuple[bool, List[Tuple[str, str, str]]]:
    """(ok, violations). A violation = an effectful action without a dominating approval
    (via a consent branch, within the same loop iteration)."""
    capmap = capmap if capmap is not None else core.AGENT_CAPS
    viol: List[Tuple[str, str, str]] = []

    def walk(node, approved: bool):
        if isinstance(node, Comm):
            if is_irreversible(node, capmap) and not approved:
                viol.append((node.sender, node.receiver, node.label))
            walk(node.cont, approved)
            if node.on_crash is not None:
                walk(node.on_crash, approved)
        elif isinstance(node, Choice):
            for b in node.branches:
                # ONLY a consent-marked branch of an approval choice discharges (C1)
                br_approved = True if (node.approval and b.consent) else approved
                walk(b.cont, br_approved)
        elif isinstance(node, Rec):
            walk(node.body, False)   # consent survives no iteration (M2)
        # TVar / End: stop

    walk(g, False)
    return (not viol), viol


# --------------------------------------------------------------------------
# Fixtures — appointment rescheduling. S=secretary, U=user, K=calendar, M=mail.
# --------------------------------------------------------------------------
CAPS_CAL = {"S": (Capability("calendar", ("event",), "cal:write", ttl=1, sigma="s1"),)}
CAPS_MAIL = {"S": (Capability("mail", ("to",), "mail:send", ttl=1, sigma="s1"),)}

# OK: irreversible Move sits in the CONSENT branch.
G_RESCHED_OK = Comm("S", "U", "Conflict", tuple(),
                    Choice("U", "S", (
                        Branch("Approve", tuple(),
                               Comm("S", "K", "Move", tuple(), End(),
                                    uses_capability="calendar", irreversible=True),
                               consent=True),
                        Branch("Deny", tuple(), Comm("S", "K", "Skip", tuple(), End())),
                    ), approval=True))

# BAD (no gate): Move without approval.
G_RESCHED_BAD = Comm("S", "U", "Conflict", tuple(),
                     Comm("S", "K", "Move", tuple(), End(),
                          uses_capability="calendar", irreversible=True))

# BAD (C1): Move in the NON-consent Deny branch.
G_DENY_ATTACK = Comm("S", "U", "Conflict", tuple(),
                     Choice("U", "S", (
                         Branch("Approve", tuple(), Comm("S", "K", "Skip", tuple(), End()), consent=True),
                         Branch("Deny", tuple(),
                                Comm("S", "K", "Move", tuple(), End(),
                                     uses_capability="calendar", irreversible=True)),
                     ), approval=True))

# BAD (C2): effectful capability (mail:send), untagged, no approval.
G_SILENT_SEND = Comm("S", "U", "Notice", tuple(),
                     Comm("S", "M", "SendEmail", tuple(), End(), uses_capability="mail"))


def run():
    print("=" * 72)
    print("SPIKE H — approval dominance (hardened: effect-to-capability, consent branch, Loop-Reset)")
    print("=" * 72)
    cases = [("G_RESCHED_OK", G_RESCHED_OK, CAPS_CAL, True),
             ("G_RESCHED_BAD", G_RESCHED_BAD, CAPS_CAL, False),
             ("G_DENY_ATTACK (C1)", G_DENY_ATTACK, CAPS_CAL, False),
             ("G_SILENT_SEND (C2)", G_SILENT_SEND, CAPS_MAIL, False)]
    out = {}
    for name, g, caps, expect in cases:
        ok, v = approval_dominated(g, caps)
        print(f"  {name:22} → {'OK (dominated)' if ok else 'VIOLATED ' + str(v)}   (expected {'sound' if expect else 'rejection'})")
        out[name] = (ok is expect)
    return out


if __name__ == "__main__":
    run()
