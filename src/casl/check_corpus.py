"""casl.check_corpus — the checker-verdict differential ORACLE (CEP-0081, brick 2 of the Python retirement).

Reuses the parse-corpus sources (`surface_corpus._sources`) and emits, per `.casl` source, the Python
checker's AUTHORITATIVE MUST-check verdicts that the Rust `casl-check` must reproduce END-TO-END (text →
verdict):

  · `wellformed`           = `tcb_bridge.projectable(g)`   — the F*-pinned predicate `casl-core.wellformed_core`
                              mirrors (contractive ∧ no_self ∧ gdistinct ∧ closed ∧ projectable{C,A,J,D}).
  · `capability_contained` = `kernel.capabilities(g, caps)` — Least Privilege; the very function `casl check`
                              uses for its verdict (line `check.py: cp = kernel.capabilities(...)`).

Single-sourced (no hand-duplicated expectations) → `rust/casl-check/tests/corpus.json`. The Rust crate parses
the text, bridges the surface AST to casl-core's types, runs casl-core's `wellformed_core` + `capability_check`,
and must agree. See docs/analyses/python-retirement-roadmap.md §6 (stage 2).
"""
from __future__ import annotations

import json
import os
from typing import List

from casl import kernel, spike_pipeline, surface, tcb_bridge
from casl.surface_corpus import _sources

_RUST_CORPUS = os.path.join(os.path.dirname(__file__), "..", "..", "rust", "casl-check", "tests", "corpus.json")


def verdicts(src: str) -> dict:
    """The authoritative per-check verdicts for one `.casl` source — computed by the SAME functions
    `casl check` uses, so the Rust differential is pinned to the reference, not a reimplementation."""
    p = surface.parse(src)
    g = p.gtype
    return {
        "casl": src,
        "wellformed": bool(tcb_bridge.projectable(g)),
        "wellformed_user": bool(kernel.wellformed(g, roles=p.roles)),
        "capability_contained": bool(kernel.capabilities(g, caps=p.caps)),
        "approval_safe": bool(kernel.approval_safety(g, caps=p.caps)),
        "pipeline_safe": bool(spike_pipeline.pipeline_safe(g)[0]),
        "linearity": bool(kernel.linearity(g)),
        "stream_safe": bool(kernel.stream_safe(g, getattr(p, "env", ()))),
        "termination": bool(kernel.termination(g)),
        "crash_tolerance": bool(kernel.crash_tolerance(g, crash_prone=getattr(p, "crash", ()))),
        "ttl_safety": bool(kernel.ttl_safety(g, caps=p.caps)),
        "concurrency_certified": bool(kernel.concurrency_certified(g)),
    }


# check-specific cases (beyond the parse corpus) to exercise BOTH polarities of the ported checks —
# e.g. an approval-dominance VIOLATION (an irreversible effect with no dominating approval gate).
_EXTRA: List[str] = [
    'protocol BadEffect {\n  roles S, U;\n  agent S caps { mail(to) scope "smtp" mode write ttl 1 sig "s"; }\n'
    '  S -> U : Send() uses mail irreversible;\n}',
    # pipeline-UNSAFE: an oracle node with no contract (R2 — the monitored boundary is missing)
    'protocol BadPipe {\n  roles A, J;\n  A -> J : Draft(x: Int) oracle;\n}',
    # linearity-UNSAFE: an oracle output (promise) sent in only ONE branch ⇒ resolved 0..1 times,
    # not exactly once (write-once/obligation violated). Contract present so it is ONLY linearity-false.
    'protocol BadLin {\n  roles A, J;\n  choice at A -> J {\n'
    '    Hit: { A -> J : Out(x: Int) [x <= 100] oracle; }\n'
    '    Miss: { A -> J : Done(); }\n  }\n}',
    # stream-SAFE (positive path): env-driven dispatch choice; every handler terminates (continue/end)
    'protocol GoodStream {\n  roles Env, S, U;\n  env Env;\n  stream Loop {\n'
    '    choice at Env -> S {\n'
    '      Ev: { S -> U : Notice(); continue Loop; }\n'
    '      Quit: { S -> U : Bye(); }\n    }\n  }\n}',
    # termination-UNSAFE: a (non-stream) rec with NO measure ⇒ ranking not guaranteed.
    'protocol BadTerm {\n  roles C, A, J;\n  rec Loop {\n    A -> J : Draft(x: Int);\n'
    '    choice at J -> C {\n      Accept: { J -> A : Done(); }\n'
    '      Reject: { J -> A : Retry(); continue Loop; }\n    }\n  }\n}',
    # crash-INTOLERANT: a crash-prone sender S with a receive that has no on_crash handler.
    'protocol BadCrash {\n  roles S, X;\n  crash S;\n  S -> X : Result();\n}',
    # ttl-UNSAFE: a finite-ttl cap (ttl 2) used inside a bounded loop (bound 5) ⇒ ttl < iteration bound.
    'protocol BadTtl {\n  roles A, J;\n  agent A caps { search(q) scope "web" mode read ttl 2 sig "s"; }\n'
    '  rec Loop measure n bound 5 {\n    A -> J : Draft(x: Int) uses search;\n'
    '    J -> A : Ack();\n    continue Loop;\n  }\n}',
    # concurrency-CERTIFIED (positive, exercises the swap rule): two role-disjoint communications; the
    # global semantics' prefix-swap captures exactly the endpoint concurrency ⇒ certified.
    'protocol GoodConc {\n  roles A, B, C, D;\n  A -> B : m();\n  C -> D : n();\n}',
    # concurrency-INCOMPLETE (negative): concurrency ACROSS a recursion — the swap rule does not cross Rec
    # (sound underestimate), so the endpoints are more concurrent than the global type captures ⇒ rejected.
    'protocol BadConc {\n  roles P, Q, R, S;\n  P -> Q : a();\n  rec t {\n    R -> S : b();\n    continue t;\n  }\n}',
]


def build_corpus() -> List[dict]:
    return [verdicts(src) for src in (_sources() + _EXTRA)]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    """Emit the verdict corpus (regen: PYTHONPATH=src python -m casl.check_corpus)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} verdict(s) → {out}")
