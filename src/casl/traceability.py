"""Line-level traceability, authorship & provenance — blame (LH-P-006 / LH-P-007, CEP-0062).

For every first-party line we answer three questions, from git:

  · WHY does it exist?   → a requirement (an `LH-*` id, or a `Requirement:` trailer, in its commit)
  · WHO is accountable?  → the commit author (a named human — the committer OWNS it)
  · HOW was it produced? → `human` (hand-written) or `llm` (model-generated), from a `Provenance:`
                            commit trailer; UNMARKED defaults to `human` (conservative: whoever
                            committed it owns it as if hand-written — no "the model wrote it" excuse).

So a bug **blames** a concrete human's lines (LH-P-007), and an untraced first-party line (no
requirement) is flagged and blocks adoption (LH-P-006). It does NOT claim the line is *correct* —
only *accountable*: provenance, not justification (the honest limit). Language-agnostic (works on any
git-tracked file). Ring 1/2; does not touch the verified core.

Convention (a project enforces it; the CASL language repo itself does not gate on it):

    <subject>

    Requirement: LH-LOCAL-001        # or an inline LH-* token anywhere in the message
    Provenance: llm                  # or: human   (default human if absent)
"""
from __future__ import annotations

import dataclasses
import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple

_REQ = re.compile(r"\bLH-[A-Za-z]+-[0-9A-Za-z]+\b")
_REQ_TRAILER = re.compile(r"^\s*Requirement:\s*(\S+)\s*$", re.M | re.I)
_PROV_TRAILER = re.compile(r"^\s*Provenance:\s*(human|llm)\s*$", re.M | re.I)


@dataclasses.dataclass(frozen=True)
class LineProv:
    lineno: int
    commit: str
    author: str
    mechanism: str        # "human" | "llm"
    requirement: Optional[str]

    @property
    def traced(self) -> bool:
        return self.requirement is not None


def _git(args: List[str], cwd: Optional[str]) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _commit_meta(sha: str, cwd: Optional[str], cache: Dict[str, Tuple[Optional[str], str]]
                 ) -> Tuple[Optional[str], str]:
    """(requirement, mechanism) for a commit, cached. mechanism defaults to 'human'."""
    if sha in cache:
        return cache[sha]
    try:
        msg = _git(["show", "-s", "--format=%B", sha], cwd)
    except subprocess.CalledProcessError:
        msg = ""
    req = None
    mt = _REQ_TRAILER.search(msg)
    if mt:
        req = mt.group(1)
    else:
        m = _REQ.search(msg)
        req = m.group(0) if m else None
    pv = _PROV_TRAILER.search(msg)
    mech = pv.group(1).lower() if pv else "human"
    cache[sha] = (req, mech)
    return cache[sha]


def line_provenance(path: str, cwd: Optional[str] = None) -> List[LineProv]:
    """Per-line (author, mechanism, requirement) via `git blame --porcelain`."""
    cwd = cwd or (os.path.dirname(os.path.abspath(path)) or ".")
    rel = os.path.relpath(os.path.abspath(path), os.path.abspath(cwd))
    out = _git(["blame", "--porcelain", "--", rel], cwd)
    authors: Dict[str, str] = {}
    meta: Dict[str, Tuple[Optional[str], str]] = {}
    res: List[LineProv] = []
    cur_sha: Optional[str] = None
    cur_final = 0
    hdr = re.compile(r"^([0-9a-f]{7,40})\s+\d+\s+(\d+)(?:\s+\d+)?$")
    for raw in out.splitlines():
        h = hdr.match(raw)
        if h:
            cur_sha, cur_final = h.group(1), int(h.group(2))
        elif raw.startswith("author ") and cur_sha is not None:
            authors[cur_sha] = raw[len("author "):].strip()
        elif raw.startswith("\t") and cur_sha is not None:
            req, mech = _commit_meta(cur_sha, cwd, meta)
            res.append(LineProv(lineno=cur_final, commit=cur_sha[:12],
                                author=authors.get(cur_sha, "?"), mechanism=mech, requirement=req))
    return res


