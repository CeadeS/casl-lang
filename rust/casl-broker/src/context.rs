//! Scoped CONTEXT GRANTS — mirrors `src/casl/context.py` (the reference); contract: docs/context-grants.md.
//!
//! A program DECLARES the data scope each capability requests; a GRANT authorizes one operation for one
//! account on one source/resource scope (and, for a disclosure, towards one receiver). A grant is signed
//! by a user key, or by an OS policy key acting inside a user-signed FRAME, or is DERIVED from a parent
//! grant (delegation) and must lie within it. A request is allowed iff it lies within the declared scope
//! AND a live grant covers it: the effective authority is always declared ∩ granted.
//!
//! Everything here is pure — signatures in, decisions out; state (revocations, use counts) and the clock
//! are arguments. Pinned to the reference by `tests/context_differential.rs`.

use std::collections::{BTreeMap, BTreeSet};

use casl_surface as surf;
use ed25519_dalek::{Signature, VerifyingKey};
use serde_json::{json, Value};
use surf::context::{
    parse_receiver, path_covers, receiver_covers, valid_host, valid_path, CONTEXT_OPS,
};

use crate::approval::class_satisfies;

pub const GRANT_DOMAIN: &[u8] = b"casl-grant-v1\n";
pub const FRAME_DOMAIN: &[u8] = b"casl-frame-v1\n";
/// Parent links followed when verifying a derived grant.
pub const MAX_CHAIN: usize = 4;

fn s<'a>(v: &'a Value, k: &str) -> Option<&'a str> {
    v.get(k).and_then(Value::as_str).filter(|x| !x.is_empty())
}

/// A JSON integer in i64 range (never a bool or a float).
fn int(v: &Value, k: &str) -> Option<i64> {
    v.get(k)
        .filter(|x| x.is_i64() || x.is_u64())
        .and_then(Value::as_i64)
}

/// Python's `x.get(k) is None`: absent or null.
fn none(v: &Value, k: &str) -> bool {
    v.get(k).is_none_or(Value::is_null)
}

fn op_of(v: &Value) -> Option<&str> {
    v.get("op")
        .and_then(Value::as_str)
        .filter(|o| CONTEXT_OPS.contains(o))
}

fn host_ok(v: &Value, k: &str) -> bool {
    v.get(k).and_then(Value::as_str).is_some_and(valid_host)
}

fn path_ok(v: &Value, k: &str) -> bool {
    v.get(k).and_then(Value::as_str).is_some_and(valid_path)
}

/// A receiver a GRANT or a REQUEST may name: a workflow, or an endpoint WITH its model. Protected content
/// is released to one concrete model, never to "whatever runs at that endpoint".
fn concrete_receiver(v: &Value, k: &str) -> bool {
    match v.get(k).and_then(Value::as_str).and_then(parse_receiver) {
        Some(surf::context::Receiver::Workflow(_)) => true,
        Some(surf::context::Receiver::Endpoint { model, .. }) => !model.is_empty(),
        None => false,
    }
}

/// `value` as JSON text with sorted keys and compact separators — the form
/// `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)` writes.
pub fn canonical(v: &Value) -> String {
    match v {
        Value::Object(m) => {
            let mut keys: Vec<&String> = m.keys().collect();
            keys.sort();
            let parts: Vec<String> = keys
                .iter()
                .map(|k| format!("{}:{}", Value::String((*k).clone()), canonical(&m[*k])))
                .collect();
            format!("{{{}}}", parts.join(","))
        }
        Value::Array(a) => {
            let parts: Vec<String> = a.iter().map(canonical).collect();
            format!("[{}]", parts.join(","))
        }
        other => other.to_string(),
    }
}

/// A stable id for a resolved request: the same access asked again has the same id.
pub fn request_id(q: &Value) -> String {
    crate::journal::sha256_hex(canonical(q).as_bytes())
}

fn str_of<'a>(v: &'a Value, k: &str) -> &'a str {
    v.get(k).and_then(Value::as_str).unwrap_or("")
}

// -- what a program declares -------------------------------------------------------------------------

