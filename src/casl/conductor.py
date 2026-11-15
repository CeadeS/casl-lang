"""casl.conductor — the project-aware conductor: `casl run --project` drives a VERIFIED choreography
END-TO-END, dispatching every model/tool call through the broker (the reference monitor).

Layer 3 (Execution). The verified `.casl` IS the state machine — determinism comes from the F* proof,
not from a runtime replay-guard (docs/conductor.md §2). The interpreter (`casl.run.run_protocol`) is the
deterministic conductor; the broker is the access/capability monitor; the conductor keeps verdict +
approval authority. See docs/conductor.md and docs/architecture.md §"Layer 3 — Execution".

Two thin seams onto the broker — the proven interpreter is untouched on its default path:
  · BrokerBackend  — ORACLE sites: `backend.generate()` → `client.oracle()` (capability-gated, H4 cost).
  · BrokerDispatch — EFFECT sites: `dispatch.effect(node)` → `client.effect()` (deny-by-default tools).
Plus project awareness: the manifest + the typed-seam bindings (site ⟶ artifact) from `casl.seam`.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from casl import activity as _activity, capability as _cap, project, run as _run, seam
from casl.oracle import OracleResult


class BrokerBackend:
    """ORACLE seam: satisfies `backend.generate(question, budget)` by asking the broker. The broker gates
    provider capability + MEASURES cost (H4); the conductor's contract monitor (inside `run_protocol`) then
    decides the verdict/branch from the measured cost. Two layers, two policies — not double-monitoring."""

    def __init__(self, client, provider: Optional[str] = None, site: str = "oracle"):
        self.client, self.provider, self.site = client, provider, site

    def generate(self, question: str, budget: int) -> OracleResult:
        kw = {"provider": self.provider} if self.provider else {}
        r = self.client.oracle(site=self.site, question=question, budget=budget, **kw)
        return OracleResult(
            answer=r.get("answer", "") or "",
            cost=r.get("cost"),
            refused=(r.get("verdict") == "refusal"),
            raw=r.get("reason") or r.get("raw") or r.get("answer") or "",
            measured_cost=r.get("measured_cost"),
        )


class BrokerDispatch:
    """EFFECT seam (CEP-0078 runtime side): routes a step's capability through the broker, AND through its
    bound single-purpose provider. The run-time twin of the gate-time no-ambient-authority check: a
    `confined` artifact realizing an effect site may act only by delegating to a granted provider — if the
    capability has no provider, the conductor refuses to dispatch it (deny-by-default), before the broker is
    even asked. Non-confined / provider-less projects keep the prior behavior.

    `providers` = {capability: provider artifact name}; `confined` = {artifact names with no ambient I/O};
    `sites` = {site label: the artifact realizing it} for the protocol being conducted.
    """

    def __init__(self, client, providers=None, confined=None, sites=None):
        self.client = client
        self.providers = dict(providers or {})
        self.confined = set(confined or ())
        self.sites = dict(sites or {})

    def effect(self, node) -> Tuple[bool, str]:
        cap = node.uses_capability
        actor = self.sites.get(node.label)            # the artifact realizing this effect site
        provider = self.providers.get(cap)            # the signed single-purpose provider for `cap`
        # runtime no-ambient-authority: a confined actor with no provider for `cap` cannot act.
        if actor in self.confined and provider is None:
            return (False, f"confined artifact {actor!r} has no provider for »{cap}« — "
                           f"no ambient authority (CEP-0078)")
        r = self.client.effect(site=node.label, tool=cap)
        ok = bool(r.get("allowed"))
        if not ok:
            return False, str(r.get("reason", "") or r.get("note", ""))
        if provider and actor in self.confined and provider != actor:
            return True, f"delegated to provider {provider!r}"   # confined caller → provider
        if provider:
            return True, f"served by provider {provider!r}"      # the site's own single-purpose provider
        return True, ""


@dataclass
class ConductorResult:
    protocol: str
    run: _run.RunResult
    site_artifact: Dict[str, str]          # "proto:Label" -> artifact name
    summary: str


def _load_protocols(project_dir: str) -> Dict[str, object]:
    """{name: parsed proto} for every casl/*.casl (full proto: gtype + caps + name)."""
    from casl import surface
    out: Dict[str, object] = {}
    for p in sorted(glob.glob(os.path.join(project_dir, "casl", "*.casl"))):
        try:
            proto = surface.parse_file(p)
            out[proto.name] = proto
        except Exception:
            pass
    return out


def _granted_tools(proto) -> set:
    """The tools the choreography DECLARES (the agent caps) — what the broker may grant for this run."""
    caps = getattr(proto, "caps", None) or {}
    return {c.tool for v in caps.values() for c in v}


class Conductor:
    """Project-aware conductor. Loads the manifest + choreographies + typed-seam bindings; `run()` gates
    the hull, stands up the broker, and conducts the verified choreography through it."""

    def __init__(self, project_dir: str):
        self.dir = project_dir
        self.manifest = project.load_manifest(os.path.join(project_dir, "casl.toml"))
        self.protocols = _load_protocols(project_dir)
        ok, viol, binds = seam.check_seam(self.manifest, project_dir)
        self.seam_ok, self.seam_violations, self.bindings = ok, viol, binds
        self._site_artifact = {(p, l): name for name, (p, l, _n) in binds.items()}
        self._by_name = {a.name: a for a in self.manifest.artifacts}

    def run(self, protocol: Optional[str] = None, provider: Optional[str] = None,
            client=None, env: Optional[Dict] = None, scenario: str = "ok",
            approve: Optional[bool] = None, on_approval=None, max_loops: int = 5,
            question: str = "", oracle_backend=None) -> ConductorResult:
        proto = self._pick(protocol)
        # GATE the hull FIRST (prove, then execute) — the conductor never runs an inadmissible spec.
        from casl.check import check_protocol
        rep = check_protocol(proto)
        if not rep.get("accepted"):
            rr = _run.RunResult("not_admissible", 0,
                                [f"⛔ {proto.name}: hull not admissible (MUST violation) — run aborted"], None)
            return ConductorResult(proto.name, rr, self._sites_for(proto.name), self._summary(proto, rr))
        # Broker: in-process unless the caller supplies a (subprocess) client. The model + tools live ONLY
        # in the broker; the conductor reaches them only by asking it.
        self._oracle_note = None
        if client is None:
            from casl.broker import Broker
            from casl.client import Client
            caps = ["oracle", "effect"] + ([f"llm:{provider}"] if provider else [])
            obk, self._oracle_note = self._oracle_backend(proto, scenario, oracle_backend)
            broker = Broker(backend=obk, granted_tools=_granted_tools(proto))
            client = Client(broker=broker, capabilities=caps)
        backend = BrokerBackend(client, provider)
        # CEP-0078 runtime side: resolve each capability to its signed single-purpose provider, and mark
        # which artifacts are confined, so the dispatch routes (and, for confined callers, refuses ambient).
        providers = {c: arts[0].name for c, arts in _cap.provider_index(self.manifest).items()}
        confined = {a.name for a in self.manifest.artifacts if getattr(a, "confined", False)}
        sites = {l: name for (p, l), name in self._site_artifact.items() if p == proto.name}
        dispatch = BrokerDispatch(client, providers=providers, confined=confined, sites=sites)
        env = dict(env or {})
        env.setdefault("budget", 100)
        try:
            rr = _run.run_protocol(proto.gtype, backend, env, dispatch=dispatch, max_loops=max_loops,
                                   question=question or env.get("question", ""),
                                   approve=approve, on_approval=on_approval,
                                   caps=getattr(proto, "caps", None))
        except Exception as e:  # broker denial (e.g. undeclared provider, -32011) or transport error
            rr = _run.RunResult("broker_denied", 0,
                                [f"⛔ broker denied / runtime error: {e!r}"], None)
        return ConductorResult(proto.name, rr, self._sites_for(proto.name), self._summary(proto, rr))

    # -- helpers ---------------------------------------------------------------
    def _oracle_backend(self, proto, scenario, override=None):
        """Pick the broker's MODEL backend. If an oracle site of `proto` is bound (typed seam) to an
        EXECUTABLE artifact (kind `oracle` with a runnable `body`), the project's own program realizes the
        oracle as a MONITORED activity (docs/analyses/activity-executor.md, casl.activity); otherwise the
        deterministic mock (offline default). An injected `override` backend wins (tests / a live provider).
        Coarse: the FIRST executable-bound oracle site wins; per-site routing is a documented refinement."""
        from casl import oracle as _oracle
        if override is not None:
            return override, f"{type(override).__name__} (injected)"
        for (p, label), name in sorted(self._site_artifact.items()):
            if p != proto.name:
                continue
            site = seam.find_site(proto.gtype, label)
            if site is None or not getattr(site, "from_oracle", False):
                continue
            art = self._by_name.get(name)
            if art is None or not getattr(art, "body", None):
                continue
            body_path = os.path.join(self.dir, art.body)
            if not os.path.exists(body_path):
                continue
            try:
                cmd = _activity.command_for(body_path)
            except ValueError:
                continue
            return (_activity.SubprocessActivity(command=cmd, cwd=self.dir, name=art.name,
                                                 confined=getattr(art, "confined", False)),
                    f"activity «{art.name}» realizes {p}:{label} — {' '.join(cmd)}")
        return _oracle.MockBackend(scenario), None

    def _pick(self, protocol):
        if protocol:
            if protocol not in self.protocols:
                raise KeyError(f"no protocol {protocol!r} in {self.dir}/casl "
                               f"(have: {sorted(self.protocols)})")
            return self.protocols[protocol]
        if len(self.protocols) == 1:
            return next(iter(self.protocols.values()))
        raise ValueError(f"project has {len(self.protocols)} protocols; pass protocol= "
                         f"(have: {sorted(self.protocols)})")

    def _sites_for(self, proto_name: str) -> Dict[str, str]:
        return {f"{p}:{l}": name for (p, l), name in self._site_artifact.items() if p == proto_name}

    def _summary(self, proto, rr) -> str:
        lines = [f"conductor: {self.manifest.name} ▸ protocol {proto.name}",
                 "  broker-mediated: oracle + effect (one reference monitor; complete mediation)"]
        if getattr(self, "_oracle_note", None):
            lines.append(f"  oracle backend: {self._oracle_note}")
        sites = self._sites_for(proto.name)
        if sites:
            lines.append(f"  bound sites ({len(sites)}):")
            for site, name in sorted(sites.items()):
                a = self._by_name[name]
                lines.append(f"    • {site} ⟶ {name} (kind={a.kind}, grade={a.grade}, floor={a.floor()})")
        provs = _cap.provider_index(self.manifest)
        if provs:
            lines.append("  capability providers: " +
                         ", ".join(f"»{c}«⟵{arts[0].name}" for c, arts in sorted(provs.items())))
        confined = sorted(a.name for a in self.manifest.artifacts if getattr(a, "confined", False))
        if confined:
            lines.append(f"  confined (no ambient I/O): {', '.join(confined)}")
        if self.seam_violations:
            lines.append(f"  seam violations ({len(self.seam_violations)}):")
            lines += [f"    ✗ {v}" for v in self.seam_violations]
        lines.append(f"  outcome: {rr.outcome} (loops={rr.loops}, final verdict={rr.last_verdict})")
        if rr.forwards:
            lines.append(f"  forwards honored: {len(rr.forwards)}")
        return "\n".join(lines)


def format_conductor(cr: ConductorResult) -> str:
    return _run.format_run(f"{cr.protocol} [conductor]", cr.run) + "\n" + cr.summary
