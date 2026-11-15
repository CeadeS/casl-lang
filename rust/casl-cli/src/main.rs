//! `casl` — the CASL command-line front-end (Rust). The single use-ready binary that ties the at-parity
//! crates together: casl-surface (parser) · casl-check (the ported MUST checks) · casl-project
//! (manifest / deps / seam / grade-flow) · casl-conductor (the deterministic interpreter).
//!
//! Strangler-fig posture: this front-end covers the verbs whose engines are ALREADY at parity with the
//! Python reference, and HONESTLY defers the rest (new / synth / ide / gate / trace / blame / observe / init)
//! to the Python `casl` until those engines are ported. The static checker is now complete on the SYNC
//! fragment (all 11 always-run MUST checks, incl. `concurrency_certified`); the one residual gap is the
//! `async` concurrency gate (`async_bounded`), not yet in `casl-check` — so an `async` protocol whose other
//! checks pass yields exit 2 (UNDETERMINED) and is confirmed with the Python `casl`. The exit-code contract
//! is pinned to the Python CLI by a single-sourced differential (tests/cli_differential.rs).
//!
//! Exit codes mirror the Python front-end exactly: 0 = ok / accepted, 1 = rejected / violations,
//! 2 = usage / IO / parse error, 3 = ran but did not complete.
#![forbid(unsafe_code)]

use casl_check as chk;
use casl_conductor as cond;
use casl_core as core;
use casl_project as proj;
use casl_surface as surf;
use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::Path;

mod act;

const VERSION: &str = env!("CARGO_PKG_VERSION");

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    std::process::exit(dispatch(&args));
}

fn dispatch(args: &[String]) -> i32 {
    let cmd = match args.first() {
        Some(c) => c.as_str(),
        None => {
            print_usage();
            return 2;
        }
    };
    let rest = &args[1..];
    match cmd {
        "-h" | "--help" => {
            print_usage();
            0
        }
        "--version" => {
            println!("casl (Rust front-end) {VERSION}");
            0
        }
        "check" => cmd_check(rest),
        "run" => cmd_run(rest),
        "project" => cmd_project(rest),
        "deps" => cmd_deps(rest),
        "seam" => cmd_seam(rest),
        "flow" => cmd_flow(rest),
        "prepare" => act::cmd_prepare(rest),
        "act" => act::cmd_act(rest),
        "resolve" => act::cmd_resolve(rest),
        "journal" => act::cmd_journal(rest),
        // Engines not yet ported to Rust — defer to the Python `casl` rather than pretend.
        "new" | "synth" | "ide" | "gate" | "trace" | "blame" | "observe" | "init" => deferred(cmd),
        other => {
            eprintln!("casl: unknown command {other:?}");
            print_usage();
            2
        }
    }
}

fn print_usage() {
    eprintln!(
        "casl — Choreographic Agent Specification Language (Rust front-end {VERSION})

USAGE: casl <command> [args]

verified core (at parity with the Python reference):
  check  FILE              static MUST checks on a .casl file        (0 accepted / 1 rejected / 2 error)
  run    FILE              check, then conduct the protocol (mock)   (0 done / 1 rejected / 3 incomplete)
  project [DIR]            introspect a project (obligation ledger)  (0 / 1 invalid / 2 missing)
  deps    [DIR]            show + check the dependency ledger        (0 / 1 burden)
  seam    [DIR]            typed .casl<->artifact bindings           (0 / 1 violations / 2 load)
  flow    [DIR]            per-site grade along the seam             (0 / 2 load)

host interface — one approved action through the broker (JSON on stdout; docs/os-pilot.md):
  prepare --program F --site L --request R       what the approver must sign      (0 / 1 rejected / 2 error)
  act     --program F --site L --request R --approval A --approvers K --journal J --allow-hosts H
                                                 perform it     (0 performed / 1 denied / 3 not performed)
          [--auth-env VAR (--account ID | --account-from-token)]   broker-held credential + its identity
  resolve --journal J --effect ID --outcome performed|not_performed   clarify an unknown outcome
  journal verify J                               check the run journal            (0 intact / 1 broken)

deferred to the Python `casl` (engines not yet ported to Rust):
  new · synth · ide · gate · trace · blame · observe · init

  casl --version          print version
  casl check FILE --json  machine-readable per-check report (Rust front-end schema)"
    );
}

