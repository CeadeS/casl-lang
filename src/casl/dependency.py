"""Dependency burden ledger (LH-Q-020 / CEP-0066).

Premise (artifact-trust-requirements.md, Premise 1): the moment a program imports a whole piece of
software we *trust* it — we cannot verify each import. Installed packages are **liabilities we accept
and carry**. CASL does not pretend to check their bodies; it makes the trust **visible and owned**:

  · every external dependency is DECLARED and version+hash **pinned** (substitution/supply-chain drift
    is then detectable);
  · it records the **human who accepted the burden** (an owned decision, not a silent transitive trust);
  · it is **contained** at runtime by the capability cage (handled by the broker / cap containment);
  · an **unpinned or unowned** entry **blocks** (deny-by-default); a **hash change expires** the
    acceptance and requires re-acceptance.

This is deliberately NOT line-trace or body-attestation — those would be dishonest for code we did not
write. Ring 1/2; does not touch the verified core.

`deps.lock` line format (comments with `#`):

    <name> <version> sha256:<hex> accepted-by:<who> [date:<iso>]
    requests 2.32.3 sha256:abc123… accepted-by:Alice date:2026-06-24
"""
from __future__ import annotations

import dataclasses
import os
from typing import List, Optional, Tuple

# Supply-chain EVIDENCE ladder (D5 / CEP-0073), escalating: a pin detects substitution; an SBOM makes
# the transitive burden complete; SLSA attests build provenance; `signed` binds a publisher identity.
# None of these make a dependency "verified" — they strengthen the EVIDENCE about an accepted burden.
EVIDENCE_RANK = {"pin": 0, "sbom": 1, "slsa": 2, "signed": 3}


@dataclasses.dataclass(frozen=True)
class Dep:
    name: str
    version: str
    sha256: str           # "sha256:<hex>" — the pin
    accepted_by: str      # the human who accepted the burden
    date: Optional[str] = None
    evidence: str = "pin"  # supply-chain evidence level (D5): pin | sbom | slsa | signed

    def well_formed(self) -> Tuple[bool, str]:
        if not self.name or not self.version:
            return False, "missing name/version"
        if not (self.sha256.startswith("sha256:") and len(self.sha256) > len("sha256:")):
            return False, "not pinned (need sha256:<hex>)"
        if not self.accepted_by:
            return False, "no accepting human (burden must be owned)"
        if self.evidence not in EVIDENCE_RANK:
            return False, f"unknown evidence level {self.evidence!r} (pin|sbom|slsa|signed)"
        return True, ""


class LedgerError(ValueError):
    pass


def parse_ledger(text: str) -> List[Dep]:
    deps: List[Dep] = []
    for ln, line in enumerate(text.splitlines(), 1):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        toks = line.split()
        if len(toks) < 2:
            raise LedgerError(f"deps.lock line {ln}: expected `<name> <version> sha256:… accepted-by:…`")
        name, version = toks[0], toks[1]
        sha = next((t for t in toks[2:] if t.startswith("sha256:")), "")
        kv = dict(t.split(":", 1) for t in toks[2:] if ":" in t and not t.startswith("sha256:"))
        deps.append(Dep(name=name, version=version, sha256=sha,
                        accepted_by=kv.get("accepted-by", ""), date=kv.get("date"),
                        evidence=kv.get("evidence", "pin")))
    return deps


def load_ledger(directory: str) -> List[Dep]:
    path = directory if directory.endswith("deps.lock") else os.path.join(directory, "deps.lock")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return parse_ledger(fh.read())


def check_ledger(deps: List[Dep]) -> Tuple[bool, List[str]]:
    """Deny-by-default: every entry must be pinned AND owned. (ok, violations)."""
    viol: List[str] = []
    for d in deps:
        ok, why = d.well_formed()
        if not ok:
            viol.append(f"{d.name or '?'} {d.version or ''}: {why}")
    return (not viol, viol)


def supply_chain_floor(deps: List[Dep]) -> Optional[str]:
    """The WEAKEST supply-chain evidence across all deps (D5) — your dependency trust is only as strong
    as the least-evidenced dependency. None when there are no deps."""
    if not deps:
        return None
    return min((d.evidence for d in deps), key=lambda e: EVIDENCE_RANK.get(e, 0))


def check_min_evidence(deps: List[Dep], minimum: Optional[str]) -> Tuple[bool, List[str]]:
    """Optional policy: every dep must carry ≥ `minimum` evidence (pin<sbom<slsa<signed). No minimum
    (None) ⇒ off (back-compat). Generating SBOM/SLSA/signatures is ecosystem tooling, not CASL's job;
    this enforces what the ledger RECORDS, and never claims the dependency body is verified."""
    if not minimum:
        return True, []
    if minimum not in EVIDENCE_RANK:
        return False, [f"unknown min_evidence {minimum!r} (pin|sbom|slsa|signed)"]
    need = EVIDENCE_RANK[minimum]
    viol = [f"{d.name} {d.version}: evidence {d.evidence} < required {minimum}"
            for d in deps if EVIDENCE_RANK.get(d.evidence, 0) < need]
    return (not viol, viol)


def check_imports(used: List[str], deps: List[Dep]) -> Tuple[bool, List[str]]:
    """Every used external import must appear (pinned+owned) in the ledger — an undeclared import
    blocks (deny-by-default). `used` is the set of top-level package names the project imports."""
    have = {d.name for d in deps}
    missing = sorted(set(used) - have)
    return (not missing, [f"undeclared dependency (not in deps.lock): {m}" for m in missing])


def verify_pin(dep: Dep, actual_sha256: str) -> Tuple[bool, str]:
    """A version/hash change expires the burden-acceptance (LH-Q-017): re-acceptance required."""
    want = dep.sha256.split("sha256:", 1)[-1]
    got = actual_sha256.split("sha256:", 1)[-1]
    if want != got:
        return False, (f"{dep.name}: pinned hash changed (was {want[:12]}…, now {got[:12]}…) — "
                       f"burden-acceptance EXPIRED, re-accept required")
    return True, ""


def report(deps: List[Dep]) -> str:
    if not deps:
        return "dependency burden ledger: empty (no external dependencies declared)"
    lines = [f"dependency burden ledger: {len(deps)} accepted liability(ies); "
             f"supply-chain floor = {supply_chain_floor(deps)} (weakest; pin<sbom<slsa<signed)"]
    for d in deps:
        ok, why = d.well_formed()
        mark = "✓" if ok else "✗"
        tail = "" if ok else f"  — {why}"
        lines.append(f"  {mark} {d.name} {d.version}  pin={d.sha256[:18]}…  evidence={d.evidence}  "
                     f"accepted-by={d.accepted_by or '—'}{tail}")
    return "\n".join(lines)