/// The context scope the program declares for capability `cap`, as plain data — or `None` if it declares
/// none, or if two agents declare different scopes under that name (ambiguous ⇒ fail closed).
pub fn declared(p: &surf::Protocol, cap: &str) -> Option<Value> {
    let mut found: Vec<Value> = Vec::new();
    for caps in p.caps.values() {
        let Some(c) = caps.iter().find(|c| c.tool == cap) else {
            continue;
        };
        let Some(d) = &c.context else { continue };
        if d.op == "disclose" {
            let from: Vec<Value> = d
                .sources
                .iter()
                .filter_map(|n| {
                    let src = caps.iter().find(|c| &c.tool == n)?;
                    let x = src.context.as_ref()?;
                    Some(json!({"cap": n, "op": x.op, "source": x.source, "resource": x.resource}))
                })
                .collect();
            found.push(json!({"cap": cap, "op": d.op, "receiver": d.receiver, "from": from}));
        } else {
            found.push(json!({"cap": cap, "op": d.op, "source": d.source, "resource": d.resource}));
        }
    }
    let first = found.first()?.clone();
    found.iter().all(|f| *f == first).then_some(first)
}

// -- well-formedness of the objects -----------------------------------------------------------------

pub fn valid_request(q: &Value) -> bool {
    if !(q.is_object()
        && s(q, "program").is_some()
        && s(q, "cap").is_some()
        && (none(q, "instance") || s(q, "instance").is_some()))
    {
        return false;
    }
    match op_of(q) {
        Some("disclose") => {
            concrete_receiver(q, "receiver")
                && q.get("origins").and_then(Value::as_array).is_some_and(|o| {
                    !o.is_empty()
                        && o.iter().all(|u| {
                            u.is_object()
                                && s(u, "account").is_some()
                                && host_ok(u, "source")
                                && path_ok(u, "resource")
                        })
                })
        }
        Some(_) => s(q, "account").is_some() && host_ok(q, "source") && path_ok(q, "resource"),
        None => false,
    }
}

pub fn valid_grant(g: &Value) -> bool {
    let Some(op) = op_of(g) else { return false };
    if !(g.is_object()
        && int(g, "v") == Some(1)
        && g.get("kind").and_then(Value::as_str) == Some("grant")
        && s(g, "id").is_some()
        && s(g, "program").is_some()
        && (none(g, "instance") || s(g, "instance").is_some())
        && s(g, "account").is_some()
        && host_ok(g, "source")
        && path_ok(g, "resource")
        && int(g, "exp").is_some()
        && (none(g, "uses") || int(g, "uses").is_some_and(|n| n >= 1)))
    {
        return false;
    }
    if op == "disclose" {
        concrete_receiver(g, "receiver")
    } else {
        none(g, "receiver")
    }
}

fn frame_ops(f: &Value) -> Option<Vec<&str>> {
    let ops = f.get("ops")?.as_array()?;
    let mut out: Vec<&str> = Vec::new();
    for o in ops {
        let o = o.as_str().filter(|o| CONTEXT_OPS.contains(o))?;
        if out.contains(&o) {
            return None;
        }
        out.push(o);
    }
    (!out.is_empty()).then_some(out)
}

fn frame_receivers(f: &Value) -> Option<Vec<&str>> {
    match f.get("receivers") {
        None => Some(Vec::new()),
        Some(Value::Array(a)) => a
            .iter()
            .map(|r| r.as_str().filter(|r| parse_receiver(r).is_some()))
            .collect(),
        Some(_) => None,
    }
}

pub fn valid_frame(f: &Value) -> bool {
    let (Some(ops), Some(receivers)) = (frame_ops(f), frame_receivers(f)) else {
        return false;
    };
    f.is_object()
        && int(f, "v") == Some(1)
        && f.get("kind").and_then(Value::as_str) == Some("frame")
        && s(f, "id").is_some()
        && f.get("policy_key")
            .and_then(Value::as_str)
            .is_some_and(|k| {
                k.len() == 64
                    && k.chars()
                        .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c))
            })
        && s(f, "account").is_some()
        && host_ok(f, "source")
        && path_ok(f, "resource")
        && (none(f, "program") || s(f, "program").is_some())
        && int(f, "exp").is_some()
        && receivers.is_empty() != ops.contains(&"disclose") // receivers iff the frame allows disclosure
}

// -- containment -------------------------------------------------------------------------------------

