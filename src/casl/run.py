"""
casl_run.py — operational interpreter: run a CASL protocol END-TO-END.

Prove the hull, then EXECUTE it with the LLM at the boundary. The runner walks
the (verified-shape) global type and:

  · at each oracle step  → calls the backend (mock or live Ollama) for the payload,
    then checks the step's contract with the synthesized monitor (blame on the
    producing agent);
  · at each choice        → follows the branch the monitor verdict implies
    (ok → a terminating branch, violation/refusal → a looping branch);
  · recursion             → bounded by `max_loops` so every run terminates.

This is the two-stage semantics in motion: the deterministic structure (projection,
types, the statically discharged contract) is fixed and proven; only the payload
comes from the nondeterministic oracle, and every oracle output is monitored.

`casl run FILE.casl` drives this; `kernel.interpreter` runs it on G_OK with a
deterministic mock (no network) so the living system stays self-contained.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from casl import core
from casl import spike_resilience as res
from casl import spike_approval as appr


@dataclass
class GateDisclosure:
    """R-N1 (LH-Q-013): what is disclosed to the human at the approval gate — the
    triggering message AND the concrete effect-bearing action(s) that a consent
    would execute. This binds consent to what actually happens
    (no "approve X, branch does Y")."""
    gate: str                    # "U→S"
    disclosed: str               # the most recently disclosed message (e.g. "S→U: Conflict()")
    consent_label: Optional[str] # label of the consent branch (e.g. "Approve")
    effects: List[str]           # concrete effect-bearing actions in the consent branch

    def __str__(self) -> str:
        eff = "; ".join(self.effects) if self.effects else "(no effect-bearing step)"
        return (f"Gate {self.gate} — disclosed: {self.disclosed or '—'} → "
                f"consent (»{self.consent_label}«) executes: {eff}")


@dataclass
class RunResult:
    outcome: str                 # "completed" | "loop_bound_reached" | "approval_denied"
    loops: int
    trace: List[str]
    last_verdict: Optional[str]
    accepted_label: Optional[str] = None
    gate_disclosures: List[GateDisclosure] = field(default_factory=list)
    observations: list = field(default_factory=list)   # OracleObservation per oracle call (LH-G-005)
    forwards: List[str] = field(default_factory=list)   # A1: forwarding edges HONORED at runtime (LH-F-012)


# --------------------------------------------------------------------------
# structural helpers
# --------------------------------------------------------------------------
def _contains_tvar(g) -> bool:
    """Does this continuation eventually loop back (reach a recursion variable)?"""
    if isinstance(g, core.TVar):
        return True
    if isinstance(g, core.Comm):
        return _contains_tvar(g.cont) or (g.on_crash is not None and _contains_tvar(g.on_crash))
    if isinstance(g, core.Choice):
        return any(_contains_tvar(b.cont) for b in g.branches)
    if isinstance(g, core.Rec):
        return _contains_tvar(g.body)
    return False


def _pick_branch(choice, verdict):
    """Monitor-verdict-driven branch policy: success → a terminating branch,
    failure (violation/refusal/none) → a looping branch (retry)."""
    if verdict == "ok":
        for b in choice.branches:
            if not _contains_tvar(b.cont):
                return b, "terminating"
        return choice.branches[0], "default"
    for b in choice.branches:
        if _contains_tvar(b.cont):
            return b, "loop"
    return choice.branches[-1], "default"


def _tool_allowed(node, capmap, revoked=None) -> bool:
    """H3 (LH-Q-014) — runtime tool broker: if a step uses a capability, the acting
    role MUST actually carry that tool in the RUNTIME capmap. This is the
    enforcement (interposition), not the static lint: even if the spec declared the tool,
    the broker blocks if the capabilities passed at runtime (e.g.
    an attenuated object) do not contain it.
    LH-Q-008 — REVOCATION: a tool revoked at runtime (in `revoked`, as (role, tool)
    or tool) is likewise denied, even if it is declared."""
    if not node.uses_capability:
        return True
    rev = revoked or set()
    if node.uses_capability in rev or (node.sender, node.uses_capability) in rev:
        return False
    return any(c.tool == node.uses_capability for c in capmap.get(node.sender, ()))


def _branch_effects(branch, capmap) -> List[str]:
    """Concrete effect-bearing actions that the `branch` (consent branch) would execute —
    for the disclosure at the gate (R-N1). Stops at a loop variable (bounded)."""
    out: List[str] = []

    def w(n):
        if isinstance(n, core.Comm):
            if appr.is_irreversible(n, capmap):
                cap = f" uses {n.uses_capability}" if n.uses_capability else ""
                tag = " [irreversible]" if n.irreversible else ""
                out.append(f"{n.sender}→{n.receiver}: {n.label}(){cap}{tag}")
            w(n.cont)
            if n.on_crash is not None:
                w(n.on_crash)
        elif isinstance(n, core.Choice):
            for b in n.branches:
                w(b.cont)
        elif isinstance(n, core.Rec):
            w(n.body)
        # TVar / End: stop

    w(branch.cont)
    return out


def _forward_step(node, produced, trace, forwards) -> Optional[str]:
    """A1 INTERPRETER-ENFORCED FORWARDING (LH-F-012). For each forwarded payload field
    (`f = Src.field`, carried on `core.Field.source`), the source MUST already have been produced
    upstream — the runtime analogue of the calculus's well-formedness side condition "the forward's
    source is already bound" (fstar/Forwarding.fst, `wf`). The runner HONORS the edge (binds
    `dst := src`) instead of letting a fresh/oracle value stand in — closing the "oracle could inject
    an independent value" gap so the running artifact realizes the forwarding the static grade assumes.
    Returns a violation message if a source is unbound, else None."""
    for f in node.fields:
        src = getattr(f, "source", None)
        if src:
            if src not in produced:
                return (f"{node.label}.{f.name} forwards from {src}, but {src} was not produced "
                        f"upstream (forwarding source unbound)")
            forwards.append(f"{node.label}.{f.name} = {src}")
            trace.append(f"  ↳ forward honored: {node.label}.{f.name} := {src}")
    return None


def _decide_approval(disclosure, approve, on_approval) -> bool:
    """C3 + R-N1: the approval decision comes from OUTSIDE (the human) and is bound to the
    **disclosure** (`disclosure`: shown message + concrete effect action).
    Order: callback(disclosure) → explicit --approve → otherwise DEFAULT-DENY. Re-evaluated
    per encounter (no consent carried across loop iterations)."""
    if callable(on_approval):
        return bool(on_approval(disclosure))
    if approve is not None:
        return bool(approve)
    return False  # default-deny


def _pick_approval_branch(node, decision):
    """At the approval gate: on consent ONLY a `consent` branch, on denial ONLY a
    non-consent branch (deny-by-default). If on denial there is no non-consent path,
    it aborts (None) — an effect branch is never entered unprompted."""
    consent = [b for b in node.branches if b.consent]
    nonconsent = [b for b in node.branches if not b.consent]
    if decision:
        cand = consent or list(node.branches)
        return (cand[0], "✅ externally released → consent") if cand else (None, "released, but no consent branch")
    if nonconsent:
        return nonconsent[0], "⛔ no release → deny (default-deny)"
    return None, "⛔ no release and no non-consent path → abort"


# --------------------------------------------------------------------------
# the interpreter
# --------------------------------------------------------------------------
def run_protocol(g, backend, env: Optional[Dict] = None, max_loops: int = 5,
                 question: str = "", approve: Optional[bool] = None,
                 on_approval=None, caps: Optional[Dict] = None, revoked=None,
                 dispatch=None) -> RunResult:
    """Walk the verified-shape global type and execute it.

    `dispatch` (the conductor, `casl.conductor`): when set, effect-bearing steps route their capability
    check through the broker process (the reference monitor) via `dispatch.effect(node) -> (ok, reason)`,
    instead of the in-process `_tool_allowed`. `dispatch=None` ⇒ this function is byte-for-byte the proven
    single-file interpreter (see docs/conductor.md §3: the broker is the access monitor, the conductor the
    contract monitor)."""
    env = dict(env or {})
    capmap = caps if caps is not None else core.AGENT_CAPS
    revoked = set(revoked or ())
    trace: List[str] = []
    disclosures: List[GateDisclosure] = []
    observations: list = []          # LH-G-005: structured prompt→response capture per oracle call
    forwards: List[str] = []         # A1: forwarding edges honored at runtime
    produced: set = set()            # A1: qualified payload fields produced so far ("Label.field")
    rec_env: Dict[str, object] = {}
    loops = 0
    last_verdict: Optional[str] = None
    last_msg: str = ""           # most recently disclosed (non-oracle) message, for the gate
    accepted_label: Optional[str] = None
    node = g

    while True:
        if isinstance(node, core.End):
            trace.append("• end")
            return RunResult("completed", loops, trace, last_verdict, accepted_label,
                             disclosures, observations, forwards)

        if isinstance(node, core.Rec):
            rec_env[node.var] = node
            node = node.body
            continue

        if isinstance(node, core.TVar):
            loops += 1
            if loops > max_loops:
                trace.append(f"↺ {node.var}: loop bound {max_loops} reached — abort")
                return RunResult("loop_bound_reached", loops, trace, last_verdict, accepted_label, disclosures, observations)
            trace.append(f"↺ {node.var} (iteration {loops})")
            node = rec_env[node.var].body
            continue

        if isinstance(node, core.Comm):
            # H3 + LH-Q-008: the capability broker interposes BEFORE execution — an undeclared OR
            # revoked tool ⇒ stop. With a broker `dispatch` wired (the conductor), the check crosses the
            # broker PROCESS (the one reference monitor, complete mediation); otherwise it is the
            # in-process check. `dispatch=None` ⇒ this branch is the proven single-file behavior.
            if dispatch is not None and node.uses_capability:
                ok, why = dispatch.effect(node)
                if not ok:
                    trace.append(f"⛔ Broker: {node.sender} does not carry »{node.uses_capability}« "
                                 f"({why or 'denied'}) — step {node.label} denied")
                    return RunResult("tool_denied", loops, trace, last_verdict, accepted_label,
                                     disclosures, observations, forwards)
                grant = (f"  ↳ broker granted »{node.uses_capability}« to {node.sender} "
                         f"for {node.label}")
                if why:                                  # CEP-0078: which provider served/was delegated to
                    grant += f" — {why}"
                trace.append(grant)
            elif not _tool_allowed(node, capmap, revoked):
                why = ("revoked" if (node.uses_capability in revoked
                       or (node.sender, node.uses_capability) in revoked)
                       else "not in runtime capabilities")
                trace.append(f"⛔ Tool broker: {node.sender} does not carry »{node.uses_capability}« "
                             f"({why}) — step {node.label} denied")
                return RunResult("tool_denied", loops, trace, last_verdict, accepted_label, disclosures, observations)
            # A1: enforce forwarding BEFORE production — a forwarded field's source must be bound.
            fv = _forward_step(node, produced, trace, forwards)
            if fv is not None:
                trace.append(f"⛔ forwarding: {fv}")
                return RunResult("forward_violation", loops, trace, last_verdict, accepted_label,
                                 disclosures, observations, forwards)
            if node.from_oracle:
                last_verdict = _oracle_step(node, backend, env, question, trace, observations)
            else:
                msg = f"{node.sender}→{node.receiver}: {node.label}({core.fields_str(node.fields)})"
                last_msg = msg
                trace.append(f"• {msg}")
            for f in node.fields:                       # A1: this site's payload fields are now produced
                produced.add(f"{node.label}.{f.name}")
            node = node.cont
            continue

        if isinstance(node, core.Choice):
            if node.approval:
                # C3 + R-N1: human at the gate, decision bound to the DISCLOSURE.
                consent_b = next((b for b in node.branches if b.consent), None)
                disc = GateDisclosure(
                    gate=f"{node.sender}→{node.receiver}",
                    disclosed=last_msg,
                    consent_label=consent_b.label if consent_b else None,
                    effects=_branch_effects(consent_b, capmap) if consent_b else [],
                )
                disclosures.append(disc)
                trace.append(f"• {disc.gate}: ⊗ approval gate — {disc}")
                decision = _decide_approval(disc, approve, on_approval)
                br, why = _pick_approval_branch(node, decision)
                if br is None:
                    trace.append(f"    {why}")
                    return RunResult("approval_denied", loops, trace, last_verdict, accepted_label, disclosures, observations)
                trace.append(f"    {why} → »{br.label}«")
            else:
                br, why = _pick_branch(node, last_verdict)
                trace.append(f"• {node.sender}→{node.receiver}: ⊕ chooses »{br.label}« "
                             f"({why}; verdict={last_verdict})")
            if not _contains_tvar(br.cont):
                accepted_label = br.label   # terminating branch → the "accepted" outcome
            node = br.cont
            continue

        raise TypeError(f"unknown node: {type(node)}")


def _record(observations, step, prompt, response, cost, measured, refused, verdict):
    """Append a structured OracleObservation (LH-G-005), if capture is active."""
    if observations is None:
        return
    import datetime as _dt
    from casl.observability import OracleObservation
    observations.append(OracleObservation(
        step=step, prompt=prompt, response=response, cost=cost, measured_cost=measured,
        refused=refused, verdict=verdict, ts=_dt.datetime.now().isoformat(timespec="seconds")))


def _oracle_step(node, backend, env, question, trace, observations=None) -> str:
    """Ask the oracle for the payload, then monitor the step's contract. Captures a structured
    OracleObservation (LH-G-005) — verbatim prompt→response + cost + verdict — for human review."""
    contract = node.contract
    if contract is not None and contract.relation and contract.relation[0] == "le":
        _, lhs, rhs = contract.relation
        bound = env.get(rhs, 0)
    else:
        lhs, rhs, bound = "cost", "budget", env.get("budget", 0)

    out = backend.generate(question or env.get("question", ""), bound)
    # H4 (LH-Q-015): check against the out-of-band measurement; the oracle claim is only a claim.
    measured = out.measured_cost if out.measured_cost is not None else out.cost
    produced = measured if measured is not None else (bound + 1)
    claim = out.cost
    misreport = (claim is not None and measured is not None and claim != measured)
    answer = (out.answer or "").strip()
    snippet = (answer[:40] + "…") if len(answer) > 40 else answer
    step = f"{node.sender}→{node.receiver}:{node.label}"
    prompt = getattr(out, "prompt", "") or f"{question or env.get('question', '')}  [{rhs} <= {bound}]"
    response = out.raw or out.answer

    if contract is not None:
        menv = {lhs: produced, rhs: bound, "refused": out.refused}
        outcome = res.synth_refusal_monitor(contract, node.sender)(menv)
        verdict, blame = outcome.kind, outcome.blame
        tag = verdict.upper() + (f" → blame {blame}" if blame else "")
        misn = f" [claim {claim}≠measured {measured}: misreport]" if misreport else ""
        trace.append(f"• {node.sender}→{node.receiver}: {node.label} ⟨oracle⟩ "
                     f"{lhs}={produced} (measured; {rhs}={bound}) → {tag}{misn}"
                     + (f"   answer={snippet!r}" if snippet else ""))
        _record(observations, step, prompt, response, claim, measured, out.refused, verdict)
        return verdict

    trace.append(f"• {node.sender}→{node.receiver}: {node.label} ⟨oracle⟩ (no contract) → OK"
                 + (f"   answer={snippet!r}" if snippet else ""))
    _record(observations, step, prompt, response, claim, measured, out.refused, "ok")
    return "ok"


def format_run(name: str, r: RunResult) -> str:
    lines = ["=" * 72, f"CASL run — {name}", "=" * 72]
    lines += [f"  {e}" for e in r.trace]
    lines.append("-" * 72)
    if r.outcome == "completed":
        lines.append(f"  Result: ✓ COMPLETED after {r.loops} loop(s) (final verdict: {r.last_verdict})")
    elif r.outcome == "approval_denied":
        lines.append("  Result: ⊗ DENIED AT THE APPROVAL GATE (default-deny) — no "
                     "effect branch entered; no release granted.")
    elif r.outcome == "tool_denied":
        lines.append("  Result: ⛔ DENIED BY THE TOOL BROKER — a step used a tool not "
                     "carried at runtime (least-privilege enforcement).")
    elif r.outcome == "forward_violation":
        lines.append("  Result: ⛔ FORWARDING VIOLATION — a forwarded field's source was not "
                     "produced upstream (A1 interpreter-enforced forwarding).")
    else:
        lines.append(f"  Result: ⟳ LOOP BOUND reached ({r.loops}) — the oracle did not "
                     f"satisfy the contract (final verdict: {r.last_verdict})")
    if r.forwards:
        lines.append(f"  forwards honored ({len(r.forwards)}): " + "; ".join(r.forwards))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# standalone demo (mock; no network)
# --------------------------------------------------------------------------
def demo() -> dict:
    from casl import oracle
    out = {}
    for scen in ("ok", "retry_then_ok", "overspend"):
        r = run_protocol(core.G_OK, oracle.MockBackend(scen),
                         {"budget": 100, "question": "What is 2 + 2?"}, max_loops=5)
        print(format_run(f"G_OK [mock:{scen}]", r))
        print()
        out[scen] = (r.outcome, r.loops)
    return out


if __name__ == "__main__":
    demo()
