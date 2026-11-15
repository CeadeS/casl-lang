"""The Tier-0 obligation gate (LH-G-006) + assurance floor (LH-Q-016) + monotonicity (LH-Q-019).

Composes the artifact-trust obligations into ONE deny-by-default check — the only opener
("agents may veto, never vouch"). A project (or an artifact) is admitted iff EVERY declared
obligation holds:

  · the manifest is valid (project.load_manifest);
  · every dependency is pinned + owned (dependency.check_ledger) — the burden ledger (LH-Q-020);
  · every OWNED artifact: its body exists; it is full line-traced (no untraced lines, LH-P-006);
    it declares a requirement; it meets its assurance floor (LH-Q-016 — unprovable ⇒ G3);
  · every UNPROVABLE owned artifact (`generated`/`oracle`) additionally carries a content-bound,
    non-self, human-identity attestation that VERIFIES (attestation.verify); a `verified` artifact is
    discharged by proof and needs no signature.

The effective project grade is the WEAKEST artifact grade (LH-Q-019, min-composition) — laundering
is impossible. (Open: grade-per-data-flow-path, so one contained call need not flatten the whole
system — docs Open-4.) Ring 1/2; does not touch the verified core.
"""
from __future__ import annotations

import os
from typing import List, Optional, Tuple

from casl import project as _proj
from casl import dependency as _dep
from casl import attestation as _att
from casl import keyring as _kr
from casl import seam as _seam

_RANK = {"G0": 0, "G1": 1, "G2": 2, "G3": 3}   # G0 strongest; weakest = max rank


def effective_grade(man: _proj.Manifest) -> str:
    """Weakest floor among artifacts — the honest end-to-end grade (LH-Q-019)."""
    if not man.artifacts:
        return "G0"
    return max((a.floor() for a in man.artifacts), key=lambda g: _RANK.get(g, 3))


def grade_by_requirement(man: _proj.Manifest) -> dict:
    """Finer than the global weakest link (CEP-0070, model A): the weakest floor WITHIN each
    requirement's artifacts. The grouping is structured (the manifest's `requirement` field), so there
    is no laundering surface. The global `effective_grade` headline is UNCHANGED and stays authoritative;
    this is an additional view that can never raise the reported number on its own. The flow-graph /
    containment-boundary models (CEP-0070 B/C) are deferred until the typed .casl↔artifact seam exists."""
    out = {}
    for req, arts in man.by_requirement().items():
        out[req] = max((a.floor() for a in arts), key=lambda g: _RANK.get(g, 3)) if arts else "G0"
    return out


def _attestation_records(directory: str, name: str):
    """All attestation records for an artifact: the primary `<name>.json` plus optional co-signer
    sidecars `<name>.2.json`, `<name>.3.json`, … (D3 second-signer). Returns [(path, AttRecord)]."""
    import glob
    d = os.path.join(directory, "attestations")
    out = []
    primary = os.path.join(d, f"{name}.json")
    if os.path.exists(primary):
        try:
            out.append((primary, _att.load_record(primary)))
        except Exception:
            pass
    for p in sorted(glob.glob(os.path.join(d, f"{name}.*.json"))):
        try:
            out.append((p, _att.load_record(p)))
        except Exception:
            pass
    return out


def signature_concentration(directory: str, man: _proj.Manifest) -> dict:
    """Per-signer count of UNPROVABLE artifacts they sign for (D3 risk-surfacing): a lot of unprovable
    surface under one signature is concentrated rubber-stamp risk. Manifest + records only (no git).
    Honest limit: this makes the risk VISIBLE; it cannot prove a signer actually reviewed — observability
    (LH-G-005) is the real mitigation, the signature is a liability anchor, the cage is the safety."""
    out: dict = {}
    for a in man.artifacts:
        if a.kind not in ("generated", "oracle"):
            continue
        for _rp, rec in _attestation_records(directory, a.name):
            if rec.signer and a.name not in out.setdefault(rec.signer, []):
                out[rec.signer].append(a.name)
    return out