pub fn grant_within_frame(g: &Value, f: &Value) -> bool {
    let op = str_of(g, "op");
    frame_ops(f).is_some_and(|ops| ops.contains(&op))
        && str_of(g, "account") == str_of(f, "account")
        && str_of(g, "source") == str_of(f, "source")
        && path_covers(str_of(f, "resource"), str_of(g, "resource"))
        && (op != "disclose"
            || frame_receivers(f)
                .is_some_and(|rs| rs.iter().any(|r| receiver_covers(r, str_of(g, "receiver")))))
        && int(g, "exp") <= int(f, "exp")
        && (none(f, "program") || str_of(f, "program") == str_of(g, "program"))
}

/// A derived (delegated) grant may narrow, never widen: same operation, account and source; a resource
/// at or below the parent's; a receiver the parent's covers; no later expiry; no more uses; the parent's
/// instance if it names one. The PROGRAM may differ — that is the delegation.
pub fn grant_within_parent(g: &Value, parent: &Value) -> bool {
    let op = str_of(g, "op");
    op == str_of(parent, "op")
        && str_of(g, "account") == str_of(parent, "account")
        && str_of(g, "source") == str_of(parent, "source")
        && path_covers(str_of(parent, "resource"), str_of(g, "resource"))
        && (op != "disclose" || receiver_covers(str_of(parent, "receiver"), str_of(g, "receiver")))
        && int(g, "exp") <= int(parent, "exp")
        && (none(parent, "uses") || int(g, "uses").is_some_and(|n| Some(n) <= int(parent, "uses")))
        && (none(parent, "instance") || s(parent, "instance") == s(g, "instance"))
}

/// The intersection of two scopes `{op, source, resource[, receiver]}` — what a delegated step may use of
/// its caller's authority. `None` = disjoint.
pub fn intersect(a: &Value, b: &Value) -> Option<Value> {
    let op = op_of(a)?;
    if a.get("op") != b.get("op") || a.get("source") != b.get("source") {
        return None;
    }
    let (ra, rb) = (str_of(a, "resource"), str_of(b, "resource"));
    let res = if path_covers(ra, rb) {
        rb
    } else if path_covers(rb, ra) {
        ra
    } else {
        return None;
    };
    let mut out = json!({"op": op, "source": a.get("source"), "resource": res});
    if op == "disclose" {
        let (ta, tb) = (str_of(a, "receiver"), str_of(b, "receiver"));
        out["receiver"] = if receiver_covers(ta, tb) {
            json!(tb)
        } else if receiver_covers(tb, ta) {
            json!(ta)
        } else {
            return None;
        };
    }
    Some(out)
}

// -- signatures --------------------------------------------------------------------------------------

fn is_hex(x: &str, len: usize, lower_only: bool) -> bool {
    x.len() == len
        && x.chars().all(|c| {
            c.is_ascii_digit()
                || ('a'..='f').contains(&c)
                || (!lower_only && ('A'..='F').contains(&c))
        })
}

fn unhex(x: &str) -> Vec<u8> {
    (0..x.len())
        .step_by(2)
        .filter_map(|i| u8::from_str_radix(&x[i..i + 2], 16).ok())
        .collect()
}

/// Envelope shape + signature; parses the payload. `Err` = the error code (and the signer key when the
/// shape was fine).
fn open(env: Option<&Value>, domain: &[u8]) -> Result<(String, Value), &'static str> {
    let Some(Value::Object(env)) = env else {
        return Err("unsigned");
    };
    let (Some(text), Some(sig), Some(key)) = (
        env.get("payload").and_then(Value::as_str),
        env.get("sig").and_then(Value::as_str),
        env.get("key").and_then(Value::as_str),
    ) else {
        return Err("malformed");
    };
    let key = key.to_lowercase();
    if !is_hex(sig, 128, false) || !is_hex(&key, 64, true) {
        return Err("malformed");
    }
    let kb: Option<[u8; 32]> = unhex(&key).try_into().ok();
    let sb: Option<[u8; 64]> = unhex(sig).try_into().ok();
    let good = match (kb.and_then(|k| VerifyingKey::from_bytes(&k).ok()), sb) {
        (Some(vk), Some(sb)) => {
            let mut msg = domain.to_vec();
            msg.extend_from_slice(text.as_bytes());
            vk.verify_strict(&msg, &Signature::from_bytes(&sb)).is_ok()
        }
        _ => false,
    };
    if !good {
        return Err("bad_signature");
    }
    serde_json::from_str(text)
        .map(|p| (key, p))
        .map_err(|_| "malformed")
}

