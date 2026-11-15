//! `casl-broker` — the CASL reference monitor, in Rust (P1; `docs/architecture.md` §3).
//!
//! Mediates all model/tool access behind the frozen wire protocol (`casl-proto`). Pure Rust. This P1
//! crate mirrors the Python reference broker (`src/casl/broker.py`) behind the SAME protocol, so the
//! existing Python client/tests drive it unchanged (the cross-impl parity check). Scope: the monitored
//! oracle boundary (mock backend + the cost/refusal monitor), deny-by-default effects, capability
//! negotiation. Real tool dispatch + the human approval gate + confinement are later phases (P2+).

use std::collections::{BTreeMap, BTreeSet, HashMap};

use casl_proto as proto;
use proto::{
    codes, ConsentParams, ConsentResult, EffectParams, EffectResult, InitializeParams,
    InitializeResult, OracleParams, OracleResult, Request, ResolveParams, Response,
};
use serde_json::json;

pub mod approval;
pub mod egress;
pub mod journal;
pub mod live;
mod provider;
pub use provider::{
    build_request, parse_response, HttpReq, MockTransport, Provider, ProviderBackend, Transport,
};

/// Normalized oracle output (mirrors `src/casl/oracle.py::OracleResult`). `measured_cost` is the
/// out-of-band measurement the monitor actually checks (H4); `cost` is the model's unchecked claim.
pub struct OracleOut {
    pub answer: String,
    pub cost: Option<i64>,
    pub measured_cost: Option<i64>,
    pub refused: bool,
}

/// The model connector. Only the broker holds one; an artifact (via a binding) cannot conjure one.
pub trait Backend {
    fn generate(&mut self, question: &str, budget: i64) -> OracleOut;
}

/// Deterministic, offline mock backend mirroring the Python scenarios (for parity + tests).
pub struct MockBackend {
    pub scenario: String,
    calls: u32,
}

impl MockBackend {
    pub fn new(scenario: &str) -> Self {
        MockBackend {
            scenario: scenario.to_string(),
            calls: 0,
        }
    }
}

impl Backend for MockBackend {
    fn generate(&mut self, _question: &str, budget: i64) -> OracleOut {
        self.calls += 1;
        match self.scenario.as_str() {
            "refusal" => OracleOut {
                answer: String::new(),
                cost: None,
                measured_cost: None,
                refused: true,
            },
            "overspend" => {
                let c = budget + 25;
                OracleOut {
                    answer: "(mock) costly".into(),
                    cost: Some(c),
                    measured_cost: Some(c),
                    refused: false,
                }
            }
            // H4: the claim looks within budget; the measurement reveals the overspend.
            "underreport" => OracleOut {
                answer: "(mock) understated".into(),
                cost: Some(budget.min(10)),
                measured_cost: Some(budget + 25),
                refused: false,
            },
            "retry_then_ok" if self.calls == 1 => {
                let c = budget + 25;
                OracleOut {
                    answer: "(mock) first too costly".into(),
                    cost: Some(c),
                    measured_cost: Some(c),
                    refused: false,
                }
            }
            _ => {
                let c = budget.min(10);
                OracleOut {
                    answer: "(mock) 42".into(),
                    cost: Some(c),
                    measured_cost: Some(c),
                    refused: false,
                }
            }
        }
    }
}

enum Ledger {
    Memory(journal::MemoryLedger),
    Durable(journal::Journal),
}

impl Ledger {
    fn state(&self) -> Result<journal::State, String> {
        match self {
            Ledger::Memory(m) => Ok(m.state()),
            Ledger::Durable(j) => j.state(),
        }
    }

    /// Guarded append (approval, intent, resolve): refused with a `Conflict` if the state forbids it.
    fn reserve(
        &mut self,
        kind: &str,
        body: serde_json::Value,
        ts: i64,
    ) -> Result<(i64, serde_json::Value), journal::ReserveError> {
        match self {
            Ledger::Memory(m) => m.reserve(kind, body),
            Ledger::Durable(j) => j.reserve(kind, body, ts),
        }
    }

    fn append(&mut self, kind: &str, body: &serde_json::Value, ts: i64) -> Result<i64, String> {
        match self {
            Ledger::Memory(m) => Ok(m.append(kind, body)),
            Ledger::Durable(j) => j.append(kind, body, ts),
        }
    }
}

