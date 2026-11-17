//! `casl prepare` / `casl act` / `casl resolve` / `casl journal` — the host interface for ONE approved
//! action (the AI-OS pilot; docs/os-pilot.md).
//!
//! The host (an OS agent) prepares an action; a human signs an approval for exactly that action; `act`
//! performs it through the broker and reports the outcome as JSON. The CASL program supplies three
//! things: the capability the site may use, the proof that the irreversible site is dominated by an
//! approval gate (`casl check` must ACCEPT the program — re-checked on every call), and the identity
//! the approval names (the hash of the program text).
//!
//! Honest scope: `act` executes ONE effect site of a verified choreography; it does not conduct the
//! whole choreography (the conductor's broker dispatch is not ported to Rust yet).
//!
//! Exit codes: 0 = performed · 1 = denied (program rejected, approval refused, effect not allowed) ·
//! 2 = usage / IO · 3 = ran but NOT performed (rejected by the target, not sent, or outcome unknown).

use std::collections::{BTreeMap, BTreeSet};
use std::fs;

use casl_broker::{approval, egress, journal, live, Broker};
use casl_proto as proto;
use casl_surface as surf;
use serde_json::{json, Value};

use crate::{read_or_io_err, verdict, Args, Verdict};

const VALFLAGS: &[&str] = &[
    "--program",
    "--site",
    "--request",
    "--approval",
    "--journal",
    "--approvers",
    "--allow-hosts",
    "--auth-env",
    "--account",
    "--require-class",
    "--mock-egress",
    "--attempt",
    "--outcome",
    "--note",
    "--grant",
    "--id",
    "--instance",
    "--origins",
    "--source",
    "--resource",
    "--receiver",
];

/// What the program says about an effect site.
struct Site {
    cap: String,
    irreversible: bool,
}

fn collect_sites(g: &surf::Gtyp, label: &str, out: &mut Vec<(String, Option<String>, bool)>) {
    match g {
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
        surf::Gtyp::Rec { body, .. } => collect_sites(body, label, out),
        surf::Gtyp::Comm {
            sender,
            label: l,
            uses,
            irreversible,
            on_crash,
            cont,
            ..
        } => {
            if l == label {
                out.push((sender.clone(), uses.clone(), *irreversible));
            }
            if let Some(c) = on_crash {
                collect_sites(c, label, out);
            }
            collect_sites(cont, label, out);
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                collect_sites(&b.cont, label, out);
            }
        }
    }
}

fn find_site(p: &surf::Protocol, label: &str) -> Result<Site, String> {
    let mut found = Vec::new();
    collect_sites(&p.gtype, label, &mut found);
    let Some((sender, uses, irreversible)) = found.first().cloned() else {
        return Err(format!("program {} has no message {label:?}", p.name));
    };
    if found
        .iter()
        .any(|f| *f != (sender.clone(), uses.clone(), irreversible))
    {
        return Err(format!(
            "message {label:?} occurs with different capabilities/effects — not a single site"
        ));
    }
    let Some(cap) = uses else {
        return Err(format!(
            "message {label:?} uses no capability — nothing to perform"
        ));
    };
    let declared = p
        .caps
        .get(&sender)
        .is_some_and(|cs| cs.iter().any(|c| c.tool == cap));
    if !declared {
        return Err(format!(
            "agent {sender} does not declare capability {cap:?}"
        ));
    }
    Ok(Site { cap, irreversible })
}

struct Loaded {
    hash: String,
    site_name: String,
    site: Site,
    /// cap → the context scope the program declares for it (docs/context-grants.md).
    contexts: BTreeMap<String, Value>,
}

/// Read + parse + CHECK the program (it must be accepted) and locate the site. `Err` = (exit code, message).
fn load(a: &Args) -> Result<Loaded, (i32, String)> {
    let (Some(file), Some(label)) = (a.val("program"), a.val("site")) else {
        return Err((2, "--program FILE and --site LABEL are required".into()));
    };
    let src = read_or_io_err(file).map_err(|c| (c, format!("cannot read {file}")))?;
    let p = surf::parse(&src).map_err(|e| (2, format!("parse error: {e}")))?;
    match verdict(&p, &casl_check::check(&p)) {
        Verdict::Accepted => {}
        Verdict::Rejected => return Err((1, "program REJECTED by casl check".into())),
        Verdict::CannotCertify => {
            return Err((
                1,
                "program cannot be certified by this front-end (async)".into(),
            ))
        }
    }
    let site = find_site(&p, label).map_err(|e| (1, e))?;
    let contexts = p
        .caps
        .values()
        .flatten()
        .filter_map(|c| casl_broker::context::declared(&p, &c.tool).map(|d| (c.tool.clone(), d)))
        .collect();
    Ok(Loaded {
        hash: format!("sha256:{}", journal::sha256_hex(src.as_bytes())),
        site_name: format!("{}:{}", p.name, label),
        site,
        contexts,
    })
}

