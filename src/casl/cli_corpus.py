"""casl.cli_corpus — the CLI exit-code differential ORACLE (CEP-0081, the casl-cli brick).

Single-sources, per CLI case (argv + a set of files materialised in a temp dir), the EXIT CODE of the
Python reference front-end `casl` (`casl.check.main`). The Rust `casl` binary must reproduce the same exit
code on the same fixtures (rust/casl-cli/tests/cli_differential.rs). Exit codes are the behavioural contract:
0 = ok/accepted, 1 = rejected/violations, 2 = usage/IO/parse error / UNDETERMINED, 3 = ran but incomplete.

The corpus is curated to the FRAGMENT the Rust front-end fully covers — no `async`, < 4 roles — so the
ported checks reproduce the Python verdict EXACTLY (outside that fragment the Rust front-end honestly returns
2 = undetermined rather than risk a wrong-accept, which is not an exit-code-parity claim). `_covered` guards
that every check/run fixture stays in-fragment; a stray out-of-fragment fixture makes the oracle raise.

Regen: PYTHONPATH=src python -m casl.cli_corpus
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from typing import Any, Dict, List

from casl import surface
from casl.check import main as _cli_main

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-cli", "tests", "cli_corpus.json"
)

# --- fixtures: small, self-contained, in the Rust-covered fragment (no async, < 4 roles) ---------------
_LIN = "protocol Lin {\n  roles A, J;\n  A -> J : M();\n  J -> A : N();\n}\n"
_Q = (
    "protocol Q {\n  roles A, J, C;\n  rec Loop {\n"
    "    A -> J : Draft(cost: Int) [cost <= budget] oracle;\n"
    "    choice at J -> C {\n      Accept: { J -> A : Done(); }\n"
    "      Reject: { J -> A : Retry(); continue Loop; }\n    }\n  }\n}\n"
)
_CAPVIOL = "protocol Bad {\n  roles A, J;\n  A -> J : Act() uses search;\n}\n"
_GARBAGE = "this is not a protocol\n"
# ≥4-role SYNC protocols — now fully covered by the ported `concurrency_certified` (LH-Q-001d), so the Rust
# front-end gives a full verdict (no longer UNDETERMINED): GoodConc = role-disjoint comms ⇒ certified ⇒ 0;
# BadConc = concurrency across a recursion ⇒ incomplete ⇒ the concurrency gate rejects ⇒ 1.
_GOODCONC = "protocol GoodConc {\n  roles A, B, C, D;\n  A -> B : m();\n  C -> D : n();\n}\n"
_BADCONC = "protocol BadConc {\n  roles P, Q, R, S;\n  P -> Q : a();\n  rec t {\n    R -> S : b();\n    continue t;\n  }\n}\n"

_TOML = (
    'name = "demo"\nversion = "0.1.0"\n[[artifact]]\nname = "checker"\nkind = "verified"\n'
    'requirement = "R1"\ngrade = "G0"\nbody = "artifacts/checker.py"\nimplements = "Demo:Verify"\n'
)
_TOML_BADSEAM = _TOML.replace('implements = "Demo:Verify"', 'implements = "Demo:Nope"')
_DEMO_CASL = "protocol Demo {\n  roles A, J;\n  A -> J : Verify(x: Int) verified;\n}\n"
_DEPS_OK = (
    "imap_client 3.0.1 "
    "sha256:6f1ed002ab5595859014ebf0951522d9a455eb9b8d1f9f0e2f1e0a0e3b6c7d8e "
    "accepted-by:Martin date:2026-06-24\n"
)
_DEPS_BAD = "foo 1.0 nothash accepted-by:Martin\n"

# Each case: id, argv (after the program name), files {relpath: content} materialised in a fresh temp dir.
_CASES: List[Dict[str, Any]] = [
    {"id": "check_linear_ok", "argv": ["check", "p.casl"], "files": {"p.casl": _LIN}},
    {"id": "check_budget_ok", "argv": ["check", "p.casl"], "files": {"p.casl": _Q}},
    {"id": "check_capviol_reject", "argv": ["check", "p.casl"], "files": {"p.casl": _CAPVIOL}},
    {"id": "check_parse_error", "argv": ["check", "p.casl"], "files": {"p.casl": _GARBAGE}},
    {"id": "check_missing_file", "argv": ["check", "nope.casl"], "files": {}},
    {"id": "check_json_ok", "argv": ["check", "p.casl", "--json"], "files": {"p.casl": _LIN}},
    {"id": "run_budget_ok", "argv": ["run", "p.casl", "--scenario", "ok"], "files": {"p.casl": _Q}},
    {"id": "run_budget_overspend", "argv": ["run", "p.casl", "--scenario", "overspend"], "files": {"p.casl": _Q}},
    {"id": "run_linear_ok", "argv": ["run", "p.casl", "--scenario", "ok"], "files": {"p.casl": _LIN}},
    {"id": "run_capviol_reject", "argv": ["run", "p.casl", "--scenario", "ok"], "files": {"p.casl": _CAPVIOL}},
    {"id": "project_ok", "argv": ["project", "proj"], "files": {"proj/casl.toml": _TOML, "proj/casl/demo.casl": _DEMO_CASL}},
    {"id": "project_missing", "argv": ["project", "empty"], "files": {"empty/.keep": ""}},
    {"id": "deps_ok", "argv": ["deps", "proj"], "files": {"proj/deps.lock": _DEPS_OK}},
    {"id": "deps_bad", "argv": ["deps", "proj"], "files": {"proj/deps.lock": _DEPS_BAD}},
    {"id": "seam_ok", "argv": ["seam", "proj"], "files": {"proj/casl.toml": _TOML, "proj/casl/demo.casl": _DEMO_CASL}},
    {"id": "seam_violation", "argv": ["seam", "proj"], "files": {"proj/casl.toml": _TOML_BADSEAM, "proj/casl/demo.casl": _DEMO_CASL}},
    {"id": "flow_ok", "argv": ["flow", "proj"], "files": {"proj/casl.toml": _TOML, "proj/casl/demo.casl": _DEMO_CASL}},
    # ≥4-role sync concurrency — now a full verdict (no UNDETERMINED) via the ported concurrency_certified.
    {"id": "check_conc_certified", "argv": ["check", "p.casl"], "files": {"p.casl": _GOODCONC}},
    {"id": "check_conc_incomplete", "argv": ["check", "p.casl"], "files": {"p.casl": _BADCONC}},
    {"id": "run_conc_certified", "argv": ["run", "p.casl", "--scenario", "ok"], "files": {"p.casl": _GOODCONC}},
]


def covered(src: str) -> bool:
    """In the Rust-covered fragment: parses and is NOT `async`. Sync protocols (any role count) are fully
    covered now that `concurrency_certified` is ported; only the `async` concurrency gate (`async_bounded`)
    is un-ported, so an `async` protocol yields Rust exit 2 (UNDETERMINED) ≠ Python and is excluded."""
    p = surface.parse(src)
    return getattr(p, "async_k", None) is None


def python_exit(argv: List[str], files: Dict[str, str]) -> int:
    """The Python reference front-end's exit code for `casl <argv>` with `files` in the cwd."""
    with tempfile.TemporaryDirectory() as td:
        for rel, content in files.items():
            path = os.path.join(td, rel)
            os.makedirs(os.path.dirname(path) or td, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        cwd = os.getcwd()
        try:
            os.chdir(td)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                rc = _cli_main(argv)
        finally:
            os.chdir(cwd)
    return int(rc)


def build_corpus() -> List[Dict[str, Any]]:
    out = []
    for c in _CASES:
        # Guard: every check/run fixture must stay in the Rust-covered fragment (else Rust → 2 ≠ Python).
        if c["argv"][0] in ("check", "run"):
            casls = [v for k, v in c["files"].items() if k.endswith(".casl")]
            for src in casls:
                try:
                    ok = covered(src)
                except Exception:
                    ok = True  # a deliberate parse-error fixture isn't a fragment-coverage concern
                assert ok, f"case {c['id']}: .casl fixture is out of the Rust-covered fragment"
        out.append({**c, "exit": python_exit(c["argv"], c["files"])})
    return out


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} CLI exit-code case(s) → {out}")