fn deferred(cmd: &str) -> i32 {
    eprintln!(
        "casl {cmd}: not yet in the Rust front-end — its engine isn't ported to Rust. \
         Use the Python `casl {cmd}` for now."
    );
    2
}

// ---------------------------------------------------------------------------
// tiny arg parser: positionals, boolean flags (by name w/o `--`), and value flags.
// ---------------------------------------------------------------------------
struct Args {
    pos: Vec<String>,
    bools: BTreeSet<String>,
    vals: BTreeMap<String, String>,
}
impl Args {
    fn parse(args: &[String], valflags: &[&str]) -> Args {
        let mut pos = Vec::new();
        let mut bools = BTreeSet::new();
        let mut vals = BTreeMap::new();
        let mut i = 0;
        while i < args.len() {
            let a = &args[i];
            if let Some(name) = a.strip_prefix("--") {
                if valflags.contains(&a.as_str()) {
                    if let Some(v) = args.get(i + 1) {
                        vals.insert(name.to_string(), v.clone());
                        i += 2;
                        continue;
                    }
                }
                bools.insert(name.to_string());
            } else {
                pos.push(a.clone());
            }
            i += 1;
        }
        Args { pos, bools, vals }
    }
    fn has(&self, f: &str) -> bool {
        self.bools.contains(f)
    }
    fn val(&self, f: &str) -> Option<&str> {
        self.vals.get(f).map(|s| s.as_str())
    }
}

