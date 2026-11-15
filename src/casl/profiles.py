"""CEP-0003 step 5 — build profiles & the layering (import-direction) guard.

The assurance-level "onion" (CEP-0003) claims that an outer ring can be *compiled out*
to shrink the trusted computing base (TCB). That is only **sound** if dependencies point
strictly INWARD: a `core` (ring-0) module must never import an `extended` (ring-1) or
`advisory` (ring-2) module — otherwise you could not ship `core` without the outer code.

This module makes that precondition mechanical: it assigns each top-level `casl` module a
ring and scans the actual `import` graph (via the AST) for any inner→outer edge. The living
audit fails on a violation, so the layering cannot silently erode.

NOTE (honest scope): this enforces the *dependency direction* that makes compile-out sound.
Physically splitting the distribution into `casl-core` / `casl-extended` / `casl-advisory`
wheels is future packaging work; the invariant proven here is its prerequisite.
"""
from __future__ import annotations

import ast
import os
from typing import Dict, List, Tuple

# Ring 0 = core / trusted base (mirrors .github/CODEOWNERS + their core dependencies).
# Ring 1 = extended capabilities. Ring 2 = advisory (oracle / synthesis / IDE / serving).
RING: Dict[str, int] = {
    # --- ring 0: trusted base ---
    "spec": 0, "authority": 0, "audit": 0, "cep": 0, "levels": 0, "profiles": 0,
    "check": 0, "core": 0, "surface": 0, "metatheory": 0, "semantics": 0,
    "requirements": 0, "tcb_bridge": 0, "tcb_corpus": 0, "kernel": 0,
    "spike_proj_mpst": 0, "spike_proj_msc": 0, "spike_capability": 0,
    "spike_hardening": 0, "spike_resilience": 0, "spike_approval": 0,
    "spike_attenuation": 0, "harden_equivalence": 0, "trace": 0, "semantics_sync": 0, "completeness": 0,
    # kernel self-test deps — import-clean (advisory bits lazy); classified so the static guard covers them
    "spike_judge": 0, "spike_smt_contract": 0, "spike_monitor_test": 0, "spike_promise": 0,
    # --- ring 1: extended ---
    "semantics_async": 1,
    # --- ring 2: advisory ---
    "oracle": 2, "synth": 2, "ide": 2, "mcp": 2, "spike_pipeline": 2,
    "run": 2, "run_all": 2,
}

RING_NAME = {0: "core", 1: "extended", 2: "advisory"}


def _src_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _mods_in_node(node) -> List[str]:
    """`casl` submodule names imported by a single Import / ImportFrom node."""
    mods: List[str] = []
    if isinstance(node, ast.ImportFrom) and node.module:
        parts = node.module.split(".")
        if parts[0] == "casl":
            if len(parts) >= 2:                     # from casl.core import X
                mods.append(parts[1])
            else:                                   # from casl import a, b
                mods.extend(n.name.split(".")[0] for n in node.names)
    elif isinstance(node, ast.Import):
        for n in node.names:                        # import casl.oracle
            parts = n.name.split(".")
            if parts[0] == "casl" and len(parts) >= 2:
                mods.append(parts[1])
    return mods


def _scan(path: str) -> Tuple[List[str], List[str]]:
    """(module-level imports, deferred/function-level imports) of `casl` submodules.

    Module-level imports load unconditionally (a hard dependency). Deferred imports
    live inside a function/method body and load only when that path runs — so they do
    not force the module into the TCB of a build that omits the importing code path.
    """
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    top: List[str] = []
    for stmt in tree.body:                          # direct children of the module
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            top.extend(_mods_in_node(stmt))
    all_mods: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            all_mods.extend(_mods_in_node(node))
    deferred = [m for m in all_mods if m not in top]
    return top, deferred


def _edges(deferred: bool) -> List[Tuple[str, str, int, int]]:
    src = _src_dir()
    out: List[Tuple[str, str, int, int]] = []
    for mod, ring_in in RING.items():
        path = os.path.join(src, mod + ".py")
        if not os.path.isfile(path):                # e.g. kernel is a package
            path = os.path.join(src, mod, "__init__.py")
            if not os.path.isfile(path):
                continue
        top_imps, def_imps = _scan(path)
        for imp in (def_imps if deferred else top_imps):
            ring_out = RING.get(imp)
            if ring_out is not None and ring_out > ring_in:
                out.append((mod, imp, ring_in, ring_out))
    return out


def layering_violations() -> List[Tuple[str, str, int, int]]:
    """HARD inner→outer edges: a lower-ring module imports a higher-ring one at
    MODULE LEVEL (loads unconditionally). These break compile-out and fail the audit."""
    return _edges(deferred=False)


def deferred_layering_edges() -> List[Tuple[str, str, int, int]]:
    """SOFT inner→outer edges: lazy (function-level) imports of an outer ring. Tolerated
    but reported — the importing code path must be excluded from a build that strips the
    outer ring. Tracked toward full plugin-ization of feature checks."""
    return _edges(deferred=True)


def tcb_modules(profile: str = "core") -> List[str]:
    """Modules that remain in the TCB at the given build profile (this ring and inward)."""
    ceiling = {"core": 0, "extended": 1, "advisory": 2}[profile]
    return sorted(m for m, r in RING.items() if r <= ceiling)


def layering_ok() -> bool:
    return not layering_violations()
