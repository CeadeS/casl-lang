"""
casl_mcp.py — MCP server: exposes the CASL-IDE tools to ANY MCP client (Claude Code, Codex,
Cursor, Claude Desktop, Cowork). docs/ide.md Phase 3, backend spine: MCP is the open standard
through which the coders use our tool — without binding to any single vendor.

BOUNDARY INVARIANT (the safety fact of this phase):
  The server is ADVISORY/read-only. It CHECKS (Tier 0), SYNTHESIZES candidates, and REPORTS what
  would need human attestation (Tier 3) — it ADOPTS NOTHING, releases NOTHING, and runs
  NO effect-bearing protocols. This preserves monotonicity across the MCP boundary:
  a coder that calls these tools cannot "open" anything — the tools open nothing.

SDK OPTIONAL: the tool FUNCTIONS (tool_check/tool_gate/tool_synthesize) run without `mcp` and are
testable offline; only `main()` (stdio transport) needs `pip install mcp`.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from casl import surface   # noqa: E402
from casl import check       # noqa: E402
from casl import synth       # noqa: E402
from casl import ide           # noqa: E402
from casl import spike_pipeline as pipe    # noqa: E402


# --------------------------------------------------------------------------
# Tool handlers — pure functions over the existing substrate (no SDK required).
# --------------------------------------------------------------------------
def tool_check(casl_text: str) -> dict:
    """Checks a .casl specification against the Tier-0 gate (deterministic checker).
    Side-effect-free. → {accepted, muss_violations, soll_hinweise, roles}."""
    try:
        proto = surface.parse(casl_text)
    except SyntaxError as e:
        return {"accepted": False, "parse_error": str(e)}
    rep = check.check_protocol(proto)
    fails = [{"check": c["label"], "detail": c["detail"]}
             for c in rep["checks"] if c["gating"] and not c["ok"]]
    warns = [c["label"] for c in rep["checks"] if not c["gating"] and not c["ok"]]
    return {"accepted": rep["accepted"], "muss_violations": fails,
            "soll_hinweise": warns, "roles": rep["roles"]}


def tool_gate(casl_text: str) -> dict:
    """Applies the monotone gate (Tier 0/1) and REPORTS what would need human attestation
    (effect-bearing actions + `verified` trust claims). NEVER releases on its own and runs nothing
    — `reviewer=None, approver=None`. → {adoptable, tier, reason, needs_human_attestation, note}."""
    try:
        proto = surface.parse(casl_text)
    except SyntaxError as e:
        return {"adoptable": False, "tier": 0, "parse_error": str(e)}
    outcome = ide.monotone_gate(proto, caps=proto.caps, reviewer=None, approver=None)
    needs_human = list(outcome.effects) + pipe.verified_nodes(proto.gtype)
    return {"adoptable": outcome.accepted, "tier": outcome.tier, "reason": outcome.reason,
            "needs_human_attestation": needs_human,
            "note": "Server does NOT approve/adopt; human approval happens in the client (Tier 3)."}


def tool_synthesize(wish: str) -> dict:
    """Proposes a .casl specification from a requirement (deterministic mock generator
    behind the Tier-0 gate) and checks it. Returns candidate + verdict — adopts NOTHING."""
    r = synth.synthesize(wish, synth.MockGenerator(), max_iters=6)
    return {"converged": r.accepted, "iterations": r.iterations,
            "casl": r.casl_text if r.accepted else "",
            "verdict": tool_check(r.casl_text) if r.accepted else None}


TOOLS = {"casl_check": tool_check, "casl_gate": tool_gate, "casl_synthesize": tool_synthesize}


# --------------------------------------------------------------------------
# MCP transport (SDK only needed here). For registration in Claude Code/Codex see docs/ide.md.
# --------------------------------------------------------------------------
def build_server():
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as e:   # pragma: no cover — only without an installed SDK
        raise SystemExit(
            "MCP SDK missing — `pip install mcp` (only needed to run the server; the tool functions "
            "and their tests run without the SDK). Detail: %r" % (e,))
    srv = FastMCP("casl-ide")
    srv.tool(name="casl_check",
             description="Check a .casl specification (Tier-0 gate, side-effect free).")(tool_check)
    srv.tool(name="casl_gate",
             description="Monotone gate (Tier 0/1); reports what must be attested by a human; "
                         "never approves, executes nothing.")(tool_gate)
    srv.tool(name="casl_synthesize",
             description="Propose a checked .casl spec from a requirement (mock generator).")(tool_synthesize)
    return srv


def main():   # pragma: no cover — Transport
    build_server().run()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        # Offline self-test of the handlers (without SDK): make the boundary invariant visible.
        from casl import synth as _syn
        ok = tool_check(_syn._FIXED)
        print("tool_check(FIXED).accepted =", ok["accepted"])
        bad = tool_check("protocol X { roles A, B; A -> B : M() oracle; }")
        print("tool_check(unmonitored oracle).accepted =", bad["accepted"], "(expected False)")
        g = tool_gate(_syn._RESCHED_SAFE)
        print("tool_gate(reschedule).adoptable =", g["adoptable"], "needs_human =", g["needs_human_attestation"])
    else:
        main()
