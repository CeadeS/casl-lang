//! Generic MEDIATED EGRESS for the broker — mirrors `src/casl/egress.py` (the reference).
//!
//! The broker performs an outbound request on a program's behalf under an abstract capability, gated by
//! a DESTINATION POLICY that runs before consent is consumed and before any connect. No domain logic
//! (no "calendar", no "tasks"): a target system is a host allowlist + a transport.
//!
//! The destination check is deliberately STRICTER than the Python reference (which leans on `urlparse`):
//! only the plain form `https://host[:port][/...]` with an allowlisted DNS name passes. Userinfo,
//! brackets, backslashes, non-ASCII and every IP literal are refused, so URL-parser differentials cannot
//! open a gap: whatever passes here also passes the reference, never the other way round.
//!
//! No live transport is wired yet: `MockEgress` serves the conformance corpus, `NoTransport` refuses.
//! The live HTTPS leaf is a separate, reviewed step.

use serde_json::Value;

use crate::journal::sha256_hex;

/// An outbound request (`egress.RequestSpec`).
#[derive(Debug, Clone, PartialEq)]
pub struct RequestSpec {
    pub method: String,
    pub url: String,
    pub headers: Vec<(String, String)>,
    pub body: String,
}

/// A JSON string literal exactly as Python's `json.dumps` (ensure_ascii=True) writes it.
pub(crate) fn py_json_string(s: &str, out: &mut String) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{08}' => out.push_str("\\b"),
            '\u{0c}' => out.push_str("\\f"),
            ' '..='~' => out.push(c),
            _ => {
                let mut buf = [0u16; 2];
                for u in c.encode_utf16(&mut buf) {
                    out.push_str(&format!("\\u{u:04x}"));
                }
            }
        }
    }
    out.push('"');
}

/// Python's `str(obj.get(key, default))` for the JSON values a request field can hold.
fn py_str(v: Option<&Value>, default: &str) -> String {
    match v {
        None => default.to_string(),
        Some(Value::String(s)) => s.clone(),
        Some(Value::Null) => "None".into(),
        Some(Value::Bool(true)) => "True".into(),
        Some(Value::Bool(false)) => "False".into(),
        Some(other) => other.to_string(),
    }
}

impl RequestSpec {
    /// `egress.RequestSpec.from_obj`. `None` = not a well-formed object ⇒ the caller must DENY.
    pub fn from_obj(obj: Option<&Value>) -> Option<RequestSpec> {
        let empty = serde_json::Map::new();
        let map = match obj {
            None | Some(Value::Null) => &empty,
            Some(Value::Object(m)) => m,
            Some(_) => return None,
        };
        let mut headers: Vec<(String, String)> = Vec::new();
        match map.get("headers") {
            None | Some(Value::Null) => {}
            Some(Value::Object(h)) => {
                for (k, v) in h {
                    headers.push((k.clone(), py_str(Some(v), "")));
                }
            }
            Some(Value::Array(a)) => {
                for pair in a {
                    match pair.as_array().map(|p| p.as_slice()) {
                        Some([k, v]) => headers.push((py_str(Some(k), ""), py_str(Some(v), ""))),
                        _ => return None,
                    }
                }
            }
            Some(_) => return None,
        }
        Some(RequestSpec {
            method: py_str(map.get("method"), "GET"),
            url: py_str(map.get("url"), ""),
            headers,
            body: py_str(map.get("body"), ""),
        })
    }

