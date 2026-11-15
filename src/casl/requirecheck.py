"""casl.requirecheck — Layer-1 (formal, deterministic) requirement-compliance checker.

Two STATIC guarantees over the effectful call sites in app/host code, fast enough to run per-commit:

  · PROVENANCE         — every effect call targets a choreography SITE (`Protocol:Label`) that is bound to an
                         artifact carrying a REQUIREMENT. An effect that "comes from" no requirement is
                         rejected (the user's "kommen die Funktionen aus einem Requirement?").
  · APPROVAL-DOMINANCE — every IRREVERSIBLE effect call carries an approval token (`approval=`) — the static
                         twin of the broker's runtime approval-binding (A). A forgotten approval gate is
                         caught here at build time too.

This is the cheap, always-run FORMAL layer. The semantic "does the code actually FULFIL the requirement"
review is Layer 2 (LLM-backed, vetoes-never-vouches), run incrementally on a diff. Layer 1 is intentionally
UNSOUND for bypasses: it keys on the seam's effect funnel; a body that sidesteps the seam is caught by
`casl.importlint` (raw I/O only in providers) + the runtime cage (A/C), not here. Pair all three.
"""
from __future__ import annotations

import ast
import glob
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from casl import project as _project
from casl import seam as _seam
from casl import surface as _surface

# The seam entry points that perform or guard an effect. Configurable; the defaults catch both the funnel
# (`effect`) and the transitional capability check (`capability`).
EFFECT_FUNCS = ("effect", "capability")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    site: Optional[str]
    rule: str            # "provenance" | "approval-dominance" | "parse"
    detail: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.detail}"


def requirement_index(project_dir: str) -> Dict[str, dict]:
    """{ 'Protocol:Label' -> {cap, irreversible, requirement, artifact} } over every artifact-bound site."""
    man = _project.load_manifest(project_dir)
    protos = {}
    for f in sorted(glob.glob(os.path.join(project_dir, "casl", "*.casl"))):
        try:
            p = _surface.parse_file(f)
            protos[p.name] = p.gtype
        except Exception:
            continue
    idx: Dict[str, dict] = {}
    for a in man.artifacts:
        impl = getattr(a, "implements", None)
        if not impl or ":" not in str(impl):
            continue
        proto, _, label = str(impl).partition(":")
        g = protos.get(proto)
        site = _seam.find_site(g, label) if g is not None else None
        idx[impl] = {"cap": getattr(site, "uses_capability", None),
                     "irreversible": bool(getattr(site, "irreversible", False)),
                     "requirement": getattr(a, "requirement", "") or "",
                     "artifact": a.name}
    return idx


def _site_of(call: ast.Call) -> Optional[str]:
    if call.args and isinstance(call.args[0], ast.Constant) and isinstance(call.args[0].value, str):
        return call.args[0].value
    for kw in call.keywords:
        if kw.arg == "site" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _is_effect_call(call: ast.Call, funcs) -> bool:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr in funcs
    if isinstance(f, ast.Name):
        return f.id in funcs
    return False


def _has_approval(call: ast.Call) -> bool:
    return any(kw.arg == "approval" for kw in call.keywords)


def scan_source(path: str, src: str, idx: Dict[str, dict], funcs=EFFECT_FUNCS) -> List[Finding]:
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [Finding(path, getattr(e, "lineno", 0) or 0, None, "parse", f"unparseable ({e.msg})")]
    out: List[Finding] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _is_effect_call(node, funcs)):
            continue
        site = _site_of(node)
        if site is None:
            out.append(Finding(path, node.lineno, None, "provenance",
                               "effect call with no static site — cannot trace it to a requirement"))
            continue
        info = idx.get(site)
        if info is None or not info["requirement"]:
            out.append(Finding(path, node.lineno, site, "provenance",
                               f"effect at {site!r} does not trace to a requirement"))
            continue
        if info["irreversible"] and not _has_approval(node):
            out.append(Finding(path, node.lineno, site, "approval-dominance",
                               f"irreversible effect {info['cap']!r} at {site} ({info['requirement']}) is "
                               f"not approval-bound (pass an `approval=` token via the gate)"))
    return out


def scan_file(path: str, idx: Dict[str, dict], funcs=EFFECT_FUNCS) -> List[Finding]:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return scan_source(path, fh.read(), idx, funcs)


def check_paths(project_dir: str, paths, funcs=EFFECT_FUNCS) -> List[Finding]:
    """Run Layer-1 over the given source files (for a per-commit hook: the staged *.py)."""
    idx = requirement_index(project_dir)
    out: List[Finding] = []
    for p in paths:
        if str(p).endswith(".py") and os.path.exists(p):
            out += scan_file(p, idx, funcs)
    return out


def report(project_dir: str, paths, funcs=EFFECT_FUNCS):
    f = check_paths(project_dir, paths, funcs)
    if not f:
        return True, ("✓ requirement-check (Layer-1): every effect call traces to a requirement and every "
                      "irreversible effect is approval-bound.")
    lines = [f"✗ requirement-check (Layer-1): {len(f)} violation(s):"] + [f"    {x}" for x in f]
    return False, "\n".join(lines)


if __name__ == "__main__":
    # Per-commit entry: `python -m casl.requirecheck PROJECT_DIR FILE.py [FILE.py ...]` (exit 1 on violation).
    import sys
    if len(sys.argv) < 3:
        print("usage: python -m casl.requirecheck PROJECT_DIR FILE.py [FILE.py ...]", file=sys.stderr)
        raise SystemExit(2)
    _ok, _rep = report(sys.argv[1], sys.argv[2:])
    print(_rep)
    raise SystemExit(0 if _ok else 1)
