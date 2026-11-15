"""casl.broker — the capability broker / reference monitor (P1; see docs/architecture.md §3,
docs/broker-protocol.md).

This is the ONE trusted chokepoint: every model/tool access from any artifact, in any language, goes
through it. It is the runtime form of "monitor the oracle" + "no ambient authority": an artifact holds no
model endpoint and no tool — it can only *ask* the broker, which decides. The broker meets the
reference-monitor bar (Anderson: always-invoked, tamperproof, small enough to verify) and is an execution
monitor (Schneider): it enforces the safety-shaped policy at the call (capability present, contract holds)
and records every crossing.

What this module is, and is NOT (P1 scope):
  · IS: the protocol dispatch (`initialize`/`oracle`/`effect`/`shutdown`), the monitored oracle boundary
    (reusing `oracle.oracle_step` + the synthesized contract monitor), deny-by-default capability checks,
    and observation capture. Transport-agnostic `handle()` + a newline-delimited JSON-RPC stdio loop.
  · IS NOT (next increments): real tool dispatch + the human approval gate for irreversible effects (P2),
    and the *confinement* (OS sandbox / WASM) that makes the broker the artifact's ONLY reachable channel —
    without it, "go through the broker" is convention, not yet an enforced guarantee (docs/architecture.md §3).
"""
from __future__ import annotations

import datetime
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from casl import core
from casl import oracle as _oracle

PROTOCOL_VERSION = "0.1"
SERVER_CAPABILITIES = ("oracle", "effect", "consent", "resolve")   # the methods this broker offers


class _BrokerError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(msg)
        self.code = code


def _err(mid, code: int, msg: str) -> dict:
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": msg}}


