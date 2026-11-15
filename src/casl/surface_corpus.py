"""casl.surface_corpus — the parse-differential ORACLE (CEP-0081, docs/analyses/python-retirement-roadmap.md).

Single-sources the corpus that pins the Rust parser (`casl-surface`) to the Python reference parser
(`casl.surface`): a list of `{"casl": <source text>, "ast": <canonical AST JSON>}`, where `ast` is the
canonical serialization of `surface.parse(text)`. `casl-surface` MUST reproduce `ast` for every entry — the
strangler-fig characterization differential; retire `surface.py` on parity (roadmap §2/§6).

The schema is deliberately explicit + field-rich (unlike the field-blind `tcb_corpus`): it captures EXACTLY
what the parser must preserve — fields/sorts/forwarding sources, contracts (with the `>=`→`le` normalization),
the oracle/uses/irreversible/verified markers, choice approval + branch consent, rec/stream/measure, agent
caps, crash, env, async. Deterministic (`sort_keys`), so the committed corpus diffs cleanly.
"""
from __future__ import annotations

import glob
import json
import os
from typing import List

from casl import core, surface

_EX = os.path.join(os.path.dirname(__file__), "..", "..", "examples")
_RUST_CORPUS = os.path.join(os.path.dirname(__file__), "..", "..", "rust", "casl-surface", "tests", "corpus.json")


# -- canonical AST serialization -------------------------------------------
def _field(f) -> dict:
    return {"name": f.name, "sort": f.sort, "source": getattr(f, "source", None)}


def _contract(c) -> dict | None:
    if c is None:
        return None
    return {"text": c.text, "relation": list(c.relation) if c.relation else None}


def gtype_to_json(g) -> dict:
    """Canonical JSON for a global-type node (the five the surface parser produces)."""
    if isinstance(g, core.End):
        return {"node": "end"}
    if isinstance(g, core.TVar):
        return {"node": "var", "var": g.var}
    if isinstance(g, core.Rec):
        return {"node": "rec", "var": g.var, "measure": g.measure, "max_iters": g.max_iters,
                "stream": bool(getattr(g, "stream", False)), "body": gtype_to_json(g.body)}
    if isinstance(g, core.Comm):
        return {"node": "comm", "sender": g.sender, "receiver": g.receiver, "label": g.label,
                "fields": [_field(f) for f in g.fields], "contract": _contract(g.contract),
                "uses": g.uses_capability, "from_oracle": bool(g.from_oracle),
                "irreversible": bool(g.irreversible), "verified": bool(g.verified),
                "on_crash": gtype_to_json(g.on_crash) if g.on_crash is not None else None,
                "cont": gtype_to_json(g.cont)}
    if isinstance(g, core.Choice):
        return {"node": "choice", "sender": g.sender, "receiver": g.receiver, "approval": bool(g.approval),
                "branches": [{"label": b.label, "fields": [_field(f) for f in b.fields],
                              "contract": _contract(b.contract), "consent": bool(b.consent),
                              "cont": gtype_to_json(b.cont)} for b in g.branches]}
    raise TypeError(f"unknown global-type node: {type(g).__name__}")


def _cap(c) -> dict:
    return {"tool": c.tool, "params": list(c.params), "scope": c.scope, "ttl": c.ttl,
            "sigma": c.sigma, "mode": c.mode}


def protocol_to_json(p) -> dict:
    """Canonical JSON for a parsed Protocol — the full structure the Rust parser must reproduce."""
    return {"name": p.name, "roles": list(p.roles),
            "caps": {r: [_cap(c) for c in cs] for r, cs in p.caps.items()},
            "crash": sorted(p.crash), "env": list(p.env), "async_k": p.async_k,
            "gtype": gtype_to_json(p.gtype)}


# -- the corpus -------------------------------------------------------------
# Inline cases pin the grammar features that exercise the parser (some may be intentionally not well-formed —
# the differential is about PARSE structure, not the checker's verdict).
_INLINE: List[str] = [
    # forwarding (name = Src.field) + a typed forward
    'protocol Fwd {\n  roles C, A;\n  C -> A : Req(x: Int);\n  A -> C : Res(y = Req.x, z: Int = Req.x);\n}',
    # approval choice + consent branch + uses + irreversible + an effect cap (mode)
    ('protocol Appr {\n  roles U, S;\n  agent S caps { mail(to) scope "smtp" mode write ttl 1 sig "s1"; }\n'
     '  S -> U : Conflict();\n  choice approval at U -> S {\n'
     '    Approve consent: { S -> U : Notify() uses mail irreversible; }\n'
     '    Deny: { S -> U : Drop(); }\n  }\n}'),
    # stream loop + env + crash + on_crash handler + continue
    ('protocol Strm {\n  roles E, S;\n  env E;\n  crash S;\n  stream Loop {\n'
     '    E -> S : Event(d: Str);\n    S -> E : Ack() on_crash { S -> E : Down(); };\n'
     '    continue Loop;\n  }\n}'),
    # async k + 4 roles + verified + a `>=` contract (normalized to `le` with a literal operand)
    ('protocol Async4 {\n  roles C, A, J, D;\n  async k 2;\n  C -> A : Q(n: Int);\n'
     '  A -> J : Draft(cost: Int) [cost >= 0] verified;\n  J -> D : Route();\n  D -> C : Done();\n}'),
    # rec with measure/bound + a len(...)>0 (nonempty) branch contract + oracle marker
    ('protocol Meas {\n  roles C, A, J;\n  rec Loop measure n bound 5 {\n'
     '    A -> J : Draft(answer: Str, cost: Int) [cost <= budget] uses search oracle;\n'
     '    choice at J -> C {\n      Accept: { J -> A : Done(); }\n'
     '      Reject(reason: Str) [len(reason) > 0]: { J -> A : Retry(); continue Loop; }\n    }\n  }\n}'),
]


def _sources() -> List[str]:
    """Inline cases + every top-level examples/*.casl that parses (best-effort; attacks/ stays out)."""
    out = list(_INLINE)
    for path in sorted(glob.glob(os.path.join(_EX, "*.casl"))):
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
            surface.parse(src)            # include only if it parses cleanly
            out.append(src)
        except Exception:
            continue
    return out


def build_corpus() -> List[dict]:
    """[{casl, ast}] — single-sourced from the Python parser. The Rust parser must reproduce every `ast`."""
    return [{"casl": src, "ast": protocol_to_json(surface.parse(src))} for src in _sources()]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    """Emit the corpus to the Rust differential's fixture (regen: PYTHONPATH=src python -m casl.surface_corpus)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    p = write_rust_corpus()
    print(f"wrote {len(build_corpus())} protocol(s) → {p}")
