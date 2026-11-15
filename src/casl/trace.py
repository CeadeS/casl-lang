#!/usr/bin/env python3
"""
trace.py — Code ↔ Commit ↔ Requirement Traceability  (LH-P-005, LH-C-001; stage T)

Makes the convention laid down in `CONTRIBUTING.md` (every commit references the
requirement IDs it touches) machine-usable and checkable:

  trace.py                 — overview: per requirement, number of commits + verification
  trace.py LH-F-003        — all commits (hash, subject, files) for one requirement
  trace.py --blame FILE    — each line → last commit → its requirement IDs
  trace.py --json          — machine-readable overview
  trace.py --strict        — exit 1 even for requirements without a commit (not just on typos)

Verification (always): commits naming a NON-existent `LH-` ID → error (exit 1).
Requirements without an ID-referencing commit are reported; those realized in the initial/baseline
commit count as "baseline-covered" (not a hard error, except under `--strict`).

The git extraction runs on the machine (like `run.sh`), not in the offline `audit.py`;
there the `versioning` building block only checks that the discipline (convention + this tool)
is documented/present.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from casl import spec  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # repo root (above prototype/)
REQ_RE = re.compile(r"LH-[A-Z]-\d+[a-z]?|PH-[A-Z]-\d+|TBD-V-\d+|TB[DR]-\d+|\bW\d+\b")


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", ROOT, *args], capture_output=True, text=True).stdout


def all_commits():
    """[(full, short, subject, ids:set)] over the entire history."""
    raw = _git("log", "--pretty=format:%H%x1f%h%x1f%s%x1f%b%x1e")
    out = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec.strip():
            continue
        parts = rec.split("\x1f")
        if len(parts) < 4:
            continue
        full, short, subj, body = parts[0], parts[1], parts[2], parts[3]
        ids = set(REQ_RE.findall(subj + "\n" + body))
        out.append((full.strip(), short.strip(), subj.strip(), ids))
    return out


def files_of(full_hash: str):
    raw = _git("show", "--pretty=format:", "--name-only", full_hash)
    return [f for f in raw.splitlines() if f.strip()]


def baseline_hash() -> str:
    return _git("rev-list", "--max-parents=0", "HEAD").strip().splitlines()[0][:9] if _git(
        "rev-list", "--max-parents=0", "HEAD").strip() else ""


def build_index():
    commits = all_commits()
    req2c = collections.defaultdict(list)
    for full, short, subj, ids in commits:
        for i in ids:
            req2c[i].append((short, subj))
    known = set(spec.REQS)
    unknown = sorted({i for _, _, _, ids in commits for i in ids
                      if i.startswith("LH-") and i not in known})
    missing = sorted(r for r in spec.REQS if not req2c.get(r))
    return commits, req2c, unknown, missing


# --------------------------------------------------------------------------
# views
# --------------------------------------------------------------------------
def cmd_summary(args) -> int:
    commits, req2c, unknown, missing = build_index()
    base = baseline_hash()
    if args.json:
        print(json.dumps({
            "commits": len(commits),
            "requirement_commits": {r: [h for h, _ in req2c.get(r, [])] for r in spec.REQS},
            "unknown_ids": unknown,
            "without_commit": missing,
            "baseline": base,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Traceability — {len(commits)} commits, {len(spec.REQS)} requirements\n")
        for r in spec.REQS:
            cs = req2c.get(r, [])
            tag = f"{len(cs):2} commit(s)" if cs else "  baseline"
            print(f"  {r:10} {tag}" + (f"  ({cs[0][0]} …)" if cs else f"  → {base}"))
        print(f"\n  Unknown LH-IDs in commits: {unknown or 'none'}")
        print(f"  Without ID commit (baseline-covered): {len(missing)}")
    if unknown:
        print(f"\nERROR: commits reference non-existent requirements: {unknown}", file=sys.stderr)
        return 1
    if args.strict and missing:
        print(f"\n--strict: {len(missing)} requirements without an ID commit", file=sys.stderr)
        return 1
    return 0


def cmd_one(args) -> int:
    rid = args.requirement
    _, req2c, _, _ = build_index()
    if rid not in spec.REQS:
        print(f"trace: unknown requirement {rid}", file=sys.stderr)
        return 2
    cs = req2c.get(rid, [])
    stufe, verif, thes = spec.REQS[rid]
    print(f"{rid}  [{stufe} · Verif {verif} · Theses {'/'.join(thes)}]")
    if not cs:
        print(f"  (no ID-referencing commit — baseline-covered: {baseline_hash()})")
        return 0
    for short, subj in cs:
        full = _git("rev-parse", short).strip()
        files = files_of(full)
        print(f"  {short}  {subj}")
        for f in files:
            print(f"        {f}")
    return 0


def cmd_blame(args) -> int:
    path = args.blame
    if not os.path.exists(os.path.join(ROOT, path)) and not os.path.exists(path):
        print(f"trace: file not found: {path}", file=sys.stderr)
        return 2
    _, req2c, _, _ = build_index()
    # hash → IDs (from the parsed commits)
    hash_ids = {}
    for full, short, subj, ids in all_commits():
        hash_ids[short] = ids
        hash_ids[full] = ids
    raw = _git("blame", "--line-porcelain", "--", path)
    line_no = 0
    per_req = collections.Counter()
    rows = []
    cur_hash = None
    for line in raw.splitlines():
        m = re.match(r"^([0-9a-f]{7,40})\s+\d+\s+\d+", line)
        if m:
            cur_hash = m.group(1)
        elif line.startswith("\t"):
            line_no += 1
            ids = hash_ids.get(cur_hash) or hash_ids.get(cur_hash[:9]) or set()
            reqs = sorted(i for i in ids if i.startswith("LH-"))
            for r in reqs:
                per_req[r] += 1
            if not reqs:
                per_req["(baseline)"] += 1
            rows.append((line_no, (cur_hash or "")[:9], reqs))
    print(f"Line traceability for {path}  ({line_no} lines)\n")
    print("  Lines per requirement:")
    for r, n in per_req.most_common():
        print(f"    {r:12} {n} line(s)")
    print(f"\n  First {min(len(rows), args.lines)} lines (line → commit → requirement):")
    for ln, h, reqs in rows[:args.lines]:
        print(f"    L{ln:<4} {h}  {','.join(reqs) if reqs else '(baseline)'}")
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog="trace", description="Code↔commit↔requirement traceability (LH-P-005).")
    p.add_argument("requirement", nargs="?", help="a requirement ID (e.g. LH-F-003)")
    p.add_argument("--blame", metavar="FILE", help="line traceability of a file")
    p.add_argument("--lines", type=int, default=25, help="max. lines in the --blame detail")
    p.add_argument("--json", action="store_true", help="overview as JSON")
    p.add_argument("--strict", action="store_true", help="exit 1 also for requirements without a commit")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.blame:
        return cmd_blame(args)
    if args.requirement:
        return cmd_one(args)
    return cmd_summary(args)


if __name__ == "__main__":
    sys.exit(main())