// ---------------------------------------------------------------------------
// shared: roles + the accept rule
// ---------------------------------------------------------------------------
fn collect_roles(g: &surf::Gtyp, out: &mut BTreeSet<String>) {
    match g {
        surf::Gtyp::Comm {
            sender,
            receiver,
            on_crash,
            cont,
            ..
        } => {
            out.insert(sender.clone());
            out.insert(receiver.clone());
            collect_roles(cont, out);
            if let Some(oc) = on_crash {
                collect_roles(oc, out);
            }
        }
        surf::Gtyp::Choice {
            sender,
            receiver,
            branches,
            ..
        } => {
            out.insert(sender.clone());
            out.insert(receiver.clone());
            for b in branches {
                collect_roles(&b.cont, out);
            }
        }
        surf::Gtyp::Rec { body, .. } => collect_roles(body, out),
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

/// Roles declared check (mirrors Python's "used ⊆ declared" gating; advisory when none declared).
fn roles_declared_ok(p: &surf::Protocol) -> bool {
    if p.roles.is_empty() {
        return true;
    }
    let mut used = BTreeSet::new();
    collect_roles(&p.gtype, &mut used);
    used.iter().all(|u| p.roles.contains(u))
}

/// Structural well-formedness: contractive ∧ no-self ∧ distinct-labels ∧ closed. These are role-independent
/// conjuncts of `casl-core::wellformed_core` (pinned by the 412-protocol conformance differential) — Python
/// lists them as four separate gating checks. We take them from `casl-core` rather than the fixed-{C,A,J,D}
/// `wellformed`, whose core-role PROJECTABILITY diverges from the user-facing (own-roles) verdict.
fn structural_wellformed(p: &surf::Protocol) -> bool {
    let (g, _) = chk::to_core(p);
    core::contractive(&g) && core::no_self(&g) && core::gdistinct(&g) && core::closed(&g)
}

/// The PORTED, always-applicable gating MUST checks EXCEPT the concurrency gate (handled per sync/async in
/// `verdict`). Matches Python `check_protocol`'s gating set. Projectability is the USER-FACING (own-roles +
/// MSC) verdict — NOT the fixed-{C,A,J,D} core `wellformed`, which rejects perfectly good own-role protocols
/// whose phantom core roles cannot merge a loop's branches. Termination / ttl / crash / branch_contracts are
/// SHOULD (non-gating) so they never block acceptance.
fn ported_gating_ok(p: &surf::Protocol, r: &chk::Report) -> bool {
    roles_declared_ok(p)
        && structural_wellformed(p)
        && r.wellformed_user
        && r.capability_contained
        && r.approval_safe
        && r.pipeline_safe
        && r.linearity
        && r.stream_safe
}

/// The front-end's verdict. `Rejected` = a ported gating check failed (sound: Rust's gating checks are a
/// subset of Python's, so a Rust reject ⟹ a Python reject). The concurrency gate splits by kind: for SYNC
/// protocols it is `concurrency_certified` — now ported and at parity, so a full Accept/Reject; for `async`
/// protocols it is `async_bounded`, which is NOT yet ported, so once the other checks pass we `CannotCertify`
/// (exit 2 = undetermined) rather than risk a wrong-accept (e.g. an `async` fan-in Python rejects).
#[derive(PartialEq, Eq)]
enum Verdict {
    Accepted,
    Rejected,
    CannotCertify,
}

fn verdict(p: &surf::Protocol, r: &chk::Report) -> Verdict {
    if !ported_gating_ok(p, r) {
        return Verdict::Rejected; // a ported gating check failed (⟹ Python rejects too)
    }
    if p.async_k.is_some() {
        return Verdict::CannotCertify; // async: the `async_bounded` concurrency gate is not ported
    }
    // sync: `concurrency_certified` (LH-Q-001d) is the 11th gating MUST, ported + differential-pinned.
    if r.concurrency_certified {
        Verdict::Accepted
    } else {
        Verdict::Rejected
    }
}

fn read_or_io_err(path: &str) -> Result<String, i32> {
    match fs::read_to_string(path) {
        Ok(s) => Ok(s),
        Err(_) => {
            eprintln!("casl: file not found: {path}");
            Err(2)
        }
    }
}

// ---------------------------------------------------------------------------
// check
// ---------------------------------------------------------------------------
fn cmd_check(args: &[String]) -> i32 {
    let a = Args::parse(args, &[]);
    let file = match a.pos.first() {
        Some(f) => f,
        None => {
            eprintln!("casl check: a .casl FILE is required");
            return 2;
        }
    };
    let src = match read_or_io_err(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    let p = match surf::parse(&src) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("casl: parse error in {file}: {e}");
            return 2;
        }
    };
    let report = chk::check(&p);
    let v = verdict(&p, &report);
    if a.has("json") {
        println!("{}", check_json(&p, &report, &v));
    } else {
        print!("{}", render_check(&p, &report, &v));
    }
    match v {
        Verdict::Accepted => 0,
        Verdict::Rejected => 1,
        Verdict::CannotCertify => {
            eprintln!(
                "casl check: UNDETERMINED (exit 2, not a rejection) — the ported checks pass but this is \
                 an `async` protocol and the async-safety gate (async_bounded) is not in the Rust \
                 front-end. Confirm with the Python `casl check`."
            );
            2
        }
    }
}

fn render_check(p: &surf::Protocol, r: &chk::Report, v: &Verdict) -> String {
    let mark = |ok: bool| if ok { "✓" } else { "✗" };
    let mut s = format!("CASL check — {}\n", p.name);
    s += &format!(
        "  [{}] Roles declared (used ⊆ declared)\n",
        mark(roles_declared_ok(p))
    );
    s += &format!(
        "  [{}] Structural well-formedness (contractive · no-self · distinct-labels · closed)\n",
        mark(structural_wellformed(p))
    );
    s += &format!(
        "  [{}] Well-formed (projectable over own roles + MSC-realizable)\n",
        mark(r.wellformed_user)
    );
    s += &format!(
        "  [{}] Capability containment (least privilege)\n",
        mark(r.capability_contained)
    );
    s += &format!(
        "  [{}] Approval dominance (effect ⇒ approval-consent)\n",
        mark(r.approval_safe)
    );
    s += &format!(
        "  [{}] Pipeline well-formedness (oracle monitored)\n",
        mark(r.pipeline_safe)
    );
    s += &format!("  [{}] Promise linearity\n", mark(r.linearity));
    s += &format!("  [{}] Stream well-formedness\n", mark(r.stream_safe));
    if p.async_k.is_none() {
        s += &format!(
            "  [{}] Concurrency certified (founded concurrency, LH-Q-001d)\n",
            mark(r.concurrency_certified)
        );
    }
    s += &format!(
        "  SHOULD (advisory): termination [{}]  ttl-safety [{}]  crash-tolerance [{}]\n",
        mark(r.termination),
        mark(r.ttl_safety),
        mark(r.crash_tolerance)
    );
    match v {
        Verdict::Accepted => s += "  Result: ✓ ACCEPTED\n",
        Verdict::Rejected => s += "  Result: ✗ REJECTED (a gating MUST check failed)\n",
        Verdict::CannotCertify => {
            s += "  Result: ? UNDETERMINED — this is an `async` protocol and the async-safety gate\n";
            s += "          (async_bounded) is not in the Rust front-end; confirm with Python `casl`.\n";
        }
    }
    s
}

fn check_json(p: &surf::Protocol, r: &chk::Report, v: &Verdict) -> String {
    // Rust front-end schema (not the Python report schema): the per-check booleans + the verdict.
    let b = |x: bool| if x { "true" } else { "false" };
    let verdict = match v {
        Verdict::Accepted => "accepted",
        Verdict::Rejected => "rejected",
        Verdict::CannotCertify => "undetermined",
    };
    format!(
        "{{\n  \"name\": {:?},\n  \"verdict\": {:?},\n  \"checks\": {{\n    \"roles_declared\": {},\n    \"structural_wellformed\": {},\n    \"wellformed_user\": {},\n    \"capability_contained\": {},\n    \"approval_safe\": {},\n    \"pipeline_safe\": {},\n    \"linearity\": {},\n    \"stream_safe\": {},\n    \"concurrency_certified\": {},\n    \"termination\": {},\n    \"ttl_safety\": {},\n    \"crash_tolerance\": {}\n  }},\n  \"async_safety_ported\": false\n}}",
        p.name,
        verdict,
        b(roles_declared_ok(p)),
        b(structural_wellformed(p)),
        b(r.wellformed_user),
        b(r.capability_contained),
        b(r.approval_safe),
        b(r.pipeline_safe),
        b(r.linearity),
        b(r.stream_safe),
        b(r.concurrency_certified),
        b(r.termination),
        b(r.ttl_safety),
        b(r.crash_tolerance),
    )
}

// ---------------------------------------------------------------------------
// run (single-file, mock oracle)
// ---------------------------------------------------------------------------
fn cmd_run(args: &[String]) -> i32 {
    let a = Args::parse(
        args,
        &[
            "--scenario",
            "--budget",
            "--max-loops",
            "--question",
            "--project",
            "--provider",
            "--model",
            "--endpoint",
        ],
    );
    if a.val("project").is_some() || a.has("project") {
        eprintln!(
            "casl run --project: project-conduct orchestration isn't in the Rust front-end yet — \
             use the Python `casl run --project DIR`. (The Rust conductor runs single files.)"
        );
        return 2;
    }
    if a.has("live") {
        eprintln!(
            "casl run --live: the live LLM oracle isn't in the Rust front-end (key-gated) — \
             use the Python `casl run --live`, or run with the deterministic mock (no --live)."
        );
        return 2;
    }
    let file = match a.pos.first() {
        Some(f) => f,
        None => {
            eprintln!("casl run: pass a .casl FILE (Rust front-end runs single files with the mock oracle)");
            return 2;
        }
    };
    let src = match read_or_io_err(file) {
        Ok(s) => s,
        Err(c) => return c,
    };
    let p = match surf::parse(&src) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("casl: parse error in {file}: {e}");
            return 2;
        }
    };
    // Gate: prove the hull (static MUST check), then execute.
    let report = chk::check(&p);
    match verdict(&p, &report) {
        Verdict::Accepted => {}
        Verdict::Rejected => {
            print!("{}", render_check(&p, &report, &Verdict::Rejected));
            eprintln!("\ncasl run: protocol not admissible (MUST violation) — run aborted.");
            return 1;
        }
        Verdict::CannotCertify => {
            print!("{}", render_check(&p, &report, &Verdict::CannotCertify));
            eprintln!(
                "\ncasl run: cannot certify the hull — this is an `async` protocol and the async-safety \
                 gate (async_bounded) is not in the Rust front-end. Use the Python `casl run`."
            );
            return 2;
        }
    }
    let scenario = a.val("scenario").unwrap_or("retry_then_ok").to_string();
    let budget: i64 = a.val("budget").and_then(|s| s.parse().ok()).unwrap_or(100);
    let max_loops: i64 = a.val("max-loops").and_then(|s| s.parse().ok()).unwrap_or(5);
    let approve = if a.has("approve") { Some(true) } else { None };
    let caps: BTreeMap<String, Vec<String>> = p
        .caps
        .iter()
        .map(|(r, cs)| (r.clone(), cs.iter().map(|c| c.tool.clone()).collect()))
        .collect();
    let mut env = BTreeMap::new();
    env.insert("budget".to_string(), budget);
    let rr = cond::run_protocol(
        &p.gtype,
        &scenario,
        &env,
        max_loops,
        approve,
        &caps,
        &BTreeSet::new(),
    );
    println!(
        "CASL run — {} [mock:{}]  budget={}\n  outcome: {}\n  loops: {}\n  last verdict: {}\n  accepted branch: {}\n  forwards: {}",
        p.name,
        scenario,
        budget,
        rr.outcome,
        rr.loops,
        rr.last_verdict.as_deref().unwrap_or("—"),
        rr.accepted_label.as_deref().unwrap_or("—"),
        if rr.forwards.is_empty() {
            "—".to_string()
        } else {
            rr.forwards.join(", ")
        }
    );
    if rr.outcome == "completed" {
        0
    } else {
        3
    }
}