/// What a valid consent token is bound to: (request digest, approval nonce, target account).
type ConsentBinding = (Option<String>, Option<String>, Option<String>);

/// A one-shot consent record minted by the approval gate, bound to (cap, site). (A)
struct Consent {
    cap: String,
    site: String,
    /// Request-bound consent: the digest of the ONE request this token authorizes (None ⇒ legacy binding).
    request: Option<String>,
    /// The nonce of the signed approval this token came from (None for a legacy assertion).
    nonce: Option<String>,
    /// Signed approvals: the target account the approval named (None = no credential involved).
    account: Option<String>,
    used: bool,
}

/// The reference monitor: holds the model backend + the tool grants. Only it may touch a capability.
pub struct Broker {
    pub backend: Option<Box<dyn Backend>>,
    pub granted_tools: BTreeSet<String>,
    /// (A) caps whose effect REQUIRES a fresh one-shot consent token bound to (cap, site).
    pub irreversible_caps: BTreeSet<String>,
    /// SIGNED approvals: a non-empty trust store (pubkey-hex → class) switches `consent` to signed-only —
    /// an `approved: true` assertion then mints nothing (closes agent self-approval).
    pub approvers: BTreeMap<String, String>,
    /// The active program version a signed approval must name.
    pub program_hash: Option<String>,
    /// cap → minimum approver class (default `human`).
    pub approval_class: BTreeMap<String, String>,
    /// Fixed clock (unix seconds) for tests; None ⇒ system time.
    pub fixed_now: Option<i64>,
    /// Capabilities the broker PERFORMS (mediated egress): cap → destination allowlist + transport.
    pub mediated: BTreeMap<String, egress::Mediated>,
    /// The ledger of approvals and attempts: the run journal (durable, shared by concurrent broker
    /// processes) or, without one, the same state in memory for this process only.
    ledger: Ledger,
    declared_caps: BTreeSet<String>,
    consents: HashMap<String, Consent>,
    consent_counter: u64,
    initialized: bool,
}

impl Broker {
    pub fn new(backend: Option<Box<dyn Backend>>, granted_tools: BTreeSet<String>) -> Self {
        Broker {
            backend,
            granted_tools,
            irreversible_caps: BTreeSet::new(),
            approvers: BTreeMap::new(),
            program_hash: None,
            approval_class: BTreeMap::new(),
            fixed_now: None,
            mediated: BTreeMap::new(),
            ledger: Ledger::Memory(journal::MemoryLedger::default()),
            declared_caps: BTreeSet::new(),
            consents: HashMap::new(),
            consent_counter: 0,
            initialized: false,
        }
    }

    /// Builder: declare which granted caps are irreversible (each effect then needs a consent token).
    pub fn with_irreversible(mut self, caps: BTreeSet<String>) -> Self {
        self.irreversible_caps = caps;
        self
    }

    /// Builder: require SIGNED approvals from this trust store, for this program version.
    pub fn with_approvers(
        mut self,
        approvers: BTreeMap<String, String>,
        program_hash: Option<String>,
        approval_class: BTreeMap<String, String>,
    ) -> Self {
        self.approvers = approvers;
        self.program_hash = program_hash;
        self.approval_class = approval_class;
        self
    }

    /// Builder: attach the run journal (it must be readable — its state decides every reservation).
    pub fn with_journal(mut self, j: journal::Journal) -> Result<Self, String> {
        j.state()?;
        self.ledger = Ledger::Durable(j);
        Ok(self)
    }

    /// Append to the ledger. `Err` ⇒ nothing was written; callers log BEFORE acting (fail closed).
    fn log(&mut self, kind: &str, body: serde_json::Value) -> Result<i64, String> {
        let now = self.now();
        self.ledger.append(kind, &body, now)
    }