def untraced_lines(path: str, cwd: Optional[str] = None) -> List[int]:
    """First-party lines with NO requirement — these block adoption (LH-P-006, deny-by-default)."""
    return [lp.lineno for lp in line_provenance(path, cwd) if not lp.traced]


def blame_line(path: str, lineno: int, cwd: Optional[str] = None) -> Optional[LineProv]:
    for lp in line_provenance(path, cwd):
        if lp.lineno == lineno:
            return lp
    return None


@dataclasses.dataclass(frozen=True)
class Region:
    """A maximal run of consecutive lines sharing the same provenance — the language-agnostic *region*
    view (D2): a blame hunk, NOT an AST function (which would need a per-language parser and break the
    language-agnostic property). The per-line data stays the ground truth and the ENFORCED unit; a
    Region is a lossless rollup for human review (a bug blames `foo.py:12-34 (llm, Bob)`, not 23 lines)."""
    start: int
    end: int
    commit: str
    author: str
    mechanism: str
    requirement: Optional[str]

    @property
    def traced(self) -> bool:
        return self.requirement is not None

    @property
    def span(self) -> str:
        return str(self.start) if self.start == self.end else f"{self.start}-{self.end}"


def regions(path: str, cwd: Optional[str] = None) -> List[Region]:
    """Aggregate line_provenance into contiguous same-(commit, requirement, author, mechanism) runs."""
    lps = line_provenance(path, cwd)
    out: List[Region] = []
    i, n = 0, len(lps)
    while i < n:
        j = i
        key = (lps[i].commit, lps[i].requirement, lps[i].author, lps[i].mechanism)
        while j + 1 < n:
            nx = lps[j + 1]
            if (nx.commit, nx.requirement, nx.author, nx.mechanism) == key and nx.lineno == lps[j].lineno + 1:
                j += 1
            else:
                break
        a = lps[i]
        out.append(Region(a.lineno, lps[j].lineno, a.commit, a.author, a.mechanism, a.requirement))
        i = j + 1
    return out


def provenance_summary(paths: List[str], cwd: Optional[str] = None) -> Dict[str, object]:
    """Aggregate the human-vs-LLM mix + per-author counts + untraced — the 'concentration of risk'
    view that feeds the assurance picture (more `llm` lines under one human = more concentrated risk)."""
    human = llm = untraced = total = 0
    by_author: Dict[str, int] = {}
    for p in paths:
        for lp in line_provenance(p, cwd):
            total += 1
            by_author[lp.author] = by_author.get(lp.author, 0) + 1
            if lp.mechanism == "llm":
                llm += 1
            else:
                human += 1
            if not lp.traced:
                untraced += 1
    return {"total": total, "human": human, "llm": llm, "untraced": untraced, "by_author": by_author}


def report(paths: List[str], cwd: Optional[str] = None) -> str:
    s = provenance_summary(paths, cwd)
    pct = (100 * s["llm"] // s["total"]) if s["total"] else 0  # type: ignore[operator]
    lines = [f"line traceability — {s['total']} lines over {len(paths)} file(s): "
             f"{s['human']} human, {s['llm']} llm ({pct}% llm), {s['untraced']} UNTRACED",
             "  by author: " + ", ".join(f"{a}:{n}" for a, n in sorted(s['by_author'].items()))]  # type: ignore[union-attr]
    untraced = [(p, r) for p in paths for r in regions(p, cwd) if not r.traced]
    if untraced:
        lines.append(f"  ✗ {len(untraced)} untraced region(s) over {s['untraced']} line(s) — block adoption "
                     f"(every line needs a requirement, LH-P-006):")
        for p, r in untraced[:20]:
            lines.append(f"      {p}:{r.span}  ({r.mechanism}, {r.author})")
        if len(untraced) > 20:
            lines.append(f"      … +{len(untraced) - 20} more region(s)")
    return "\n".join(lines)