fn read_json(path: &str) -> Result<Value, (i32, String)> {
    let text = fs::read_to_string(path).map_err(|_| (2, format!("cannot read {path}")))?;
    serde_json::from_str(&text).map_err(|e| (2, format!("{path}: not JSON ({e})")))
}

/// The credential the broker will add on the wire, and its IDENTITY — what the approval must name.
/// `--auth-env VAR` needs exactly one of `--account ID` (a credential reference you configure) or
/// `--account-from-token` (issuer/tenant/subject read from the JWT the broker holds).
type Credential = (Vec<(String, String)>, Option<String>);

fn credential(a: &Args) -> Result<Credential, (i32, String)> {
    let (explicit, derive) = (a.val("account"), a.has("account-from-token"));
    let Some(var) = a.val("auth-env") else {
        if explicit.is_some() || derive {
            return Err((
                2,
                "--account/--account-from-token name a credential: give --auth-env VAR too".into(),
            ));
        }
        return Ok((Vec::new(), None));
    };
    let token = match std::env::var(var) {
        Ok(t) if !t.is_empty() => t,
        _ => return Err((2, format!("--auth-env {var}: the variable is not set"))),
    };
    let account = match (explicit, derive) {
        (Some(id), false) if !id.is_empty() => id.to_string(),
        (None, true) => egress::account_from_bearer(&token).ok_or((
            2,
            "--account-from-token: the credential is not a JWT with `iss` and a subject; use --account ID".to_string(),
        ))?,
        _ => {
            return Err((
                2,
                "--auth-env needs exactly one of --account ID or --account-from-token (the approval must name whose account the request acts on)".into(),
            ))
        }
    };
    Ok((
        vec![("Authorization".to_string(), format!("Bearer {token}"))],
        Some(account),
    ))
}

fn fail(code: i32, msg: String) -> i32 {
    println!("{}", json!({"status": "error", "error": msg}));
    code
}

/// `casl prepare` — what the approver must sign for this action (the host adds `nonce` and `exp`).
pub fn cmd_prepare(args: &[String]) -> i32 {
    let a = Args::parse(args, VALFLAGS);
    let l = match load(&a) {
        Ok(l) => l,
        Err((c, m)) => return fail(c, m),
    };
    let Some(req_path) = a.val("request") else {
        return fail(2, "--request FILE is required".into());
    };
    let request = match read_json(req_path) {
        Ok(v) => v,
        Err((c, m)) => return fail(c, m),
    };
    let Some(digest) = approval::request_digest(Some(&request)) else {
        return fail(
            2,
            "request is not an object {method, url, headers, body}".into(),
        );
    };
    let account = match credential(&a) {
        Ok((_, account)) => account,
        Err((c, m)) => return fail(c, m),
    };
    let mut sign = json!({"v": 1, "kind": "action", "program": l.hash, "cap": l.site.cap,
                          "site": l.site_name, "request": digest});
    if let Some(id) = account {
        sign["account"] = json!(id); // whose account the request acts on — show it to the approver
    }
    println!(
        "{}",
        json!({"status": "ok", "irreversible": l.site.irreversible, "sign": sign,
               "domain": "casl-approval-v1\n"})
    );
    0
}

fn rpc(b: &mut Broker, method: &str, params: Value) -> Result<Value, String> {
    let resp = b.handle(&proto::Request {
        jsonrpc: "2.0".into(),
        id: json!(1),
        method: method.into(),
        params,
    });
    match (resp.result, resp.error) {
        (Some(v), _) => Ok(v),
        (None, Some(e)) => Err(format!("{}: {}", e.code, e.message)),
        (None, None) => Err("empty broker response".into()),
    }
}

fn open_journal(b: Broker, path: &str) -> Result<Broker, (i32, String)> {
    journal::Journal::open(path)
        .and_then(|j| b.with_journal(j))
        .map_err(|e| (2, e))
}

