"""casl.project_corpus — the manifest-differential ORACLE (CEP-0081, Track C brick 1 of the Python retirement).

Emits, per `casl.toml` source, the Python authority's load+validate result — computed by the SAME function
the CLI/conductor/obligation-gate use (`project.load_manifest`), so the Rust `casl-project` differential is
pinned to the reference, not a reimplementation:

  · `ok`     = the manifest loads + validates (deny-by-default: unknown kind/grade, missing name/version,
               trace-regime mismatch (LH-P-009), missing body for an owned non-oracle artifact, … ⇒ reject).
  · `model`  = the validated `Manifest` (name/version/attest/min_evidence + each `Artifact` incl. the derived
               `floor` (LH-Q-016) and `owned`). `root` (an abspath) is intentionally excluded — machine-specific.

Single-sourced (no hand-duplicated expectations) → `rust/casl-project/tests/corpus.json`. The Rust crate
parses the text, runs the same validation, and must agree on the accept/reject decision AND the model.
See docs/analyses/python-retirement-roadmap.md.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List, Optional

from casl import project

_RUST_CORPUS = os.path.join(
    os.path.dirname(__file__), "..", "..", "rust", "casl-project", "tests", "corpus.json"
)


def _artifact_json(a: project.Artifact) -> Dict[str, Any]:
    return {
        "name": a.name,
        "kind": a.kind,
        "requirement": a.requirement,
        "grade": a.grade,
        "trace": a.trace,
        "body": a.body,
        "signers": a.signers,
        "implements": a.implements,
        "provides": a.provides,
        "confined": a.confined,
        "floor": a.floor(),
        "owned": a.owned(),
    }


def _manifest_json(m: project.Manifest) -> Dict[str, Any]:
    return {
        "name": m.name,
        "version": m.version,
        "attest_pubkey": m.attest_pubkey,
        "min_evidence": m.min_evidence,
        "artifacts": [_artifact_json(a) for a in m.artifacts],
    }


def verdict(toml: str) -> Dict[str, Any]:
    """Load + validate one manifest via the SAME authority `casl check`/the conductor use."""
    d = tempfile.mkdtemp(prefix="casl_manifest_")
    with open(os.path.join(d, "casl.toml"), "w", encoding="utf-8") as fh:
        fh.write(toml)
    model: Optional[Dict[str, Any]] = None
    try:
        m = project.load_manifest(d)
        model = _manifest_json(m)
        ok = True
    except project.ManifestError:
        ok = False
    return {"toml": toml, "ok": ok, "model": model}


# Valid (accepted) + invalid (deny-by-default rejected) manifests — both polarities, every validation rule.
_MANIFESTS: List[str] = [
    # -- valid --
    'name = "p"\nversion = "0.1.0"\n',                                   # minimal, no artifacts
    'name = "p"\nversion = "0.1.0"\n[attest]\npubkey = ".casl/attest.pub"\n'
    '[[artifact]]\nname = "conflict_check"\nkind = "verified"\nrequirement = "R2"\n'
    'grade = "G0"\nbody = "artifacts/conflict_check.py"\n',              # verified ⇒ owned/full, floor G0
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "dep"\nkind = "external"\n'
    'requirement = "R1"\ngrade = "G0"\n',                               # external ⇒ burden, floor G3
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "draft"\nkind = "generated"\n'
    'requirement = "R3"\ngrade = "G3"\nbody = "artifacts/draft.py"\n'
    '[[artifact]]\nname = "cls"\nkind = "oracle"\nrequirement = "R4"\ngrade = "G3"\n',  # two artifacts
    'name = "triage"\nversion = "0.1.0"\n[[artifact]]\nname = "classify"\nkind = "oracle"\n'
    'requirement = "T1"\ngrade = "G3"\nimplements = "Triage:Classify"\n'
    '[[artifact]]\nname = "notify"\nkind = "external"\nrequirement = "T2"\ngrade = "G3"\n'
    'implements = "Triage:Notify"\nprovides = "mail"\n',                # seam + provider
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "g"\nkind = "generated"\n'
    'requirement = "R"\ngrade = "G3"\nbody = "artifacts/g.py"\nsigners = 2\n',  # signers=2
    'name = "p"\nversion = "0.1.0"\nmin_evidence = "pin"\n[[artifact]]\nname = "dep"\n'
    'kind = "external"\nrequirement = "R"\ngrade = "G3"\n',             # min_evidence policy
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "w"\nkind = "generated"\n'
    'requirement = "R"\ngrade = "G2"\nbody = "artifacts/w.py"\nconfined = true\n',  # confined
    # -- invalid (deny-by-default) --
    'version = "0.1.0"\n',                                              # no name
    'name = "p"\n',                                                     # no version
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "bogus"\nrequirement = "R"\n',  # unknown kind
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "verified"\n'
    'grade = "G9"\nbody = "b"\n',                                       # bad grade
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "generated"\nrequirement = "R"\n',  # generated, no body
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "verified"\n'
    'body = "b"\ntrace = "burden"\n',                                   # trace-regime mismatch (LH-P-009)
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "oracle"\n'
    'requirement = "R"\nimplements = "noColon"\n',                      # implements without ':'
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "external"\n'
    'requirement = "R"\nprovides = ""\n',                              # provides empty
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nkind = "verified"\nbody = "b"\n',  # artifact without name
    'name = "p"\nversion = "0.1.0"\n[[artifact]]\nname = "a"\nkind = "generated"\n'
    'body = "b"\nsigners = 0\n',                                        # signers < 1
]


def build_corpus() -> List[Dict[str, Any]]:
    return [verdict(t) for t in _MANIFESTS]


def to_text() -> str:
    return json.dumps(build_corpus(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_rust_corpus(path: str = _RUST_CORPUS) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_text())
    return path


if __name__ == "__main__":
    out = write_rust_corpus()
    print(f"wrote {len(build_corpus())} manifest verdict(s) → {out}")