def check_project(directory: str, *, repo: Optional[str] = None,
                  require_signed: bool = True) -> Tuple[bool, List[str]]:
    """(ok, lines) — deny-by-default over all obligations. `repo` enables git line-trace + signature
    verification; when None, trace/signature checks that need git are reported as unchecked (and, for
    signatures of unprovable artifacts, that means deny-by-default)."""
    lines: List[str] = []
    ok = True
    try:
        man = _proj.load_manifest(directory)
    except (FileNotFoundError, _proj.ManifestError) as e:
        return False, [f"manifest: {e}"]

    deps = _dep.load_ledger(directory)
    dok, dv = _dep.check_ledger(deps)
    if not dok:
        ok = False
        lines += [f"dependency burden: {v}" for v in dv]
    mok, mv = _dep.check_min_evidence(deps, getattr(man, "min_evidence", None))   # D5 supply-chain policy
    if not mok:
        ok = False
        lines += [f"supply-chain evidence: {v}" for v in mv]
    dep_names = {d.name for d in deps}

    for a in man.artifacts:
        tag = f"artifact {a.name}"
        if a.kind == "external":
            if a.name not in dep_names:
                ok = False
                lines.append(f"{tag}: external but not pinned in deps.lock (LH-Q-020)")
            continue
        # confinement-by-default (docs/analyses/confinement-by-default-llm-artifacts.md): an LLM-authored
        # kind (generated/oracle) MUST be `confined` — a body we did not write may not hold ambient
        # authority. The loader already forbids opting out; this denies forgetting to opt in.
        if a.kind in ("generated", "oracle") and not getattr(a, "confined", False):
            ok = False
            lines.append(f"{tag}: kind {a.kind} must be `confined` (confinement-by-default) — an "
                         f"LLM-authored body may not hold ambient authority (CEP-0078)")
        if not a.requirement:
            ok = False
            lines.append(f"{tag}: no requirement (every owned unit must trace, LH-P-006)")
        body = os.path.join(directory, a.body) if a.body else None
        if a.kind in ("generated", "verified"):
            if not body or not os.path.exists(body):
                ok = False
                lines.append(f"{tag}: body missing ({a.body})")
                continue
            if repo is not None:
                from casl import traceability as _tr
                try:
                    u = _tr.untraced_lines(body, repo)
                    if u:
                        ok = False
                        lines.append(f"{tag}: {len(u)} untraced line(s) — block (LH-P-006)")
                except Exception as e:
                    ok = False
                    lines.append(f"{tag}: trace check failed ({e})")
        # attestation: needed iff unprovable (generated/oracle), OR the artifact is a capability PROVIDER
        # (CEP-0078: granting world-access is an unprovable trust act — even a `verified` provider needs a
        # human signature for its I/O grant; `external` providers are governed by the deps ledger instead).
        if a.kind in ("generated", "oracle") or (getattr(a, "provides", None) and a.kind != "external"):
            recs = _attestation_records(directory, a.name)
            if not recs:
                ok = False
                lines.append(f"{tag}: no attestation record (unprovable ⇒ needs a human signature, LH-Q-016/018)")
                continue
            valid_signers = set()
            for rp, rec in recs:
                target = body if body else rp
                vok, reason = _att.verify(rec, target, repo=repo, require_signed=require_signed)
                if vok and rec.signer:
                    kok, kreason = _kr.authorized(directory, rec.signer, rec.ts)   # D4: opt-in key policy
                    if kok:
                        valid_signers.add(rec.signer.strip().lower())
                    else:
                        lines.append(f"{tag}: attestation {os.path.basename(rp)} — {kreason} (D4 key lifecycle, LH-Q-018)")
                elif not vok:
                    lines.append(f"{tag}: attestation {os.path.basename(rp)} NOT valid — {reason}")
            need = max(1, getattr(a, "signers", 1))     # D3: second-signer knob (default 1)
            if len(valid_signers) < need:
                ok = False
                lines.append(f"{tag}: needs {need} distinct valid human signature(s), have {len(valid_signers)} "
                             f"[{', '.join(sorted(valid_signers)) or 'none'}] — LH-Q-018 (D3 second-signer)")

    # LH-F-012 (full): typed seam — bound artifacts must resolve to a real site of matching nature.
    sok, sviol, _bind = _seam.check_seam(man, directory)
    if not sok:
        ok = False
        lines += [f"typed seam: {v}" for v in sviol]
    # CEP-0078: capability providers single-purpose + unambiguous; confined artifacts have NO ambient
    # authority (every used capability resolves to a granted provider). Inert when no providers/confined.
    from casl import capability as _cap
    cok, cviol = _cap.check(man, directory)
    if not cok:
        ok = False
        lines += [f"capability: {v}" for v in cviol]
    return ok, lines


def report(directory: str, *, repo: Optional[str] = None, require_signed: bool = True) -> Tuple[int, str]:
    ok, lines = check_project(directory, repo=repo, require_signed=require_signed)
    head, breakdown = "Tier-0 obligation gate", ""
    try:
        man = _proj.load_manifest(directory)
        eff = effective_grade(man)
        head = f"Tier-0 obligation gate — {man.name} v{man.version} · effective grade ≥{eff} (weakest link)"
        per = grade_by_requirement(man)
        if per:
            breakdown = ("\n  per requirement (CEP-0070, finer view; the weakest-link headline stays "
                         "authoritative):\n" +
                         "\n".join(f"    {req or '(no requirement!)'}: ≥{g}" for req, g in sorted(per.items())))
        conc = signature_concentration(directory, man)
        if conc:
            breakdown += ("\n  signature concentration (D3 — unprovable artifacts per signer; observability "
                          "(LH-G-005) is the real mitigation, the signature is only a liability anchor):\n" +
                          "\n".join(f"    {s}: {len(arts)} unprovable artifact(s) [{', '.join(sorted(arts))}]"
                                    for s, arts in sorted(conc.items())))
        floor = _dep.supply_chain_floor(_dep.load_ledger(directory))
        if floor:
            breakdown += (f"\n  supply-chain evidence floor: {floor} (weakest dependency; "
                          f"pin<sbom<slsa<signed, CEP-0073)")
    except Exception:
        pass
    body = "\n".join(f"  ✗ {l}" for l in lines)
    if ok:
        return 0, head + breakdown + "\n  ✓ all obligations satisfied (manifest + deps + trace + attestation)"
    return 1, head + breakdown + "\n" + body + "\n  → DENY (deny-by-default; agents may veto, never vouch)"
