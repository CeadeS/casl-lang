#!/usr/bin/env bash
# Enable the EMULATED branch protection (private repo — GitHub rulesets need a public/paid repo).
# Points git at the tracked hooks/ dir so hooks/pre-push runs before every push. See docs/branch-guard.md.
set -euo pipefail
root="$(git rev-parse --show-toplevel)"
chmod +x "$root"/hooks/* 2>/dev/null || true
git -C "$root" config core.hooksPath hooks
echo "✓ core.hooksPath = hooks  —  pre-push branch-guard is now active on this clone."
echo "  disable: git config --unset core.hooksPath   ·   one-off bypass: git push --no-verify"
