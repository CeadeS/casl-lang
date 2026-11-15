"""casl.conductor_corpus — the interpreter run-trace differential ORACLE (CEP-0081, Track C / COND).

Emits, per (protocol, scenario, budget, approve, max_loops) case, the Python authority's STRUCTURED run
result — computed by `run.run_protocol` with the deterministic `oracle.MockBackend` (no network, dispatch=None,
on_approval=None). The Rust `casl-conductor` must reproduce the same execution decision:

  · outcome         (completed | loop_bound_reached | tool_denied | forward_violation | approval_denied)
  · loops, last_verdict (ok|violation|refusal), accepted_label, forwards (A1 edges honored).

The prose trace + observability capture are rendering detail (not pinned). Single-sourced →
`rust/casl-conductor/tests/corpus.json`. See docs/analyses/python-retirement-roadmap.md.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from casl import oracle, run, surface

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-conductor", "tests", "corpus.json"
)


def verdict(src: str, scenario: str, budget: int, approve: Optional[bool], max_loops: int) -> Dict[str, Any]:
    p = surface.parse(src)
    rr = run.run_protocol(
        p.gtype, oracle.MockBackend(scenario), {"budget": budget},
        max_loops=max_loops, approve=approve, caps=p.caps,
    )
    return {
        "casl": src, "scenario": scenario, "budget": budget, "approve": approve, "max_loops": max_loops,
        "outcome": rr.outcome, "loops": rr.loops, "last_verdict": rr.last_verdict,
        "accepted_label": rr.accepted_label, "forwards": list(rr.forwards),
    }


_Q = ('protocol Q {\n  roles A, J, C;\n  rec Loop {\n    A -> J : Draft(cost: Int) [cost <= budget] oracle;\n'
      '    choice at J -> C {\n      Accept: { J -> A : Done(); }\n'
      '      Reject: { J -> A : Retry(); continue Loop; }\n    }\n  }\n}')
_AP1 = ('protocol Ap1 {\n  roles U, S, M;\n  agent S caps { mail(to) scope "smtp" mode write ttl 1 sig "s"; }\n'
        '  S -> U : Notice();\n  choice approval at U -> S {\n    Approve consent: { S -> M : Send() uses mail; }\n  }\n}')
_APD = ('protocol ApD {\n  roles U, S, M;\n  agent S caps { mail(to) scope "smtp" mode write ttl 1 sig "s"; }\n'
        '  S -> U : Notice();\n  choice approval at U -> S {\n    Approve consent: { S -> M : Send() uses mail; }\n'
        '    Deny: { S -> M : Drop(); }\n  }\n}')
_TD = 'protocol Td {\n  roles A, J;\n  A -> J : Act() uses search;\n}'
_TOK = ('protocol Tok {\n  roles A, J;\n  agent A caps { search(q) scope "web" mode read ttl 1 sig "s"; }\n'
        '  A -> J : Act() uses search;\n}')
_FWD = 'protocol Fwd {\n  roles A, J, C;\n  A -> J : First(x: Int);\n  J -> C : Second(y = First.x);\n}'
_FWDBAD = 'protocol FwdBad {\n  roles A, J, C;\n  J -> C : Second(y = First.x);\n  A -> J : First(x: Int);\n}'
_LIN = 'protocol Lin {\n  roles A, J;\n  A -> J : M();\n  J -> A : N();\n}'

_CASES: List[Tuple[str, str, int, Optional[bool], int]] = [
    (_Q, "ok", 100, None, 5),               # completes first pass
    (_Q, "overspend", 100, None, 5),         # violation → loops to bound
    (_Q, "refusal", 100, None, 5),           # refusal → loops to bound
    (_Q, "retry_then_ok", 100, None, 5),     # one retry then completes
    (_Q, "underreport", 100, None, 5),       # meter catches the overspend → loop bound
    (_AP1, "ok", 100, True, 5),              # released → consent branch → completed
    (_AP1, "ok", 100, False, 5),             # no release, no non-consent branch → approval_denied
    (_APD, "ok", 100, True, 5),              # released → Approve
    (_APD, "ok", 100, False, 5),             # denied → Deny branch (completed)
    (_TD, "ok", 100, None, 5),               # uses a tool not carried → tool_denied
    (_TOK, "ok", 100, None, 5),              # tool carried → completed
    (_FWD, "ok", 100, None, 5),              # forward honored → completed, forwards=[…]
    (_FWDBAD, "ok", 100, None, 5),           # forward source unbound → forward_violation
    (_LIN, "ok", 100, None, 5),              # plain linear → completed, no verdict
]


def build_corpus() -> List[Dict[str, Any]]:
    return [verdict(*c) for c in _CASES]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} run-trace verdict(s) → {out}")
