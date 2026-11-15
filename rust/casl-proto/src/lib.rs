//! `casl-proto` — the CASL broker **wire protocol** (JSON-RPC 2.0).
//!
//! Pure Rust (serde only). This crate is the single source of truth for the broker <-> binding
//! contract (see `docs/broker-protocol.md`): the message envelope, the typed method params/results,
//! and newline-delimited framing. The per-language bindings are generated against THIS schema; the
//! broker (`casl-broker`) and any Rust client share these types directly.
//!
//! Trust note: this crate carries no policy — only the data shapes. All enforcement lives in the
//! broker (the reference monitor).

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::io::{self, Write};

/// Protocol version advertised at `initialize` (capability-negotiated; see docs/broker-protocol.md).
pub const PROTOCOL_VERSION: &str = "0.1";

/// JSON-RPC error codes used by the broker.
pub mod codes {
    pub const PARSE_ERROR: i64 = -32700;
    pub const METHOD_NOT_FOUND: i64 = -32601;
    pub const NOT_INITIALIZED: i64 = -32002;
    pub const NO_MODEL: i64 = -32010;
    pub const CAPABILITY_DENIED: i64 = -32011;
    pub const INTERNAL: i64 = -32603;
}

/// A JSON-RPC 2.0 request. `id` is kept as a raw `Value` (number|string|null) and echoed verbatim.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Request {
    pub jsonrpc: String,
    #[serde(default)]
    pub id: Value,
    pub method: String,
    #[serde(default)]
    pub params: Value,
}

/// A JSON-RPC 2.0 error object.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
}

/// A JSON-RPC 2.0 response: exactly one of `result` / `error` is present.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Response {
    pub jsonrpc: String,
    pub id: Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<RpcError>,
}

impl Response {
    pub fn ok(id: Value, result: Value) -> Self {
        Response {
            jsonrpc: "2.0".into(),
            id,
            result: Some(result),
            error: None,
        }
    }
    pub fn err(id: Value, code: i64, message: impl Into<String>) -> Self {
        Response {
            jsonrpc: "2.0".into(),
            id,
            result: None,
            error: Some(RpcError {
                code,
                message: message.into(),
            }),
        }
    }
}

// ---- typed method params / results ----------------------------------------

