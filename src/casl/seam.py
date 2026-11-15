"""Typed `.casl`↔artifact seam (LH-F-012 *full* / CEP-0074).

Binds an artifact (`casl.toml` `implements = "<protocol>:<Label>"`) to a choreography SITE — a `Comm`
with a typed signature (`fields`), an optional `contract` (pre/post), and flags (`oracle`/`verified`/
`irreversible`/`uses`). It checks the BINDING + the boundary, NOT the body (W17): the site exists, the
artifact `kind` matches the site's nature, and the site contract is the artifact's obligation. This makes
the artifact↔site↔requirement triangle explicit — which unblocks the observability requirement-link and
the grade flow-graph (D1-B/C). Opt-in: only artifacts that declare `implements` are bound-checked.

Ring 1/2; the verified core IR and the parser are untouched (the binding lives in the manifest).
"""
from __future__ import annotations

import glob
import os
from typing import Dict, List, Optional, Tuple

from casl import core

# which artifact kinds may realize which site nature (structured, not name-inferred — the R-H1 rule)
_KIND_OK = {
    "oracle":   {"oracle"},
    "verified": {"verified"},
    "effect":   {"generated", "external"},
    "plain":    {"generated", "verified", "external", "oracle"},
}


def load_choreographies(project_dir: str) -> Dict[str, object]:
    """{protocol_name: gtype} for every casl/*.casl in the project (best-effort parse)."""
    from casl import surface
    out: Dict[str, object] = {}
    for p in sorted(glob.glob(os.path.join(project_dir, "casl", "*.casl"))):
        try:
            proto = surface.parse_file(p)
            out[proto.name] = proto.gtype
        except Exception:
            pass
    return out


def _walk(g) -> List[core.Comm]:
    """Every Comm node reachable in a global type."""
    out: List[core.Comm] = []

    def rec(n):
        if n is None:
            return
        if isinstance(n, core.Comm):
            out.append(n)
            rec(n.cont)
            rec(getattr(n, "on_crash", None))
        elif isinstance(n, core.Choice):
            for b in n.branches:
                rec(b.cont)
        elif isinstance(n, core.Rec):
            rec(n.body)
        # End / TVar: stop
    rec(g)
    return out


def find_site(gtype, label: str) -> Optional[core.Comm]:
    return next((c for c in _walk(gtype) if c.label == label), None)


def _site_nature(c: core.Comm) -> str:
    if getattr(c, "from_oracle", False):
        return "oracle"
    if getattr(c, "verified", False):
        return "verified"
    if getattr(c, "irreversible", False) or getattr(c, "uses_capability", None):
        return "effect"
    return "plain"


def check_seam(manifest, project_dir: str) -> Tuple[bool, List[str], Dict[str, Tuple[str, str, str]]]:
    """(ok, violations, bindings). Only artifacts that DECLARE `implements` are bound-checked (opt-in)."""
    choreos = load_choreographies(project_dir)
    viol: List[str] = []
    bindings: Dict[str, Tuple[str, str, str]] = {}
    for a in manifest.artifacts:
        impl = getattr(a, "implements", None)
        if not impl:
            continue
        proto, _, label = impl.partition(":")
        g = choreos.get(proto)
        if g is None:
            viol.append(f"{a.name}: implements unknown protocol {proto!r} (no casl/{proto}.casl)")
            continue
        site = find_site(g, label)
        if site is None:
            viol.append(f"{a.name}: implements {impl} — no site {label!r} in protocol {proto}")
            continue
        nature = _site_nature(site)
        if a.kind not in _KIND_OK.get(nature, set()):
            viol.append(f"{a.name}: kind {a.kind} cannot realize a {nature} site ({impl}) — "
                        f"expected one of {sorted(_KIND_OK[nature])}")
            continue
        bindings[a.name] = (proto, label, nature)
    return (not viol, viol, bindings)


def site_requirements(manifest, project_dir: str) -> Dict[Tuple[str, str], str]:
    """{(proto, label): requirement} for every bound artifact — the requirement↔site link."""
    by_name = {a.name: a for a in manifest.artifacts}
    out: Dict[Tuple[str, str], str] = {}
    for name, (proto, label, _n) in check_seam(manifest, project_dir)[2].items():
        out[(proto, label)] = by_name[name].requirement
    return out


def unbound_sites(manifest, project_dir: str) -> List[str]:
    """Effect/oracle sites with NO artifact implementing them — a gap (reported, not a hard deny)."""
    choreos = load_choreographies(project_dir)
    bound = {(p, l) for (p, l, _n) in check_seam(manifest, project_dir)[2].values()}
    out: List[str] = []
    for proto, g in choreos.items():
        for c in _walk(g):
            if _site_nature(c) in ("oracle", "effect") and (proto, c.label) not in bound:
                out.append(f"{proto}:{c.label} ({_site_nature(c)})")
    return out


def report(manifest, project_dir: str) -> str:
    _ok, viol, bindings = check_seam(manifest, project_dir)
    lines = [f"typed seam: {len(bindings)} binding(s)"]
    for name, (proto, label, nature) in sorted(bindings.items()):
        lines.append(f"  ✓ {name} ⟶ {proto}:{label} ({nature})")
    for v in viol:
        lines.append(f"  ✗ {v}")
    ub = unbound_sites(manifest, project_dir)
    if ub:
        lines.append(f"  · {len(ub)} unbound effect/oracle site(s): {', '.join(ub[:8])}")
    return "\n".join(lines)
