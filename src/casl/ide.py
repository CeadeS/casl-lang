"""
casl_ide.py — requirement-driven IDE, Phase 1 (MVP): the MONOTONE GATE.

Reference: `docs/ide.md`. The user states requirements (authority), a generator oracle
proposes an artifact (choreography), and a LAYERED, MONOTONE gate decides
what may be adopted. Guiding invariant:

    "Agents may veto, never vouch."

Each layer can only SHRINK the permitted set; the deterministic checker (Tier 0)
is the ONLY opener. This is structurally enforced here: the Tier-2 review yields a
type `Tier2 ∈ {PASS, VETO, ESCALATE}` — there is NO `APPROVE`. A reviewer therefore
cannot release at all, only wave through (PASS), reject (VETO), or escalate to the human (ESCALATE).

Layers:
  Tier 0  deterministic checker      (casl check: projection/types/caps/SMT/approval)  — sole opener
  Tier 1  deterministic runtime       (mock run: terminates, no deadlock/tool_denied)   — binding
  Tier 2  agent review                (PASS | VETO | ESCALATE)                           — never release
  Tier 3  human                       (attests effect-bearing/irreversible artifacts)   — by-exception

Everything is reused: casl_check (Tier 0), casl_run (Tier 1/run), casl_synth (generator loop).
The proven core stays untouched.
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from casl import core          # noqa: E402
from casl import surface    # noqa: E402
from casl import check        # noqa: E402
from casl import run            # noqa: E402
from casl import synth        # noqa: E402
from casl import oracle as orc              # noqa: E402
from casl import spike_approval as appr     # noqa: E402
from casl import spike_pipeline as pipe     # noqa: E402


# --------------------------------------------------------------------------
# Tier-2 verdict — STRUCTURALLY monotone: there is NO APPROVE.
# A reviewer can only wave through, reject, or escalate — never release.
# --------------------------------------------------------------------------
class Tier2(Enum):
    PASS = "pass"        # no objections — does NOT release, only passes it on
    VETO = "veto"        # reject
    ESCALATE = "escalate"  # escalate to the human (forces Tier 3)


Reviewer = Callable[[object], Tier2]              # (Protocol) -> Tier2   (cannot approve)
Approver = Callable[[str], bool]                  # (disclosure) -> bool  (human, Tier 3)


@dataclass(frozen=True)
class GateOutcome:
    accepted: bool
    tier: int            # deciding layer 0..3; 4 = all passed
    reason: str
    effects: Tuple[str, ...] = ()    # detected effect-bearing actions (for the Tier-3 disclosure)


# --------------------------------------------------------------------------
# Effect detection (for Tier 3): irreversible OR non-read capability
# --------------------------------------------------------------------------
def _effect_actions(g, caps: Optional[dict]) -> List[str]:
    caps = caps or {}
    out: List[str] = []

    def cap_effectful(sender, tool) -> bool:
        for c in caps.get(sender, ()):
            if c.tool == tool:
                return appr.effectful(c)
        return True   # used but undeclared tool ⇒ effect-bearing as a precaution

    def walk(n):
        if isinstance(n, core.Comm):
            if n.irreversible or (n.uses_capability and cap_effectful(n.sender, n.uses_capability)):
                out.append(f"{n.sender}→{n.receiver}:{n.label}"
                           + (" [irreversible]" if n.irreversible else f" ⟨{n.uses_capability}⟩"))
            walk(n.cont)
            if n.on_crash is not None:
                walk(n.on_crash)
        elif isinstance(n, core.Choice):
            for b in n.branches:
                walk(b.cont)
        elif isinstance(n, core.Rec):
            walk(n.body)

    walk(g)
    return out


# --------------------------------------------------------------------------
# Tier 1 — deterministic runtime view (mock run, no network)
# --------------------------------------------------------------------------
def _tier1_runtime(proto) -> Tuple[bool, str]:
    """The artifact run under the deterministic mock oracle terminates without deadlock /
    tool denial (approve=True, so that approval gates remain reserved for Tier 3)."""
    try:
        r = run.run_protocol(proto.gtype, orc.MockBackend("ok"),
                             {"budget": 100, "question": "q"}, max_loops=5,
                             approve=True, caps=proto.caps)
    except Exception as e:                     # a runtime error is a Tier-1 failure
        return False, f"runtime error {e!r}"
    if r.outcome in ("completed", "loop_bound_reached"):
        return True, r.outcome
    return False, f"run ended as {r.outcome}"


# --------------------------------------------------------------------------
# The monotone gate
# --------------------------------------------------------------------------
def monotone_gate(proto, *, caps: Optional[dict] = None,
                  reviewer: Optional[Reviewer] = None,
                  approver: Optional[Approver] = None,
                  tier1: bool = True) -> GateOutcome:
    caps = caps if caps is not None else getattr(proto, "caps", {})

    # Tier 0 — deterministic checker: the ONLY opener.
    report = check.check_protocol(proto)
    if not report["accepted"]:
        fails = [c["label"] for c in report["checks"] if c["gating"] and not c["ok"]]
        return GateOutcome(False, 0, "Tier0 det. checker rejected: " + "; ".join(fails))

    # Tier 1 — deterministic runtime (binding).
    if tier1:
        ok1, why1 = _tier1_runtime(proto)
        if not ok1:
            return GateOutcome(False, 1, f"Tier1 runtime: {why1}")

    # Tier 2 — agent review: can ONLY veto/escalate (the type enforces it).
    escalated = False
    if reviewer is not None:
        v = reviewer(proto)
        if v == Tier2.VETO:
            return GateOutcome(False, 2, "Tier2 agent review: VETO")
        if v == Tier2.ESCALATE:
            escalated = True

    # Tier 3 — human: attests effect-bearing/irreversible artifacts, escalated cases AND
    # `verified` trust claims (the machine cannot prove an external program — W17).
    effects = _effect_actions(proto.gtype, caps)
    trust = pipe.verified_nodes(proto.gtype)
    if effects or trust or escalated:
        bits = []
        if effects:
            bits.append("effect-bearing: " + ", ".join(effects))
        if trust:
            bits.append("verified trust claim (to be attested by a human): " + ", ".join(trust))
        if escalated and not (effects or trust):
            bits.append("escalated by Tier-2 review")
        why = "; ".join(bits) if bits else "escalated"
        disclosure = f"Adoption of «{proto.name}» — {why}. Approve?"
        if approver is None or not approver(disclosure):
            return GateOutcome(False, 3, f"Tier3 human: no approval ({why})", tuple(effects))

    return GateOutcome(True, 4, "passed all layers", tuple(effects))


# --------------------------------------------------------------------------
# Generator behind the gate (Tier-0 convergence via synth loop, then the full gate)
# --------------------------------------------------------------------------
def synthesize_gated(wish: str, generator, *, caps: Optional[dict] = None,
                     reviewer: Optional[Reviewer] = None, approver: Optional[Approver] = None,
                     max_iters: int = 6) -> Tuple[GateOutcome, "synth.SynthResult"]:
    r = synth.synthesize(wish, generator, max_iters=max_iters)
    if not r.accepted:
        return GateOutcome(False, 0, "Tier0: synthesis did not converge"), r
    proto = surface.parse(r.casl_text)
    outcome = monotone_gate(proto, caps=caps or proto.caps, reviewer=reviewer, approver=approver)
    return outcome, r


# --------------------------------------------------------------------------
# Example reviewer / approver (deterministic, offline)
# --------------------------------------------------------------------------
def policy_reviewer_no_admin(proto) -> Tier2:
    """Example Tier-2 policy (something Tier 0 ALLOWS but the org forbids):
    no `admin` capability. Demonstrates a restriction beyond the deterministic gate."""
    for caps in (getattr(proto, "caps", {}) or {}).values():
        for c in caps:
            if getattr(c, "mode", "write") == "admin":
                return Tier2.VETO
    return Tier2.PASS


def always_pass(proto) -> Tier2:
    return Tier2.PASS


def deny_approver(_disclosure: str) -> bool:
    return False


def auto_approver(_disclosure: str) -> bool:
    return True


# --------------------------------------------------------------------------
# Tier 2 — LLM reviewer (Phase 2). The LLM is an oracle; its output is
# DETERMINISTICALLY CLAMPED to {PASS, VETO, ESCALATE} — it can never open.
# --------------------------------------------------------------------------
REVIEW_SYSTEM = (
    "You are a SAFETY/POLICY REVIEWER for CASL protocol specifications. The spec has ALREADY passed "
    "the deterministic checker (well-formed, capability-contained, approval-dominated) — admissibility "
    "is NOT your call. Your ONLY job is to flag what the checker cannot see: policy violations, the spec "
    "not matching the stated requirement, risky or unclear designs. You CANNOT approve. Respond with "
    "EXACTLY one verdict token on the first line, then a one-line reason:\n"
    "  PASS      no concern (this does NOT approve — the checker already decided admissibility)\n"
    "  VETO      a concrete, serious concern → reject\n"
    "  ESCALATE  needs human judgement\n"
    "Output only the token and the reason.")


def parse_tier2(text: str) -> Tier2:
    """DETERMINISTIC clamp: any reviewer output → {PASS, VETO, ESCALATE}. An LLM-uttered
    "APPROVE/LGTM/ship it" is clamped to PASS (does NOT open — Tier 0 is the only
    opener, Tier 3 remains responsible for effects). The unrecognizable falls FAIL-SAFE to ESCALATE (human)."""
    t = (text or "").strip().upper()
    head = t.split()[0].strip(".:,!") if t.split() else ""
    if head in ("VETO", "REJECT", "BLOCK", "DENY", "NO", "UNSAFE"):
        return Tier2.VETO
    if head in ("ESCALATE", "HUMAN", "UNSURE", "UNCLEAR", "MAYBE"):
        return Tier2.ESCALATE
    if head in ("PASS", "APPROVE", "ACCEPT", "OK", "LGTM", "YES", "SAFE", "FINE"):
        return Tier2.PASS   # "APPROVE" is CLAMPED to PASS — a reviewer cannot release
    return Tier2.ESCALATE   # anything unrecognized → to the human (fail-safe), never silently PASS


def _render_for_review(proto) -> str:
    lines = ["protocol " + str(getattr(proto, "name", "?")), core.global_pretty(proto.gtype)]
    caps = getattr(proto, "caps", {}) or {}
    parts = []
    for r, cs in caps.items():
        if not cs:
            continue
        tools = ", ".join(c.tool + "(mode=" + getattr(c, "mode", "write") + ")" for c in cs)
        parts.append(str(r) + ": " + tools)
    if parts:
        lines.append("capabilities: " + "; ".join(parts))
    return "\n".join(lines)


def llm_review(chat, proto, wish: str = "") -> Tier2:
    """Tier-2 review via a chat call `chat(system, user) -> str`. FAIL-CLOSED: if the
    reviewer oracle is unreachable, ESCALATE (human) is returned — never silently PASS."""
    user = _render_for_review(proto) + (f"\n\nRequirement: {wish}" if wish else "")
    try:
        out = chat(REVIEW_SYSTEM, user)
    except orc.OracleUnavailable:
        return Tier2.ESCALATE   # review not feasible ⇒ to the human, do not wave through
    return parse_tier2(out)


def make_llm_reviewer(backend, wish: str = "") -> Reviewer:
    """Builds a Tier-2 reviewer from a backend with `.chat(system,user)` (e.g. oracle.OllamaBackend
    of a DIFFERENT model than the generator — cross-model against self-preference bias)."""
    return lambda proto: llm_review(backend.chat, proto, wish)


# --------------------------------------------------------------------------
# Project model (lightweight): requirements (authority) + adopted artifacts + trace
# --------------------------------------------------------------------------
@dataclass
class Project:
    path: str

    @property
    def artifacts_dir(self) -> str:
        return os.path.join(self.path, "artifacts")

    @property
    def trace_file(self) -> str:
        return os.path.join(self.path, "trace.jsonl")

    @property
    def requirements_file(self) -> str:
        return os.path.join(self.path, "requirements.md")

    def init(self) -> "Project":
        os.makedirs(self.artifacts_dir, exist_ok=True)
        if not os.path.exists(self.requirements_file):
            with open(self.requirements_file, "w", encoding="utf-8") as f:
                f.write(f"# Requirements — {os.path.basename(self.path)}\n\n"
                        "The user is the authority. Each line is one requirement (R-n).\n")
        return self

    def add_requirement(self, text: str) -> str:
        rid = f"R-{int(time.time())}"
        with open(self.requirements_file, "a", encoding="utf-8") as f:
            f.write(f"- {rid}: {text}\n")
        return rid

    def adopt(self, name: str, casl_text: str, requirement: str, outcome: GateOutcome) -> str:
        """Call only after the gate has passed. Writes the artifact + trace (requirement↔artifact↔verdict)."""
        os.makedirs(self.artifacts_dir, exist_ok=True)
        p = os.path.join(self.artifacts_dir, f"{name}.casl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(casl_text if casl_text.endswith("\n") else casl_text + "\n")
        with open(self.trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "requirement": requirement, "artifact": name,
                                "accepted": outcome.accepted, "tier": outcome.tier,
                                "reason": outcome.reason, "effects": list(outcome.effects)},
                               ensure_ascii=False) + "\n")
        return p


# --------------------------------------------------------------------------
# Interactive session (CLI) + non-interactive batch (for tests/demo)
# --------------------------------------------------------------------------
def _interactive_approver() -> Approver:
    def ask(disclosure: str) -> bool:
        if not sys.stdin.isatty():
            print(f"\n[Tier 3 — human] {disclosure}\n  → no TTY ⇒ default-deny", file=sys.stderr)
            return False
        print(f"\n[Tier 3 — human] {disclosure}")
        try:
            return input("  Approve? [y/N] ").strip().lower() in ("y", "yes", "j", "ja")
        except EOFError:
            return False
    return ask


def session(project_path: str, generator=None, reviewer: Optional[Reviewer] = None,
            reviewer_backend=None, approver: Optional[Approver] = None) -> int:
    """Interactive requirement loop: requirement in → generator → monotone gate → adopt if applicable.
    `reviewer_backend` (with `.chat`) activates the Tier-2 LLM review (cross-model, built per requirement with
    the wish); otherwise the static `reviewer` applies (default: always_pass)."""
    proj = Project(project_path).init()
    generator = generator or synth.MockGenerator()
    approver = approver or _interactive_approver()
    static_reviewer = reviewer if reviewer is not None else always_pass
    print("=" * 72)
    print(f"CASL-IDE — project {project_path}   (leave empty + Enter to finish)")
    print("The user states requirements; everything else is checked (monotone gate).")
    if reviewer_backend is not None:
        print(f"Tier-2 LLM review active (model: {getattr(reviewer_backend, 'model', '?')}).")
    print("=" * 72)
    while True:
        try:
            wish = input("\nRequirement> ").strip()
        except EOFError:
            break
        if not wish:
            break
        rid = proj.add_requirement(wish)
        reviewer = make_llm_reviewer(reviewer_backend, wish) if reviewer_backend is not None else static_reviewer
        outcome, r = synthesize_gated(wish, generator, caps=None, reviewer=reviewer, approver=approver)
        print(f"  [{rid}] synthesis: {'accepted' if r.accepted else 'did not converge'} "
              f"({r.iterations} iters) → gate: " + ("✓ ADOPTABLE" if outcome.accepted
              else f"✗ rejected @ Tier {outcome.tier}"))
        print(f"        {outcome.reason}")
        if outcome.accepted:
            name = r.casl_text.split("protocol", 1)[-1].strip().split()[0] if "protocol" in r.casl_text else rid
            path = proj.adopt(name, r.casl_text, rid, outcome)
            print(f"        adopted → {os.path.relpath(path, project_path)}; trace: trace.jsonl")
    print("\nSession finished.")
    return 0


if __name__ == "__main__":
    # Offline demo of the monotone gate (deterministic, no network).
    print("=" * 72)
    print("CASL-IDE — monotone gate (demo, offline)")
    print("=" * 72)
    # 1) safe artifact (budgeted QA, search=read) → all layers
    o1, _ = synthesize_gated("Budgeted QA with retry", synth.MockGenerator(),
                             reviewer=always_pass, approver=deny_approver)
    print(f"  QA (no effect):              {'✓' if o1.accepted else '✗'} Tier {o1.tier} — {o1.reason}")
    # 2) the same safe case, but the reviewer vetoes → Tier 2 (shows: veto beats Tier-0 acceptance)
    o2, _ = synthesize_gated("Budgeted QA with retry", synth.MockGenerator(),
                             reviewer=lambda p: Tier2.VETO, approver=auto_approver)
    print(f"  QA + reviewer veto:          {'✓' if o2.accepted else '✗'} Tier {o2.tier} — {o2.reason}")
    # 3) effect-bearing artifact (reschedule) without/with the human
    pr = surface.Protocol(name="Reschedule", roles=["S", "U", "K"], caps=appr.CAPS_CAL,
                          crash=set(), gtype=appr.G_RESCHED_OK)
    od = monotone_gate(pr, caps=appr.CAPS_CAL, reviewer=always_pass, approver=deny_approver)
    oa = monotone_gate(pr, caps=appr.CAPS_CAL, reviewer=always_pass, approver=auto_approver)
    print(f"  Reschedule (effect), deny:   {'✓' if od.accepted else '✗'} Tier {od.tier} — {od.reason}")
    print(f"  Reschedule (effect), approve:{'✓' if oa.accepted else '✗'} Tier {oa.tier} — {oa.reason}")
    print(f"  Monotone by construction: Tier2 has no APPROVE option → {[t.name for t in Tier2]}")
