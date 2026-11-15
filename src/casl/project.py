"""CASL project model — the manifest, the canonical layout, and `casl init` / `casl project`.

Realizes the synthesized design in docs/analyses/project-structure-and-modules.md:

    myproject/
      casl.toml         # MANIFEST: name, version, [attest] pubkey, [[artifact]] → requirement/grade/trace/body
      requirements/     # project requirements — human authority
      casl/             # choreographies (*.casl) — seams + wiring, human-read
      artifacts/        # artifact bodies (one file per artifact; LLM-written, contained)
      attestations/     # one obligation+signature record per artifact
      deps.lock         # dependency burden ledger (LH-Q-020 — handled in dependency.py)
      .casl/attest.pub  # recorded human signing identity

An **artifact** is a first-class named unit (seam + body + obligation). Its `kind` (provenance) is
STRUCTURED and validated — never inferred from a name or free text (LH-F-013, the R-H1/W14 lesson).
This module is the checker/IDE layer (ring 1/2); it does NOT touch the verified core.
"""
from __future__ import annotations

import dataclasses
import os
from typing import Any, Dict, List, Optional

# the four artifact provenances (LH-F-013). `external` is the dependency/burden class; the rest are owned.
KINDS = ("external", "generated", "verified", "oracle")
TRACE_REGIMES = ("full", "burden")          # full = line-traced (owned); burden = pinned, not line-traced
GRADES = ("G0", "G1", "G2", "G3")
# the unprovable provenances have a hard floor of G3 (LH-Q-016): they need a human act to enter.
UNPROVABLE = ("external", "generated", "oracle")


# --------------------------------------------------------------------------
# minimal, dependency-free TOML reader (prefers stdlib tomllib / tomli when present)
# handles exactly the manifest grammar: [table], [[array.table]], key = "str" | int | bool | ["a","b"]
# --------------------------------------------------------------------------
def _parse_toml(text: str) -> Dict[str, Any]:
    try:
        import tomllib  # py311+
        return tomllib.loads(text)
    except Exception:
        pass
    try:
        import tomli  # backport, if installed
        return tomli.loads(text)
    except Exception:
        pass
    return _parse_toml_subset(text)


def _toml_value(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_toml_value(p) for p in _split_top(inner)]
    if len(raw) >= 2 and raw[0] in "\"'" and raw[-1] == raw[0]:
        return raw[1:-1]
    if raw in ("true", "false"):
        return raw == "true"
    try:
        return int(raw)
    except ValueError:
        return raw


def _split_top(s: str) -> List[str]:
    """split a TOML inline array on top-level commas, respecting quotes."""
    out, buf, q = [], [], None
    for ch in s:
        if q:
            buf.append(ch)
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            buf.append(ch)
        elif ch == ",":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf))
    return out


def _parse_toml_subset(text: str) -> Dict[str, Any]:
    root: Dict[str, Any] = {}
    cur: Dict[str, Any] = root
    for line in text.splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        s = line.strip()
        if s.startswith("[[") and s.endswith("]]"):
            key = s[2:-2].strip()
            root.setdefault(key, [])
            cur = {}
            root[key].append(cur)
        elif s.startswith("[") and s.endswith("]"):
            key = s[1:-1].strip()
            cur = root.setdefault(key, {})
        elif "=" in s:
            k, v = s.split("=", 1)
            cur[k.strip()] = _toml_value(v)
    return root


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------
@dataclasses.dataclass(frozen=True)
class Artifact:
    name: str
    kind: str            # one of KINDS (validated)
    requirement: str     # the requirement this artifact realises/serves
    grade: str           # declared required assurance grade (one of GRADES)
    trace: str           # 'full' (owned) | 'burden' (dependency)
    body: Optional[str]  # path to the body file (None for oracle/live calls)
    signers: int = 1     # distinct human signatures required (D3 second-signer; default 1, opt-in for teams)
    implements: Optional[str] = None   # typed seam (LH-F-012 full): "<protocol>:<Label>" site this realizes
    provides: Optional[str] = None     # capability provider (CEP-0078): the ONE capability this artifact offers
    confined: bool = False             # opt-in confinement (CEP-0078): no ambient I/O — only granted providers

    def floor(self) -> str:
        """The hard assurance floor implied by provenance (LH-Q-016): unprovable ⇒ G3."""
        return "G3" if self.kind in UNPROVABLE else self.grade

    def owned(self) -> bool:
        """First-party (we are accountable) vs dependency (burden). Ownership, not who typed it."""
        return self.kind != "external"


