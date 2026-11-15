# CASL — Installation

Two installation tiers: the **core** (language + checker + IDE CLI, needs only Python + z3) and optionally the **MCP server** (so that Claude Code / Codex can use the IDE tools). F\* and the Rust engine are purely optional.

---

## 1. Prerequisites

| For | Requirement |
|---|---|
| **Core** (`./casl`, audit, `casl ide`) | Python **≥ 3.9** + `z3-solver` (installed by the script) |
| **MCP server** (Claude Code / Codex) | Python **≥ 3.10** (!) + `mcp` |
| Claude Code / Codex as oracle | `claude` or `codex` CLI on the `PATH` |
| Formal core (optional) | `fstar.exe` |
| Rust engine (optional) | `cargo` |

> **Important pitfall:** the MCP SDK needs **Python ≥ 3.10**. If your `python3` is older (e.g. 3.9), the MCP server must run under a newer interpreter (e.g. `python3.12`). The core itself also runs under 3.9. `scripts/setup-ide.sh` automatically selects a suitable interpreter.

---

## 2. Install the Core

```bash
./scripts/install.sh
```

This installs `z3-solver` and verifies the installation via the living audit. Manually:

```bash
python3 -m pip install -r requirements.txt        # append --break-system-packages if needed
PYTHONPATH=src python3 -m casl.audit              # must print "AUDIT: ✓ PASSED"
```

### Verify

```bash
./casl check examples/budgeted_qa.casl            # ✓ ACCEPTED (Exit 0)
./casl check examples/attacks/silent_send.casl    # ✗ REJECTED  (Exit 1)
```

First steps with the language: **`docs/guide.md`**.

---

## 3. IDE / MCP Server (Claude Code & Codex)

So that an agentic coder uses the tools `casl_check`, `casl_gate`, `casl_synthesize`. One command:

```bash
./scripts/setup-ide.sh
```

This finds a Python ≥ 3.10, installs `mcp` + `z3-solver`, and registers the server with Claude Code (`claude mcp add`). It additionally prints the Codex snippet.

### Manually

```bash
# Python ≥3.10 + SDK
python3.12 -m pip install -r requirements-ide.txt

# Claude Code
claude mcp add casl-ide -- python3.12 "$(pwd)/src/casl/mcp.py"
claude mcp get casl-ide        # Status: ✔ Connected

# Codex  (~/.codex/config.toml)
[mcp_servers.casl-ide]
command = "python3.12"
args    = ["/ABSOLUTE/PATH/src/casl/mcp.py"]
```

Use the **absolute** path to `casl_mcp.py` and a Python command that is ≥3.10.

### As a Claude Code Plugin (in-place)

`plugin/casl-ide/` contains a plugin manifest (`.claude-plugin/plugin.json` + `.mcp.json`). It loads the server in-place; for the tested registration, `setup-ide.sh` is the recommended path.

**Security note:** The MCP server is *advisory* — it checks, synthesizes, and reports what a human must attest. It never releases and never executes effectful protocols.

---

## 4. Optional: Formal Core (F\*) and Engine (Rust)

```bash
make -C fstar verify        # machine-verify CASL.fst (0 admits)   [needs fstar.exe]
make -C fstar ocaml-run     # extract + run the verified core as OCaml
cargo test  --manifest-path rust/Cargo.toml      # the Rust workspace                [needs cargo]
./run.sh                    # full run: versions + F* + audit + oracle check → logs/
```

---

## 5. Live Oracle (optional)

`casl run --live` / `casl synth --live` / `casl ide --review` talk to an OpenAI-compatible LLM. Endpoint/model from `.env` (`OLLAMA_URL`, `OLLAMA_MODEL`) or via `--endpoint`/`--model`. Without `--live`, everything runs deterministically with a mock oracle (no network). Local coders as oracle: `oracle.CoderBackend("claude")` or `"codex"`.

---

## 6. Troubleshooting

- **`No module named 'mcp'` / server does not start:** the server is running under a Python < 3.10. Register it with a ≥3.10 interpreter (`python3.12 …`); `setup-ide.sh` does this automatically.
- **`error: externally-managed-environment` (pip, PEP 668):** append `--break-system-packages`, or use a venv/conda env. `install.sh`/`setup-ide.sh` fall back to that automatically.
- **codex does not start / was deleted:** the macOS Gatekeeper may remove the vendored codex binary on suspicion of malware. Reinstall (`npm install -g @openai/codex`) and, if needed, allow it in the security settings. `claude` works independently of this.
- **`claude mcp get casl-ide` does not show "Connected":** check the path to `mcp.py` and the Python command; `python3.12 src/casl/mcp.py --selftest` should print three OK lines.
- **Audit/live fails only in a sandbox:** egress may be blocked — the live endpoint is reachable from your own machine but possibly not from a sandbox. The audit itself is offline and needs no network.
