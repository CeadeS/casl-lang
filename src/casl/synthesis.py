"""casl.synthesis — the requirements → verified PROJECT loop (CEP-0079).

The authoring front door. A requirement (NL) → an UNTRUSTED generator proposes a `.casl` → the MONOTONE
GATE decides (Tier-0 `check_protocol` is the sole opener; "agents veto, never vouch") → on acceptance,
emit a complete, CONDUCTABLE project (manifest + choreography + artifacts bound to sites) → conduct it
through the broker. This closes the loop from intent to a running, verified system.

CEGIS-shaped (Solar-Lezama; LLM-Modulo / Clover): the gate is the SOLE arbiter of emission, so EVERY
emitted project is gate-accepted regardless of how the generator produced it — the proposer can only ever
be rejected, never vouch. **Fail-closed:** if the gate does not accept within the budget, NOTHING is
emitted (no downgraded artifact).

Honest scope (validation ≠ verification): the gate certifies *spec ⊨ safety*, NOT *spec ≅ intent*. The
emitted project's unprovable artifacts carry attestation OBLIGATIONS a human still signs — the loop
produces the obligation, never discharges it. Verified here with a deterministic mock generator; the live
generator (`casl.synth.ChatGenerator` over Ollama/CoderBackend) is wired but its real run needs a model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional

from casl import ide, project, seam, surface


@dataclass
class NewProjectResult:
    accepted: bool                       # did the gate accept (⇒ a project was emitted)?
    project_dir: Optional[str]
    gate: ide.GateOutcome
    synth: object                        # synth.SynthResult (the proposal trace)
    conducted: object = None             # conductor.ConductorResult | None
    artifacts: List[str] = field(default_factory=list)
    summary: str = ""


def derive_manifest(proto, requirement: str) -> str:
    """Emit `casl.toml` `[[artifact]]` entries from an ACCEPTED choreography: one `oracle` artifact per
    oracle site (bound to it via the typed seam), one single-purpose `external` provider per distinct
    effect capability. Deterministic; the project it produces is gate-clean and conductable."""
    sites = seam._walk(proto.gtype)
    out = [f'name = "{proto.name.lower()}"', 'version = "0.1.0"', ""]
    for c in sites:                                  # oracle sites → monitored oracle artifacts
        if getattr(c, "from_oracle", False):
            out += ["[[artifact]]",
                    f'name        = "{c.label.lower()}"',
                    'kind        = "oracle"',
                    f'requirement = "{requirement}"',
                    'grade       = "G3"',
                    f'implements  = "{proto.name}:{c.label}"', ""]
    seen = set()
    for c in sites:                                  # effect capabilities → single-purpose providers
        cap = getattr(c, "uses_capability", None)
        if cap and cap not in seen:
            seen.add(cap)
            out += ["[[artifact]]",
                    f'name        = "{cap}_provider"',
                    'kind        = "external"',
                    f'requirement = "{requirement}"',
                    'grade       = "G3"',
                    f'provides    = "{cap}"', ""]
    return "\n".join(out)


def new_project(wish: str, project_dir: str, generator, *, reviewer=None, approver=None,
                max_iters: int = 6, conduct: bool = True, scenario: str = "ok",
                requirement: str = "R-SYNTH") -> NewProjectResult:
    """Requirement → gated proposal → (on accept) emit a conductable project → conduct it. Fail-closed."""
    # 1) the gated CEGIS loop — the monotone gate is the SOLE arbiter (Tier-0 opener; veto-never-vouch).
    approver = approver or ide.auto_approver         # offline path; the human signs the obligations at gate-time
    outcome, sr = ide.synthesize_gated(wish, generator, reviewer=reviewer, approver=approver,
                                       max_iters=max_iters)
    if not outcome.accepted:
        # 2) FAIL-CLOSED — emit nothing. A rejected proposal never becomes a project.
        return NewProjectResult(False, None, outcome, sr,
                                summary=f"no gate-accepted spec in {sr.iterations} iter(s) — nothing "
                                        f"emitted (fail-closed; gate @ Tier {outcome.tier}: {outcome.reason})")
    # 3) EMIT a conductable project — ONLY on acceptance.
    proto = surface.parse(sr.casl_text)
    name = proto.name.lower()
    project.init_project(project_dir, name=name)
    with open(os.path.join(project_dir, "casl", f"{name}.casl"), "w", encoding="utf-8") as f:
        f.write(sr.casl_text if sr.casl_text.endswith("\n") else sr.casl_text + "\n")
    with open(os.path.join(project_dir, "casl.toml"), "w", encoding="utf-8") as f:
        f.write(derive_manifest(proto, requirement) + "\n")
    reqs = os.path.join(project_dir, "requirements", "REQUIREMENTS.md")
    os.makedirs(os.path.dirname(reqs), exist_ok=True)
    with open(reqs, "a", encoding="utf-8") as f:
        f.write(f"\n- {requirement}: {wish}\n")
    man = project.load_manifest(os.path.join(project_dir, "casl.toml"))
    artifacts = [a.name for a in man.artifacts]
    # 4) CONDUCT it — prove the emitted project runs end-to-end through the broker.
    cr = None
    if conduct:
        from casl import conductor
        cr = conductor.Conductor(project_dir).run(scenario=scenario, approve=True,
                                                  env={"budget": 100, "question": wish})
    return NewProjectResult(True, project_dir, outcome, sr, cr, artifacts,
                            summary=_summary(proto, outcome, artifacts, cr))


def _summary(proto, outcome, artifacts, cr) -> str:
    lines = [f"requirements → verified project: «{proto.name}» (gate ✓ Tier {outcome.tier})",
             f"  emitted artifacts: {', '.join(artifacts) or '(none)'}"]
    if cr is not None:
        lines.append(f"  conducted end-to-end through the broker: {cr.run.outcome}")
    lines.append("  NOTE: gate certifies spec ⊨ safety, not spec ≅ intent; unprovable artifacts carry "
                 "human-attestation obligations (validation ≠ verification).")
    return "\n".join(lines)


def format_new(res: NewProjectResult) -> str:
    head = ["=" * 72, "CASL — requirements → verified project", "=" * 72]
    if not res.accepted:
        return "\n".join(head + [f"  ✗ {res.summary}"])
    return "\n".join(head + [f"  ✓ emitted + {('conducted' if res.conducted else 'ready')} at {res.project_dir}",
                             "", res.summary])
