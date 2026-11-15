"""
casl_synth.py — requirement-driven synthesis: NL → Spec → code → test → feedback loop.
[LH-G-004; stage T]   (Vision: design-time oracle behind the verifier gate)

The loop in one sentence: *the LLM proposes a specification, `casl check` decides,
derived tests run, the human adopts.*

  1. NL → Spec : a generator (mock | live Gemma) produces a `.casl` from the wish.
  2. Spec → code: `casl check` is the GATE; only the well-formed passes. "code" = the
     projected local types (+ prompts) — the deterministic, derived part.
  3. → test    : tests derived from the spec (mock runs via casl_run: ok → terminates,
     overspend → loop bound).
  4. → feedback: on rejection the MUST diagnostics go back as feedback to the generator
     (bounded iterations) until accepted. Adoption ("adopt") is the human approval.

The design-time oracle is thus fenced in just like the runtime oracle: nothing unchecked
gets through. Mock = deterministic/offline (living system); live = a real Gemma.
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from casl import core          # noqa: E402
from casl import surface    # noqa: E402
from casl import check        # noqa: E402
from casl import run            # noqa: E402
from casl import oracle as orc              # noqa: E402
from casl import spike_proj_mpst as mpst    # noqa: E402


@dataclass
class SynthResult:
    accepted: bool
    iterations: int
    casl_text: str
    trace: List[Tuple[int, str, Optional[str]]] = field(default_factory=list)
    locals_: Dict[str, str] = field(default_factory=dict)
    tests: Dict[str, bool] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Generators (design-time oracle)
# --------------------------------------------------------------------------
# Deterministic mock: the first attempt has a non-local choice (A cannot tell the branches
# apart) → fails well-formedness; after the feedback it delivers the corrected
# version (== budgeted_qa) → passes. This makes the repair loop provable offline.
_BROKEN = """protocol BudgetedQA {
  roles C, A, J;
  C -> A : Request(question: Str, budget: Int);
  A -> J : Draft(answer: Str, cost: Int);
  choice at J -> C {
    Accept: { }
    Reject(reason: Str): { J -> A : Retry(); }
  }
}"""

_FIXED = """protocol BudgetedQA {
  roles C, A, J;
  agent A caps { search(query) scope "web:readonly" mode read ttl 3 sig "sig-A1"; }
  C -> A : Request(question: Str, budget: Int);
  rec Loop {
    A -> J : Draft(answer: Str, cost: Int) [cost <= budget] uses search oracle;
    choice at J -> C {
      Accept: { J -> A : Done(); }
      Reject(reason: Str) [len(reason) > 0]: { J -> A : Retry(); continue Loop; }
    }
  }
}"""


class MockGenerator:
    """Scripted generator: broken first, correct after feedback (deterministic)."""

    def __init__(self):
        self.calls = 0

    def propose(self, wish: str, feedback: str) -> str:
        self.calls += 1
        return _BROKEN if self.calls == 1 else _FIXED


# Safety-repair scenario: the first draft performs an IRREVERSIBLE/effect-bearing
# action (Move, uses calendar) WITHOUT an approval gate → `casl check` rejects it with
# "approval dominance". The repair (adding an approval-consent gate) is triggered CAUSALLY by
# exactly this diagnostic — not by a call counter.
_RESCHED_UNSAFE = """protocol Reschedule {
  roles S, U, K;
  agent S caps { calendar(event) scope "cal:write" mode write ttl 1 sig "s1"; }
  S -> U : Conflict(detail: Str);
  S -> K : Move() uses calendar irreversible;
}"""

_RESCHED_SAFE = """protocol Reschedule {
  roles S, U, K;
  agent S caps { calendar(event) scope "cal:write" mode write ttl 1 sig "s1"; }
  S -> U : Conflict(detail: Str);
  choice approval at U -> S {
    Approve consent: { S -> K : Move() uses calendar irreversible; }
    Deny:            { S -> K : Skip(); }
  }
}"""


class RepairMockGenerator:
    """Feedback-RESPONSIVE generator (deterministic, offline): the repair depends on the CONTENT
    of the verifier feedback, not on a call counter. Without feedback → unsafe draft;
    if the feedback names approval dominance, it adds the approval-consent gate. This makes the
    loop demonstrably diagnostic-driven ("the verifier decides, the feedback repairs")."""

    def propose(self, wish: str, feedback: str) -> str:
        fb = (feedback or "").lower()
        if "approval" in fb or "consent" in fb:
            return _RESCHED_SAFE
        return _RESCHED_UNSAFE


_GRAMMAR_HINT = """CASL surface grammar (concise):
protocol Name { roles R1, R2, R3; [agent R caps { tool(p) scope "s" (mode read|write|admin)? ttl N sig "x"; }]*
  R1 -> R2 : Label(field: Sort) [contract]? (uses tool)? (oracle)? (irreversible)? ;
  rec Loop { ... continue Loop; }   choice [approval] at R1 -> R2 { Label [contract]?: { ... } ... } }
