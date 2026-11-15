# casl-ide — Claude Code plugin

Exposes the CASL-IDE tooling as MCP tools for Claude Code (and any MCP client):

- **`casl_check`** — checks a `.casl` specification against the deterministic Tier-0 gate.
- **`casl_gate`** — applies the monotone gate and reports what must be attested by a human.
- **`casl_synthesize`** — proposes a checked `.casl` spec from a requirement.

**Boundary invariant:** the server is advisory — it checks, synthesizes, and reports; it never grants and executes nothing.

## Installation

Recommended (picks Python ≥3.10, installs dependencies, registers):

```bash
../../scripts/setup-ide.sh
```

Or manually — see `INSTALL.md` §3. The server requires **Python ≥ 3.10** (MCP SDK); `.mcp.json` uses `python3.12`. Adjust the command if your ≥3.10 interpreter has a different name.
