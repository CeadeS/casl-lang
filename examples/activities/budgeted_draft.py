#!/usr/bin/env python3
"""A minimal CASL activity — realize an oracle site as a REAL, polyglot program.

Reads one JSON request on stdin, writes one JSON answer on stdout: the SAME {"answer","cost"} contract the
LLM oracle uses, so the conductor monitors it identically (contract + blame; veto-never-vouch). No network,
no key, no `casl` import — any language that can read stdin and write stdout can be an activity.

    in :  {"question": "...", "budget": 100}
    out:  {"answer": "...", "cost": 7}        (or {"refused": true})

This stand-in answers and reports a cost well within budget. A real activity would call a (local) model or
compute the answer — the point is that the conductor monitors WHATEVER it returns; the activity cannot vouch
for itself (the trusted monitor, not this program, decides ok/violation/refusal).
"""
import json
import sys


def main() -> None:
    try:
        req = json.loads(sys.stdin.readline())
    except (ValueError, TypeError):
        print(json.dumps({"refused": True}))
        return
    question = str(req.get("question", "")).strip()
    budget = req.get("budget", 0)
    answer = f"draft: {question[:80]}" if question else "draft: (no question)"
    cost = 7 if isinstance(budget, int) and not isinstance(budget, bool) and budget >= 7 else 0
    print(json.dumps({"answer": answer, "cost": cost}))


if __name__ == "__main__":
    main()
