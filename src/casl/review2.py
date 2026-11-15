"""casl.review2 — Layer-2 SEMANTIC requirement review (vetoes-never-vouches).

Layer 1 (`casl.requirecheck`) is the FORMAL, deterministic gate (provenance + approval-dominance). Layer 2 is
the SEMANTIC judgement Layer 1 cannot make: does the code actually FULFIL its requirement, or contradict it
(perform an effect the requirement forbids, skip an approval/limit it mandates)? That judgement is an LLM's,
so it runs as a MONITORED ORACLE through the broker — and it may only VETO (raise a concern), never VOUCH
(an "OK" is the absence of a flagged concern, not a proof; agents may veto, never vouch). Run INCREMENTALLY
on a diff (the changed files) so the slow semantic pass stays cheap per commit.

The oracle is pluggable (`Oracle = Callable[[str], str]`); a mock drives the tests offline. Production wiring
is the broker's `llm:*` oracle (capability-gated, cost-metered, graded) — this module builds the prompts and
aggregates the verdicts; it holds no model. See docs/analyses/requirement-checker-and-approval-binding.md.
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from casl import requirecheck as _rc

Oracle = Callable[[str], str]   # prompt -> reply text (the monitored boundary; mock in tests)


@dataclass(frozen=True)
class Concern:
    requirement: str
    site: str
    path: str
    line: int
    reason: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.requirement} @ {self.site}] {self.reason}"


PROMPT = (
    "You are a CASL requirement reviewer. You may only VETO (raise a concern) or pass; you may NEVER vouch "
    "that code is correct.\n\nRequirement {req}:\n\"\"\"{text}\"\"\"\n\n"
    "Code realizing the effect site {site!r}:\n```\n{code}\n```\n\n"
    "Does the code CONTRADICT or fail to fulfil the requirement (e.g. performs an effect it forbids, or skips "
    "an approval / limit it mandates)? Reply EXACTLY one line:\n  OK\n  CONCERN: <one sentence>\n"
)


def build_prompt(req: str, text: str, site: str, code: str) -> str:
    return PROMPT.format(req=req, text=text or "(requirement text not found)", site=site, code=code[:4000])


def parse_verdict(reply: str) -> Optional[str]:
    """Extract a concern (a veto). Anything not clearly a CONCERN line is 'no concern raised' — NOT a vouch."""
    for line in (reply or "").splitlines():
        s = line.strip()
        if s.upper().startswith("CONCERN"):
            return s.split(":", 1)[1].strip() if ":" in s else "unspecified concern"
    return None


def load_requirement_texts(project_dir: str) -> Dict[str, str]:
    """Best-effort: pull `ID — text` (e.g. `**SCR-APPT-002** — …`) lines from requirements/*.md."""
    out: Dict[str, str] = {}
    rd = os.path.join(project_dir, "requirements")
    if not os.path.isdir(rd):
        return out
    pat = re.compile(r"\*{0,2}(?P<id>[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\*{0,2}\s*[—:-]\s*(?P<txt>.+)")
    for f in sorted(os.listdir(rd)):
        if not f.endswith(".md"):
            continue
        with open(os.path.join(rd, f), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = pat.search(line)
                if m:
                    out.setdefault(m.group("id"), m.group("txt").strip())
    return out


def _effect_sites(src: str):
    """(lineno, site) for each effect call with a static site (mirrors requirecheck's funnel)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _rc._is_effect_call(node, _rc.EFFECT_FUNCS):
            site = _rc._site_of(node)
            if site:
                out.append((node.lineno, site))
    return out


def review(project_dir: str, paths, oracle: Oracle,
           requirements: Optional[Dict[str, str]] = None) -> List[Concern]:
    """Run the semantic review over the given (changed) files. Returns the concerns raised (vetoes only)."""
    idx = _rc.requirement_index(project_dir)
    texts = requirements if requirements is not None else load_requirement_texts(project_dir)
    concerns: List[Concern] = []
    for p in paths:
        if not (str(p).endswith(".py") and os.path.exists(p)):
            continue
        with open(p, encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        for line, site in _effect_sites(src):
            req = (idx.get(site) or {}).get("requirement", "") or "(no requirement)"
            c = parse_verdict(oracle(build_prompt(req, texts.get(req, ""), site, src)))
            if c:
                concerns.append(Concern(req, site, str(p), line, c))
    return concerns


def report(project_dir: str, paths, oracle: Oracle, requirements=None):
    cs = review(project_dir, paths, oracle, requirements)
    if not cs:
        return True, ("✓ requirement-review (Layer-2): no semantic concern raised (vetoes-never-vouches — "
                      "the absence of a flag, NOT a proof of correctness).")
    return False, (f"✗ requirement-review (Layer-2): {len(cs)} concern(s):\n"
                   + "\n".join(f"    {c}" for c in cs))
