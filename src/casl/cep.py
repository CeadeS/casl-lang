"""
cep.py — CASL Enhancement Proposals (CEPs): the versioned, machine-checked requirement log.

Modeled on Python's PEPs / IETF RFCs, but with one addition they do not have: a CEP's
status is *enforced by the machine*, not asserted in prose. Each requirement/enhancement
is a numbered CEP file in `proposals/` with structured frontmatter. The living audit turns
the corpus into a contract:

  · the corpus must be schema-valid;
  · it must agree exactly with `spec.REQS` (round-trip) — the prose log cannot drift from
    the runtime spine;
  · a CEP may claim `Final`/`Accepted` only if its `realized-by` building blocks exist in
    the kernel registry — and, the audit being green, those blocks pass. Prose can veto,
    never vouch (P0/P9).

This module is a DEPENDENCY-FREE loader/validator (no third-party deps, no internal imports
beyond the standard library) so it works on any supported Python and never perturbs import
order. The runtime spine (`spec.REQS`) does NOT depend on this module, so the pip-installed
package never needs the `proposals/` directory; the corpus is a development/governance layer
that the audit (run from the repository) checks.
"""
from __future__ import annotations
import glob
import os
from typing import Dict, List, Optional, Tuple

VALID_STATUS = {"Draft", "Accepted", "Final", "Rejected", "Withdrawn", "Deferred", "Superseded"}
VALID_TYPE = {"Standards", "Process", "Informational"}
VALID_LEVEL = {"MUST", "SHOULD", "MAY"}
VALID_VERIF = {"B", "S", "M", "T", "—"}
REQUIRED_FIELDS = ["cep", "title", "status", "type"]


def proposals_dir(d: Optional[str] = None) -> str:
    if d:
        return d
    here = os.path.dirname(os.path.abspath(__file__))      # src/casl
    root = os.path.dirname(os.path.dirname(here))           # repo root
    return os.path.join(root, "proposals")


def _scalar(v: str):
    """Parse a frontmatter value: a [a, b] list or a bare scalar string."""
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip() for x in inner.split(",") if x.strip()] if inner else []
    return v


def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Return (meta, body). Frontmatter = the leading '---'-delimited block of key: value lines."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = text[3:end].strip("\n")
    body = text[end + 4:]
    meta: dict = {}
    for line in fm.splitlines():
        line = line.rstrip()
        if not line or line.lstrip().startswith("#") or ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = _scalar(v)
    return meta, body


def load_ceps(d: Optional[str] = None) -> List[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(proposals_dir(d), "cep-*.md"))):
        meta, body = parse_frontmatter(open(f, encoding="utf-8").read())
        meta["_file"] = os.path.basename(f)
        meta["_body"] = body
        out.append(meta)
    return out


def _as_list(x) -> List[str]:
    if isinstance(x, list):
        return x
    return [x] if x else []


def requirements(ceps: Optional[List[dict]] = None) -> Dict[str, tuple]:
    """{requirement-id: (level, verification, [theses])} — the same shape as spec.REQS,
    for every CEP that carries a `requirement-id`."""
    ceps = load_ceps() if ceps is None else ceps
    out: Dict[str, tuple] = {}
    for c in ceps:
        rid = c.get("requirement-id")
        if rid:
            out[rid] = (c.get("level"), c.get("verification"), _as_list(c.get("theses")))
    return out


def validate(ceps: Optional[List[dict]] = None) -> List[Tuple[str, str]]:
    """Schema validation: required fields present, enums valid, numbers/requirement-ids unique,
    requires/supersedes resolve to existing CEPs."""
    ceps = load_ceps() if ceps is None else ceps
    v: List[Tuple[str, str]] = []
    nums = {str(c.get("cep")) for c in ceps}
    seen_num, seen_rid = set(), set()
    for c in ceps:
        f = c.get("_file", "?")
        for k in REQUIRED_FIELDS:
            if not c.get(k):
                v.append((f, f"missing required field '{k}'"))
        if c.get("status") and c["status"] not in VALID_STATUS:
            v.append((f, f"invalid status '{c['status']}'"))
        if c.get("type") and c["type"] not in VALID_TYPE:
            v.append((f, f"invalid type '{c['type']}'"))
        if c.get("level") and c["level"] not in VALID_LEVEL:
            v.append((f, f"invalid level '{c['level']}'"))
        verif = c.get("verification")
        if verif and verif != "—" and not all(p in {"B", "S", "M", "T"} for p in verif.split("/")):
            v.append((f, f"invalid verification stage '{verif}'"))
        n = str(c.get("cep"))
        if n in seen_num:
            v.append((f, f"duplicate CEP number {n}"))
        seen_num.add(n)
        rid = c.get("requirement-id")
        if rid:
            if rid in seen_rid:
                v.append((f, f"duplicate requirement-id {rid}"))
            seen_rid.add(rid)
        for r in _as_list(c.get("requires")):
            if str(r) not in nums:
                v.append((f, f"requires unknown CEP {r}"))
        for s in _as_list(c.get("supersedes")):
            if str(s) not in nums:
                v.append((f, f"supersedes unknown CEP {s}"))
    return v


def status_consistency(registry_ids, accepted_gap_ids,
                       ceps: Optional[List[dict]] = None) -> List[Tuple[str, str]]:
    """The 'proven' rule. A CEP may claim Final/Accepted only if every `realized-by` building
    block exists in the kernel registry (the audit being green ⇒ those blocks pass). An
    accepted gap must be reflected as Deferred, and vice versa — prose status cannot outrun
    the machine."""
    ceps = load_ceps() if ceps is None else ceps
    reg, gaps = set(registry_ids), set(accepted_gap_ids)
    v: List[Tuple[str, str]] = []
    for c in ceps:
        f, st, rid = c.get("_file", "?"), c.get("status"), c.get("requirement-id")
        rb = _as_list(c.get("realized-by"))
        # The realized-by ('proven') rule applies to Standards CEPs (requirements); Process /
        # Informational CEPs are governance documents and carry no building block.
        if st in ("Final", "Accepted") and c.get("type") == "Standards":
            if not rb:
                v.append((f, f"status {st} but no realized-by building block"))
            missing = [b for b in rb if b not in reg]
            if missing:
                v.append((f, f"status {st} but realized-by not in registry: {missing}"))
        if rid and rid in gaps and st not in ("Deferred", "Draft"):
            v.append((f, f"{rid} is an accepted gap but CEP status is {st} (expected Deferred)"))
        if st == "Deferred" and rid and rid not in gaps:
            v.append((f, f"status Deferred but {rid} is not a tracked accepted gap"))
    return v


def roundtrip_diff(spec_reqs: Dict[str, tuple],
                   ceps: Optional[List[dict]] = None) -> List[str]:
    """Differences between the CEP-derived requirement table and the runtime spine spec.REQS.
    Empty ⇒ the versioned log and the runtime spine are identical."""
    cep_reqs = requirements(ceps)
    diffs = []
    for rid in sorted(set(spec_reqs) | set(cep_reqs)):
        a, b = spec_reqs.get(rid), cep_reqs.get(rid)
        if a != b:
            diffs.append(f"{rid}: spec={a} cep={b}")
    return diffs
