"""casl.seam_corpus — the typed-seam differential ORACLE (CEP-0081, Track C brick 3).

Emits, per (manifest, choreographies) fixture, the Python authority's seam verdict — computed by the SAME
function `casl check` uses (`seam.check_seam`): for every artifact that declares `implements`, the protocol +
site must exist and the artifact `kind` must be able to realize the site NATURE (oracle/verified/effect/plain,
structured per R-H1). Single-sourced → `rust/casl-project/tests/seam_corpus.json`.

  · `ok`         = no seam violations.
  · `viol_count` = number of violations (unknown protocol/site, or kind cannot realize the site nature).
  · `bindings`   = artifact name → [protocol, label, nature] for each successfully bound artifact.

See docs/analyses/python-retirement-roadmap.md.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Tuple

from casl import project, seam

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-project", "tests", "seam_corpus.json"
)


def verdict(toml: str, choreos: List[str]) -> Dict[str, Any]:
    d = tempfile.mkdtemp(prefix="casl_seam_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    os.makedirs(os.path.join(d, "casl"), exist_ok=True)
    for i, c in enumerate(choreos):
        with open(os.path.join(d, "casl", f"c{i}.casl"), "w", encoding="utf-8") as fh:
            fh.write(c)
    man = project.load_manifest(d)
    ok, viol, bindings = seam.check_seam(man, d)
    return {
        "toml": toml,
        "choreos": choreos,
        "ok": ok,
        "viol_count": len(viol),
        "bindings": {name: [p, l, n] for name, (p, l, n) in bindings.items()},
    }


_T_ORACLE = "protocol T {\n  roles A, J;\n  A -> J : Classify(x: Int) oracle;\n}"
_N_EFFECT = "protocol N {\n  roles S, M;\n  S -> M : Notify() uses mail;\n}"
_V_VERIFIED = "protocol V {\n  roles A, J;\n  A -> J : Draft(x: Int) verified;\n}"
_P_PLAIN = "protocol P {\n  roles A, J;\n  A -> J : Msg();\n}"


def _man(*arts: str) -> str:
    return 'name = "p"\nversion = "0.1.0"\n' + "".join(arts)


def _art(name: str, kind: str, *, body: bool = False, implements: str | None = None) -> str:
    s = f'[[artifact]]\nname = "{name}"\nkind = "{kind}"\nrequirement = "R"\n'
    if body:
        s += f'body = "artifacts/{name}.py"\n'
    if implements is not None:
        s += f'implements = "{implements}"\n'
    return s


_CASES: List[Tuple[str, List[str]]] = [
    # -- ok: each site nature bound by a compatible kind --
    (_man(_art("classify", "oracle", implements="T:Classify")), [_T_ORACLE]),
    (_man(_art("notify", "external", implements="N:Notify")), [_N_EFFECT]),
    (_man(_art("conflict", "verified", body=True, implements="V:Draft")), [_V_VERIFIED]),
    (_man(_art("draft", "generated", body=True, implements="P:Msg")), [_P_PLAIN]),
    # -- ok: an artifact WITHOUT implements is not bound-checked (no binding, no violation) --
    (_man(_art("dep", "external")), []),
    # -- ok: two correct bindings --
    (_man(_art("classify", "oracle", implements="T:Classify"), _art("notify", "external", implements="N:Notify")),
     [_T_ORACLE, _N_EFFECT]),
    # -- violation: kind cannot realize the site nature (verified artifact, oracle site) --
    (_man(_art("a", "verified", body=True, implements="T:Classify")), [_T_ORACLE]),
    # -- violation: unknown protocol --
    (_man(_art("a", "oracle", implements="Nope:X")), []),
    # -- violation: unknown site in a known protocol --
    (_man(_art("a", "oracle", implements="T:Missing")), [_T_ORACLE]),
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
    print(f"wrote {len(build_corpus())} seam verdict(s) → {out}")