    fn now(&self) -> i64 {
        self.fixed_now.unwrap_or_else(|| {
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_secs() as i64)
                .unwrap_or(i64::MAX) // a broken clock fails closed: everything is expired
        })
    }

    /// Mint a one-shot, unforgeable consent token (process-seeded RandomState ⇒ unpredictable; no crypto dep).
    fn mint_token(&mut self) -> String {
        use std::hash::{BuildHasher, Hasher};
        self.consent_counter += 1;
        let n = self.consent_counter;
        let mut h1 = std::collections::hash_map::RandomState::new().build_hasher();
        h1.write_u64(n);
        h1.write_u64(0x00C0_FFEE);
        let mut h2 = std::collections::hash_map::RandomState::new().build_hasher();
        h2.write_u64(n);
        h2.write_u64(0x00BE_EF00);
        format!("{:016x}{:016x}", h1.finish(), h2.finish())
    }

    /// Check a consent token: present, unused, bound to this (cap, site) and — for a request-bound token —
    /// to THIS request's digest. Does NOT burn it (the caller journals the intent first, then burns).
    /// `Ok` = (bound request digest, approval nonce); `Err` = the denial reason.
    fn check_consent(
        &self,
        token: Option<&str>,
        cap: &str,
        site: &str,
        request: Option<&serde_json::Value>,
    ) -> Result<ConsentBinding, String> {
        let c = token
            .and_then(|t| self.consents.get(t))
            .filter(|c| !c.used && c.cap == cap && c.site == site)
            .ok_or_else(|| {
                format!(
                    "irreversible effect {cap:?} at {site} needs a fresh matching approval token (deny-by-default)"
                )
            })?;
        if let Some(bound) = &c.request {
            if approval::request_digest(request).as_ref() != Some(bound) {
                return Err(
                    "approval token does not match this request (request-bound consent) — the human approved a different request"
                        .into(),
                );
            }
        }
        if c.nonce.is_some() {
            // a SIGNED approval — checked AGAIN at execution: the credential the broker would use now
            // must still be the principal the approval named
            let held = self.mediated.get(cap).and_then(|m| m.account.as_ref());
            if c.account.as_ref() != held {
                return Err(
                    "approval names a different target account than the credential in use".into(),
                );
            }
        }
        Ok((c.request.clone(), c.nonce.clone(), c.account.clone()))
    }

    /// The `effect` method (mirrors `Broker._effect` of the reference). `Err` = an internal failure
    /// (the journal could not be written) — nothing was performed.
    fn effect(&mut self, p: EffectParams) -> Result<EffectResult, String> {
        let (tool, site) = (p.tool.clone(), p.site.clone());
        let deny = |reason: String, outcome: Option<&str>| EffectResult {
            allowed: false,
            tool: tool.clone(),
            site: site.clone(),
            reason: Some(reason),
            outcome: outcome.map(str::to_string),
            ..Default::default()
        };
        let unresolved = |attempt: i64, account: Option<String>| {
            EffectResult {
            allowed: false,
            tool: tool.clone(),
            site: site.clone(),
            outcome: Some("unresolved".into()),
            attempt: Some(attempt),
            account,
            reason: Some(format!(
                "attempt {attempt} of this exact request has an unknown outcome or is in flight — clarify it at the target system and `resolve` it before retrying"
            )),
            ..Default::default()
        }
        };
        if !self.granted_tools.contains(&tool) {
            return Ok(deny(
                format!("capability {tool:?} not granted for site {site} (deny-by-default)"),
                None,
            ));
        }
        let irreversible = self.irreversible_caps.contains(&tool);
        // Mediated egress: the destination policy runs FIRST — before consent is consumed and before
        // any connect (a denied destination burns no token).
        let mut spec: Option<egress::RequestSpec> = None;
        if let Some(m) = self.mediated.get(&tool) {
            let Some(s) = egress::RequestSpec::from_obj(p.request.as_ref()) else {
                return Ok(deny(
                    "destination denied: request is not an object".into(),
                    None,
                ));
            };
            if let Err(r) = egress::check_destination(&s.url, &m.allow_hosts) {
                return Ok(deny(format!("destination denied: {r}"), None));
            }
            if let Some(h) = m.conflicting_header(&s) {
                return Ok(deny(
                    format!("request denied: header {h:?} is held by the broker and must not be supplied by the caller"),
                    None,
                ));
            }
            if irreversible {
                // NO BLIND REPEAT: an earlier attempt of this exact request, under this account, may
                // have reached the target. (The same request under another account is another resource.)
                if let Some(a) = self
                    .ledger
                    .state()?
                    .blocking(m.account.as_deref(), &s.digest())
                {
                    return Ok(unresolved(a, m.account.clone()));
                }
            }
            spec = Some(s);
        }
        let digest = spec.as_ref().map(|s| s.digest());
        let held = self.mediated.get(&tool).and_then(|m| m.account.clone());
        let mut attempt: Option<i64> = None;
        if irreversible {
            // (A) an irreversible cap needs a fresh, matching, one-shot consent token.
            let (bound, nonce, _account) =
                match self.check_consent(p.approval.as_deref(), &tool, &site, p.request.as_ref()) {
                    Ok(x) => x,
                    Err(reason) => return Ok(deny(reason, None)),
                };
            match &digest {
                None => {
                    self.log(
                        "grant",
                        json!({"cap": tool, "site": site, "request": bound, "nonce": nonce}),
                    )?;
                }
                Some(d) => {
                    // INTENT before the send, durably, and as a RESERVATION: the journal re-checks
                    // under its write lock that this scope is not in flight and this approval made no
                    // attempt yet — of several broker processes only one proceeds. If the broker dies
                    // after this line the journal still says the request may have gone out (an intent
                    // without a result replays as "unknown").
                    let now = self.now();
                    let body = json!({"effect": d, "cap": tool, "site": site, "nonce": nonce, "account": held});
                    match self.ledger.reserve("intent", body, now) {
                        Ok((seq, _)) => attempt = Some(seq),
                        Err(journal::ReserveError::Conflict(journal::Conflict::Unresolved(a))) => {
                            return Ok(unresolved(a, held))
                        }
                        Err(journal::ReserveError::Conflict(_)) => {
                            return Ok(deny(
                                "this approval was already used for an attempt (one approval, one attempt)".into(),
                                None,
                            ))
                        }
                        Err(journal::ReserveError::Io(e)) => return Err(e),
                    }
                }
            };
            if let Some(c) = p.approval.as_deref().and_then(|t| self.consents.get_mut(t)) {
                c.used = true; // one-shot: a token authorizes exactly ONE attempt
            }
        }
        let (Some(spec), Some(digest)) = (spec, digest) else {
            return Ok(EffectResult {
                allowed: true,
                tool,
                site,
                note: Some(
                    if irreversible {
                        "granted (consent consumed)"
                    } else {
                        "granted"
                    }
                    .into(),
                ),
                ..Default::default()
            });
        };
        let sent = match self.mediated.get_mut(&tool) {
            Some(m) => {
                // credentials the broker holds are added on the wire only — never part of the approved
                // request, never visible to the caller
                let mut wire = spec.clone();
                wire.headers.extend(m.inject.iter().cloned());
                m.transport.send(&wire)
            }
            None => Err(egress::TransportFailure::NotSent),
        };
        let (outcome, status, body) = match sent {
            Ok(r) => (egress::classify(r.status), Some(r.status), Some(r.body)),
            Err(f) => (f.outcome(), None, None),
        };
        if irreversible {
            self.log(
                "result",
                json!({"attempt": attempt, "effect": digest, "account": held, "outcome": outcome,
                       "status": status,
                       "body_sha256": body.as_ref().map(|b| journal::sha256_hex(b.as_bytes()))}),
            )?;
        }
        Ok(EffectResult {
            allowed: true,
            tool,
            site,
            outcome: Some(outcome.into()),
            performed: Some(outcome == "performed"),
            receipt: status.map(|st| json!({"request": digest, "status": st})),
            attempt,
            account: if irreversible { held } else { None },
            request: Some(digest),
            status,
            body,
            ..Default::default()
        })
    }

    /// `resolve` without the RPC envelope (for an in-process host such as `casl resolve`).
    pub fn resolve_attempt(
        &mut self,
        attempt: i64,
        outcome: &str,
        note: &str,
    ) -> Result<serde_json::Value, String> {
        self.resolve(ResolveParams {
            attempt: json!(attempt),
            outcome: outcome.into(),
            note: note.into(),
        })
    }

    /// The `resolve` method: record the clarified outcome of an ATTEMPT whose outcome was unknown.
    /// Addressed by attempt id, so it cannot land on another account's attempt.
    fn resolve(&mut self, p: ResolveParams) -> Result<serde_json::Value, String> {
        if p.outcome != "performed" && p.outcome != "not_performed" {
            return Ok(
                json!({"resolved": false, "reason": "outcome must be 'performed' or 'not_performed'"}),
            );
        }
        let Some(attempt) = p.attempt.as_i64().filter(|_| p.attempt.is_i64()) else {
            return Ok(
                json!({"resolved": false, "reason": "attempt must be the integer id an effect result reported"}),
            );
        };
        let now = self.now();
        let body = json!({"attempt": attempt, "outcome": p.outcome, "note": p.note});
        match self.ledger.reserve("resolve", body, now) {
            Ok((_, written)) => {
                let mut out = json!({"resolved": true, "attempt": attempt, "outcome": p.outcome,
                                     "request": written["effect"]});
                if !written["account"].is_null() {
                    out["account"] = written["account"].clone();
                }
                Ok(out)
            }
            Err(journal::ReserveError::Conflict(_)) => Ok(
                json!({"resolved": false, "reason": "no attempt with an unknown outcome under this id"}),
            ),
            Err(journal::ReserveError::Io(e)) => Err(e),
        }
    }

    /// Transport-agnostic JSON-RPC dispatch.
    pub fn handle(&mut self, req: &Request) -> Response {
        let id = req.id.clone();
        match req.method.as_str() {
            "initialize" => {
                if !self.initialized {
                    let program = self.program_hash.clone();
                    if let Err(e) = self.log(
                        "run",
                        json!({"program": program, "impl": "rust", "protocol": proto::PROTOCOL_VERSION}),
                    ) {
                        return Response::err(id, codes::INTERNAL, e);
                    }
                }
                self.initialized = true;
                let ip: InitializeParams =
                    serde_json::from_value(req.params.clone()).unwrap_or_default();
                self.declared_caps = ip.capabilities.into_iter().collect();
                let r = InitializeResult {
                    server: "casl-broker".into(),
                    version: proto::PROTOCOL_VERSION.into(),
                    capabilities: vec![
                        "oracle".into(),
                        "effect".into(),
                        "consent".into(),
                        "resolve".into(),
                    ],
                };
                Response::ok(id, serde_json::to_value(r).unwrap())
            }
            "shutdown" => Response::ok(id, json!({"ok": true})),
            "oracle" => {
                if !self.initialized {
                    return Response::err(id, codes::NOT_INITIALIZED, "broker not initialized");
                }
                let p: OracleParams = match serde_json::from_value(req.params.clone()) {
                    Ok(p) => p,
                    Err(e) => {
                        return Response::err(id, codes::INTERNAL, format!("bad params: {e}"))
                    }
                };
                if let Some(prov) = &p.provider {
                    let cap = format!("llm:{prov}");
                    if !self.declared_caps.contains(&cap) {
                        return Response::err(
                            id,
                            codes::CAPABILITY_DENIED,
                            format!("artifact did not declare capability {cap:?} — flag it to use provider {prov:?}"),
                        );
                    }
                }
                let out = match self.backend.as_mut() {
                    Some(b) => b.generate(&p.question, p.budget),
                    None => {
                        return Response::err(
                            id,
                            codes::NO_MODEL,
                            "no model connector configured in the broker",
                        )
                    }
                };
                let res = monitor(&out, p.budget, &p.producer);
                Response::ok(id, serde_json::to_value(res).unwrap())
            }
            "effect" => {
                if !self.initialized {
                    return Response::err(id, codes::NOT_INITIALIZED, "broker not initialized");
                }
                let p: EffectParams = match serde_json::from_value(req.params.clone()) {
                    Ok(p) => p,
                    Err(e) => {
                        return Response::err(id, codes::INTERNAL, format!("bad params: {e}"))
                    }
                };
                match self.effect(p) {
                    Ok(res) => Response::ok(id, serde_json::to_value(res).unwrap()),
                    Err(e) => Response::err(id, codes::INTERNAL, e),
                }
            }
            "resolve" => {
                if !self.initialized {
                    return Response::err(id, codes::NOT_INITIALIZED, "broker not initialized");
                }
                let p: ResolveParams = match serde_json::from_value(req.params.clone()) {
                    Ok(p) => p,
                    Err(e) => {
                        return Response::err(id, codes::INTERNAL, format!("bad params: {e}"))
                    }
                };
                match self.resolve(p) {
                    Ok(v) => Response::ok(id, v),
                    Err(e) => Response::err(id, codes::INTERNAL, e),
                }
            }
            "consent" => {
                if !self.initialized {
                    return Response::err(id, codes::NOT_INITIALIZED, "broker not initialized");
                }
                let p: ConsentParams = match serde_json::from_value(req.params.clone()) {
                    Ok(p) => p,
                    Err(e) => {
                        return Response::err(id, codes::INTERNAL, format!("bad params: {e}"))
                    }
                };
                let held = self.mediated.get(&p.tool).and_then(|m| m.account.clone());
                let unbound = self
                    .mediated
                    .get(&p.tool)
                    .is_some_and(|m| !m.inject.is_empty() && m.account.is_none());
                let r = if !self.approvers.is_empty() && unbound {
                    // a credential whose principal is unknown cannot be approved: the signer could not
                    // know whose account the request acts on
                    ConsentResult {
                        granted: false,
                        token: None,
                        reason: Some(format!(
                            "the broker holds a credential for {:?} without an identity — configure its account so approvals can name it",
                            p.tool
                        )),
                        code: Some("account_unbound".into()),
                        approver_class: None,
                        account: None,
                    }
                } else if !self.approvers.is_empty() {
                    // SIGNED mode: the human is bound by a signature the calling agent cannot produce.
                    // The token is ALWAYS bound to the digest the signer committed to.
                    let now = self.now();
                    let mut seen = match self.ledger.state() {
                        Ok(st) => st.nonces,
                        Err(e) => return Response::err(id, codes::INTERNAL, e),
                    };
                    let required = self
                        .approval_class
                        .get(&p.tool)
                        .cloned()
                        .unwrap_or_else(|| "human".into());
                    match approval::verify_signed(
                        p.signed.as_ref(),
                        &self.approvers,
                        self.program_hash.as_deref(),
                        &p.tool,
                        &p.site,
                        now,
                        &mut seen,
                        &required,
                        held.as_deref(),
                    ) {
                        Err(d) => ConsentResult {
                            granted: false,
                            token: None,
                            reason: Some(d.reason),
                            code: Some(d.code.into()),
                            approver_class: None,
                            account: None,
                        },
                        Ok(v) => {
                            // journal the verified approval (payload + signature ⇒ re-verifiable
                            // later) BEFORE minting the token — as a RESERVATION of the nonce: of
                            // several broker processes holding the same approval, one wins
                            let env = p.signed.as_ref();
                            let part = |k: &str| env.and_then(|e| e.get(k)).cloned();
                            let body = json!({"nonce": v.nonce, "cap": p.tool, "site": p.site,
                                              "request": v.request, "program": v.program, "exp": v.exp,
                                              "key": v.key, "class": v.class, "account": v.account,
                                              "payload": part("payload"), "sig": part("sig")});
                            match self.ledger.reserve("approval", body, now) {
                                Ok(_) => {}
                                Err(journal::ReserveError::Conflict(_)) => {
                                    let r = ConsentResult {
                                        granted: false,
                                        token: None,
                                        reason: Some("this approval was already used".into()),
                                        code: Some("replayed".into()),
                                        approver_class: None,
                                        account: None,
                                    };
                                    return Response::ok(id, serde_json::to_value(r).unwrap());
                                }
                                Err(journal::ReserveError::Io(e)) => {
                                    return Response::err(id, codes::INTERNAL, e)
                                }
                            }
                            let token = self.mint_token();
                            self.consents.insert(
                                token.clone(),
                                Consent {
                                    cap: p.tool,
                                    site: p.site,
                                    request: Some(v.request),
                                    nonce: Some(v.nonce),
                                    account: v.account.clone(),
                                    used: false,
                                },
                            );
                            ConsentResult {
                                granted: true,
                                token: Some(token),
                                reason: None,
                                code: Some("ok".into()),
                                approver_class: Some(v.class),
                                account: v.account,
                            }
                        }
                    }
                } else if !p.approved {
                    ConsentResult {
                        granted: false,
                        token: None,
                        reason: Some("approval withheld at the gate (deny-by-default)".into()),
                        code: None,
                        approver_class: None,
                        account: None,
                    }
                } else {
                    // Legacy (no trust store): `approved` is the UI's assertion. Optionally request-bound.
                    let request = match &p.request {
                        None => None,
                        Some(r) => match approval::request_digest(Some(r)) {
                            Some(d) => Some(d),
                            None => {
                                return Response::err(
                                    id,
                                    codes::INTERNAL,
                                    "bad params: request is not an object",
                                )
                            }
                        },
                    };
                    let token = self.mint_token();
                    self.consents.insert(
                        token.clone(),
                        Consent {
                            cap: p.tool,
                            site: p.site,
                            request,
                            nonce: None,
                            account: None,
                            used: false,
                        },
                    );
                    ConsentResult {
                        granted: true,
                        token: Some(token),
                        reason: None,
                        code: None,
                        approver_class: None,
                        account: None,
                    }
                };
                Response::ok(id, serde_json::to_value(r).unwrap())
            }
            other => Response::err(
                id,
                codes::METHOD_NOT_FOUND,
                format!("method not found: {other:?}"),
            ),
        }
    }
}