@dataclasses.dataclass(frozen=True)
class Manifest:
    name: str
    version: str
    attest_pubkey: Optional[str]
    artifacts: List[Artifact]
    root: str            # project directory
    min_evidence: Optional[str] = None   # optional supply-chain policy (D5): pin|sbom|slsa|signed

    def by_requirement(self) -> Dict[str, List[Artifact]]:
        out: Dict[str, List[Artifact]] = {}
        for a in self.artifacts:
            out.setdefault(a.requirement, []).append(a)
        return out


class ManifestError(ValueError):
    pass


def load_manifest(path: str) -> Manifest:
    """Load + VALIDATE a casl.toml. Structured validation, deny-by-default: an unknown kind/grade/
    trace, a missing body for an owned non-oracle artifact, etc. raise rather than silently pass."""
    if os.path.isdir(path):
        path = os.path.join(path, "casl.toml")
    with open(path, encoding="utf-8") as fh:
        data = _parse_toml(fh.read())
    root = os.path.dirname(os.path.abspath(path))
    name = data.get("name")
    version = data.get("version")
    if not name or not version:
        raise ManifestError("casl.toml must declare `name` and `version`")
    attest = (data.get("attest") or {}).get("pubkey")
    arts: List[Artifact] = []
    for i, raw in enumerate(data.get("artifact", [])):
        a = _artifact_from(raw, i)
        arts.append(a)
    return Manifest(name=name, version=str(version), attest_pubkey=attest, artifacts=arts, root=root,
                    min_evidence=data.get("min_evidence"))


def _strict_bool(raw: Dict[str, Any], key: str, nm: str) -> Optional[bool]:
    """Parse a SECURITY flag strictly: absent ⇒ None; a real bool ⇒ that bool; anything else (a string like
    "false", an int) is a hard error. A misspelled/mistyped security flag must never fail OPEN — note that
    bool("false") is True. See docs/analyses/confinement-by-default-llm-artifacts.md."""
    if key not in raw:
        return None
    v = raw[key]
    if isinstance(v, bool):
        return v
    raise ManifestError(f"artifact {nm!r}: `{key}` must be a boolean (true/false), got {v!r}")


def _artifact_from(raw: Dict[str, Any], i: int) -> Artifact:
    nm = raw.get("name")
    if not nm:
        raise ManifestError(f"[[artifact]] #{i} has no `name`")
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ManifestError(f"artifact {nm!r}: kind must be one of {KINDS}, got {kind!r}")
    grade = raw.get("grade", "G3")
    if grade not in GRADES:
        raise ManifestError(f"artifact {nm!r}: grade must be one of {GRADES}, got {grade!r}")
    # provenance fixes the trace regime (LH-P-009): owned ⇒ full, external ⇒ burden — not free choice.
    declared_trace = raw.get("trace")
    trace = "burden" if kind == "external" else "full"
    if declared_trace is not None and declared_trace != trace:
        raise ManifestError(
            f"artifact {nm!r}: trace regime follows ownership (kind={kind} ⇒ {trace}), "
            f"not the declared {declared_trace!r} (LH-P-009)")
    body = raw.get("body")
    if kind in ("generated", "verified") and not body:
        raise ManifestError(f"artifact {nm!r}: kind {kind} requires a `body` path")
    try:
        signers = int(raw.get("signers", 1) or 1)
    except (TypeError, ValueError):
        raise ManifestError(f"artifact {nm!r}: signers must be an integer ≥1")
    if signers < 1:
        raise ManifestError(f"artifact {nm!r}: signers must be ≥1, got {signers}")
    implements = raw.get("implements")
    if implements is not None and ":" not in str(implements):
        raise ManifestError(f"artifact {nm!r}: implements must be '<protocol>:<Label>', got {implements!r}")
    # CEP-0078: a capability provider declares the ONE capability it offers (single-purpose). `confined`
    # opts the artifact into having NO ambient I/O (it may act only through granted providers).
    provides = raw.get("provides")
    if provides is not None and (not str(provides).strip() or not isinstance(provides, str)):
        raise ManifestError(f"artifact {nm!r}: provides must be a non-empty capability name, got {provides!r}")
    # confinement-by-default (docs/analyses/confinement-by-default-llm-artifacts.md): `confined` is a
    # security flag, parsed STRICTLY (no truthy-string fail-open). An LLM-authored kind (generated/oracle)
    # may NOT opt out of it — a body must not be able to grant ITSELF ambient authority (R-H1).
    confined_decl = _strict_bool(raw, "confined", nm)
    if _strict_bool(raw, "unconfined", nm) or _strict_bool(raw, "native", nm):
        if kind in ("generated", "oracle"):
            raise ManifestError(f"artifact {nm!r}: an LLM-authored kind ({kind}) cannot opt out of "
                                f"confinement (`unconfined`/`native`) — a body must not grant itself "
                                f"ambient authority (R-H1)")
        raise ManifestError(f"artifact {nm!r}: confinement opt-out (`unconfined`/`native`) is not yet "
                            f"available — it requires a human attestation + graded obligation (P4)")
    if kind in ("generated", "oracle") and confined_decl is False:
        raise ManifestError(f"artifact {nm!r}: an LLM-authored kind ({kind}) cannot set `confined = false` "
                            f"(confinement-by-default) — omit it or set true")
    confined = bool(confined_decl)
    return Artifact(name=nm, kind=kind, requirement=raw.get("requirement", ""),
                    grade=grade, trace=trace, body=body, signers=signers, implements=implements,
                    provides=(str(provides) if provides else None), confined=confined)


