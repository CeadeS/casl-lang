#!/usr/bin/env bash
# =============================================================================
# install.sh — install and verify the CASL core.
#   Prerequisite: Python ≥ 3.9. Only third-party dependency: z3-solver.
#   Afterwards `./casl check/run/synth` and the living audit will run.
#   Override:  PYTHON=/path/to/python3 ./scripts/install.sh
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "python3 not found (set PYTHON=…)." >&2; exit 1; }
echo "Python:  $("$PY" --version 2>&1)  ($PY)"

echo "Installing core dependencies (z3-solver) ..."
# First the normal way; for externally-managed environments (PEP 668) with --break-system-packages.
"$PY" -m pip install -q -r "$HERE/requirements.txt" \
  || "$PY" -m pip install -q --break-system-packages -r "$HERE/requirements.txt"

echo "Verifying (living audit) ..."
if PYTHONPATH="$HERE/src" "$PY" -m casl.audit >/dev/null 2>&1; then
  echo "✓ CASL core installed, audit green."
else
  echo "✗ Audit failed — please check the output: PYTHONPATH=src $PY -m casl.audit" >&2
  exit 1
fi

cat <<EOF

Getting started:
  ./casl check examples/budgeted_qa.casl     # check a .casl (exit 0/1)
  ./casl run   examples/budgeted_qa.casl     # run it (mock oracle)
  ./casl ide   myproject                   # requirement-driven session

Optional:
  ./scripts/setup-ide.sh                     # MCP server for Claude Code/Codex (Python ≥3.10)
  ./run.sh                                   # versions + F* verification + audit + oracle check

Full guide: INSTALL.md
EOF
