#!/usr/bin/env bash
# =============================================================================
# setup-ide.sh — register the CASL-IDE MCP server with Claude Code (and optionally Codex).
# CASL-IDE.md phase 5 (packaging). Codifies the tested workflow:
#   1) find Python ≥3.10 (the MCP SDK requires it; the system python3 may be too old),
#   2) install dependencies (mcp = transport, z3-solver = checker),
#   3) register with Claude Code; print the Codex snippet.
# =============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$HERE/src/casl/mcp.py"
[ -f "$SERVER" ] || { echo "Server not found: $SERVER" >&2; exit 1; }

# 1) Python ≥3.10 (MCP SDK requirement)
PY=""
for c in python3.12 python3.13 python3.11 python3.10 python3; do
  command -v "$c" >/dev/null 2>&1 || continue
  if "$c" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
[ -n "$PY" ] || { echo "No Python ≥3.10 found — the MCP SDK requires it." >&2; exit 1; }
echo "Python:  $PY ($($PY --version 2>&1))"
echo "Server:  $SERVER"

# 2) Dependencies
echo "Installing mcp + z3-solver ..."
"$PY" -m pip install -q mcp z3-solver

# 3) Register with Claude Code
if command -v claude >/dev/null 2>&1; then
  claude mcp add casl-ide -- "$PY" "$SERVER" && echo "✓ registered with Claude Code: casl-ide"
else
  echo "claude CLI not found — manually: claude mcp add casl-ide -- \"$PY\" \"$SERVER\""
fi

# 4) Codex (optional)
cat <<EOF

Codex (if installed): add to ~/.codex/config.toml:
  [mcp_servers.casl-ide]
  command = "$PY"
  args = ["$SERVER"]

Done. Tools in the client: casl_check, casl_gate, casl_synthesize.
EOF