/// `casl act` — perform ONE approved action through the broker.
pub fn cmd_act(args: &[String]) -> i32 {
    let a = Args::parse(args, VALFLAGS);
    match act(&a) {
        Ok((code, out)) => {
            println!("{out}");
            code
        }
        Err((c, m)) => fail(c, m),
    }
}

fn act(a: &Args) -> Result<(i32, Value), (i32, String)> {
    let l = load(a)?;
    let request = read_json(
        a.val("request")
            .ok_or((2, "--request FILE is required".to_string()))?,
    )?;
    let hosts: Vec<String> = a
        .val("allow-hosts")
        .unwrap_or("")
        .split(',')
        .map(|h| h.trim().to_string())
        .filter(|h| !h.is_empty())
        .collect();
    if hosts.is_empty() {
        return Err((
            2,
            "--allow-hosts HOST[,HOST] is required (the destination allowlist)".into(),
        ));
    }
    let cap = l.site.cap.clone();
    if l.contexts.contains_key(&cap) {
        return Err((
            1,
            format!(
                "capability {cap:?} has a context scope — it is performed through `casl access`"
            ),
        ));
    }
    let mut b = Broker::new(None, BTreeSet::from([cap.clone()]));
    if l.site.irreversible {
        // An irreversible action needs: a trust store, a signed approval, and a journal.
        let (Some(ap), Some(_), Some(jp)) =
            (a.val("approvers"), a.val("approval"), a.val("journal"))
        else {
            return Err((
                2,
                "an irreversible site needs --approvers FILE, --approval FILE and --journal PATH"
                    .into(),
            ));
        };
        let text = fs::read_to_string(ap).map_err(|_| (2, format!("cannot read {ap}")))?;
        let approvers = approval::parse_approvers(&text);
        if approvers.is_empty() {
            return Err((
                2,
                format!("{ap}: no valid `<pubkey-hex>=<human|personal>` entry"),
            ));
        }
        let class: BTreeMap<String, String> = a
            .val("require-class")
            .map(|c| BTreeMap::from([(cap.clone(), c.to_string())]))
            .unwrap_or_default();
        b = b
            .with_irreversible(BTreeSet::from([cap.clone()]))
            .with_approvers(approvers, Some(l.hash.clone()), class);
        b = open_journal(b, jp)?;
    } else if let Some(jp) = a.val("journal") {
        b = open_journal(b, jp)?;
    }
    let (inject, account) = credential(a)?;
    let transport: Box<dyn egress::EgressTransport> = match a.val("mock-egress") {
        Some(m) => Box::new(egress::MockEgress::from_spec(m)),
        None => Box::new(live::LiveTransport::new()),
    };
    b.mediated.insert(
        cap.clone(),
        egress::Mediated {
            allow_hosts: hosts,
            transport,
            inject,
            account,
        },
    );
    let internal = |e: String| (2, e);
    rpc(&mut b, "initialize", json!({"client": "casl-act"})).map_err(internal)?;
    let mut out = json!({"program": l.hash, "site": l.site_name, "cap": cap,
                         "consent": Value::Null, "effect": Value::Null});
    let mut token = Value::Null;
    if l.site.irreversible {
        let signed = read_json(a.val("approval").unwrap_or(""))?;
        let c = rpc(
            &mut b,
            "consent",
            json!({"site": l.site_name, "tool": cap, "signed": signed}),
        )
        .map_err(internal)?;
        token = c.get("token").cloned().unwrap_or(Value::Null);
        let granted = c.get("granted").and_then(Value::as_bool).unwrap_or(false);
        let mut shown = c;
        if let Some(m) = shown.as_object_mut() {
            m.remove("token"); // one-shot and already spent below; not for the host
        }
        out["consent"] = shown;
        if !granted {
            out["status"] = json!("denied");
            return Ok((1, out));
        }
    }
    let e = rpc(
        &mut b,
        "effect",
        json!({"site": l.site_name, "tool": cap, "approval": token, "request": request}),
    )
    .map_err(internal)?;
    let allowed = e.get("allowed").and_then(Value::as_bool).unwrap_or(false);
    let outcome = e
        .get("outcome")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    out["effect"] = e;
    let (code, status) = match (allowed, outcome.as_str()) {
        (true, "performed") => (0, "performed".to_string()),
        (true, o) => (3, o.to_string()),
        (false, "unresolved") => (1, "unresolved".to_string()),
        (false, _) => (1, "denied".to_string()),
    };
    out["status"] = json!(status);
    Ok((code, out))
}

