"""casl.grade_corpus — the grade-flow differential ORACLE (CEP-0081, Track C brick 4).

Emits, per (manifest, choreographies) fixture, the Python authority's SOUND STRUCTURAL grade-flow — computed
by `grade_flow.flow_grades(manifest, dir, apply_rebase=False)` + `grade_flow.containment_boundaries`:

  · `flow_grades` = per BOUND site, the weakest assurance floor at-or-upstream in protocol order (sound;
    never raised). [[proto, label, grade], …] sorted.
  · `boundaries`  = site identifiers where a re-base COULD apply (verified / oracle+contract / approval),
    i.e. the prefix of each `containment_boundaries` line before its prose. sorted.

The A2/A1 forwarding re-base layer (z3 SMT entailment + CERT-FID) is intentionally OUT of scope here — the
Rust port covers the sound structural core. Single-sourced → `rust/casl-project/tests/grade_corpus.json`.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Tuple

from casl import grade_flow, project

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-project", "tests", "grade_corpus.json"
)


def verdict(toml: str, choreos: List[str]) -> Dict[str, Any]:
    d = tempfile.mkdtemp(prefix="casl_grade_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    os.makedirs(os.path.join(d, "casl"), exist_ok=True)
    for i, c in enumerate(choreos):
        with open(os.path.join(d, "casl", f"c{i}.casl"), "w", encoding="utf-8") as fh:
            fh.write(c)
    man = project.load_manifest(d)
    fg = grade_flow.flow_grades(man, d, apply_rebase=False)
    cb = grade_flow.containment_boundaries(man, d)
    return {
        "toml": toml,
        "choreos": choreos,
        "flow_grades": sorted([p, l, g] for (p, l), g in fg.items()),
        "boundaries": sorted(s.split(" (", 1)[0] for s in cb),
    }


def _man(*arts: str) -> str:
    return 'name = "p"\nversion = "0.1.0"\n' + "".join(arts)


def _art(name: str, kind: str, *, grade: str = "G3", body: bool = False, implements: str | None = None) -> str:
    s = f'[[artifact]]\nname = "{name}"\nkind = "{kind}"\nrequirement = "R"\ngrade = "{grade}"\n'
    if body:
        s += f'body = "artifacts/{name}.py"\n'
    if implements is not None:
        s += f'implements = "{implements}"\n'
    return s


_CASES: List[Tuple[str, List[str]]] = [
    # 1. upstream verified (G0) kept; downstream oracle (G3); verified site is a boundary
    (_man(_art("s", "verified", grade="G0", body=True, implements="W:First"),
          _art("w", "oracle", implements="W:Weak")),
     ["protocol W {\n  roles A, J, C;\n  A -> J : First(x: Int) verified;\n  J -> C : Weak() oracle;\n}"]),
    # 2. oracle+contract monitored boundary; bound oracle site floors at G3
    (_man(_art("d", "oracle", implements="M:Draft")),
     ["protocol M {\n  roles A, J;\n  A -> J : Draft(x: Int) [x <= 100] oracle;\n}"]),
    # 3. approval gate boundary + a verified bound site
    (_man(_art("s", "verified", grade="G0", body=True, implements="G:Pre")),
     ["protocol G {\n  roles A, J, C;\n  A -> J : Pre(x: Int) verified;\n"
      "  choice approval at J -> C {\n    Go consent: { J -> A : Ok(); }\n    Stop: { J -> A : No(); }\n  }\n}"]),
    # 4. degradation chain: a weak (oracle) middle degrades a downstream verified site to G3
    (_man(_art("s1", "verified", grade="G0", body=True, implements="X:First"),
          _art("w", "oracle", implements="X:Mid"),
          _art("s2", "verified", grade="G0", body=True, implements="X:Last")),
     ["protocol X {\n  roles A, J, C;\n  A -> J : First(x: Int) verified;\n  J -> C : Mid() oracle;\n"
      "  C -> A : Last(y: Int) verified;\n}"]),
    # 5. no bound sites, no boundaries ⇒ empty flow + empty boundaries
    (_man(_art("dep", "external")),
     ["protocol P {\n  roles A, J;\n  A -> J : Msg();\n}"]),
]


def build_corpus() -> List[Dict[str, Any]]:
    return [verdict(t, c) for t, c in _CASES]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} grade-flow verdict(s) → {out}")