Sorts: Str|Int|Bool|Real. Contracts: [x <= y], [x >= y] (operands are a variable OR an integer, e.g. [size <= 500]) or [len(x) > 0]. Every used role must be declared.
Capability `mode` is the effect: read = non-effect-bearing (no approval needed); write/admin (default) = effect-bearing ⇒ must sit behind an approval gate/consent branch. The effect follows from `mode`, not from `scope`.
A bystander of a choice must be able to tell the branches apart (each branch sends/recvs a distinct label to it).
HARD SYNTAX RULES (common mistakes): a capability is ALWAYS `scope "..." mode write ttl N sig "..."` — the word `mode` is MANDATORY (not `scope "..." write`). `uses <tool>` takes NO parentheses/arguments. There is NO `contract` keyword — conditions are square brackets `[a <= b]` directly after the message. After a `rec` block NO further statement may follow (tail position). No `oracle` inside a `stream` handler."""

# A COMPLETE, valid example — the generator should copy forms from it, not guess.
_EXAMPLE = _FIXED


# Error-specific repair hints: the raw parser error message alone does not reliably steer a mid-tier
# model (it stays in the same error basin). We map known parser errors
# to CONCRETE, constructive corrections — this is the actual convergence lever.
_ERROR_HINTS = [
    ("found 'scope'", "A capability needs a parameter list in parentheses: "
     "`tool(param) scope \"...\" mode write ttl N sig \"...\";` — the parentheses after the tool name are missing."),
    ("found 'write'", "The keyword `mode` precedes the effect: `scope \"...\" mode write ttl N`, "
     "not `scope \"...\" write`."),
    ("found 'admin'", "`mode` precedes the effect: `scope \"...\" mode admin ttl N`."),
    ("found 'contract'", "There is NO `contract` keyword. Conditions are square brackets directly "
     "after the message: `A -> B : Label(x: Int) [x <= y];`"),
    ("Expected 'ttl'", "Capability order exactly: `tool(param) scope \"s\" mode write ttl N sig \"x\";`"),
    ("Expected 'sig'", "After `ttl N` comes `sig \"...\"`: `... ttl N sig \"x\";`"),
    ("Expected ':'", "A message ends with `;`; a choice branch is written `Label: { ... }`."),
    ("found '>'", "Strict comparisons `>`/`<` do not exist — use `>=`/`<=` "
     "(e.g. `[amount >= 1]` instead of `[amount > 0]`); test non-emptiness with `[len(x) > 0]`."),
    ("found '<'", "Strict comparisons `<`/`>` do not exist — use `<=`/`>=`."),
    ("found '=='", "Equality does not exist in a contract — only `<=`, `>=`, `[len(x) > 0]`."),
]


def _repair_hint(errmsg: str) -> str:
    for needle, hint in _ERROR_HINTS:
        if needle in errmsg:
            return " " + hint
    return ""


def _synth_messages(wish: str, feedback: str):
    """(system, user) for synthesis — shared by OllamaGenerator and ChatGenerator."""
    system = ("You write CASL protocol specifications. Output ONLY one fenced ```casl code block, "
              "nothing else.\n" + _GRAMMAR_HINT
              + "\n\nA COMPLETE, VALID example — copy these exact forms:\n```casl\n" + _EXAMPLE + "\n```")
    user = f"Wish: {wish}\n" + (f"\nThe previous attempt was REJECTED:\n{feedback}\nFix it, output the full corrected protocol." if feedback else "")
    return system, user


class OllamaGenerator:
    """Real Gemma oracle: produces a .casl from the wish (+ feedback).
    Robust: HTTP / response errors are typed as orc.OracleUnavailable (no traceback)."""

    def __init__(self, url=None, model=None):
        self.backend = orc.OllamaBackend(url=url, model=model)
        self.calls = 0

    def propose(self, wish: str, feedback: str) -> str:
        self.calls += 1
        system, user = _synth_messages(wish, feedback)
        # Temperature schedule: first round deterministic; raise it slightly afterwards so that repeated
        # identical failed attempts actually vary (otherwise the repair iterations are duplicates).
        temp = 0 if self.calls == 1 else 0.3
        body = {"model": self.backend.model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temp, "max_tokens": 512, "stream": False}
        resp = self.backend._http("/chat/completions", body)
        try:
            text = resp["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as e:
            raise orc.OracleUnavailable(f"unexpected oracle response structure: {e}") from e
        return _extract_casl(text)


class ChatGenerator:
    """Generator over ANY `.chat` backend (oracle.OllamaBackend OR oracle.CoderBackend).
    This lets a local agentic coder (claude/codex) serve as the design-time oracle behind the gate.
    Robust: the backend raises orc.OracleUnavailable on errors (synthesize() catches it)."""

    def __init__(self, backend):
        self.backend = backend
        self.calls = 0

    def propose(self, wish: str, feedback: str) -> str:
        self.calls += 1
        system, user = _synth_messages(wish, feedback)
        temp = 0 if self.calls == 1 else 0.3
        return _extract_casl(self.backend.chat(system, user, temperature=temp, max_tokens=512))


def _extract_casl(text: str) -> str:
    m = re.search(r"```(?:casl)?\s*(.+?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"(protocol\b.*})", text, re.DOTALL)
    return m.group(1).strip() if m else text.strip()


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------
def _derive_tests(proto) -> Dict[str, bool]:
    """Tests derived from the spec: mock-ok terminates; mock-overspend stays bound-safe."""
    env = {"budget": 100, "question": "q"}
    r_ok = run.run_protocol(proto.gtype, orc.MockBackend("ok"), env, max_loops=3)
    r_bad = run.run_protocol(proto.gtype, orc.MockBackend("overspend"), env, max_loops=3)
    return {"mock_ok_terminates": r_ok.outcome == "completed",
            "mock_overspend_bound_safe": r_bad.outcome in ("completed", "loop_bound_reached")}


def synthesize(wish: str, generator, max_iters: int = 6) -> SynthResult:
    feedback = ""
    text = ""
    seen_hints: List[str] = []   # ACCUMULATED across iterations (the fail-fast parser names only 1 error per round)
    trace: List[Tuple[int, str, Optional[str]]] = []
    for i in range(1, max_iters + 1):
        try:
            text = generator.propose(wish, feedback)
        except orc.OracleUnavailable as e:
            # Oracle unreachable/faulty → clean, typed abort (no traceback).
            trace.append((i, "oracle-error", str(e)))
            return SynthResult(False, i, text, trace)
        try:
            proto = surface.parse(text)
        except SyntaxError as e:
            # The parser is fail-fast and reports only ONE error per round. Without accumulation
            # the model fixes the named one and reintroduces the previous (oscillation). We
            # therefore collect the targeted hints seen so far and show them ALL — so the
            # model knows the whole constraint set, not just the respective first error.
            h = _repair_hint(str(e))
            if h and h not in seen_hints:
                seen_hints.append(h)
            allh = "".join(seen_hints) if seen_hints else _repair_hint(str(e))
            feedback = (f"Parse error: {e}.{allh} Observe ALL points named so far SIMULTANEOUSLY. "
                        f"Follow the grammar and the full example exactly and output the WHOLE protocol.")
            trace.append((i, "parse-fail", feedback))
            continue
        report = check.check_protocol(proto)
        if report["accepted"]:
            trace.append((i, "accepted", None))
            locals_ = {}
            for r in (proto.roles or []):
                try:
                    locals_[r] = mpst.local_pretty(mpst.project(proto.gtype, r))
                except mpst.NonProjectable as e:
                    locals_[r] = f"✗ {e}"
            return SynthResult(True, i, text, trace, locals_, _derive_tests(proto))
        fails = [f"{c['label']}" + (f" ({'; '.join(c['detail'])})" if c["detail"] else "")
                 for c in report["checks"] if c["gating"] and not c["ok"]]
        feedback = "MUST violations: " + " | ".join(fails)
        trace.append((i, "rejected", feedback))
    return SynthResult(False, max_iters, text, trace)


def format_synth(wish: str, r: SynthResult) -> str:
    out = ["=" * 72, f"CASL synth — wish: {wish}", "=" * 72, "Feedback loop:"]
    for i, status, fb in r.trace:
        out.append(f"  Iteration {i}: {status}" + (f" — {fb}" if fb else ""))
    out.append("-" * 72)
    if not r.accepted:
        out.append(f"  Result: ✗ NO well-formed spec in {r.iterations} iterations")
        return "\n".join(out)
    out.append(f"  Result: ✓ ACCEPTED spec after {r.iterations} iteration(s) (casl check passed)")
    out.append("\n  code (projected local types):")
    for role, lt in r.locals_.items():
        out.append(f"    {role}: {lt}")
    out.append("\n  derived tests:")
    for name, ok in r.tests.items():
        out.append(f"    [{'PASS' if ok else 'FAIL'}] {name}")
    out.append("\n  → Adoption (adopt) is the human approval (e.g. write into examples/).")
    return "\n".join(out)


def demo() -> dict:
    r = synthesize("Budgeted question-answering with checking and retry", MockGenerator())
    print(format_synth("Budgeted QA [mock]", r))
    return {"accepted": r.accepted, "iterations": r.iterations,
            "tests_ok": all(r.tests.values()) if r.accepted else False}


if __name__ == "__main__":
    if "--live" in sys.argv:
        wish = next((a for a in sys.argv[1:] if not a.startswith("-")), "Budgeted QA with retry")
        print(format_synth(wish + " [live]", synthesize(wish, OllamaGenerator())))
    else:
        demo()