# --------------------------------------------------------------------------
# scaffold + introspection
# --------------------------------------------------------------------------
_SAMPLE_MANIFEST = '''\
name = "{name}"
version = "0.1.0"

# The recorded human signing identity (LH-Q-018). A human signs AS a human: use a git-native
# identity key (GPG/SSH, ideally hardware/passphrase) that a local agent CANNOT read and reuse.
[attest]
pubkey = ".casl/attest.pub"

# Each artifact is a first-class unit: a typed seam (declared in casl/*.casl), a body file
# (artifacts/<name>.<ext>, LLM-writable, contained), and this obligation record. `kind` is
# structured + validated (LH-F-013); the trace regime follows ownership (LH-P-009).
# [[artifact]]
# name        = "smtp_send"
# kind        = "generated"        # external | generated | verified | oracle
# requirement = "LH-LOCAL-001"
# grade       = "G3"               # unprovable kinds (external/generated/oracle) floor at G3
# body        = "artifacts/smtp_send.py"
'''

_DIRS = ("requirements", "casl", "artifacts", "attestations", "tests", ".casl")


def init_project(directory: str, name: Optional[str] = None) -> str:
    """Scaffold the canonical layout. Idempotent: never overwrites an existing casl.toml."""
    os.makedirs(directory, exist_ok=True)
    name = name or os.path.basename(os.path.abspath(directory)) or "casl-project"
    for d in _DIRS:
        os.makedirs(os.path.join(directory, d), exist_ok=True)
    man = os.path.join(directory, "casl.toml")
    if not os.path.exists(man):
        with open(man, "w", encoding="utf-8") as fh:
            fh.write(_SAMPLE_MANIFEST.format(name=name))
    lock = os.path.join(directory, "deps.lock")
    if not os.path.exists(lock):
        with open(lock, "w", encoding="utf-8") as fh:
            fh.write("# dependency burden ledger (LH-Q-020): name version sha256 accepted-by date\n")
    pub = os.path.join(directory, ".casl", "attest.pub")
    if not os.path.exists(pub):
        with open(pub, "w", encoding="utf-8") as fh:
            fh.write("# put your signing identity's PUBLIC key / key-id here (committed, CODEOWNERS).\n"
                     "# the PRIVATE key stays in your agent (gpg/ssh) — never in the repo.\n")
    keys = os.path.join(directory, ".casl", "attest_keys")
    if not os.path.exists(keys):
        with open(keys, "w", encoding="utf-8") as fh:
            fh.write("# attestation keyring (D4 / CEP-0072, LH-Q-018): <identity> added:<iso> "
                     "[retired:<iso>] [revoked:<iso> reason:..]\n"
                     "# OPT-IN: while this file has no entries, the key policy is OFF. Add a line per signing\n"
                     "# identity. RETAIN retired keys (old attestations still verify); a REVOKED key invalidates\n"
                     "# signatures made at/after its date (re-attest). A LOST key ⇒ out-of-band re-attestation.\n"
                     "# example:  martin@example.org  added:2026-01-01\n")
    return man


def report(manifest: Manifest) -> str:
    """The cockpit/ledger VIEW: requirement → artifacts → kind/grade/trace (LH-P-008)."""
    lines = [f"CASL project: {manifest.name} v{manifest.version}",
             f"  attestation identity: {manifest.attest_pubkey or '(none declared)'}",
             f"  artifacts: {len(manifest.artifacts)}"]
    if not manifest.artifacts:
        lines.append("  (no [[artifact]] declared yet)")
    for req, arts in sorted(manifest.by_requirement().items()):
        lines.append(f"\n  {req or '(no requirement!)'}:")
        for a in arts:
            own = "owned" if a.owned() else "BURDEN"
            lines.append(f"    - {a.name:18} kind={a.kind:9} grade≥{a.floor()} "
                         f"trace={a.trace:6} [{own}] body={a.body or '—'}")
    return "\n".join(lines)
