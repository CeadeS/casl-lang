//! Context scope selectors — mirrors the selector part of `src/casl/core.py` (docs/context-grants.md).
//!
//! WHICH data a capability may search, read or disclose is declared in a structured `context` clause and
//! validated here. The selector grammar is deliberately small: whatever is not exactly of this form is
//! UNSUPPORTED and fails closed (rejected at parse, denied at match). Pinned to the Python reference by
//! the context corpus (`rust/casl-broker/tests/context_corpus.json`).

use crate::Capability;

pub const CONTEXT_OPS: [&str; 3] = ["search", "read", "disclose"];

/// The context scope a capability REQUESTS (a declaration, not an authorization).
/// search/read: `source` + `resource`. disclose: `receiver` + `sources` (the capabilities whose content
/// may be passed on). Unused fields are empty.
#[derive(Debug, Clone, PartialEq, Default)]
pub struct ContextDecl {
    pub op: String,
    pub source: String,
    pub resource: String,
    pub receiver: String,
    pub sources: Vec<String>,
}

fn path_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || "._~!$&'()+,;=:@-".contains(c)
}

/// A SOURCE / endpoint host: a plain lower-case DNS name. No IP literal, no `localhost`, no port.
pub fn valid_host(h: &str) -> bool {
    !h.is_empty()
        && h.len() <= 253
        && h.chars()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '.' || c == '-')
        && !h.starts_with(['.', '-'])
        && !h.ends_with(['.', '-'])
        && !h.contains("..")
        && h.chars().any(|c| c.is_ascii_lowercase())
        && h != "localhost"
}

/// A RESOURCE scope / endpoint path: absolute, segment-wise, unambiguous. No query, fragment, wildcard,
/// percent-escape, empty/`.`/`..` segment or trailing slash (other than the root `/`).
pub fn valid_path(p: &str) -> bool {
    if p.is_empty() || p.len() > 2048 || !p.starts_with('/') {
        return false;
    }
    if p == "/" {
        return true;
    }
    p[1..]
        .split('/')
        .all(|seg| !seg.is_empty() && seg != "." && seg != ".." && seg.chars().all(path_char))
}

/// `scope` covers `path` iff both are valid and `path` is `scope` itself or lies below it, SEGMENT-wise
/// (`/a/b` covers `/a/b/c`, not `/a/bc`). Case-sensitive.
pub fn path_covers(scope: &str, path: &str) -> bool {
    valid_path(scope)
        && valid_path(path)
        && (scope == "/"
            || path == scope
            || path
                .strip_prefix(scope)
                .is_some_and(|rest| rest.starts_with('/')))
}

/// A parsed disclosure receiver.
#[derive(Debug, Clone, PartialEq)]
pub enum Receiver {
    Workflow(String),
    Endpoint {
        host: String,
        path: String,
        model: String,
    },
}

/// `endpoint:<host><path>[#<model>]` (a resolved model/provider endpoint) or `workflow:<Name>`.
/// `None` = unsupported.
pub fn parse_receiver(r: &str) -> Option<Receiver> {
    if let Some(name) = r.strip_prefix("workflow:") {
        let ok = !name.is_empty()
            && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
            && !name.starts_with(|c: char| c.is_ascii_digit());
        return ok.then(|| Receiver::Workflow(name.to_string()));
    }
    let rest = r.strip_prefix("endpoint:")?;
    let (rest, model) = match rest.split_once('#') {
        Some((a, m)) => (a, Some(m)),
        None => (rest, None),
    };
    let slash = rest.find('/').filter(|i| *i > 0)?;
    let (host, path) = rest.split_at(slash);
    if !valid_host(host) || !valid_path(path) {
        return None;
    }
    if let Some(m) = model {
        let ok = !m.is_empty()
            && m.chars()
                .all(|c| c.is_ascii_alphanumeric() || "._:-".contains(c));
        if !ok {
            return None;
        }
    }
    Some(Receiver::Endpoint {
        host: host.to_string(),
        path: path.to_string(),
        model: model.unwrap_or("").to_string(),
    })
}

/// `scope` covers `receiver`: the same workflow; or the same endpoint host, a covering path and — if the
/// scope names a model — exactly that model (a scope without a model covers every model there).
pub fn receiver_covers(scope: &str, receiver: &str) -> bool {
    match (parse_receiver(scope), parse_receiver(receiver)) {
        (Some(Receiver::Workflow(a)), Some(Receiver::Workflow(b))) => a == b,
        (
            Some(Receiver::Endpoint {
                host: h1,
                path: p1,
                model: m1,
            }),
            Some(Receiver::Endpoint {
                host: h2,
                path: p2,
                model: m2,
            }),
        ) => h1 == h2 && path_covers(&p1, &p2) && (m1.is_empty() || m1 == m2),
        _ => false,
    }
}

/// Validate the context clauses of ONE agent's capabilities (deny-by-default: a malformed, ambiguous or
/// unsupported scope never becomes part of a program).
pub fn check_context_decls(caps: &[Capability]) -> Result<(), String> {
    for c in caps {
        let Some(d) = &c.context else { continue };
        if !CONTEXT_OPS.contains(&d.op.as_str()) {
            return Err(format!(
                "capability {}: invalid context operation {:?} (allowed: search, read, disclose)",
                c.tool, d.op
            ));
        }
        if c.mode != "read" {
            return Err(format!(
                "capability {}: a context capability must be `mode read` (a context scope never authorizes a write)",
                c.tool
            ));
        }
        if d.op == "disclose" {
            if parse_receiver(&d.receiver).is_none() {
                return Err(format!(
                    "capability {}: unsupported receiver {:?} (endpoint:<host><path>[#<model>] | workflow:<Name>)",
                    c.tool, d.receiver
                ));
            }
            let mut seen: Vec<&String> = Vec::new();
            for name in &d.sources {
                if seen.contains(&name) {
                    return Err(format!(
                        "capability {}: `from` must name the capabilities whose content is disclosed, each once",
                        c.tool
                    ));
                }
                seen.push(name);
                let ok = caps.iter().any(|s| {
                    &s.tool == name
                        && s.context
                            .as_ref()
                            .is_some_and(|x| x.op == "search" || x.op == "read")
                });
                if !ok {
                    return Err(format!(
                        "capability {}: `from {}` is not a search/read context capability of this agent",
                        c.tool, name
                    ));
                }
            }
            if d.sources.is_empty() {
                return Err(format!(
                    "capability {}: `from` must name the capabilities whose content is disclosed, each once",
                    c.tool
                ));
            }
        } else {
            if !valid_host(&d.source) {
                return Err(format!(
                    "capability {}: unsupported source {:?} (a plain DNS host name)",
                    c.tool, d.source
                ));
            }
            if !valid_path(&d.resource) {
                return Err(format!(
                    "capability {}: unsupported resource {:?} (an absolute path, no wildcards)",
                    c.tool, d.resource
                ));
            }
        }
    }
    Ok(())
}