/// `casl resolve` — record the outcome, clarified at the target system, of an effect that was unknown.
pub fn cmd_resolve(args: &[String]) -> i32 {
    let a = Args::parse(args, VALFLAGS);
    let usage = "usage: casl resolve --journal PATH --attempt ID --outcome performed|not_performed [--note TEXT]";
    let (Some(jp), Some(attempt), Some(outcome)) = (
        a.val("journal"),
        a.val("attempt").and_then(|v| v.parse::<i64>().ok()),
        a.val("outcome"),
    ) else {
        return fail(2, usage.into());
    };
    if !std::path::Path::new(jp).is_file() {
        return fail(2, format!("no journal at {jp}"));
    }
    let mut b = match open_journal(Broker::new(None, BTreeSet::new()), jp) {
        Ok(b) => b,
        Err((c, m)) => return fail(c, m),
    };
    // No `initialize` (that would journal a run): resolution is a journal operation, not a run.
    let r = b.resolve_attempt(attempt, outcome, a.val("note").unwrap_or(""));
    match r {
        Ok(v) => {
            let ok = v.get("resolved").and_then(Value::as_bool).unwrap_or(false);
            println!("{v}");
            i32::from(!ok)
        }
        Err(e) => fail(2, e),
    }
}

/// `casl journal verify PATH` — exit 0 intact · 1 broken · 2 usage/unreadable.
pub fn cmd_journal(args: &[String]) -> i32 {
    let (Some("verify"), Some(path), 2) =
        (args.first().map(String::as_str), args.get(1), args.len())
    else {
        eprintln!("usage: casl journal verify PATH");
        return 2;
    };
    match journal::Journal::open_readonly(path).map(|j| j.verify()) {
        Ok(Ok(())) => {
            println!("journal intact");
            0
        }
        Ok(Err((seq, reason))) => {
            println!("journal BROKEN at seq {seq}: {reason}");
            if seq == 0 {
                2
            } else {
                1
            }
        }
        Err(e) => {
            eprintln!("casl: {e}");
            2
        }
    }
}

// ---------------------------------------------------------------------------------------------------
// context access (docs/context-grants.md): `casl grant add|revoke`, `casl access`
// ---------------------------------------------------------------------------------------------------

fn trust_store(a: &Args) -> Result<BTreeMap<String, String>, (i32, String)> {
    let ap = a
        .val("approvers")
        .ok_or((2, "--approvers FILE is required".to_string()))?;
    let text = fs::read_to_string(ap).map_err(|_| (2, format!("cannot read {ap}")))?;
    let approvers = approval::parse_approvers(&text);
    if approvers.is_empty() {
        return Err((
            2,
            format!("{ap}: no valid `<pubkey-hex>=<human|personal>` entry"),
        ));
    }
    Ok(approvers)
}

/// `casl grant add --journal J --approvers K --grant G.json` · `casl grant revoke --journal J --id ID`
/// Exit: 0 recorded (or already on record) · 1 refused · 2 usage / IO.
pub fn cmd_grant(args: &[String]) -> i32 {
    let a = Args::parse(args.get(1..).unwrap_or(&[]), VALFLAGS);
    let run = || -> Result<(i32, Value), (i32, String)> {
        let jp = a
            .val("journal")
            .ok_or((2, "--journal PATH is required".to_string()))?;
        match args.first().map(String::as_str) {
            Some("add") => {
                let env = read_json(
                    a.val("grant")
                        .ok_or((2, "--grant FILE is required".to_string()))?,
                )?;
                let b = Broker::new(None, BTreeSet::new()).with_approvers(
                    trust_store(&a)?,
                    None,
                    BTreeMap::new(),
                );
                let mut b = open_journal(b, jp)?;
                let r = b.grant_add(Some(&env)).map_err(|e| (2, e))?;
                let ok = r["added"] == true || r["code"] == "exists";
                Ok((i32::from(!ok), r))
            }
            Some("revoke") => {
                let id = a.val("id").ok_or((2, "--id ID is required".to_string()))?;
                if !std::path::Path::new(jp).is_file() {
                    return Err((2, format!("no journal at {jp}")));
                }
                let mut b = open_journal(Broker::new(None, BTreeSet::new()), jp)?;
                Ok((0, b.grant_revoke(Some(id)).map_err(|e| (2, e))?))
            }
            _ => Err((
                2,
                "usage: casl grant add --journal J --approvers K --grant G.json | casl grant revoke --journal J --id ID".into(),
            )),
        }
    };
    match run() {
        Ok((code, out)) => {
            println!("{out}");
            code
        }
        Err((c, m)) => fail(c, m),
    }
}

