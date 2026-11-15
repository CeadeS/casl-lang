"""
completeness.py — W19 completeness via the USER/EXTERNAL as a completeness ORACLE behind the monitored
boundary (route C′). CASL's sound, fast, syntactic-merge projection decides by default (deny-by-default).
When it REJECTS a protocol that is in fact implementable, completeness is recovered from OUTSIDE — but
NEVER soundness: the oracle can only lift a conservative reject to an accept, and even then the TRUSTED
semantic oracle re-validates the supplied witness. Two grades:

  · STRONG (no new trust): the user/tool supplies a CERTIFICATE = an explicit local type per role; CASL's
    trusted oracle re-validates it — the endpoint system must be SAFE (semantics_sync) AND FAITHFUL to the
    global type g (bisimilar to g's global reduction). If both hold, g IS implementable ⇒ admit at mode
    `tested` (G2). The label-deterministic endpoint/global LTSs make the two-way simulation a bisimulation.
  · WEAK (fallback, bounded trust): no machine witness ⇒ a human Tier-3 ATTESTATION admits at mode
    `attested` (G3), disclosed & reviewable; deny-by-default if absent.

HARD INVARIANT: only a conservative REJECT can be lifted; the sound core keeps the safety verdict, so no
oracle (human or tool) can turn an unsafe g into an accepted one. See docs/analyses/w19-projection-completeness.md.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from casl.core import Comm, Choice, Branch, Rec, TVar, End
from casl import semantics_sync as S
from casl.spike_proj_mpst import local_pretty


# ---- global-type one-step reduction (synchronous), with μ-unfolding ----
def _subst_g(g, x, r):
    if isinstance(g, End) or isinstance(g, TVar):
        return r if (isinstance(g, TVar) and g.var == x) else g
    if isinstance(g, Rec):
        return g if g.var == x else Rec(g.var, _subst_g(g.body, x, r))
    if isinstance(g, Comm):
        return Comm(g.sender, g.receiver, g.label, g.fields, _subst_g(g.cont, x, r))
    if isinstance(g, Choice):
        return Choice(g.sender, g.receiver,
                      tuple(Branch(b.label, b.fields, _subst_g(b.cont, x, r)) for b in g.branches))
    return g


def _g_unfold(g):
    seen = 0
    while isinstance(g, Rec):
        g = _subst_g(g.body, g.var, g)
        seen += 1
        if seen > 2000:
            return None
    return g


def global_steps(g) -> Optional[List[Tuple[tuple, object]]]:
    """One synchronous global step of g: list of (event, g'). None if non-contractive."""
    g = _g_unfold(g)
    if g is None:
        return None
    if isinstance(g, Comm):
        return [((g.sender, g.receiver, g.label), g.cont)]
    if isinstance(g, Choice):
        return [((g.sender, g.receiver, b.label), b.cont) for b in g.branches]
    return []          # End / TVar — terminal


def endpoint_steps(cfg: Dict[str, object], roles) -> List[Tuple[tuple, Dict[str, object]]]:
    """One synchronous endpoint step: matched (p sends a to q) & (q receives a from p)."""
    out = []
    for p in roles:
        for (q, a), cp in S._sends(cfg[p]).items():
            if q in cfg:
                rq = S._recvs(cfg[q])
                if (p, a) in rq:
                    nxt = dict(cfg); nxt[p] = cp; nxt[q] = rq[(p, a)]
                    out.append(((p, q, a), nxt))
    return out


def _bisimilar(a0, step_a, key_a, b0, step_b, key_b, max_pairs=50000) -> bool:
    """Two-way simulation on label-deterministic LTSs (= bisimulation): every move on one side is
    matched by the same-event move on the other, recursively. States compared via key functions."""
    seen = set()
    stack = [(a0, b0)]
    n = 0
    while stack:
        a, b = stack.pop()
        kab = (key_a(a), key_b(b))
        if kab in seen:
            continue
        seen.add(kab)
        n += 1
        if n > max_pairs:
            return False
        sa, sb = step_a(a), step_b(b)
        if sa is None or sb is None:
            return False
        ea = {e for e, _ in sa}
        eb = {e for e, _ in sb}
        if ea != eb:                                   # same set of enabled events (both directions)
            return False
        for e, a2 in sa:
            for e2, b2 in sb:
                if e2 == e:
                    stack.append((a2, b2))
    return True


def _lkey(l):
    return local_pretty(l)


def _gkey(g):
    gu = _g_unfold(g)
    return _gpp(gu)


def _gpp(g):
    if isinstance(g, End):
        return "end"
    if isinstance(g, TVar):
        return g.var
    if isinstance(g, Rec):
        return f"mu {g.var}.({_gpp(g.body)})"
    if isinstance(g, Comm):
        return f"{g.sender}->{g.receiver}:{g.label}.{_gpp(g.cont)}"
    if isinstance(g, Choice):
        return f"{g.sender}->{g.receiver}{{" + "|".join(f"{b.label}:{_gpp(b.cont)}" for b in g.branches) + "}"
    return "?"


def faithful(g, endpoints: Dict[str, object], roles) -> bool:
    """The endpoint system realises exactly g: g's global LTS is bisimilar to the endpoint product LTS."""
    def gstep(gx):
        s = global_steps(gx)
        return None if s is None else s
    def estep(cfg):
        return endpoint_steps(cfg, roles)
    return _bisimilar(g, gstep, _gkey,
                      {r: endpoints[r] for r in roles}, estep,
                      lambda c: tuple((r, _lkey(c[r])) for r in roles))


def accept_with_certificate(g, endpoints: Dict[str, object]) -> Tuple[bool, str]:
    """STRONG completeness lift: admit a (possibly non-projectable) g iff the user-supplied endpoint
    certificate is SAFE and FAITHFUL to g — both re-validated by the trusted oracle. Mode `tested` (G2)."""
    roles = S.collect_roles(g) or tuple(sorted(endpoints))
    if any(r not in endpoints for r in roles):
        return (False, "certificate missing a role")
    safe, why = S.safe_config(endpoints, roles)
    if safe is not True:
        return (False, f"certificate endpoints not safe: {why}")
    if not faithful(g, endpoints, roles):
        return (False, "certificate does not faithfully implement g (not bisimilar to g)")
    return (True, "ACCEPTED via re-checked certificate (mode=tested/G2)")


def attest(g, who: str, rationale: str) -> Tuple[bool, str]:
    """WEAK completeness lift: a human Tier-3 attestation (mode `attested`/G3), disclosed & reviewable.
    No machine witness — bounded trust in the human. Deny-by-default if not invoked."""
    if not who or not rationale:
        return (False, "attestation requires an identified human + a rationale (deny-by-default)")
    return (True, f"ACCEPTED via human attestation (mode=attested/G3) — by {who}: {rationale}")
