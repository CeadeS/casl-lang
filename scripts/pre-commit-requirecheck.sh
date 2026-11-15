#!/usr/bin/env bash
# CASL Layer-1 requirement check on STAGED Python files (per-commit, incremental).
#
# Runs the deterministic, fast checks on just the staged *.py: every effect call must trace to a
# requirement (provenance) and every irreversible effect must be approval-bound (approval-dominance).
# The slower semantic "does it fulfil the requirement" review is Layer 2 (LLM-backed), run separately.
#
# Install (from the app project's repo root):
#   ln -s "$(pwd)/scripts/pre-commit-requirecheck.sh" .git/hooks/pre-commit
# Configure (if CASL src / the project root are elsewhere):
#   export CASL_SRC=/path/to/llang/src   CASL_PROJECT=/path/to/project
set -euo pipefail

PROJECT="${CASL_PROJECT:-.}"
SRC="${CASL_SRC:-src}"

# staged, added/copied/modified .py files
mapfile -t FILES < <(git diff --cached --name-only --diff-filter=ACM -- '*.py')
if [ "${#FILES[@]}" -eq 0 ]; then
  exit 0
fi

if ! PYTHONPATH="$SRC" python3 -m casl.requirecheck "$PROJECT" "${FILES[@]}"; then
  echo "" >&2
  echo "commit blocked: a staged effect either does not trace to a requirement, or an irreversible" >&2
  echo "effect is not approval-bound. Fix it, or (last resort) bypass with: git commit --no-verify" >&2
  exit 1
fi