/// `"12,15=/path"` → `[{"access":12},{"access":15,"resource":"/path"}]`: the earlier accesses a disclosure
/// cites; a search hit names its own resource.
fn parse_origins(text: &str) -> Result<Value, (i32, String)> {
    let mut out = Vec::new();
    for part in text.split(',').map(str::trim).filter(|p| !p.is_empty()) {
        let (id, res) = match part.split_once('=') {
            Some((i, r)) => (i, Some(r)),
            None => (part, None),
        };
        let id: i64 = id
            .parse()
            .map_err(|_| (2, format!("--origins: {id:?} is not an access id")))?;
        out.push(match res {
            Some(r) => json!({"access": id, "resource": r}),
            None => json!({"access": id}),
        });
    }
    Ok(json!(out))
}

/// `casl access` — ONE context access (search, read or disclose) through the broker.
/// Exit: 0 granted (and performed, when the broker sends it) · 1 denied · 2 usage / IO ·
/// 3 granted but not performed (target outcome) · 4 needs a grant.
pub fn cmd_access(args: &[String]) -> i32 {
    let a = Args::parse(args, VALFLAGS);
    match access(&a) {
        Ok((code, out)) => {
            println!("{out}");
            code
        }
        Err((c, m)) => fail(c, m),
    }
}

fn access(a: &Args) -> Result<(i32, Value), (i32, String)> {
    let l = load(a)?;
    let cap = l.site.cap.clone();
    if !l.contexts.contains_key(&cap) {
        return Err((
            1,
            format!("capability {cap:?} declares no context scope — `casl access` performs context capabilities only"),
        ));
    }
    let jp = a
        .val("journal")
        .ok_or((2, "--journal PATH is required".to_string()))?;
    let mut b = Broker::new(None, BTreeSet::from([cap.clone()])).with_approvers(
        trust_store(a)?,
        Some(l.hash.clone()),
        BTreeMap::new(),
    );
    b.contexts = l.contexts.clone();
    let mut params = json!({"site": l.site_name, "tool": cap, "instance": a.val("instance")});
    if let Some(o) = a.val("origins") {
        params["origins"] = parse_origins(o)?;
    }
    if a.has("host-performed") {
        // the host performs the access itself (local index, IMAP, a loopback model); CASL decides and records
        let mut hp = serde_json::Map::new();
        for k in ["account", "source", "resource", "receiver"] {
            if let Some(v) = a.val(k) {
                hp.insert(k.to_string(), json!(v));
            }
        }
        params["host_performed"] = Value::Object(hp);
    } else {
        params["request"] = read_json(
            a.val("request")
                .ok_or((2, "--request FILE is required".to_string()))?,
        )?;
        let hosts: Vec<String> = a
            .val("allow-hosts")
            .unwrap_or("")
            .split(',')
            .map(|h| h.trim().to_string())
            .filter(|h| !h.is_empty())
            .collect();
        if hosts.is_empty() {
            return Err((
                2,
                "--allow-hosts HOST[,HOST] is required (the destination allowlist)".into(),
            ));
        }
        let (inject, account) = credential(a)?;
        let transport: Box<dyn egress::EgressTransport> = match a.val("mock-egress") {
            Some(m) => Box::new(egress::MockEgress::from_spec(m)),
            None => Box::new(live::LiveTransport::new()),
        };
        b.mediated.insert(
            cap.clone(),
            egress::Mediated {
                allow_hosts: hosts,
                transport,
                inject,
                account,
            },
        );
    }
    let mut b = open_journal(b, jp)?;
    let internal = |e: String| (2, e);
    rpc(&mut b, "initialize", json!({"client": "casl-access"})).map_err(internal)?;
    let r = rpc(&mut b, "access", params).map_err(internal)?;
    let (code, status) = match (r["decision"].as_str(), r["by"].as_str()) {
        (Some("granted"), Some("host")) => (0, "granted".to_string()),
        (Some("granted"), _) if r["performed"] == true => (0, "performed".to_string()),
        (Some("granted"), _) => (3, r["outcome"].as_str().unwrap_or("unknown").to_string()),
        (Some("needs_grant"), _) => (4, "needs_grant".to_string()),
        _ => (1, "denied".to_string()),
    };
    Ok((
        code,
        json!({"program": l.hash, "site": l.site_name, "cap": cap, "status": status, "access": r}),
    ))
}
