"""Grade flow-graph (D1-B / CEP-0070) — per-site grade along the typed-seam edges.

The global `effective_grade` (LH-Q-019) is the weakest link across ALL artifacts — sound but coarse. Now
that the typed seam (LH-F-012 full) binds artifacts to choreography sites, the choreography's message
order is a *checkable* dependency graph (parsed protocol, not author free-text → no laundering). This
computes, for each bound site, the weakest floor among the bound artifacts **at-or-upstream** of it in
protocol order — so a site *upstream* of a weak artifact keeps its strong grade.

**Conservative v1 (sound, never over-claims):** a site's grade only DEGRADES with upstream weak
artifacts; it is never raised. Containment boundaries (a `verified` proof site, an `oracle`+contract
monitored site, an approval gate) are *detected and reported* as re-base points, but the downstream
re-base (raising a grade past an upstream floor) is **deferred** — it needs per-artifact dataflow typing
(what each consumes/produces) to be sound. The global weakest-link headline stays authoritative; this is
an additional finer view. Ring 1/2; the verified core is untouched.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from casl import core
from casl import seam as _seam

_RANK = {"G0": 0, "G1": 1, "G2": 2, "G3": 3}


def _weakest(a: str, b: str) -> str:
    return a if _RANK.get(a, 3) >= _RANK.get(b, 3) else b


def cert_fid_verified() -> bool:
    """True iff CERT-FID — the F* forwarding-fidelity lemma `fstar/Forwarding.fst` — is present and
    free of proof holes (admit/assume/magic/sorry), the same non-vacuity gate the core uses
    (scripts/check_admits.sh). CERT-FID machine-checks that a forwarded payload is delivered
    UNCHANGED and that identity forwarding + contract entailment ⇒ the destination satisfies its
    contract BY PROOF (`rebase_sound`). When it is present, a forwarded+entailed site re-bases to
    **G0** — carrying the SAME standing calculus↔runtime TCB caveat (H1/W11) as the rest of the
    F*-proved core. Absent or holed ⇒ the conservative **G2** structural cap (A2, spec-conformance
    assumed). Missing file ⇒ False ⇒ G2 (never over-claims)."""
    import os
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(here))          # src/casl -> src -> repo root
    path = os.path.join(root, "fstar", "Forwarding.fst")
    try:
        with open(path, encoding="utf-8") as fh:
            s = fh.read()
    except OSError:
        return False
    s = re.sub(r"\(\*.*?\*\)", "", s, flags=re.S)          # strip (* block comments *)
    s = re.sub(r"//[^\n]*", "", s)                          # strip // line comments
    return re.search(r"\b(admit|assume|magic|sorry)\b", s) is None


def _rebase_grade() -> str:
    """The grade a sound forwarding re-base may grant: G0 when CERT-FID is proved, else the G2 cap."""
    return "G0" if cert_fid_verified() else "G2"


def flow_grades(manifest, project_dir: str, apply_rebase: bool = True) -> Dict[Tuple[str, str], str]:
    """{(proto, label): grade} per bound site — weakest floor at-or-upstream in protocol order. With
    apply_rebase (default), a sound A2 forwarding re-base may RAISE a site to G2 (see applied_rebases)."""
    bindings = _seam.check_seam(manifest, project_dir)[2]          # name -> (proto, label, nature)
    by_name = {a.name: a for a in manifest.artifacts}
    site_floor = {(proto, label): by_name[name].floor()
                  for name, (proto, label, _n) in bindings.items()}
    out: Dict[Tuple[str, str], str] = {}

    def dfs(node, proto, running):
        if node is None:
            return
        if isinstance(node, core.Comm):
            f = site_floor.get((proto, node.label))
            cur = _weakest(running, f) if f is not None else running
            if f is not None:
                prev = out.get((proto, node.label))
                out[(proto, node.label)] = _weakest(prev, cur) if prev is not None else cur
            dfs(node.cont, proto, cur)
            dfs(getattr(node, "on_crash", None), proto, cur)
        elif isinstance(node, core.Choice):
            for b in node.branches:
                dfs(b.cont, proto, running)
        elif isinstance(node, core.Rec):
            dfs(node.body, proto, running)

    for proto, g in _seam.load_choreographies(project_dir).items():
        dfs(g, proto, "G0")
    if apply_rebase:
        for site, grade in applied_rebases(manifest, project_dir).items():
            if site in out and _RANK.get(grade, 3) < _RANK.get(out[site], 3):
                out[site] = grade
    return out


def containment_boundaries(manifest, project_dir: str) -> List[str]:
    """Sites where downstream grade *could* be re-based (deferred): a `verified` proof site, an
    `oracle`+contract monitored site, or an approval gate."""
    out: List[str] = []

    def rec(node, proto):
        if node is None:
            return
        if isinstance(node, core.Comm):
            if getattr(node, "verified", False):
                out.append(f"{proto}:{node.label} (verified — proof boundary)")
            elif getattr(node, "from_oracle", False) and getattr(node, "contract", None):
                out.append(f"{proto}:{node.label} (oracle+contract — monitored boundary)")
            rec(node.cont, proto)
            rec(getattr(node, "on_crash", None), proto)
        elif isinstance(node, core.Choice):
            if getattr(node, "approval", False):
                out.append(f"{proto}:{node.sender}->{node.receiver} (approval gate — consent boundary)")
            for b in node.branches:
                rec(b.cont, proto)
        elif isinstance(node, core.Rec):
            rec(node.body, proto)

    for proto, g in _seam.load_choreographies(project_dir).items():
        rec(g, proto)
    return out


def _rel_to_z3(rel, env):
    """A contract relation tuple → a z3 constraint, sharing `env` so equal var names = the same quantity."""
    from z3 import Int, IntVal
    if not rel or len(rel) < 3:
        return None
    op, lhs, rhs = rel[0], rel[1], rel[2]

    def term(x):
        if isinstance(x, bool):
            return None
        if isinstance(x, int):
            return IntVal(x)
        if isinstance(x, str):
            return env.setdefault(x, Int(x))
        return None

    L, R = term(lhs), term(rhs)
    if L is None or R is None:
        return None
    if op == "le":
        return L <= R
    if op == "ge":
        return L >= R
    return None


def _entails(rel_b, rel_s) -> bool:
    """φ_B ⇒ φ_S, decided by SMT (UNSAT of φ_B ∧ ¬φ_S). Conservative: unknown ops / mismatched vars ⇒ False."""
    try:
        from z3 import Not, Solver, unsat
    except Exception:
        return False
    env: dict = {}
    cb = _rel_to_z3(rel_b, env)
    cs = _rel_to_z3(rel_s, env)
    if cb is None or cs is None:
        return False
    s = Solver()
    s.add(cb)
    s.add(Not(cs))
    return s.check() == unsat


def rebase_candidates(manifest, project_dir: str) -> List[Tuple[str, str]]:
    """(boundary_site, downstream_site) pairs where a dominating upstream `verified` boundary's proved
    contract SMT-ENTAILS a downstream site's contract — i.e. a re-base *could* apply. NOT applied: in
    MPST each message payload is a fresh binding, so name-based entailment does not establish that the
    downstream value IS the proved one — a sound GRANT needs verified data lineage (deferred). These are
    candidates, surfaced to show where lineage analysis would pay off (Model-C, grade-rebase.md)."""
    fg = flow_grades(manifest, project_dir)
    out: List[Tuple[str, str]] = []

    def dfs(node, proto, vctx):
        if node is None:
            return
        if isinstance(node, core.Comm):
            rel = node.contract.relation if getattr(node, "contract", None) else None
            if rel is not None and fg.get((proto, node.label)) not in (None, "G0"):
                for (bp, bl, brel) in vctx:
                    if _entails(brel, rel):
                        out.append((f"{bp}:{bl}", f"{proto}:{node.label}"))
                        break
            nv = vctx + ([(proto, node.label, rel)]
                         if (getattr(node, "verified", False) and rel is not None) else [])
            dfs(node.cont, proto, nv)
            dfs(getattr(node, "on_crash", None), proto, nv)
        elif isinstance(node, core.Choice):
            for b in node.branches:
                dfs(b.cont, proto, vctx)
        elif isinstance(node, core.Rec):
            dfs(node.body, proto, vctx)

    for proto, g in _seam.load_choreographies(project_dir).items():
        dfs(g, proto, [])
    return out


def _forwarding_map(gtype) -> Dict[Tuple[str, str], Tuple[str, str]]:
    """{(label, fieldname): (src_label, src_field)} for every forwarded field (A2: `name = Src.field`)."""
    out: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for c in _seam._walk(gtype):
        for f in c.fields:
            src = getattr(f, "source", None)
            if src and "." in src:
                sl, sf = src.split(".", 1)
                out[(c.label, f.name)] = (sl, sf)
    return out


def _verified_contracts(gtype) -> Dict[str, tuple]:
    return {c.label: c.contract.relation for c in _seam._walk(gtype)
            if getattr(c, "verified", False) and getattr(c, "contract", None)}


def applied_rebases(manifest, project_dir: str) -> Dict[Tuple[str, str], str]:
    """Sites whose grade is SOUNDLY raised: a forwarded field carries a value from a `verified`
    boundary whose proved contract entails this site's contract. The granted grade is
    `_rebase_grade()` — **G0** when CERT-FID (the F* forwarding-fidelity lemma) is proved, else the
    conservative **G2** structural cap (A2). Never raises a site already at-or-above the achievable
    grade. Soundness rests on three facts, all from the PARSED PROTOCOL (never oracle data — so the
    endorsement decision is adversary-independent, Askarov–Myers ESOP 2010): the forward edge
    (`field = Src.field`), the source being a `verified` boundary, and the SMT entailment
    φ_src ⇒ φ_dst. Entailment WITHOUT a forward edge stays a candidate (no lineage)."""
    base = flow_grades(manifest, project_dir, apply_rebase=False)
    target = _rebase_grade()
    out: Dict[Tuple[str, str], str] = {}
    for proto, g in _seam.load_choreographies(project_dir).items():
        fwd = _forwarding_map(g)
        vcon = _verified_contracts(g)
        for c in _seam._walk(g):
            scon = c.contract.relation if getattr(c, "contract", None) else None
            cur = base.get((proto, c.label))
            if scon is None or cur is None or _RANK.get(cur, 3) <= _RANK[target]:
                continue                                   # already at/above the achievable grade
            for f in c.fields:
                src = fwd.get((c.label, f.name))
                if src and src[0] in vcon and _entails(vcon[src[0]], scon):
                    out[(proto, c.label)] = target
                    break
    return out


def report(manifest, project_dir: str) -> str:
    fg = flow_grades(manifest, project_dir)               # apply_rebase=True ⇒ reflects A2 re-bases
    applied = applied_rebases(manifest, project_dir)
    lines = ["grade flow-graph (per-site grade from the parsed-protocol edges — no laundering):"]
    if not fg:
        lines.append("  (no bound sites — declare `implements` on artifacts to map the flow)")
    for (proto, label), grade in sorted(fg.items()):
        tag = ("A2 re-base: forwarded from a verified boundary" if (proto, label) in applied
               else "weakest bound artifact at-or-upstream")
        lines.append(f"  {proto}:{label:14} ≥{grade}   ({tag})")
    bn = containment_boundaries(manifest, project_dir)
    if bn:
        lines.append("  containment boundaries:")
        for b in bn:
            lines.append(f"    · {b}")
    if applied:
        if cert_fid_verified():
            lines.append("  re-base APPLIED (A1 — PROVED by CERT-FID, the F* forwarding-fidelity lemma: a "
                         "forwarded value carries a verified boundary's proved property, so identity "
                         "forwarding + entailment ⇒ the destination satisfies its contract BY PROOF → G0; "
                         "standing calculus↔runtime TCB caveat as for the whole proven core):")
        else:
            lines.append("  re-base APPLIED (A2; a forwarded value carries a verified boundary's proved "
                         "property — sound, capped at G2 via statically-checked structural lineage; add "
                         "CERT-FID (fstar/Forwarding.fst) to reach G0):")
        for (proto, label), grade in sorted(applied.items()):
            lines.append(f"    ✓ {proto}:{label} → ≥{grade}")
    cand = [(b, s) for (b, s) in rebase_candidates(manifest, project_dir)
            if tuple(s.split(":", 1)) not in applied]
    if cand:
        lines.append("  re-base candidates (entailment holds but NO data lineage — NOT applied; add a "
                     "forwarding `field = Src.field` to make it sound, or attest the lineage):")
        for b, s in cand:
            lines.append(f"    ? {b} ⇒ {s}  (would re-base if lineage holds)")
    return "\n".join(lines)