    /// The stable content digest — reproduces `json.dumps({"m","u","h","b"}, sort_keys=True,
    /// separators=(",", ":"))` of the reference byte for byte, then sha256.
    pub fn digest(&self) -> String {
        let mut headers = self.headers.clone();
        headers.sort();
        let mut canon = String::from("{\"b\":");
        py_json_string(&self.body, &mut canon);
        canon.push_str(",\"h\":[");
        for (i, (k, v)) in headers.iter().enumerate() {
            if i > 0 {
                canon.push(',');
            }
            canon.push('[');
            py_json_string(k, &mut canon);
            canon.push(',');
            py_json_string(v, &mut canon);
            canon.push(']');
        }
        canon.push_str("],\"m\":");
        py_json_string(&self.method.to_uppercase(), &mut canon);
        canon.push_str(",\"u\":");
        py_json_string(&self.url, &mut canon);
        canon.push('}');
        sha256_hex(canon.as_bytes())
    }
}

/// The destination policy (SSRF guard): `Ok(())` only for `https://<allowlisted dns name>[:port][/...]`.
pub fn check_destination(url: &str, allow_hosts: &[String]) -> Result<(), String> {
    let rest = match url.get(..8) {
        Some(p) if p.eq_ignore_ascii_case("https://") => &url[8..],
        _ => return Err("only https:// destinations are allowed".into()),
    };
    if !url.is_ascii() || url.bytes().any(|b| b <= b' ' || b == 0x7f || b == b'\\') {
        return Err("url contains characters outside the strict form".into());
    }
    let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
    let (host, port) = match authority.split_once(':') {
        Some((h, p)) => (h, Some(p)),
        None => (authority, None),
    };
    if let Some(p) = port {
        if p.is_empty() || p.len() > 5 || !p.bytes().all(|b| b.is_ascii_digit()) {
            return Err("malformed port".into());
        }
    }
    let host = host.to_ascii_lowercase();
    if host.is_empty()
        || !host
            .bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'.' || b == b'-')
    {
        return Err("host is not a plain DNS name (no userinfo, brackets or IP forms)".into());
    }
    if host.parse::<std::net::Ipv4Addr>().is_ok() || host == "localhost" {
        return Err(format!(
            "destination {host:?} is an IP literal or loopback name (blocked — SSRF guard)"
        ));
    }
    if !allow_hosts.iter().any(|h| h.to_ascii_lowercase() == host) {
        return Err(format!(
            "destination {host:?} not in the manifest allowlist"
        ));
    }
    Ok(())
}

/// The outcome a response status proves (`egress.classify`): 2xx performed · 4xx rejected · else unknown.
pub fn classify(status: i64) -> &'static str {
    match status {
        200..=299 => "performed",
        400..=499 => "rejected",
        _ => "unknown",
    }
}

pub struct EgressResponse {
    pub status: i64,
    pub body: String,
}

/// A send that produced no response — what is KNOWN about the request's fate. A transport that cannot
/// tell must report `Unknown`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum TransportFailure {
    /// Provably never left (refused connection, DNS failure): nothing happened.
    NotSent,
    /// May have reached the target (timeout, reset after send).
    Unknown,
}

impl TransportFailure {
    pub fn outcome(self) -> &'static str {
        match self {
            TransportFailure::NotSent => "not_sent",
            TransportFailure::Unknown => "unknown",
        }
    }
}

pub trait EgressTransport {
    fn send(&mut self, req: &RequestSpec) -> Result<EgressResponse, TransportFailure>;
}

/// Offline transport: a canned response or failure; records calls.
pub struct MockEgress {
    pub status: i64,
    pub body: String,
    pub fail: Option<TransportFailure>,
    pub calls: Vec<RequestSpec>,
}

impl MockEgress {
    /// `"200"`, `"404"`, `"not_sent"`, `"unknown"` (anything unparseable ⇒ unknown, the conservative reading).
    pub fn from_spec(spec: &str) -> MockEgress {
        let (status, fail) = match spec.trim() {
            "not_sent" => (0, Some(TransportFailure::NotSent)),
            s => match s.parse::<i64>() {
                Ok(n) => (n, None),
                Err(_) => (0, Some(TransportFailure::Unknown)),
            },
        };
        MockEgress {
            status,
            body: "OK".into(),
            fail,
            calls: Vec::new(),
        }
    }
}

