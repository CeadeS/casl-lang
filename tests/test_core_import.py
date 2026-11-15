"""Backlog B2 — compile-out precondition at RUNTIME: importing the core checker must not pull in any
outer-ring (extended/advisory) module. Run in a FRESH interpreter (subprocess) so a prior test that
imported an outer module cannot mask the result. Complements the static AST guard in profiles.py."""
import os
import subprocess
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
_OUTER = ["oracle", "synth", "ide", "mcp", "run", "run_all", "spike_pipeline", "semantics_async"]


def _import_and_check(entry: str):
    code = (
        "import importlib, sys\n"
        f"importlib.import_module({entry!r})\n"
        f"bad = [m for m in {_OUTER!r} if ('casl.' + m) in sys.modules]\n"
        "sys.stderr.write('LOADED_OUTER=' + ','.join(bad))\n"
        "sys.exit(1 if bad else 0)\n"
    )
    env = dict(os.environ, PYTHONPATH=_SRC)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)


def test_core_checker_import_pulls_no_outer_ring():
    r = _import_and_check("casl.check")
    assert r.returncode == 0, f"core checker import loaded outer ring: {r.stderr}"


def test_levels_and_profiles_import_clean():
    for entry in ("casl.levels", "casl.profiles", "casl.authoritative"):
        r = _import_and_check(entry)
        assert r.returncode == 0, f"{entry} loaded outer ring: {r.stderr}"
