//! `casl-broker` binary — newline-delimited JSON-RPC over stdio (MCP/LSP style).
//!
//! `casl-broker` reads one request per line on stdin, writes one response per line on stdout. Offline
//! by default (MockBackend); a live model is the broker's configuration, never the client's. The
//! existing Python client (`casl.client.Client(command=["casl-broker"])`) drives this unchanged.
//!
//! Env: `CASL_BROKER_SCENARIO` (mock scenario, default "ok"), `CASL_BROKER_TOOLS` (comma-separated
//! granted tool capabilities).

use std::collections::{BTreeMap, BTreeSet};
use std::io::{self, BufRead};

use casl_broker::{egress, journal, Backend, Broker, MockBackend};
use casl_proto as proto;

fn main() {
    // `casl-broker verify-journal PATH` → exit 0 intact · 1 broken · 2 usage/unreadable
    let args: Vec<String> = std::env::args().collect();
    if args.len() > 1 {
        if args.len() != 3 || args[1] != "verify-journal" {
            eprintln!("usage: casl-broker [verify-journal PATH]");
            std::process::exit(2);
        }
        match journal::Journal::open_readonly(&args[2]).map(|j| j.verify()) {
            Ok(Ok(())) => {
                println!("journal intact");
                std::process::exit(0);
            }
            Ok(Err((seq, reason))) => {
                println!("journal BROKEN at seq {seq}: {reason}");
                std::process::exit(if seq == 0 { 2 } else { 1 });
            }
            Err(e) => {
                eprintln!("casl-broker: {e}");
                std::process::exit(2);
            }
        }
    }
    let scenario = std::env::var("CASL_BROKER_SCENARIO").unwrap_or_else(|_| "ok".into());
    let parse_set = |var: &str| -> BTreeSet<String> {
        std::env::var(var)
            .ok()
            .map(|s| {
                s.split(',')
                    .map(|x| x.trim().to_string())
                    .filter(|x| !x.is_empty())
                    .collect()
            })
            .unwrap_or_default()
    };
    let granted = parse_set("CASL_BROKER_TOOLS");
    let irreversible = parse_set("CASL_BROKER_IRREVERSIBLE");

    let backend: Option<Box<dyn Backend>> = Some(Box::new(MockBackend::new(&scenario)));
    // Signed approvals: `CASL_BROKER_APPROVERS` ("<pubkey-hex>=<class>,...") is the trust store; when set,
    // `consent` accepts only an approval signed by one of these keys for `CASL_BROKER_PROGRAM`.
    // `CASL_BROKER_APPROVAL_CLASS` ("cap=class,...") raises the minimum approver class per capability.
    // `CASL_BROKER_NOW` pins the clock (conformance tests only).
    let approvers = casl_broker::approval::parse_approvers(
        &std::env::var("CASL_BROKER_APPROVERS").unwrap_or_default(),
    );
    let program = std::env::var("CASL_BROKER_PROGRAM")
        .ok()
        .filter(|s| !s.is_empty());
    let approval_class: BTreeMap<String, String> = std::env::var("CASL_BROKER_APPROVAL_CLASS")
        .unwrap_or_default()
        .split(',')
        .filter_map(|kv| kv.split_once('='))
        .map(|(k, v)| (k.trim().to_string(), v.trim().to_string()))
        .collect();
    let mut broker = Broker::new(backend, granted)
        .with_irreversible(irreversible)
        .with_approvers(approvers, program, approval_class);
    broker.fixed_now = std::env::var("CASL_BROKER_NOW")
        .ok()
        .and_then(|s| s.parse().ok());
    // Mediated egress: `CASL_BROKER_EGRESS` ("cap=host|host;cap2=host") names the capabilities the broker
    // PERFORMS and their destination allowlists. Transport: `CASL_BROKER_MOCK_EGRESS` ("200" | "404" |
    // "not_sent" | "unknown") ⇒ a mock answers; `CASL_BROKER_LIVE=1` ⇒ real HTTPS; neither ⇒ nothing is
    // ever sent (outcome `not_sent`).
    // `CASL_BROKER_EGRESS_ACCOUNT` ("cap=IDENTITY;...") — the identity of that credential, which a signed
    // approval must name. `cap=@token` derives it from the bearer's JWT claims (issuer/tenant/subject).
    let accounts: BTreeMap<String, String> = std::env::var("CASL_BROKER_EGRESS_ACCOUNT")
        .unwrap_or_default()
        .split(';')
        .filter_map(|kv| kv.split_once('='))
        .map(|(cap, id)| (cap.trim().to_string(), id.trim().to_string()))
        .collect();
    let mock = std::env::var("CASL_BROKER_MOCK_EGRESS").ok();
    let live = std::env::var("CASL_BROKER_LIVE").is_ok_and(|v| v == "1");
    // `CASL_BROKER_EGRESS_AUTH` ("cap=ENVVAR;...") — the broker adds `Authorization: Bearer $ENVVAR`.
    let auth: BTreeMap<String, String> = std::env::var("CASL_BROKER_EGRESS_AUTH")
        .unwrap_or_default()
        .split(';')
        .filter_map(|kv| kv.split_once('='))
        .filter_map(|(cap, var)| {
            std::env::var(var.trim())
                .ok()
                .map(|tok| (cap.trim().to_string(), tok))
        })
        .collect();
    for part in std::env::var("CASL_BROKER_EGRESS")
        .unwrap_or_default()
        .split(';')
    {
        if let Some((cap, hosts)) = part.split_once('=') {
            let transport: Box<dyn egress::EgressTransport> = match &mock {
                Some(m) => Box::new(egress::MockEgress::from_spec(m)),
                None if live => Box::new(casl_broker::live::LiveTransport::new()),
                None => Box::new(egress::NoTransport),
            };
            broker.mediated.insert(
                cap.trim().to_string(),
                egress::Mediated {
                    allow_hosts: hosts
                        .split('|')
                        .map(|h| h.trim().to_string())
                        .filter(|h| !h.is_empty())
                        .collect(),
                    transport,
                    inject: auth
                        .get(cap.trim())
                        .map(|t| vec![("Authorization".to_string(), format!("Bearer {t}"))])
                        .unwrap_or_default(),
                    account: match accounts.get(cap.trim()).map(String::as_str) {
                        Some("@token") => auth
                            .get(cap.trim())
                            .and_then(|t| egress::account_from_bearer(t)),
                        Some(id) if !id.is_empty() => Some(id.to_string()),
                        _ => None,
                    },
                },
            );
        }
    }
    // Context access: `CASL_BROKER_CONTEXTS` = JSON {cap: declared scope} (what the checked program declares).
    if let Ok(text) = std::env::var("CASL_BROKER_CONTEXTS") {
        match serde_json::from_str::<BTreeMap<String, serde_json::Value>>(&text) {
            Ok(c) => broker.contexts = c,
            Err(e) => {
                eprintln!("casl-broker: CASL_BROKER_CONTEXTS is not a JSON object ({e})");
                std::process::exit(2);
            }
        }
    }
    // The run journal: `CASL_BROKER_JOURNAL` = path of the broker-owned SQLite file. If it is set but
    // cannot be opened or replayed the broker REFUSES to start (never run unjournaled by accident).
    if let Ok(path) = std::env::var("CASL_BROKER_JOURNAL") {
        let opened = journal::Journal::open(&path).and_then(|j| broker.with_journal(j));
        broker = match opened {
            Ok(b) => b,
            Err(e) => {
                eprintln!("casl-broker: {e}");
                std::process::exit(2);
            }
        };
    }

    let stdin = io::stdin();
    let mut out = io::stdout();
    for line in stdin.lock().lines() {
        let line = match line {
            Ok(l) => l,
            Err(_) => break,
        };
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        match proto::parse_request(line) {
            Ok(req) => {
                let resp = broker.handle(&req);
                let _ = proto::write_message(&mut out, &resp);
                if req.method == "shutdown" {
                    break;
                }
            }
            Err(_) => {
                let resp = proto::Response::err(
                    serde_json::Value::Null,
                    proto::codes::PARSE_ERROR,
                    "parse error",
                );
                let _ = proto::write_message(&mut out, &resp);
            }
        }
    }
}