impl EgressTransport for MockEgress {
    fn send(&mut self, req: &RequestSpec) -> Result<EgressResponse, TransportFailure> {
        self.calls.push(req.clone());
        match self.fail {
            Some(f) => Err(f),
            None => Ok(EgressResponse {
                status: self.status,
                body: self.body.clone(),
            }),
        }
    }
}

/// The placeholder until the live HTTPS leaf exists: nothing is ever sent.
pub struct NoTransport;

impl EgressTransport for NoTransport {
    fn send(&mut self, _req: &RequestSpec) -> Result<EgressResponse, TransportFailure> {
        Err(TransportFailure::NotSent)
    }
}

/// A capability the broker PERFORMS: its destination allowlist + transport.
pub struct Mediated {
    pub allow_hosts: Vec<String>,
    pub transport: Box<dyn EgressTransport>,
    /// Headers the BROKER adds on the wire (e.g. `Authorization`). The secret lives only here: the
    /// calling agent never sees it, so it cannot reach the target system around the broker.
    pub inject: Vec<(String, String)>,
}

impl Mediated {
    /// The first header of `req` that collides (case-insensitively) with a broker-held one.
    pub fn conflicting_header<'a>(&self, req: &'a RequestSpec) -> Option<&'a str> {
        req.headers
            .iter()
            .map(|(k, _)| k.as_str())
            .find(|k| self.inject.iter().any(|(i, _)| i.eq_ignore_ascii_case(k)))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn allow() -> Vec<String> {
        vec![
            "api.example.com".into(),
            "10.0.0.5".into(),
            "localhost".into(),
        ]
    }

    #[test]
    fn destination_policy_is_strict() {
        let a = allow();
        for ok in [
            "https://api.example.com/x",
            "HTTPS://API.example.com:443/x?y#z",
            "https://api.example.com",
        ] {
            assert!(check_destination(ok, &a).is_ok(), "{ok}");
        }
        for bad in [
            "http://api.example.com/x",
            "https://evil.example.net/",
            "https://10.0.0.5/",
            "https://127.0.0.1/",
            "https://localhost/",
            "https://api.example.com@evil.example.net/",
            "https://evil.example.net\\@api.example.com/",
            "https://[::1]/",
            "https://api.example.com:x/",
            "https://api.example.com:/",
            "https://api.exämple.com/",
            "https:// api.example.com/",
            "https:///x",
            "",
            "api.example.com",
        ] {
            assert!(check_destination(bad, &a).is_err(), "{bad}");
        }
    }

    #[test]
    fn digest_is_spelling_independent() {
        let a = RequestSpec::from_obj(Some(
            &json!({"method":"post","url":"https://x/y","body":"ä",
            "headers":{"b":"2","a":"1"}}),
        ))
        .unwrap();
        let b = RequestSpec::from_obj(Some(
            &json!({"method":"POST","url":"https://x/y","body":"ä",
            "headers":[["a","1"],["b","2"]]}),
        ))
        .unwrap();
        assert_eq!(a.digest(), b.digest());
        assert_eq!(
            RequestSpec::from_obj(None).unwrap().digest(),
            RequestSpec::from_obj(Some(&json!({}))).unwrap().digest()
        );
        assert!(RequestSpec::from_obj(Some(&json!("not an object"))).is_none());
    }

    #[test]
    fn escapes_like_python() {
        let mut s = String::new();
        py_json_string("a\"b\\c\nä😀\u{7f}", &mut s);
        assert_eq!(s, "\"a\\\"b\\\\c\\n\\u00e4\\ud83d\\ude00\\u007f\"");
    }

    #[test]
    fn status_classes() {
        assert_eq!(classify(201), "performed");
        assert_eq!(classify(409), "rejected");
        assert_eq!(classify(503), "unknown");
        assert_eq!(classify(302), "unknown");
    }
}
