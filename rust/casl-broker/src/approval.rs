//! Signed approvals + request digests — mirrors `src/casl/approval.py` and `egress.RequestSpec.digest`.
//!
//! A signed approval binds a HUMAN to the broker by a signature the calling agent cannot produce
//! (it does not hold the key). The envelope is `{payload, sig, key}`; the signed bytes are
//! `b"casl-approval-v1\n" + payload` — the exact payload text, so no cross-language JSON
//! canonicalization is involved. The payload commits the signer to one request digest, at one site,
//! under one capability, for one program version, once, before `exp`.
//!
//! The request digest, by contrast, IS recomputed on both sides, so `request_digest` reproduces
//! Python's `json.dumps(..., sort_keys=True, separators=(",", ":"))` byte for byte (ASCII-escaped).
//! Both are pinned by the signed conformance corpus (`tests/test_approval_signed.py`).

use std::collections::{BTreeMap, BTreeSet};

use ed25519_dalek::{Signature, VerifyingKey};
use serde_json::Value;

pub const DOMAIN: &[u8] = b"casl-approval-v1\n";
/// Approver classes, ascending strength: `human` (a human holds the key) < `personal` (a named person).
pub const CLASSES: [&str; 2] = ["human", "personal"];

pub fn class_satisfies(have: &str, need: &str) -> bool {
    match (
        CLASSES.iter().position(|c| *c == have),
        CLASSES.iter().position(|c| *c == need),
    ) {
        (Some(h), Some(n)) => h >= n,
        _ => false,
    }
}

/// `<pubkey-hex>=<class>` entries separated by commas/newlines. Malformed entries are dropped
/// (deny-by-default: an unparseable key approves nothing).
pub fn parse_approvers(text: &str) -> BTreeMap<String, String> {
    let mut out = BTreeMap::new();
    for part in text.replace('\n', ",").split(',') {
        let part = part.split('#').next().unwrap_or("").trim();
        if let Some((k, c)) = part.split_once('=') {
            let (k, c) = (k.trim().to_lowercase(), c.trim().to_lowercase());
            if k.len() == 64
                && k.chars().all(|ch| ch.is_ascii_hexdigit())
                && CLASSES.contains(&c.as_str())
            {
                out.insert(k, c);
            }
        }
    }
    out
}

fn hex_decode(s: &str) -> Option<Vec<u8>> {
    if !s.len().is_multiple_of(2) || !s.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok())
        .collect()
}

/// The stable content digest of an outbound request; `None` = not a well-formed object ⇒ DENY.
pub fn request_digest(obj: Option<&Value>) -> Option<String> {
    crate::egress::RequestSpec::from_obj(obj).map(|r| r.digest())
}

/// A verified approval: the request digest the signer committed to + the approver class of the key.
pub struct Verified {
    pub request: String,
    pub class: String,
    pub nonce: String,
    pub program: String,
    pub exp: i64,
    pub key: String,
    /// The target account the approval names (identity of the broker-held credential), if any.
    pub account: Option<String>,
    /// The workflow instance and step the approval names, if it is for a step of an instance.
    pub instance: Option<String>,
    pub step: Option<i64>,
}

/// A typed denial: a stable code (compared cross-implementation) + a human-readable reason.
pub struct Denied {
    pub code: &'static str,
    pub reason: String,
}

fn deny(code: &'static str, reason: impl Into<String>) -> Result<Verified, Denied> {
    Err(Denied {
        code,
        reason: reason.into(),
    })
}

