"""casl.capability — the capability-provider gate (CEP-0078, docs/confinement.md).

No ambient I/O authority (the object-capability law / POLA): raw I/O lives ONLY inside single-purpose,
human-signed PROVIDER artifacts; a `confined` artifact has zero ambient I/O and may act only by invoking a
granted provider. These are the gate-time, by-construction (rung-2) checks; the OS-level enforcement
(rung-3) that makes them hold against *malicious* code is `rust/casl-host`.

This INSTANTIATES the model CASL already has (capabilities, attenuation, attestation, the grade lattice) —
it does not reinvent it. The human-SIGNATURE requirement for a provider is enforced by the obligation gate
(which treats `provides` as requiring an attestation); here we enforce the structural rules: single-purpose,
unambiguous, and no-ambient-authority for confined callers.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from casl import seam

# Capabilities the broker itself provides (the broker IS the default capability provider / reference
# monitor). A confined artifact may always reach these — they are mediated. Everything else needs a
# human-signed, single-purpose provider artifact.
BROKER_BUILTINS = {"broker"}


def provider_index(manifest) -> Dict[str, list]:
    """{capability -> [provider artifacts]} over every artifact that declares `provides`."""
    out: Dict[str, list] = {}
    for a in manifest.artifacts:
        cap = getattr(a, "provides", None)
        if cap:
            out.setdefault(cap, []).append(a)
    return out


def required_capability(artifact, project_dir: str) -> Optional[str]:
    """The capability an artifact NEEDS: the `uses_capability` of the choreography site it implements
    (the typed seam, CEP-0074). None if it implements no effect site."""
    impl = getattr(artifact, "implements", None)
    if not impl:
        return None
    proto, _, label = impl.partition(":")
    g = seam.load_choreographies(project_dir).get(proto)
    if g is None:
        return None
    site = seam.find_site(g, label)
    return getattr(site, "uses_capability", None) if site is not None else None


def _cap_modes(project_dir: str) -> Dict[str, Dict[str, str]]:
    """{protocol -> {tool -> mode}} from the agent cap declarations. Lets the no-ambient check tell a READ
    capability (the monitored-oracle boundary; broker-mediated, NOT ambient I/O) from an EFFECT (write/admin)
    capability (which needs a single-purpose signed provider). A confined brain may use reads freely."""
    import glob
    import os as _os
    from casl import surface
    out: Dict[str, Dict[str, str]] = {}
    for path in sorted(glob.glob(_os.path.join(project_dir, "casl", "*.casl"))):
        try:
            proto = surface.parse_file(path)
        except Exception:
            continue
        modes: Dict[str, str] = {}
        for _role, caps in (getattr(proto, "caps", None) or {}).items():
            for c in caps:
                if getattr(c, "tool", None):
                    modes[c.tool] = getattr(c, "mode", None)
        out[proto.name] = modes
    return out


def _is_read_cap(artifact, cap: Optional[str], modes: Dict[str, Dict[str, str]]) -> bool:
    """A read-mode capability is the broker-mediated oracle boundary — not ambient I/O a provider must hold."""
    impl = getattr(artifact, "implements", None)
    proto = impl.partition(":")[0] if impl else ""
    return bool(cap) and modes.get(proto, {}).get(cap) == "read"


def check_providers(manifest) -> Tuple[bool, List[str]]:
    """A provider is SINGLE-PURPOSE (one capability — enforced by the field) and UNAMBIGUOUS (no two
    providers offer the same capability), and is not itself `confined` (it HOLDS authority). The
    human-signature requirement is enforced by the obligation gate (CEP-0078)."""
    viol: List[str] = []
    for cap, arts in sorted(provider_index(manifest).items()):
        if len(arts) > 1:
            names = ", ".join(sorted(a.name for a in arts))
            viol.append(f"capability {cap!r} provided by >1 artifact ({names}) — a provider must be the "
                        f"single, unambiguous holder of its authority (CEP-0078)")
    for a in manifest.artifacts:
        if getattr(a, "provides", None) and getattr(a, "confined", False):
            viol.append(f"artifact {a.name!r}: a provider cannot itself be `confined` — it holds the I/O "
                        f"authority it provides (CEP-0078)")
    return (not viol, viol)


def check_no_ambient_authority(manifest, project_dir: str) -> Tuple[bool, List[str]]:
    """Every capability a CONFINED artifact uses must resolve to a granted provider (or a broker builtin).
    A confined artifact naming an unprovided capability is REJECTED — there is no ambient path (the
    by-construction half of the egress invariant; rung-2)."""
    viol: List[str] = []
    idx = provider_index(manifest)
    modes = _cap_modes(project_dir)
    for a in manifest.artifacts:
        if not getattr(a, "confined", False):
            continue
        cap = required_capability(a, project_dir)
        if cap is None:
            continue
        # READ caps are the broker-mediated oracle boundary, not ambient I/O — a confined brain may use them
        # freely (it holds no write capability). Only EFFECT caps need a signed single-purpose provider.
        if _is_read_cap(a, cap, modes):
            continue
        if cap not in idx and cap not in BROKER_BUILTINS:
            viol.append(f"confined artifact {a.name!r} uses capability {cap!r} with no provider — no "
                        f"ambient authority (CEP-0078): add a single-purpose signed provider (or route via "
                        f"the broker)")
    return (not viol, viol)


def io_grade(manifest, project_dir: str) -> Dict[str, str]:
    """{confined artifact -> the assurance grade of its I/O} = the floor of the provider it is granted
    (the weakest-link / honesty rule). Confinement (rung-3) is what later promotes this above attested."""
    idx = provider_index(manifest)
    modes = _cap_modes(project_dir)
    out: Dict[str, str] = {}
    for a in manifest.artifacts:
        if not getattr(a, "confined", False):
            continue
        cap = required_capability(a, project_dir)
        if _is_read_cap(a, cap, modes):
            out[a.name] = "G3"          # broker-mediated oracle read; attested by default
        elif cap and cap in idx:
            out[a.name] = idx[cap][0].floor()
        elif cap in BROKER_BUILTINS:
            out[a.name] = "G3"          # broker-mediated; attested by default
    return out


def check(manifest, project_dir: str) -> Tuple[bool, List[str]]:
    """The combined gate-time capability-provider check (rung-2). Inert for manifests with no providers
    and no confined artifacts (backward-compatible). The signature requirement lives in the obligation
    gate."""
    pok, pv = check_providers(manifest)
    aok, av = check_no_ambient_authority(manifest, project_dir)
    return (pok and aok), (pv + av)


def report(manifest, project_dir: str) -> str:
    idx = provider_index(manifest)
    lines = [f"capability providers: {len(idx)}"]
    for cap, arts in sorted(idx.items()):
        a = arts[0]
        lines.append(f"  ✓ {cap} ⟵ {a.name} (kind={a.kind}, floor={a.floor()}, single-purpose)")
    _ok, viol = check(manifest, project_dir)
    lines += [f"  ✗ {v}" for v in viol]
    for name, g in sorted(io_grade(manifest, project_dir).items()):
        lines.append(f"  · confined {name}: I/O grade {g} (= its provider's floor)")
    return "\n".join(lines)