/// Where a verified grant's authority comes from.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Chain {
    /// `user` | `policy` | `derived`
    pub issuer: Option<&'static str>,
    pub key: Option<String>,
    pub frame: Option<String>,
    /// (id, uses) of each parent, nearest first.
    pub ancestors: Vec<(String, Option<i64>)>,
}

/// A grant that passed `verify_grant`.
#[derive(Debug, Clone)]
pub struct Verified {
    pub grant: Value,
    pub chain: Chain,
}

/// Verify a grant envelope and its chain of authority. Time is NOT checked here (an expired grant is still
/// well-formed; `decide` reports it as expired) — but a revoked frame or parent kills everything issued
/// under it, here and again in `decide`. `Err` = (code, the chain as far as it was established).
pub fn verify_grant(
    env: Option<&Value>,
    approvers: &BTreeMap<String, String>,
    revoked: &BTreeSet<String>,
    required: &str,
) -> Result<Verified, &'static str> {
    verify_at(env, approvers, revoked, required, 0)
}

fn verify_at(
    env: Option<&Value>,
    approvers: &BTreeMap<String, String>,
    revoked: &BTreeSet<String>,
    required: &str,
    depth: usize,
) -> Result<Verified, &'static str> {
    let (key, g) = open(env, GRANT_DOMAIN)?;
    if !valid_grant(&g) {
        return Err("malformed");
    }
    let env = env.and_then(Value::as_object).ok_or("unsigned")?;
    let mut chain = Chain {
        key: Some(key.clone()),
        ..Default::default()
    };
    if let Some(parent_env) = env.get("parent") {
        // a derived grant: authority comes from its parent
        if depth >= MAX_CHAIN {
            return Err("parent_invalid");
        }
        let parent = verify_at(Some(parent_env), approvers, revoked, required, depth + 1)
            .map_err(|_| "parent_invalid")?;
        let pid = str_of(&parent.grant, "id").to_string();
        if revoked.contains(&pid) {
            return Err("parent_revoked");
        }
        // only the parent's issuer (or a user) may derive
        if parent.chain.key.as_ref() != Some(&key) && !approvers.contains_key(&key) {
            return Err("unknown_key");
        }
        if !grant_within_parent(&g, &parent.grant) {
            return Err("outside_parent");
        }
        chain.issuer = Some("derived");
        chain.frame = parent.chain.frame.clone();
        chain.ancestors = vec![(pid, int(&parent.grant, "uses"))];
        chain.ancestors.extend(parent.chain.ancestors);
        return Ok(Verified { grant: g, chain });
    }
    if let Some(class) = approvers.get(&key) {
        // signed by a user key directly
        if env.contains_key("frame") {
            return Err("malformed"); // a user grant carries no frame (one authority, not two)
        }
        if !class_satisfies(class, required) {
            return Err("class_insufficient");
        }
        chain.issuer = Some("user");
        return Ok(Verified { grant: g, chain });
    }
    let Some(frame_env) = env.get("frame") else {
        return Err("unknown_key"); // not a user key and no frame vouching for it
    };
    let (fkey, f) = match open(Some(frame_env), FRAME_DOMAIN) {
        Ok(x) => x,
        Err("bad_signature") => return Err("frame_bad_signature"),
        Err(_) => return Err("frame_malformed"),
    };
    if !valid_frame(&f) {
        return Err("frame_malformed");
    }
    let Some(fclass) = approvers.get(&fkey) else {
        return Err("frame_untrusted"); // the frame is not signed by a trusted user key
    };
    if !class_satisfies(fclass, required) {
        return Err("class_insufficient");
    }
    if str_of(&f, "policy_key") != key {
        return Err("frame_key_mismatch"); // the frame authorizes another policy key
    }
    let fid = str_of(&f, "id").to_string();
    if revoked.contains(&fid) {
        return Err("frame_revoked");
    }
    if !grant_within_frame(&g, &f) {
        return Err("outside_frame");
    }
    chain.issuer = Some("policy");
    chain.frame = Some(fid);
    Ok(Verified { grant: g, chain })
}

// -- the decision ------------------------------------------------------------------------------------