// ---------------------------------------------------------------------------
// project / deps / seam / flow
// ---------------------------------------------------------------------------
fn dir_arg(args: &[String]) -> (Args, String) {
    let a = Args::parse(args, &[]);
    let dir = a.pos.first().cloned().unwrap_or_else(|| ".".to_string());
    (a, dir)
}

fn cmd_project(args: &[String]) -> i32 {
    let (_, dir) = dir_arg(args);
    let toml = Path::new(&dir).join("casl.toml");
    if !toml.exists() {
        eprintln!("casl: no casl.toml in {dir} (run `casl init` first)");
        return 2;
    }
    let text = match fs::read_to_string(&toml) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("casl: cannot read {}: {e}", toml.display());
            return 2;
        }
    };
    let m = match proj::load_manifest_text(&text) {
        Ok(m) => m,
        Err(e) => {
            eprintln!("casl: invalid manifest — {e}");
            return 1;
        }
    };
    println!("CASL project — {} v{}", m.name, m.version);
    let grades = proj::obligation::grade_by_requirement(&m);
    for (req, arts) in m.by_requirement() {
        let g = grades.get(&req).map(|s| s.as_str()).unwrap_or("?");
        println!("  requirement {req}  [grade {g}]");
        for art in arts {
            println!(
                "    - {} ({}, floor {}){}",
                art.name,
                art.kind,
                art.floor(),
                art.implements
                    .as_ref()
                    .map(|i| format!(", implements {i}"))
                    .unwrap_or_default()
            );
        }
    }
    println!(
        "  effective grade (weakest-link): {}",
        proj::obligation::effective_grade(&m)
    );
    0
}