/// The monitored oracle boundary (mirrors `oracle.oracle_step` + `synth_refusal_monitor`): refusal is a
/// typed outcome (no blame); a contract breach blames the producer; the cost CHECKED is the out-of-band
/// measurement (H4), never the model's claim.
pub fn monitor(out: &OracleOut, budget: i64, producer: &str) -> OracleResult {
    if out.refused {
        return OracleResult {
            verdict: "refusal".into(),
            answer: out.answer.clone(),
            cost: out.cost,
            measured_cost: out.measured_cost,
            blame: None,
            reason: format!("oracle {producer} refused — typed, no blame"),
            branch: "Reject (refusal → Retry)".into(),
        };
    }
    let checked = out.measured_cost.or(out.cost).unwrap_or(budget + 1);
    if checked <= budget {
        OracleResult {
            verdict: "ok".into(),
            answer: out.answer.clone(),
            cost: out.cost,
            measured_cost: out.measured_cost,
            blame: None,
            reason: format!("{checked} <= {budget}"),
            branch: "Accept".into(),
        }
    } else {
        OracleResult {
            verdict: "violation".into(),
            answer: out.answer.clone(),
            cost: out.cost,
            measured_cost: out.measured_cost,
            blame: Some(producer.to_string()),
            reason: format!("{checked} > {budget} — blame {producer}"),
            branch: "Reject (blame A → Retry)".into(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{from_value, Value};

    fn req(method: &str, params: Value) -> Request {
        Request {
            jsonrpc: "2.0".into(),
            id: json!(1),
            method: method.into(),
            params,
        }
    }
    fn mk(scenario: &str, tools: &[&str]) -> Broker {
        Broker::new(
            Some(Box::new(MockBackend::new(scenario))),
            tools.iter().map(|s| s.to_string()).collect(),
        )
    }

    #[test]
    fn oracle_ok() {
        let mut b = mk("ok", &[]);
        b.handle(&req("initialize", json!({})));
        let r: OracleResult = from_value(
            b.handle(&req(
                "oracle",
                json!({"site":"Draft","question":"q","budget":100}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert_eq!(r.verdict, "ok");
    }
    #[test]
    fn oracle_overspend_blamed() {
        let mut b = mk("overspend", &[]);
        b.handle(&req("initialize", json!({})));
        let r: OracleResult = from_value(
            b.handle(&req("oracle", json!({"site":"D","budget":100})))
                .result
                .unwrap(),
        )
        .unwrap();
        assert_eq!(r.verdict, "violation");
        assert_eq!(r.blame.as_deref(), Some("A"));
    }
    #[test]
    fn oracle_underreport_caught_by_measurement() {
        let mut b = mk("underreport", &[]);
        b.handle(&req("initialize", json!({})));
        let r: OracleResult = from_value(
            b.handle(&req("oracle", json!({"site":"D","budget":100})))
                .result
                .unwrap(),
        )
        .unwrap();
        assert_eq!(r.verdict, "violation");
    }
    #[test]
    fn effect_deny_by_default() {
        let mut b = mk("ok", &["mail"]);
        b.handle(&req("initialize", json!({})));
        let yes: EffectResult = from_value(
            b.handle(&req("effect", json!({"site":"Notify","tool":"mail"})))
                .result
                .unwrap(),
        )
        .unwrap();
        assert!(yes.allowed);
        let no: EffectResult = from_value(
            b.handle(&req("effect", json!({"site":"Move","tool":"calendar"})))
                .result
                .unwrap(),
        )
        .unwrap();
        assert!(!no.allowed);
    }
    #[test]
    fn oracle_without_init_errors() {
        let mut b = mk("ok", &[]);
        assert!(b
            .handle(&req("oracle", json!({"site":"D","budget":100})))
            .error
            .is_some());
    }
    #[test]
    fn no_model_errors() {
        let mut b = Broker::new(None, BTreeSet::new());
        b.handle(&req("initialize", json!({})));
        let resp = b.handle(&req("oracle", json!({"site":"D","budget":100})));
        assert_eq!(resp.error.unwrap().code, codes::NO_MODEL);
    }
    #[test]
    fn unknown_method() {
        let mut b = mk("ok", &[]);
        b.handle(&req("initialize", json!({})));
        assert_eq!(
            b.handle(&req("frobnicate", json!({}))).error.unwrap().code,
            codes::METHOD_NOT_FOUND
        );
    }
    #[test]
    fn provider_requires_declared_capability() {
        let mut b = mk("ok", &[]);
        b.handle(&req("initialize", json!({"capabilities": []})));
        let resp = b.handle(&req(
            "oracle",
            json!({"site":"D","budget":100,"provider":"claude"}),
        ));
        assert_eq!(resp.error.unwrap().code, codes::CAPABILITY_DENIED);
    }
    #[test]
    fn declared_provider_capability_allows_use() {
        let mut b = mk("ok", &[]);
        b.handle(&req("initialize", json!({"capabilities": ["llm:claude"]})));
        let r: OracleResult = from_value(
            b.handle(&req(
                "oracle",
                json!({"site":"D","budget":100,"provider":"claude"}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert_eq!(r.verdict, "ok");
    }

    // ---- (A) approval-binding -------------------------------------------------
    fn mk_irrev(tools: &[&str], irreversible: &[&str]) -> Broker {
        Broker::new(
            Some(Box::new(MockBackend::new("ok"))),
            tools.iter().map(|s| s.to_string()).collect(),
        )
        .with_irreversible(irreversible.iter().map(|s| s.to_string()).collect())
    }

    #[test]
    fn irreversible_effect_denied_without_token() {
        let mut b = mk_irrev(&["calendar"], &["calendar"]);
        b.handle(&req("initialize", json!({})));
        let r: EffectResult = from_value(
            b.handle(&req("effect", json!({"site":"Book","tool":"calendar"})))
                .result
                .unwrap(),
        )
        .unwrap();
        assert!(!r.allowed);
    }

    #[test]
    fn consent_then_effect_one_shot() {
        let mut b = mk_irrev(&["calendar"], &["calendar"]);
        b.handle(&req("initialize", json!({})));
        let c: ConsentResult = from_value(
            b.handle(&req(
                "consent",
                json!({"site":"Book","tool":"calendar","approved":true}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert!(c.granted);
        let tok = c.token.unwrap();
        let r1: EffectResult = from_value(
            b.handle(&req(
                "effect",
                json!({"site":"Book","tool":"calendar","approval":tok}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert!(r1.allowed);
        let r2: EffectResult = from_value(
            b.handle(&req(
                "effect",
                json!({"site":"Book","tool":"calendar","approval":tok}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert!(!r2.allowed); // one-shot: token consumed
    }

    #[test]
    fn consent_withheld_and_site_mismatch() {
        let mut b = mk_irrev(&["calendar"], &["calendar"]);
        b.handle(&req("initialize", json!({})));
        let no: ConsentResult = from_value(
            b.handle(&req(
                "consent",
                json!({"site":"Book","tool":"calendar","approved":false}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert!(!no.granted);
        let c: ConsentResult = from_value(
            b.handle(&req(
                "consent",
                json!({"site":"Book","tool":"calendar","approved":true}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        let tok = c.token.unwrap();
        let mism: EffectResult = from_value(
            b.handle(&req(
                "effect",
                json!({"site":"Other","tool":"calendar","approval":tok}),
            ))
            .result
            .unwrap(),
        )
        .unwrap();
        assert!(!mism.allowed); // bound to (cap, site)
    }
}