fn in_declared(decl: &Value, q: &Value) -> bool {
    if decl.get("op") != q.get("op") {
        return false;
    }
    if str_of(q, "op") == "disclose" {
        let from = decl.get("from").and_then(Value::as_array);
        let origins = q.get("origins").and_then(Value::as_array);
        return receiver_covers(str_of(decl, "receiver"), str_of(q, "receiver"))
            && match (from, origins) {
                (Some(from), Some(origins)) => origins.iter().all(|u| {
                    from.iter().any(|x| {
                        str_of(x, "source") == str_of(u, "source")
                            && path_covers(str_of(x, "resource"), str_of(u, "resource"))
                    })
                }),
                _ => false,
            };
    }
    str_of(decl, "source") == str_of(q, "source")
        && path_covers(str_of(decl, "resource"), str_of(q, "resource"))
}

/// Why a matching grant cannot be used right now, or `None`. Revocation and use bounds apply along the
/// whole chain.
fn dead(
    v: &Verified,
    now: i64,
    revoked: &BTreeSet<String>,
    used: &BTreeMap<String, i64>,
) -> Option<&'static str> {
    let id = str_of(&v.grant, "id").to_string();
    let mut bounds: Vec<(String, Option<i64>)> = vec![(id, int(&v.grant, "uses"))];
    bounds.extend(v.chain.ancestors.iter().cloned());
    if bounds.iter().any(|(i, _)| revoked.contains(i))
        || v.chain.frame.as_ref().is_some_and(|f| revoked.contains(f))
    {
        return Some("revoked");
    }
    if int(&v.grant, "exp").is_none_or(|e| e <= now) {
        return Some("expired");
    }
    if bounds
        .iter()
        .any(|(i, n)| n.is_some_and(|n| used.get(i).copied().unwrap_or(0) >= n))
    {
        return Some("exhausted");
    }
    None
}

/// Decide ONE access request. `decl` = `declared(protocol, cap)`; `grants` = VERIFIED grants; `revoked` =
/// revoked grant/frame ids; `used` = accesses already counted per grant id (an access counts against the
/// grant relied on AND each of its ancestors). Returns `{decision, code}` plus `grants` (ids relied on)
/// when granted, or `missing` (indexes of the uncovered units) when a grant is needed.
pub fn decide(
    decl: Option<&Value>,
    q: &Value,
    grants: &[Verified],
    now: i64,
    revoked: &BTreeSet<String>,
    used: &BTreeMap<String, i64>,
) -> Value {
    let Some(decl) = decl else {
        return json!({"decision": "denied", "code": "undeclared"});
    };
    if !valid_request(q) {
        return json!({"decision": "denied", "code": "unsupported"});
    }
    if !in_declared(decl, q) {
        return json!({"decision": "denied", "code": "outside_declared_scope"});
    }
    let op = str_of(q, "op");
    let single = [q.clone()];
    let units: &[Value] = if op == "disclose" {
        q.get("origins")
            .and_then(Value::as_array)
            .map(Vec::as_slice)
            .unwrap_or(&[])
    } else {
        &single
    };
    let (mut relied, mut missing, mut why): (Vec<String>, Vec<usize>, Option<&str>) =
        (Vec::new(), Vec::new(), None);
    for (i, u) in units.iter().enumerate() {
        let mut cands: Vec<&Verified> = grants
            .iter()
            .filter(|v| {
                let g = &v.grant;
                str_of(g, "program") == str_of(q, "program")
                    && (none(g, "instance") || s(g, "instance") == s(q, "instance"))
                    && str_of(g, "op") == op
                    && str_of(g, "account") == str_of(u, "account")
                    && str_of(g, "source") == str_of(u, "source")
                    && path_covers(str_of(g, "resource"), str_of(u, "resource"))
                    && (op != "disclose"
                        || receiver_covers(str_of(g, "receiver"), str_of(q, "receiver")))
            })
            .collect();
        cands.sort_by(|a, b| str_of(&a.grant, "id").cmp(str_of(&b.grant, "id")));
        if let Some(live) = cands.iter().find(|v| dead(v, now, revoked, used).is_none()) {
            let id = str_of(&live.grant, "id").to_string();
            if !relied.contains(&id) {
                relied.push(id);
            }
            continue;
        }
        missing.push(i);
        if why.is_none() {
            why = Some(match cands.first() {
                Some(v) => dead(v, now, revoked, used).unwrap_or("no_grant"),
                None => "no_grant",
            });
        }
    }
    if !missing.is_empty() {
        return json!({"decision": "needs_grant", "code": why.unwrap_or("no_grant"), "missing": missing});
    }
    json!({"decision": "granted", "code": "ok", "grants": relied})
}