@dataclass
class Broker:
    """The reference monitor. ONLY the broker holds the model connector and the tool grants; an artifact
    (via a thin client binding) can do nothing but send it requests."""
    backend: Any = None                                  # the model connector (Mock/Ollama) — broker-only
    granted_tools: set = field(default_factory=set)      # tool capabilities artifacts may invoke
    contracts: Dict[str, core.Contract] = field(default_factory=dict)   # per-site oracle contract
    observations: List[Any] = field(default_factory=list)
    declared_caps: set = field(default_factory=set)      # flags the artifact declared at initialize (P1.5)
    irreversible_caps: set = field(default_factory=set)  # caps whose effect REQUIRES a fresh consent token (A)
    transports: Dict[str, Any] = field(default_factory=dict)  # (b) cap -> egress.MediatedCapability the broker PERFORMS
    _consents: Dict[str, dict] = field(default_factory=dict)  # token -> {cap, site, request, used} (one-shot, broker-minted)
    # SIGNED approvals (casl.approval): a non-empty trust store switches `consent` to signed-only — an
    # `approved: true` assertion then mints NOTHING (closes agent self-approval).
    approvers: Dict[str, str] = field(default_factory=dict)        # pubkey-hex -> class ("human"|"personal")
    program_hash: Optional[str] = None                             # the active program version approvals must name
    approval_class: Dict[str, str] = field(default_factory=dict)   # cap -> minimum approver class (default "human")
    clock: Any = None                                              # () -> unix seconds; None ⇒ time.time (test seam)
    _nonces: set = field(default_factory=set)                      # used approval nonces (durable when a journal is set)
    # RUN JOURNAL (casl.journal): approvals, effect intents and results, hash-chained. With a journal the
    # replay protection and the "unknown outcome" state survive a broker restart.
    journal: Any = None
    _effects: Dict[str, str] = field(default_factory=dict)         # request digest -> latest outcome of an irreversible effect

    def __post_init__(self):
        if self.journal is not None:
            nonces, effects = self.journal.replay()
            self._nonces |= nonces
            self._effects.update(effects)

    def _now(self) -> int:
        import time
        return int(self.clock() if self.clock else time.time())

    def _log(self, kind: str, body: dict) -> None:
        """Append to the run journal. A failed append RAISES — callers log BEFORE acting, so an effect that
        cannot be journaled is not performed (fail closed)."""
        if self.journal is not None:
            self.journal.append(kind, body, self._now())
    _initialized: bool = False

    # -- JSON-RPC dispatch (transport-agnostic) --------------------------------
    def handle(self, req: dict) -> dict:
        mid = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        try:
            if method == "initialize":
                result = self._initialize(params)
            elif method == "oracle":
                result = self._oracle(params)
            elif method == "effect":
                result = self._effect(params)
            elif method == "consent":
                result = self._consent(params)
            elif method == "resolve":
                result = self._resolve(params)
            elif method == "shutdown":
                result = {"ok": True}
            else:
                return _err(mid, -32601, f"method not found: {method!r}")
            return {"jsonrpc": "2.0", "id": mid, "result": result}
        except _BrokerError as e:
            return _err(mid, e.code, str(e))
        except Exception as e:                           # never crash the broker on a bad request
            return _err(mid, -32603, f"internal error: {e!r}")

    def _initialize(self, params: dict) -> dict:
        # capability negotiation (LSP/MCP style): advertise ours; unknown client capabilities are ignored.
        # The artifact's DECLARED capability flags (`llm:claude`, `websocket`, `tool:*`) are recorded — they
        # drive grade + monitoring and gate provider use (P1.5; engineering-plan §0.5).
        if not self._initialized:
            self._log("run", {"program": self.program_hash, "impl": "python", "protocol": PROTOCOL_VERSION})
        self._initialized = True
        self.declared_caps = {str(c) for c in (params.get("capabilities") or [])}
        return {"server": "casl-broker", "version": PROTOCOL_VERSION,
                "capabilities": list(SERVER_CAPABILITIES)}

    def _oracle(self, params: dict) -> dict:
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        site = str(params.get("site", "?"))
        question = str(params.get("question", ""))
        budget = int(params.get("budget", 0))
        producer = str(params.get("producer", "A"))
        provider = params.get("provider")
        if provider:
            cap = f"llm:{provider}"
            if cap not in self.declared_caps:
                raise _BrokerError(-32011, f"artifact did not declare capability {cap!r} — "
                                           f"flag it to use provider {provider!r}")
        if self.backend is None:
            # the model lives ONLY in the broker — a client cannot conjure one
            raise _BrokerError(-32010, "no model connector configured in the broker")
        contract = self.contracts.get(site, core.C_COST_LE_BUDGET)
        sr = _oracle.oracle_step(self.backend, question, budget, producer=producer, contract=contract)
        self._record(site, question, sr)
        return {"verdict": sr.kind, "answer": sr.answer, "cost": sr.cost,
                "measured_cost": sr.measured_cost, "blame": sr.blame,
                "reason": sr.reason, "branch": sr.branch}

    def _effect(self, params: dict) -> dict:
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        site = str(params.get("site", "?"))
        tool = str(params.get("tool", ""))
        if tool not in self.granted_tools:               # deny-by-default (fail-safe)
            return {"allowed": False, "tool": tool, "site": site,
                    "reason": f"capability {tool!r} not granted for site {site} (deny-by-default)"}
        # (b) MEDIATED egress: for a capability the broker PERFORMS, the destination policy runs FIRST —
        # before consent is consumed and before any connect (SSRF gate; a denied destination burns no token).
        irreversible = tool in self.irreversible_caps
        mc = self.transports.get(tool)
        spec = digest = None
        if mc is not None:
            from casl import egress as _eg
            spec = _eg.RequestSpec.from_obj(params.get("request"))
            digest = spec.digest()
            ok, reason = mc.policy.check(spec.url)
            if not ok:
                return {"allowed": False, "tool": tool, "site": site, "reason": f"destination denied: {reason}"}
            held = mc.conflicting_header(spec)
            if held is not None:
                return {"allowed": False, "tool": tool, "site": site,
                        "reason": f"request denied: header {held!r} is held by the broker and must not be "
                                  f"supplied by the caller"}
            if irreversible and self._effects.get(digest) == "unknown":
                # NO BLIND REPEAT: an earlier attempt of this exact request may have reached the target.
                return {"allowed": False, "tool": tool, "site": site, "outcome": "unresolved",
                        "reason": "an earlier attempt of this exact request has an unknown outcome — "
                                  "clarify it at the target system and `resolve` it before retrying"}
        # (A) approval-binding: an IRREVERSIBLE capability needs a fresh, broker-minted consent token bound
        # to this (cap, site) — minted only via `consent` after the human approval gate. No / already-used /
        # mismatched token ⇒ DENY. A forgotten approval gate therefore FAILS CLOSED, never performs the effect.
        nonce = None
        if irreversible:
            token = params.get("approval")
            rec = self._consents.get(token) if token else None
            if rec is None or rec.get("used") or rec.get("cap") != tool or rec.get("site") != site:
                return {"allowed": False, "tool": tool, "site": site,
                        "reason": f"irreversible effect {tool!r} at {site} needs a fresh matching approval "
                                  f"token (deny-by-default) — obtain consent at the approval gate first"}
            if rec.get("request") is not None:            # request-bound consent: must match THIS request
                from casl import egress as _eg
                if _eg.RequestSpec.from_obj(params.get("request")).digest() != rec["request"]:
                    return {"allowed": False, "tool": tool, "site": site,
                            "reason": "approval token does not match this request (request-bound consent) — "
                                      "the human approved a different request"}
            nonce = rec.get("nonce")
            if mc is None:
                self._log("grant", {"cap": tool, "site": site, "request": rec.get("request"), "nonce": nonce})
            else:
                # INTENT before the send, durably: if the broker dies after this line, the journal still says
                # the request may have gone out (replay reads an intent without a result as "unknown").
                self._log("intent", {"effect": digest, "cap": tool, "site": site, "nonce": nonce})
                self._effects[digest] = "unknown"
            rec["used"] = True                            # one-shot: a token authorizes exactly ONE attempt
        if mc is None:
            return {"allowed": True, "tool": tool, "site": site,
                    "note": "granted" + (" (consent consumed)" if irreversible else "")}
        from casl import egress as _eg
        status = body = None
        try:
            resp = mc.transport.send(mc.wire(spec))      # broker-held credentials are added on the wire only
            status, body = resp.status, resp.body
            outcome = _eg.classify(status)
        except _eg.TransportError as e:
            outcome = e.kind
        except Exception:                                 # a transport that fails in an unforeseen way
            outcome = "unknown"                           # proves nothing about the request's fate
        if irreversible:
            import hashlib
            self._effects[digest] = outcome
            self._log("result", {"effect": digest, "outcome": outcome, "status": status,
                                 "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body is not None else None})
        out = {"allowed": True, "performed": outcome == "performed", "tool": tool, "site": site,
               "outcome": outcome, "effect": digest}
        if status is not None:
            out.update({"status": status, "body": body, "receipt": {"request": digest, "status": status}})
        return out

    def _resolve(self, params: dict) -> dict:
        """Record the clarified outcome of an effect whose outcome was unknown. Whether the target acted is a
        fact of the TARGET system (the provider looks it up there); this only records the finding, so the
        journal stays complete and a retry — which needs a NEW approval anyway — is no longer blocked."""
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        effect = str(params.get("effect", ""))
        outcome = str(params.get("outcome", ""))
        if outcome not in ("performed", "not_performed"):
            return {"resolved": False, "reason": "outcome must be 'performed' or 'not_performed'"}
        if self._effects.get(effect) != "unknown":
            return {"resolved": False, "reason": "no effect with an unknown outcome under this id"}
        self._log("resolve", {"effect": effect, "outcome": outcome, "note": str(params.get("note", ""))})
        self._effects[effect] = outcome
        return {"resolved": True, "effect": effect, "outcome": outcome}

    def _consent(self, params: dict) -> dict:
        """Mint a ONE-SHOT consent token bound to (cap, site) — the runtime form of the approval gate
        dominating an irreversible effect. Minted IFF the human approved the disclosed effect; broker-minted
        (unforgeable) and single-use, so `_effect` can require it for an irreversible cap. Without it the
        effect is denied (deny-by-default). Two modes: with a trust store (`approvers`) only a SIGNED approval
        (casl.approval) mints a token — the human is bound to the broker directly; without one, `approved`
        is the UI's assertion that a human consented (legacy; adequate only when no agent sits in the
        calling path). (A) closes the *forgotten-gate* class — an effect on a path that never sought consent."""
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        import secrets
        cap = str(params.get("tool", ""))
        site = str(params.get("site", "?"))
        if self.approvers:
            # SIGNED mode: the human is bound by a signature the calling agent cannot produce. The token is
            # ALWAYS request-bound to the digest the signer committed to (never to a caller-supplied request).
            from casl import approval as _ap
            env = params.get("signed")
            ok, code, reason, payload, klass = _ap.verify_signed(
                env, approvers=self.approvers, program=self.program_hash, cap=cap, site=site,
                now=self._now(), seen_nonces=self._nonces, required=self.approval_class.get(cap, "human"))
            if not ok:
                return {"granted": False, "code": code, "reason": reason}
            # journal the verified approval (payload + signature ⇒ re-verifiable later) BEFORE minting
            self._log("approval", {"nonce": payload["nonce"], "cap": cap, "site": site, "request": payload["request"],
                                   "program": payload["program"], "exp": payload["exp"], "key": env["key"].lower(),
                                   "class": klass, "payload": env["payload"], "sig": env["sig"]})
            token = secrets.token_hex(16)
            self._consents[token] = {"cap": cap, "site": site, "request": payload["request"],
                                     "nonce": payload["nonce"], "used": False}
            return {"granted": True, "token": token, "cap": cap, "site": site, "code": "ok", "class": klass}
        if not bool(params.get("approved", False)):
            return {"granted": False, "reason": "approval withheld at the gate (deny-by-default)"}
        token = secrets.token_hex(16)
        # (b) optionally REQUEST-BIND the consent: when the gate discloses a concrete request, the token is
        # valid only for that exact request digest (red-team Crit-2). Absent ⇒ legacy (cap, site) binding.
        req = params.get("request")
        digest = None
        if req is not None:
            from casl import egress as _eg
            digest = _eg.RequestSpec.from_obj(req).digest()
        self._consents[token] = {"cap": cap, "site": site, "request": digest, "used": False}
        return {"granted": True, "token": token, "cap": cap, "site": site}

    def _record(self, site: str, question: str, sr) -> None:
        try:
            from casl.observability import OracleObservation
            self.observations.append(OracleObservation(
                step=site, prompt=question, response=sr.answer, cost=sr.cost,
                measured_cost=sr.measured_cost, refused=(sr.kind == "refusal"),
                verdict=sr.kind, ts=datetime.datetime.now().isoformat(timespec="seconds")))
        except Exception:
            pass

    # -- stdio transport (newline-delimited JSON-RPC, MCP/LSP style) -----------
    def serve_stdio(self, instream=None, outstream=None) -> None:
        instream = instream or sys.stdin
        outstream = outstream or sys.stdout
        for line in instream:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                outstream.write(json.dumps(_err(None, -32700, "parse error")) + "\n")
                outstream.flush()
                continue
            resp = self.handle(req)
            outstream.write(json.dumps(resp) + "\n")
            outstream.flush()
            if req.get("method") == "shutdown":
                break


if __name__ == "__main__":
    # A runnable broker for the subprocess transport: `python -m casl.broker`.
    # Offline by default (MockBackend); a live model is the broker's config, never the client's.
    import os
    scen = os.environ.get("CASL_BROKER_SCENARIO", "ok")
    Broker(backend=_oracle.MockBackend(scen)).serve_stdio()