/// `initialize` params: the artifact declares the broker capabilities it intends to use (`llm:claude`,
/// `websocket`, `tool:mail`, …). The declaration drives monitoring + grade; it is trusted as an
/// attestation for human-authored artifacts and must be *enforced* (confinement/static check) for
/// untrusted/LLM-generated ones. (docs/engineering-plan.md §0.5)
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct InitializeParams {
    #[serde(default)]
    pub client: String,
    #[serde(default)]
    pub version: String,
    #[serde(default)]
    pub capabilities: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InitializeResult {
    pub server: String,
    pub version: String,
    pub capabilities: Vec<String>,
}

fn default_producer() -> String {
    "A".into()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OracleParams {
    pub site: String,
    #[serde(default)]
    pub question: String,
    #[serde(default)]
    pub budget: i64,
    #[serde(default = "default_producer")]
    pub producer: String,
    /// Optional LLM provider to route through (e.g. "claude"); requires the artifact declared `llm:<provider>`.
    #[serde(default)]
    pub provider: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OracleResult {
    pub verdict: String, // "ok" | "violation" | "refusal"
    pub answer: String,
    pub cost: Option<i64>,
    pub measured_cost: Option<i64>,
    pub blame: Option<String>,
    pub reason: String,
    pub branch: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EffectParams {
    pub site: String,
    pub tool: String,
    #[serde(default)]
    pub args: Value,
    /// (A) one-shot consent token from the approval gate; REQUIRED for an irreversible capability.
    #[serde(default)]
    pub approval: Option<String>,
    /// The concrete outbound request (method/url/headers/body). A request-bound consent token is valid
    /// only for the request whose digest it was minted for.
    #[serde(default)]
    pub request: Option<Value>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct EffectResult {
    pub allowed: bool,
    pub tool: String,
    pub site: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub note: Option<String>,
    // -- mediated egress (a capability the broker PERFORMS) --
    /// `performed` | `rejected` | `not_sent` | `unknown` (sent, fate unproven) | `unresolved` (blocked:
    /// an earlier attempt of this request is still unknown).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub outcome: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub performed: Option<bool>,
    /// The effect id (= request digest) — the handle for `resolve`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub effect: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub body: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub receipt: Option<Value>,
}

/// `resolve` params: the clarified outcome of an effect whose outcome was unknown.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ResolveParams {
    #[serde(default)]
    pub effect: String,
    #[serde(default)]
    pub outcome: String,
    #[serde(default)]
    pub note: String,
}

/// `consent` params: the approval gate's decision for an irreversible effect at a site (A).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsentParams {
    pub site: String,
    pub tool: String,
    #[serde(default)]
    pub approved: bool,
    /// Legacy (unsigned) request-binding: the request the gate disclosed; the token binds to its digest.
    #[serde(default)]
    pub request: Option<Value>,
    /// A SIGNED approval envelope `{payload, sig, key}`. Required when the broker has a trust store —
    /// then `approved` alone mints nothing. Kept as a raw value so a malformed envelope is a typed denial.
    #[serde(default)]
    pub signed: Option<Value>,
}

/// `consent` result: a one-shot token (when granted) bound to (tool, site), for the matching effect.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConsentResult {
    pub granted: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub token: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    /// Signed mode: a stable outcome code (`ok`, `unsigned`, `unknown_key`, `bad_signature`, ...).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub code: Option<String>,
    /// Signed mode: the approver class of the verifying key (`human` | `personal`).
    #[serde(default, rename = "class", skip_serializing_if = "Option::is_none")]
    pub approver_class: Option<String>,
}

// ---- newline-delimited framing (MCP/LSP-style) ----------------------------

/// Write one response as a single newline-terminated JSON line and flush.
pub fn write_message<W: Write>(w: &mut W, resp: &Response) -> io::Result<()> {
    let s = serde_json::to_string(resp).map_err(io::Error::other)?;
    w.write_all(s.as_bytes())?;
    w.write_all(b"\n")?;
    w.flush()
}

/// Parse one request line. A malformed line yields a parse-error `Err(String)` the caller maps to a
/// `codes::PARSE_ERROR` response.
pub fn parse_request(line: &str) -> Result<Request, String> {
    serde_json::from_str(line).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn request_roundtrips_and_params_decode() {
        let r = Request {
            jsonrpc: "2.0".into(),
            id: json!(1),
            method: "oracle".into(),
            params: json!({"site": "Draft", "question": "q", "budget": 100}),
        };
        let s = serde_json::to_string(&r).unwrap();
        let back: Request = serde_json::from_str(&s).unwrap();
        assert_eq!(back.method, "oracle");
        let p: OracleParams = serde_json::from_value(back.params).unwrap();
        assert_eq!(p.site, "Draft");
        assert_eq!(p.budget, 100);
        assert_eq!(p.producer, "A"); // defaulted
    }

    #[test]
    fn ok_response_has_result_only() {
        let s = serde_json::to_string(&Response::ok(json!(1), json!({"x": 1}))).unwrap();
        assert!(s.contains("\"result\""));
        assert!(!s.contains("\"error\""));
    }

    #[test]
    fn err_response_has_error_only() {
        let s = serde_json::to_string(&Response::err(json!(1), codes::METHOD_NOT_FOUND, "nope"))
            .unwrap();
        assert!(s.contains("\"error\""));
        assert!(!s.contains("\"result\""));
    }

    #[test]
    fn parse_request_rejects_garbage() {
        assert!(parse_request("not json").is_err());
    }
}