fn cmd_deps(args: &[String]) -> i32 {
    let (_, dir) = dir_arg(args);
    let path = Path::new(&dir).join("deps.lock");
    if !path.exists() {
        println!("CASL deps — {dir}\n  (no deps.lock — no declared dependencies)");
        return 0;
    }
    let text = match fs::read_to_string(&path) {
        Ok(t) => t,
        Err(e) => {
            eprintln!("casl: cannot read {}: {e}", path.display());
            return 2;
        }
    };
    let deps = match proj::dependency::parse_ledger(&text) {
        Ok(d) => d,
        Err(e) => {
            eprintln!("casl: invalid deps.lock — {}", e.0);
            return 1;
        }
    };
    println!("CASL deps — {dir}");
    let mut viol = 0;
    for d in &deps {
        let ok = d.well_formed();
        if !ok {
            viol += 1;
        }
        println!(
            "  [{}] {} {} — accepted-by={} evidence={}",
            if ok { "✓" } else { "✗" },
            d.name,
            d.version,
            if d.accepted_by.is_empty() {
                "(none)"
            } else {
                &d.accepted_by
            },
            d.evidence
        );
    }
    if let Some(floor) = proj::dependency::supply_chain_floor(&deps) {
        println!("  supply-chain floor (weakest evidence): {floor}");
    }
    if viol > 0 || !proj::dependency::check_ledger(&deps) {
        println!("  → deny-by-default: every dependency must be pinned (sha256) AND owned (accepted-by).");
        return 1;
    }
    0
}