/// Check a signed approval envelope. Order: structure → trust store → signature → only THEN is the
/// payload parsed and believed. A successful check records the nonce (one approval ⇒ one token).
#[allow(clippy::too_many_arguments)]
pub fn verify_signed(
    env: Option<&Value>,
    approvers: &BTreeMap<String, String>,
    program: Option<&str>,
    cap: &str,
    site: &str,
    now: i64,
    seen_nonces: &mut BTreeSet<String>,
    required: &str,
    account: Option<&str>,
) -> Result<Verified, Denied> {
    let Some(Value::Object(env)) = env else {
        return deny(
            "unsigned",
            "a signed approval is required (an `approved` assertion is not enough)",
        );
    };
    let (Some(text), Some(sig), Some(key)) = (
        env.get("payload").and_then(Value::as_str),
        env.get("sig").and_then(Value::as_str),
        env.get("key").and_then(Value::as_str),
    ) else {
        return deny(
            "malformed",
            "approval envelope needs string payload/sig/key",
        );
    };
    let key = key.to_lowercase();
    let Some(class) = approvers.get(&key) else {
        return deny(
            "unknown_key",
            "the signing key is not in the broker's trust store",
        );
    };
    let sig_bytes: Option<[u8; 64]> = if sig.len() == 128 {
        hex_decode(sig).and_then(|v| v.try_into().ok())
    } else {
        None
    };
    let Some(sig_bytes) = sig_bytes else {
        return deny("malformed", "sig is not 64 hex-encoded bytes");
    };
    let key_bytes: Option<[u8; 32]> = hex_decode(&key).and_then(|v| v.try_into().ok());
    let verified = key_bytes
        .and_then(|kb| VerifyingKey::from_bytes(&kb).ok())
        .map(|vk| {
            let mut msg = DOMAIN.to_vec();
            msg.extend_from_slice(text.as_bytes());
            vk.verify_strict(&msg, &Signature::from_bytes(&sig_bytes))
                .is_ok()
        })
        .unwrap_or(false);
    if !verified {
        return deny(
            "bad_signature",
            "signature does not verify over this payload",
        );
    }
    let p: Option<Value> = serde_json::from_str(text).ok();
    let field = |k: &str| -> Option<&str> {
        p.as_ref()
            .and_then(|p| p.get(k))
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
    };
    let int = |k: &str| -> Option<i64> {
        p.as_ref()
            .and_then(|p| p.get(k))
            .filter(|v| v.is_i64() || v.is_u64())
            .and_then(Value::as_i64)
    };
    let (Some(1), Some("action"), Some(pp), Some(pc), Some(ps), Some(pr), Some(pn), Some(exp)) = (
        int("v"),
        field("kind"),
        field("program"),
        field("cap"),
        field("site"),
        field("request"),
        field("nonce"),
        int("exp"),
    ) else {
        return deny("malformed", "payload is not a v1 action approval");
    };
    // optional `account`: absent, or a non-empty string
    let pa = match p.as_ref().and_then(|p| p.get("account")) {
        None => None,
        Some(Value::String(s)) if !s.is_empty() => Some(s.as_str()),
        Some(_) => return deny("malformed", "payload is not a v1 action approval"),
    };
    // optional `instance` + `step` (a step of a workflow instance): both or neither
    let pi = match p.as_ref().and_then(|p| p.get("instance")) {
        None => None,
        Some(Value::String(s)) if !s.is_empty() => Some(s.clone()),
        Some(_) => return deny("malformed", "payload is not a v1 action approval"),
    };
    let pst = match p.as_ref().and_then(|p| p.get("step")) {
        None => None,
        Some(v) if v.as_i64().is_some_and(|n| n >= 0) && (v.is_i64() || v.is_u64()) => v.as_i64(),
        Some(_) => return deny("malformed", "payload is not a v1 action approval"),
    };
    if pi.is_some() != pst.is_some() {
        return deny("malformed", "payload is not a v1 action approval");
    }
    if program.is_none_or(|have| have.is_empty() || have != pp) {
        return deny(
            "program_mismatch",
            "approval is for a different program version",
        );
    }
    if pc != cap || ps != site {
        return deny(
            "binding_mismatch",
            "approval is for a different capability/site",
        );
    }
    if pa != account {
        // `account` = the identity of the credential the broker holds for this capability (None = none).
        // Both directions deny: another principal, no principal named although a credential will be
        // used, or a principal the broker cannot vouch for.
        return deny(
            "account_mismatch",
            "approval is for a different target account than the broker holds",
        );
    }
    if exp <= now {
        return deny("expired", "approval has expired");
    }
    if !class_satisfies(class, required) {
        return deny(
            "class_insufficient",
            format!("capability {cap:?} needs a {required:?} approver, key is {class:?}"),
        );
    }
    if seen_nonces.contains(pn) {
        return deny("replayed", "this approval was already used");
    }
    seen_nonces.insert(pn.to_string());
    Ok(Verified {
        request: pr.to_string(),
        class: class.clone(),
        nonce: pn.to_string(),
        program: pp.to_string(),
        exp,
        key,
        account: pa.map(str::to_string),
        instance: pi,
        step: pst,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn class_order() {
        assert!(class_satisfies("personal", "human"));
        assert!(!class_satisfies("human", "personal"));
        assert!(!class_satisfies("robot", "human"));
    }
}
