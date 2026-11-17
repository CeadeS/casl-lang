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
SERVER_CAPABILITIES = ("oracle", "effect", "consent", "resolve", "access", "grant", "revoke")   # the methods this broker offers


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
    # RUN JOURNAL (casl.journal): approvals, effect intents and results, hash-chained. With a journal the
    # replay protection and the "unknown outcome" state survive a restart and hold across concurrent broker
    # processes; without one an in-memory ledger gives the same decisions for this process only.
    journal: Any = None
    # CONTEXT ACCESS (docs/context-grants.md): cap -> the data scope the checked program DECLARES for it.
    # A capability listed here is performed only through `access` (grant-checked), never through `effect`.
    contexts: Dict[str, dict] = field(default_factory=dict)
    _ledger: Any = None
    _initialized: bool = False

    def __post_init__(self):
        from casl import journal as _j
        self._ledger = self.journal if self.journal is not None else _j.MemoryLedger()

    def _now(self) -> int:
        import time
        return int(self.clock() if self.clock else time.time())

    def _log(self, kind: str, body: dict) -> int:
        """Append to the ledger. A failed append RAISES — callers log BEFORE acting, so an effect that
        cannot be journaled is not performed (fail closed)."""
        return self._ledger.append(kind, body, self._now())

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
            elif method == "access":
                result = self._access(params)
            elif method == "grant":
                result = self._grant(params)
            elif method == "revoke":
                result = self._revoke(params)
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
        if tool in self.contexts:
            # a context capability reads or discloses protected data: it runs only through `access`, where
            # the grant is checked — never through the plain effect path (no bypass of the workflow step)
            return {"allowed": False, "tool": tool, "site": site,
                    "reason": f"capability {tool!r} has a context scope — it is performed through `access` only"}
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
            blocking = self._ledger.state().blocking(mc.account, digest) if irreversible else None
            if blocking is not None:
                # NO BLIND REPEAT: an earlier attempt of this exact request, under this account, may have
                # reached the target. (The same request under another account is another resource.)
                return self._unresolved(tool, site, blocking, mc.account)
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
            if "account" in rec and rec["account"] != (mc.account if mc is not None else None):
                # checked AGAIN at execution: the credential the broker would use now must still be the
                # principal the approval named
                return {"allowed": False, "tool": tool, "site": site,
                        "reason": "approval names a different target account than the credential in use"}
            nonce = rec.get("nonce")
            if mc is None:
                self._log("grant", {"cap": tool, "site": site, "request": rec.get("request"), "nonce": nonce})
            else:
                # INTENT before the send, durably, and as a RESERVATION: the journal re-checks under its write
                # lock that this scope is not in flight and this approval made no attempt yet — so of several
                # broker processes only one proceeds. If the broker dies after this line, the journal still
                # says the request may have gone out (an intent without a result replays as "unknown").
                from casl import journal as _j
                try:
                    attempt = self._ledger.reserve("intent", {"effect": digest, "cap": tool, "site": site,
                                                              "nonce": nonce, "account": mc.account}, self._now())
                except _j.Conflict as c:
                    if c.code == "unresolved":
                        return self._unresolved(tool, site, c.attempt, mc.account)
                    return {"allowed": False, "tool": tool, "site": site,
                            "reason": "this approval was already used for an attempt (one approval, one attempt)"}
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
        out = {"allowed": True, "performed": outcome == "performed", "tool": tool, "site": site,
               "outcome": outcome, "request": digest}
        if irreversible:
            import hashlib
            self._log("result", {"attempt": attempt, "effect": digest, "account": mc.account, "outcome": outcome,
                                 "status": status,
                                 "body_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest() if body is not None else None})
            out["attempt"] = attempt                      # the handle for `resolve`
            if mc.account is not None:
                out["account"] = mc.account
        if status is not None:
            out.update({"status": status, "body": body, "receipt": {"request": digest, "status": status}})
        return out

    def _unresolved(self, tool: str, site: str, attempt, account) -> dict:
        out = {"allowed": False, "tool": tool, "site": site, "outcome": "unresolved", "attempt": attempt,
               "reason": f"attempt {attempt} of this exact request has an unknown outcome or is in flight — "
                         f"clarify it at the target system and `resolve` it before retrying"}
        if account is not None:
            out["account"] = account
        return out

    def _resolve(self, params: dict) -> dict:
        """Record the clarified outcome of an ATTEMPT whose outcome was unknown. Whether the target acted is a
        fact of the TARGET system (the provider looks it up there, under the attempt's account); this records
        the finding, so the journal stays complete and a retry — which needs a NEW approval anyway — is no
        longer blocked. Addressed by attempt id: it cannot land on another account's attempt."""
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        from casl import journal as _j
        attempt, outcome = params.get("attempt"), str(params.get("outcome", ""))
        if outcome not in ("performed", "not_performed"):
            return {"resolved": False, "reason": "outcome must be 'performed' or 'not_performed'"}
        if type(attempt) is not int:
            return {"resolved": False, "reason": "attempt must be the integer id an effect result reported"}
        body = {"attempt": attempt, "outcome": outcome, "note": str(params.get("note", ""))}
        try:
            self._ledger.reserve("resolve", body, self._now())
        except _j.Conflict:
            return {"resolved": False, "reason": "no attempt with an unknown outcome under this id"}
        out = {"resolved": True, "attempt": attempt, "outcome": outcome, "request": body["effect"]}
        if body["account"] is not None:
            out["account"] = body["account"]
        return out

    # -- context access (docs/context-grants.md; casl-lang#7) ---------------------------------------------
    def _verified_grants(self, state) -> list:
        """The grants on record, re-verified against the CURRENT trust store: (payload, chain) pairs.
        Revocation is applied by `decide`, so a revoked grant reads as revoked, not as absent."""
        from casl import context as _cx
        out = []
        for env in state.grants.values():
            ok, _code, g, chain = _cx.verify_grant(env, approvers=self.approvers)
            if ok:
                out.append((g, chain))
        return out

    def _grant(self, params: dict) -> dict:
        """Record a context grant. Only a grant that verifies — a user key, a policy key inside its frame, or
        a derivation inside its parent — is recorded; the declaration in the program never is one."""
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        from casl import context as _cx, journal as _j
        env = params.get("grant")
        ok, code, g, chain = _cx.verify_grant(env, approvers=self.approvers,
                                              revoked=frozenset(self._ledger.state().revoked))
        if not ok:
            return {"added": False, "code": code}
        try:
            self._ledger.reserve("ctx_grant", {"id": g["id"], "envelope": env}, self._now())
        except _j.Conflict as c:
            return {"added": False, "code": c.code, "id": g["id"]}      # exists (same grant) | duplicate_id
        return {"added": True, "code": "ok", "id": g["id"], "issuer": chain["issuer"]}

    def _revoke(self, params: dict) -> dict:
        """Revoke a grant or a frame by id. Unsigned on purpose: revocation only removes authority. It takes
        effect at the next access; an access already decided is in flight and completes."""
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        gid = params.get("id")
        if not (isinstance(gid, str) and gid):
            return {"revoked": False, "reason": "id must be a grant or frame id"}
        if gid not in self._ledger.state().revoked:
            self._log("revoke", {"id": gid})
        return {"revoked": True, "id": gid}

    def _access(self, params: dict) -> dict:
        """ONE context access — search, read or disclose — decided against the current grants and, if the
        broker performs it, sent. The request is RESOLVED here from trusted inputs (the actual URL, the
        credential the broker holds, the journal of earlier accesses), not taken from the caller's claims.
        Decision and record are one journal transaction; only a granted access is sent."""
        if not self._initialized:
            raise _BrokerError(-32002, "broker not initialized (call initialize first)")
        import hashlib
        from casl import context as _cx, egress as _eg
        site, cap = str(params.get("site", "?")), str(params.get("tool", ""))
        instance = params.get("instance") if isinstance(params.get("instance"), str) and params.get("instance") else None
        decl, mc, hp = self.contexts.get(cap), self.transports.get(cap), params.get("host_performed")
        base = {"program": self.program_hash, "instance": instance, "site": site, "cap": cap,
                "by": "host" if hp is not None else "broker"}

        def early(code: str, reason: str) -> dict:
            body = dict(base, request=_cx.request_id(dict(base, code=code)), decision="denied", code=code,
                        op=decl["op"] if decl else None)
            self._log("access", body)
            return {"decision": "denied", "code": code, "reason": reason, "request": body["request"]}

        if decl is None:
            return early("undeclared", f"the program declares no context scope for {cap!r}")
        if not self.program_hash:
            return early("unsupported", "the broker has no program identity")
        op, spec, q = decl["op"], None, dict(program=self.program_hash, instance=instance, cap=cap, op=decl["op"])
        if hp is not None:
            # the HOST performs this access (a local index, IMAP, a loopback model): the broker decides and
            # records, the host states where it goes. Attested, not enforced — the grade says so (`by: host`).
            if not isinstance(hp, dict):
                return early("unsupported", "host_performed must describe the access")
            if op == "disclose":
                q["receiver"] = hp.get("receiver")
            else:
                q.update(account=hp.get("account"), source=hp.get("source"), resource=hp.get("resource"))
        else:
            if mc is None:
                return early("unsupported", f"the broker performs nothing for {cap!r} (no transport)")
            spec = _eg.RequestSpec.from_obj(params.get("request"))
            ok, reason = mc.policy.check(spec.url)
            if not ok:
                return early("destination_denied", f"destination denied: {reason}")
            held = mc.conflicting_header(spec)
            if held is not None:
                return early("unsupported", f"header {held!r} is held by the broker and must not be supplied by the caller")
            parts = _eg.split_url(spec.url)
            if parts is None:
                return early("unsupported", "the url is not of the strict https form")
            host, port, path = parts
            if op == "disclose":
                try:
                    model = json.loads(spec.body).get("model")
                except (ValueError, AttributeError):
                    model = None
                if not core.valid_model(model):
                    return early("unsupported", "a disclosure must name its model in the JSON body field `model`")
                q["receiver"] = f"endpoint:{host}{':' + port if port else ''}{path}#{model}"
            else:
                if port is not None:
                    return early("unsupported", "a source on a non-default port is not supported")
                q.update(account=mc.account, source=host, resource=path)
        refs = params.get("origins") if op == "disclose" else None

        def step(state):
            body, cited = dict(base, op=op), []
            if op == "disclose":
                # ORIGINS: where the disclosed content came from — earlier GRANTED search/read accesses of
                # this program, cited by their journal id. Account, source and resource scope come from the
                # journal entry; a search hit names its own resource, which must lie inside what was searched.
                units = []
                allowed = [f["cap"] for f in decl["from"]]
                if not (isinstance(refs, list) and refs):
                    return self._no(body, q, "unsupported", "a disclosure must cite its origins")
                for r in refs:
                    acc = state.accesses.get(r.get("access")) if isinstance(r, dict) else None
                    if (acc is None or acc.get("op") not in ("search", "read") or acc.get("program") != self.program_hash
                            or acc.get("instance") != instance):
                        return self._no(body, q, "origin_invalid", "an origin is not a granted search/read of this run")
                    if acc.get("cap") not in allowed:
                        return self._no(body, q, "outside_declared_scope",
                                        f"content of {acc.get('cap')!r} may not be disclosed by {cap!r}")
                    res = r.get("resource", acc["resource"] if acc["op"] == "read" else None)
                    if not core.path_covers(acc["resource"], res):
                        return self._no(body, q, "origin_invalid",
                                        "a search hit must name its resource, inside the searched scope")
                    units.append({"account": acc["account"], "source": acc["source"], "resource": res})
                    cited.append({"access": r["access"], "account": acc["account"], "source": acc["source"], "resource": res})
                q["origins"] = units
            grants = self._verified_grants(state)
            d = _cx.decide(decl, q, grants, now=self._now(), revoked=frozenset(state.revoked), used=state.used)
            rid = _cx.request_id(q)
            body.update(request=rid, decision=d["decision"], code=d["code"],
                        **{k: q[k] for k in ("account", "source", "resource", "receiver") if k in q})
            if op == "disclose":
                body["origins"] = cited
            if d["decision"] == "granted":
                chains = {g["id"]: c for g, c in grants}
                body["grants"] = d["grants"]
                body["counted"] = [i for gid in d["grants"] for i in [gid] + [a["id"] for a in chains[gid]["ancestors"]]]
            elif d["decision"] == "needs_grant":
                body["missing"] = d["missing"]
                waiting = state.pending.get(rid)
                if waiting is not None and waiting.get("code") == d["code"]:
                    return [], (d, rid, waiting, waiting["seq"])        # the same ask again: one pending record
            return [("access", body)], (d, rid, body, None)

        seqs, (d, rid, body, seq) = self._ledger.transact(step, self._now())
        seq = seqs[0] if seqs else seq
        out = {"decision": d["decision"], "code": d["code"], "request": rid, "access": seq, "by": base["by"]}
        if d.get("reason"):
            out["reason"] = d["reason"]
        if d["decision"] == "needs_grant":
            # what the host needs to ask for authorization, and to correlate the answer after a restart
            out["missing"] = d["missing"]
            out["pending"] = {k: body.get(k) for k in ("request", "program", "instance", "site", "cap", "op", "account",
                                                         "source", "resource", "receiver", "origins") if body.get(k) is not None}
        if d["decision"] != "granted":
            return out
        out["grants"] = d["grants"]
        if spec is None:
            return out                                    # host-performed: decided and recorded, nothing sent
        status = text = None
        try:
            resp = mc.transport.send(mc.wire(spec))      # broker-held credentials are added on the wire only
            status, text = resp.status, resp.body
            outcome = _eg.classify(status)
        except _eg.TransportError as e:
            outcome = e.kind
        except Exception:
            outcome = "unknown"
        self._log("access_result", {"access": seq, "outcome": outcome, "status": status,
                                    "body_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if text is not None else None})
        out.update(outcome=outcome, performed=outcome == "performed")
        if status is not None:
            out.update(status=status, body=text)
        return out

    @staticmethod
    def _no(body: dict, q: dict, code: str, reason: str):
        """A denial found while resolving the request inside the decision step."""
        from casl import context as _cx
        rid = _cx.request_id(dict(q, code=code))
        full = dict(body, request=rid, decision="denied", code=code)
        return [("access", full)], ({"decision": "denied", "code": code, "reason": reason}, rid, full, None)

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
            mc = self.transports.get(cap)
            account = mc.account if mc is not None else None
            if mc is not None and mc.inject and account is None:
                # a credential whose principal is unknown cannot be approved: the signer could not know
                # whose account the request acts on
                return {"granted": False, "code": "account_unbound",
                        "reason": f"the broker holds a credential for {cap!r} without an identity — "
                                  f"configure its account so approvals can name it"}
            ok, code, reason, payload, klass = _ap.verify_signed(
                env, approvers=self.approvers, program=self.program_hash, cap=cap, site=site,
                now=self._now(), seen_nonces=set(self._ledger.state().nonces),
                required=self.approval_class.get(cap, "human"),
                account=account)
            if not ok:
                return {"granted": False, "code": code, "reason": reason}
            # journal the verified approval (payload + signature ⇒ re-verifiable later) BEFORE minting — as a
            # RESERVATION of the nonce: of several broker processes holding the same approval, one wins
            from casl import journal as _j
            try:
                self._ledger.reserve("approval", {
                    "nonce": payload["nonce"], "cap": cap, "site": site, "request": payload["request"],
                    "program": payload["program"], "exp": payload["exp"], "key": env["key"].lower(),
                    "class": klass, "account": account, "payload": env["payload"], "sig": env["sig"]}, self._now())
            except _j.Conflict:
                return {"granted": False, "code": "replayed", "reason": "this approval was already used"}
            token = secrets.token_hex(16)
            self._consents[token] = {"cap": cap, "site": site, "request": payload["request"],
                                     "nonce": payload["nonce"], "account": account, "used": False}
            out = {"granted": True, "token": token, "cap": cap, "site": site, "code": "ok", "class": klass}
            if account is not None:
                out["account"] = account
            return out
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