/// Parse every `casl/*.casl` in a project into {declared protocol name → global type} (best-effort,
/// mirroring the Python loaders that skip unparseable files).
fn load_choreos(dir: &str) -> BTreeMap<String, surf::Gtyp> {
    let mut out = BTreeMap::new();
    let cdir = Path::new(dir).join("casl");
    let entries = match fs::read_dir(&cdir) {
        Ok(e) => e,
        Err(_) => return out,
    };
    for ent in entries.flatten() {
        let path = ent.path();
        if path.extension().and_then(|e| e.to_str()) != Some("casl") {
            continue;
        }
        if let Ok(src) = fs::read_to_string(&path) {
            if let Ok(p) = surf::parse(&src) {
                out.insert(p.name.clone(), p.gtype.clone());
            }
        }
    }
    out
}

fn load_manifest_or(dir: &str, missing_code: i32) -> Result<proj::Manifest, i32> {
    let toml = Path::new(dir).join("casl.toml");
    let text = match fs::read_to_string(&toml) {
        Ok(t) => t,
        Err(_) => {
            eprintln!("casl: no casl.toml in {dir}");
            return Err(missing_code);
        }
    };
    proj::load_manifest_text(&text).map_err(|e| {
        eprintln!("casl: invalid manifest — {e}");
        missing_code
    })
}

fn cmd_seam(args: &[String]) -> i32 {
    let (_, dir) = dir_arg(args);
    let m = match load_manifest_or(&dir, 2) {
        Ok(m) => m,
        Err(c) => return c,
    };
    let choreos = load_choreos(&dir);
    let r = proj::seam::check_seam(&m, &choreos);
    println!("CASL seam — {} ({} binding(s))", m.name, r.bindings.len());
    for (name, (pr, label, nature)) in &r.bindings {
        println!("  ✓ {name} → {pr}:{label} ({nature} site)");
    }
    for v in &r.violations {
        println!("  ✗ {v}");
    }
    if r.ok {
        0
    } else {
        1
    }
}

fn cmd_flow(args: &[String]) -> i32 {
    let (_, dir) = dir_arg(args);
    let m = match load_manifest_or(&dir, 2) {
        Ok(m) => m,
        Err(c) => return c,
    };
    let choreos = load_choreos(&dir);
    let grades = proj::grade_flow::flow_grades(&m, &choreos);
    println!(
        "CASL grade flow — {} ({} bound site(s))",
        m.name,
        grades.len()
    );
    for ((pr, label), g) in &grades {
        println!("  {pr}:{label}  →  {g}");
    }
    let boundaries = proj::grade_flow::containment_boundaries(&choreos);
    if !boundaries.is_empty() {
        println!(
            "  re-base boundaries (deferred layer): {}",
            boundaries.join(", ")
        );
    }
    0
}
