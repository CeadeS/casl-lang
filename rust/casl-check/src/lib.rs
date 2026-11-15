//! casl-check — the CASL static checker, END-TO-END (`.casl` text → MUST-check verdicts).
//!
//! Strangler-fig brick 2 (CEP-0081). It bridges the [`casl_surface`] AST to [`casl_core`]'s types and reuses
//! casl-core's checks: **well-formedness** (`wellformed_core` — the F*-pinned predicate: contractive ∧
//! no_self ∧ gdistinct ∧ closed ∧ projectable{C,A,J,D}) and **Least-Privilege capability containment**
//! (`capability_check`). It is pinned to the Python reference (`casl check`) by a verdict differential over a
//! single-sourced corpus (`src/casl/check_corpus.py` → `tests/corpus.json`). Retires those Python verdicts on
//! parity (docs/analyses/python-retirement-roadmap.md §6, stage 2).
//!
//! Honest scope: well-formedness + capability containment reuse casl-core (on the bridged AST); **approval
//! dominance** and **pipeline-safety** run on the rich surface AST directly (they need the `irreversible`/
//! `approval`/`consent`/`oracle`/`verified` markers + cap `mode` + contract presence the bridge drops). The
//! bridge still drops what NO ported check uses (forwarding `source`, contract *relations*, the `stream`
//! marker) — those feed the remaining checks (linearity, concurrency, async, stream), subsequent bricks. Only
//! well-formedness has an F* proof; capability containment, approval dominance, and pipeline-safety are
//! characterization-pinned to the Python reference.
//!
//! Note: `wellformed` here is the F*-core predicate `wellformed_core` (projectability over the FIXED core
//! roles {C,A,J,D}, pinned to `tcb_bridge.projectable`). It is STRICTER than `casl check`'s user-facing
//! well-formedness line (projectability over the protocol's OWN declared roles + MSC-realizability) — e.g. it
//! rejects the canonical BudgetedQA loop because the absent role D cannot reconcile terminate-vs-loop.
//! Matching that user-facing line exactly is a later brick.

#![forbid(unsafe_code)]

use casl_core as core;
use casl_surface as surf;

pub mod concurrency;

/// The per-check report (the MUST-check verdicts ported so far).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Report {
    /// The F*-core predicate `wellformed_core` (fixed roles {C,A,J,D}); see the note above.
    pub wellformed: bool,
    /// `casl check`'s user-facing well-formedness: projectable over the protocol's OWN roles + MSC-realizable.
    pub wellformed_user: bool,
    pub capability_contained: bool,
    pub approval_safe: bool,
    pub pipeline_safe: bool,
    pub linearity: bool,
    pub stream_safe: bool,
    pub termination: bool,
    pub crash_tolerance: bool,
    pub ttl_safety: bool,
    /// LH-Q-001d founded concurrency: the global semantics (with the swap rule) exactly captures the
    /// endpoint configuration's behaviour at every reachable state (`correspondence_class == certified`).
    pub concurrency_certified: bool,
}

// -- bridge: surface AST → casl-core AST (drop what these two checks do not consume) --
fn bridge_field(f: &surf::Field) -> core::Field {
    core::Field {
        name: f.name.clone(),
        sort: f.sort.clone(),
    }
}

fn bridge_contract(c: &Option<surf::Contract>) -> Option<core::Contract> {
    c.as_ref().map(|ct| core::Contract {
        text: ct.text.clone(),
    })
}

fn bridge_gtyp(g: &surf::Gtyp) -> core::Gtyp {
    match g {
        surf::Gtyp::End => core::Gtyp::End,
        surf::Gtyp::Var(v) => core::Gtyp::Var(v.clone()),
        surf::Gtyp::Rec {
            var,
            measure,
            max_iters,
            body,
            ..
        } => core::Gtyp::Rec {
            var: var.clone(),
            body: Box::new(bridge_gtyp(body)),
            measure: measure.clone(),
            max_iters: *max_iters,
        },
        surf::Gtyp::Comm {
            sender,
            receiver,
            label,
            fields,
            contract,
            uses,
            from_oracle,
            on_crash,
            cont,
            ..
        } => core::Gtyp::Comm {
            sender: sender.clone(),
            receiver: receiver.clone(),
            label: label.clone(),
            fields: fields.iter().map(bridge_field).collect(),
            cont: Box::new(bridge_gtyp(cont)),
            contract: bridge_contract(contract),
            uses_capability: uses.clone(),
            from_oracle: *from_oracle,
            on_crash: on_crash.as_ref().map(|g| Box::new(bridge_gtyp(g))),
        },
        surf::Gtyp::Choice {
            sender,
            receiver,
            branches,
            ..
        } => core::Gtyp::Choice {
            sender: sender.clone(),
            receiver: receiver.clone(),
            branches: branches
                .iter()
                .map(|b| core::Branch {
                    label: b.label.clone(),
                    fields: b.fields.iter().map(bridge_field).collect(),
                    cont: bridge_gtyp(&b.cont),
                    contract: bridge_contract(&b.contract),
                })
                .collect(),
        },
    }
}

fn bridge_caps(p: &surf::Protocol) -> core::CapMap {
    let mut m = core::CapMap::new();
    for (role, caps) in &p.caps {
        m.insert(
            role.clone(),
            caps.iter()
                .map(|c| core::Capability {
                    tool: c.tool.clone(),
                    params: c.params.clone(),
                    scope: c.scope.clone(),
                    ttl: c.ttl,
                    sigma: c.sigma.clone(),
                })
                .collect(),
        );
    }
    m
}

/// Bridge a parsed protocol to casl-core's `(gtype, capability map)`.
pub fn to_core(p: &surf::Protocol) -> (core::Gtyp, core::CapMap) {
    (bridge_gtyp(&p.gtype), bridge_caps(p))
}

// -- user-facing well-formedness: projectable over the protocol's OWN declared roles + MSC-realizable
//    (mirrors kernel.wellformed = mpst_ok ∧ msc_ok). The MSC realizability is a faithful port of
//    spike_proj_msc.realizability: at each choice, a non-participant role must be able to locally tell the
//    branches apart (the first divergence in its lifeline projection of the leading scenario is a receive,
//    and the branches don't diverge in length without a distinguishing message). --
type Ev = (String, String, String); // (sender, receiver, label); ("*","*",var) marks a loop back-edge

fn first_scenario(g: &core::Gtyp, out: &mut Vec<Ev>) {
    match g {
        core::Gtyp::End => {}
        core::Gtyp::Var(v) => out.push(("*".into(), "*".into(), v.clone())),
        core::Gtyp::Rec { body, .. } => first_scenario(body, out),
        core::Gtyp::Comm {
            sender,
            receiver,
            label,
            cont,
            ..
        } => {
            out.push((sender.clone(), receiver.clone(), label.clone()));
            first_scenario(cont, out);
        }
        core::Gtyp::Choice {
            sender,
            receiver,
            branches,
        } => {
            if let Some(b) = branches.first() {
                out.push((sender.clone(), receiver.clone(), b.label.clone()));
                first_scenario(&b.cont, out);
            }
        }
    }
}

fn lifeline_proj(evs: &[Ev], role: &str) -> Vec<String> {
    let mut seq = Vec::new();
    for (s, r, lbl) in evs {
        if s == "*" && r == "*" {
            seq.push(format!("↺{}", lbl));
            continue;
        }
        if s == role {
            seq.push(format!("!{}:{}", r, lbl));
        }
        if r == role {
            seq.push(format!("?{}:{}", s, lbl));
        }
    }
    seq
}

fn msc_walk(g: &core::Gtyp, roles: &[String], ok: &mut bool) {
    match g {
        core::Gtyp::Comm { cont, .. } => msc_walk(cont, roles, ok),
        core::Gtyp::Rec { body, .. } => msc_walk(body, roles, ok),
        core::Gtyp::Choice {
            sender,
            receiver,
            branches,
        } => {
            for role in roles {
                if role == sender || role == receiver {
                    continue;
                }
                let projs: Vec<Vec<String>> = branches
                    .iter()
                    .map(|b| {
                        let mut evs = Vec::new();
                        first_scenario(&b.cont, &mut evs);
                        lifeline_proj(&evs, role)
                    })
                    .collect();
                if projs.iter().any(|p| *p != projs[0]) {
                    let maxlen = projs.iter().map(|p| p.len()).max().unwrap_or(0);
                    for i in 0..maxlen {
                        let elems: Vec<Option<&String>> = projs.iter().map(|p| p.get(i)).collect();
                        if elems.iter().all(|e| *e == elems[0]) {
                            continue;
                        }
                        if elems.iter().any(|e| e.is_none()) {
                            *ok = false; // length divergence without a distinguishing message
                        } else if elems.iter().any(|e| !e.unwrap().starts_with('?')) {
                            *ok = false; // first divergence is not a receive ⇒ not locally determinable
                        }
                        break;
                    }
                }
            }
            for b in branches {
                msc_walk(&b.cont, roles, ok);
            }
        }
        core::Gtyp::End | core::Gtyp::Var(_) => {}
    }
}

fn msc_realizable(g: &core::Gtyp, roles: &[String]) -> bool {
    let mut ok = true;
    msc_walk(g, roles, &mut ok);
    ok
}

/// `casl check`'s user-facing well-formedness: projectable over the protocol's OWN declared roles + MSC.
pub fn wellformed_userfacing(p: &surf::Protocol) -> bool {
    let g = bridge_gtyp(&p.gtype);
    p.roles.iter().all(|r| core::project(&g, r).is_ok()) && msc_realizable(&g, &p.roles)
}

// -- approval dominance (on the rich surface AST: it needs the markers + cap `mode` the bridge drops).
//    Mirrors spike_approval.approval_dominated / kernel.approval_safety: an effect-bearing action (tagged
//    `irreversible`, OR using a non-readonly capability) must be dominated on every path by an approval gate
//    via a `consent` branch; consent survives no loop iteration. --
fn cap_effectful(p: &surf::Protocol, sender: &str, tool: &str) -> bool {
    p.caps.get(sender).is_some_and(|cs| {
        cs.iter()
            .any(|c| c.tool == tool && !c.mode.trim().eq_ignore_ascii_case("read"))
    })
}

fn is_irreversible(
    p: &surf::Protocol,
    sender: &str,
    irreversible: bool,
    uses: &Option<String>,
) -> bool {
    irreversible || matches!(uses, Some(t) if cap_effectful(p, sender, t))
}

fn approval_walk(p: &surf::Protocol, g: &surf::Gtyp, approved: bool, ok: &mut bool) {
    match g {
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
        surf::Gtyp::Rec { body, .. } => approval_walk(p, body, false, ok), // consent survives no iteration
        surf::Gtyp::Comm {
            sender,
            uses,
            irreversible,
            on_crash,
            cont,
            ..
        } => {
            if is_irreversible(p, sender, *irreversible, uses) && !approved {
                *ok = false;
            }
            approval_walk(p, cont, approved, ok);
            if let Some(oc) = on_crash {
                approval_walk(p, oc, approved, ok);
            }
        }
        surf::Gtyp::Choice {
            approval, branches, ..
        } => {
            for b in branches {
                let br_approved = if *approval && b.consent {
                    true
                } else {
                    approved
                };
                approval_walk(p, &b.cont, br_approved, ok);
            }
        }
    }
}

/// Approval dominance: every effect-bearing action is dominated by a human approval-consent gate.
pub fn approval_dominated(p: &surf::Protocol) -> bool {
    let mut ok = true;
    approval_walk(p, &p.gtype, false, &mut ok);
    ok
}

// -- pipeline-safety (on the surface AST: needs the `oracle`/`verified` markers + contract presence).
//    Mirrors spike_pipeline.pipeline_safe: R1 no node is both `oracle` AND `verified` (opaque vs. proven);
//    R2 every `oracle` node carries a contract (the monitored boundary). --
fn pipeline_walk(g: &surf::Gtyp, ok: &mut bool) {
    match g {
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
        surf::Gtyp::Rec { body, .. } => pipeline_walk(body, ok),
        surf::Gtyp::Comm {
            from_oracle,
            verified,
            contract,
            on_crash,
            cont,
            ..
        } => {
            if *from_oracle && *verified {
                *ok = false; // R1
            }
            if *from_oracle && contract.is_none() {
                *ok = false; // R2
            }
            pipeline_walk(cont, ok);
            if let Some(oc) = on_crash {
                pipeline_walk(oc, ok);
            }
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                pipeline_walk(&b.cont, ok);
            }
        }
    }
}

/// Pipeline well-formedness: oracle nodes are monitored (carry a contract) and never also `verified`.
pub fn pipeline_safe(p: &surf::Protocol) -> bool {
    let mut ok = true;
    pipeline_walk(&p.gtype, &mut ok);
    ok
}

// -- linearity (promise discipline): every oracle output (a "promise") is sent EXACTLY ONCE along its
//    producer's local type (write-once + obligation). Mirrors spike_hardening.linearity_check. --
fn promises(g: &core::Gtyp, out: &mut Vec<(String, String)>) {
    match g {
        core::Gtyp::Comm {
            sender,
            label,
            from_oracle,
            on_crash,
            cont,
            ..
        } => {
            if *from_oracle {
                out.push((sender.clone(), label.clone()));
            }
            promises(cont, out);
            if let Some(oc) = on_crash {
                promises(oc, out);
            }
        }
        core::Gtyp::Choice { branches, .. } => {
            for b in branches {
                promises(&b.cont, out);
            }
        }
        core::Gtyp::Rec { body, .. } => promises(body, out),
        core::Gtyp::End | core::Gtyp::Var(_) => {}
    }
}

fn count_sends(l: &core::Ltyp, label: &str) -> (u32, u32) {
    match l {
        core::Ltyp::End | core::Ltyp::Var(_) => (0, 0),
        core::Ltyp::Rec { body, .. } => count_sends(body, label),
        core::Ltyp::Send {
            label: lbl, cont, ..
        } => {
            let c = if lbl == label { 1 } else { 0 };
            let (mn, mx) = count_sends(cont, label);
            (c + mn, c + mx)
        }
        core::Ltyp::Recv { cont, .. } => count_sends(cont, label),
        core::Ltyp::IntChoice { opts, .. } | core::Ltyp::ExtChoice { opts, .. } => {
            if opts.is_empty() {
                return (0, 0);
            }
            let rs: Vec<(u32, u32)> = opts.iter().map(|(_, _, c)| count_sends(c, label)).collect();
            (
                rs.iter().map(|r| r.0).min().unwrap(),
                rs.iter().map(|r| r.1).max().unwrap(),
            )
        }
    }
}

/// Promise linearity: every oracle output is sent exactly once along the producer's projected local type.
pub fn linearity(p: &surf::Protocol) -> bool {
    let g = bridge_gtyp(&p.gtype);
    let mut proms = Vec::new();
    promises(&g, &mut proms);
    for (sender, label) in &proms {
        match core::project(&g, sender) {
            Ok(l) => {
                let (mn, mx) = count_sends(&l, label);
                if !(mn == 1 && mx == 1) {
                    return false;
                }
            }
            Err(_) => return false, // non-projectable producer ⇒ write-once cannot be established
        }
    }
    true
}

// -- stream safety (LH-F-009): every `stream` loop dispatches via a Choice whose selector is an env
//    role (each iteration consumes an external event ⇒ productivity) and carries a TERMINATING handler
//    in every branch. Mirrors spike_hardening.stream_wellformed + _handler_terminates. --
fn handler_terminates(g: &surf::Gtyp) -> bool {
    match g {
        surf::Gtyp::Comm { cont, on_crash, .. } => {
            handler_terminates(cont)
                && match on_crash {
                    Some(oc) => handler_terminates(oc),
                    None => true,
                }
        }
        surf::Gtyp::Choice { branches, .. } => branches.iter().all(|b| handler_terminates(&b.cont)),
        surf::Gtyp::Rec {
            stream,
            measure,
            body,
            ..
        } => {
            // an unbounded inner loop (a nested stream, or a rec with no measure) does NOT terminate
            if *stream || measure.is_none() {
                false
            } else {
                handler_terminates(body)
            }
        }
        surf::Gtyp::End | surf::Gtyp::Var(_) => true,
    }
}

fn collect_recs<'a>(g: &'a surf::Gtyp, out: &mut Vec<&'a surf::Gtyp>) {
    match g {
        surf::Gtyp::Comm { cont, on_crash, .. } => {
            collect_recs(cont, out);
            if let Some(oc) = on_crash {
                collect_recs(oc, out);
            }
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                collect_recs(&b.cont, out);
            }
        }
        surf::Gtyp::Rec { body, .. } => {
            out.push(g);
            collect_recs(body, out);
        }
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

/// Stream/event-loop safety: each `stream` loop is env-driven (its dispatch Choice's selector is an
/// env role) and every branch handler terminates (no unbounded inner loop).
pub fn stream_safe(p: &surf::Protocol) -> bool {
    let env: std::collections::BTreeSet<&str> = p.env.iter().map(|s| s.as_str()).collect();
    let mut recs: Vec<&surf::Gtyp> = Vec::new();
    collect_recs(&p.gtype, &mut recs);
    for r in recs {
        if let surf::Gtyp::Rec { stream, body, .. } = r {
            if !*stream {
                continue;
            }
            match body.as_ref() {
                surf::Gtyp::Choice {
                    sender, branches, ..
                } => {
                    if !env.contains(sender.as_str()) {
                        return false; // dispatch selector is not an env role
                    }
                    if !branches.iter().all(|b| handler_terminates(&b.cont)) {
                        return false; // a handler has an unbounded inner loop
                    }
                }
                _ => return false, // stream body is not a dispatch choice
            }
        }
    }
    true
}

// -- termination (ranking): every loop declares a measure (stream loops are EXEMPT — their liveness is
//    "every handler terminates", checked by stream_safe). The well-founded ranking lemma itself (a
//    strictly-decreasing measure bounded below terminates) is a protocol-INDEPENDENT SMT tautology, so it
//    is a constant True; the only protocol-dependent obligation is measure coverage. Mirrors
//    spike_hardening.termination_check (which re-proves that constant lemma via z3 on each run). --
/// Termination: every non-`stream` loop declares a ranking measure.
pub fn termination(p: &surf::Protocol) -> bool {
    let mut recs: Vec<&surf::Gtyp> = Vec::new();
    collect_recs(&p.gtype, &mut recs);
    recs.iter().all(|r| match r {
        surf::Gtyp::Rec {
            stream, measure, ..
        } => *stream || measure.is_some(),
        _ => true,
    })
}

// -- crash tolerance (resilience, SHOULD): every receive from a crash-prone sender has a typed
//    `on_crash` continuation (else the receiver could block forever). The crash-prone set = the
//    protocol's `crash` declarations. Mirrors spike_resilience.crash_tolerance. --
fn crash_walk(g: &surf::Gtyp, crash: &std::collections::BTreeSet<&str>, ok: &mut bool) {
    match g {
        surf::Gtyp::Comm {
            sender,
            on_crash,
            cont,
            ..
        } => {
            if crash.contains(sender.as_str()) && on_crash.is_none() {
                *ok = false;
            }
            crash_walk(cont, crash, ok);
            if let Some(oc) = on_crash {
                crash_walk(oc, crash, ok);
            }
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                crash_walk(&b.cont, crash, ok);
            }
        }
        surf::Gtyp::Rec { body, .. } => crash_walk(body, crash, ok),
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

/// Crash tolerance: every receive from a crash-prone sender carries a typed `on_crash` continuation.
pub fn crash_tolerance(p: &surf::Protocol) -> bool {
    let crash: std::collections::BTreeSet<&str> = p.crash.iter().map(|s| s.as_str()).collect();
    let mut ok = true;
    crash_walk(&p.gtype, &crash, &mut ok);
    ok
}

// -- ttl-safety (LH-Q-008, SHOULD): a finite-ttl capability used inside a loop is safe iff its ttl covers
//    the loop's iteration bound. A `stream` loop re-grants the capability PER ITERATION (refresh), so the
//    ttl need only cover the uses along a SINGLE handler path. Mirrors spike_hardening.ttl_safety_check
//    (+ _path_uses, _uses_in). Note: matches Python's two different max_iters idioms — `is not None` in the
//    loop-bound walk (0 ⇒ Bounded(0)) vs. truthiness in _path_uses (0 ⇒ 1). --
#[derive(Clone, Copy)]
enum LoopBound {
    Outside,
    Bounded(i64),
    Unbounded,
}

fn cap_ttl(p: &surf::Protocol, sender: &str, tool: &str) -> Option<i64> {
    p.caps
        .get(sender)
        .and_then(|cs| cs.iter().find(|c| c.tool == tool))
        .map(|c| c.ttl)
}

/// max uses of (sender, tool) along a single iteration path (inner bounded loop counts uses × max_iters;
/// inner stream counts per-iteration). Mirrors spike_hardening._path_uses.
fn path_uses(g: &surf::Gtyp, sender: &str, tool: &str) -> i64 {
    match g {
        surf::Gtyp::Comm {
            sender: s,
            uses,
            on_crash,
            cont,
            ..
        } => {
            let h = i64::from(s == sender && uses.as_deref() == Some(tool));
            let mut nxt = path_uses(cont, sender, tool);
            if let Some(oc) = on_crash {
                nxt = nxt.max(path_uses(oc, sender, tool));
            }
            h + nxt
        }
        surf::Gtyp::Choice { branches, .. } => branches
            .iter()
            .map(|b| path_uses(&b.cont, sender, tool))
            .max()
            .unwrap_or(0),
        surf::Gtyp::Rec {
            stream,
            max_iters,
            body,
            ..
        } => {
            let per = path_uses(body, sender, tool);
            if *stream {
                per
            } else {
                let m = match max_iters {
                    Some(n) if *n != 0 => *n,
                    _ => 1, // None or 0 ⇒ 1 (Python truthiness idiom)
                };
                per * m
            }
        }
        surf::Gtyp::End | surf::Gtyp::Var(_) => 0,
    }
}

/// collect every (sender, tool) capability use in a subtree. Mirrors spike_hardening._uses_in.
fn uses_in<'a>(g: &'a surf::Gtyp, acc: &mut std::collections::BTreeSet<(&'a str, &'a str)>) {
    match g {
        surf::Gtyp::Comm {
            sender,
            uses,
            on_crash,
            cont,
            ..
        } => {
            if let Some(t) = uses {
                acc.insert((sender.as_str(), t.as_str()));
            }
            uses_in(cont, acc);
            if let Some(oc) = on_crash {
                uses_in(oc, acc);
            }
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                uses_in(&b.cont, acc);
            }
        }
        surf::Gtyp::Rec { body, .. } => uses_in(body, acc),
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

fn ttl_walk(p: &surf::Protocol, g: &surf::Gtyp, bound: LoopBound, ok: &mut bool) {
    match g {
        surf::Gtyp::Comm {
            sender,
            uses,
            on_crash,
            cont,
            ..
        } => {
            if let Some(tool) = uses {
                if let Some(ttl) = cap_ttl(p, sender, tool) {
                    match bound {
                        LoopBound::Unbounded => *ok = false,
                        LoopBound::Bounded(b) if ttl < b => *ok = false,
                        _ => {}
                    }
                }
            }
            ttl_walk(p, cont, bound, ok);
            if let Some(oc) = on_crash {
                ttl_walk(p, oc, bound, ok);
            }
        }
        surf::Gtyp::Choice { branches, .. } => {
            for b in branches {
                ttl_walk(p, &b.cont, bound, ok);
            }
        }
        surf::Gtyp::Rec {
            stream,
            max_iters,
            body,
            ..
        } => {
            if *stream {
                // refresh per iteration: ttl must cover the uses of a SINGLE handler path
                let mut used = std::collections::BTreeSet::new();
                uses_in(body, &mut used);
                for &(sender, tool) in &used {
                    if let Some(ttl) = cap_ttl(p, sender, tool) {
                        if ttl < path_uses(body, sender, tool) {
                            *ok = false;
                        }
                    }
                }
                ttl_walk(p, body, LoopBound::Outside, ok); // inner bounded loops check themselves
            } else {
                let b = match max_iters {
                    Some(n) => LoopBound::Bounded(*n), // `is not None` idiom (0 ⇒ Bounded(0))
                    None => LoopBound::Unbounded,
                };
                ttl_walk(p, body, b, ok);
            }
        }
        surf::Gtyp::End | surf::Gtyp::Var(_) => {}
    }
}

/// ttl-safety: a finite-ttl capability used in a loop has ttl covering the loop's iteration bound (a
/// `stream` loop refreshes per iteration, so ttl need only cover a single handler path).
pub fn ttl_safety(p: &surf::Protocol) -> bool {
    let mut ok = true;
    ttl_walk(p, &p.gtype, LoopBound::Outside, &mut ok);
    ok
}

/// Run the ported MUST checks on a parsed protocol.
pub fn check(p: &surf::Protocol) -> Report {
    let (g, caps) = to_core(p);
    Report {
        wellformed: core::wellformed_core(&g),
        wellformed_user: wellformed_userfacing(p),
        capability_contained: core::capability_check(&g, &caps).is_ok(),
        approval_safe: approval_dominated(p),
        pipeline_safe: pipeline_safe(p),
        linearity: linearity(p),
        stream_safe: stream_safe(p),
        termination: termination(p),
        crash_tolerance: crash_tolerance(p),
        ttl_safety: ttl_safety(p),
        concurrency_certified: concurrency::concurrency_certified(&g),
    }
}

/// End-to-end: `.casl` text → verdicts (parse via casl-surface, then check).
pub fn check_text(src: &str) -> Result<Report, String> {
    Ok(check(&surf::parse(src)?))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn linear_protocol_is_wellformed_and_contained() {
        // linear, no choice/rec/uses ⇒ projectable for all four core roles {C,A,J,D} ⇒ well-formed; contained.
        let src = "protocol P {\n  roles C, A, J;\n  C -> A : M(x: Int);\n  A -> J : N();\n  J -> C : O();\n}";
        assert_eq!(
            check_text(src).unwrap(),
            Report {
                wellformed: true,
                wellformed_user: true,
                capability_contained: true,
                approval_safe: true,
                pipeline_safe: true,
                linearity: true,
                stream_safe: true,
                termination: true,
                crash_tolerance: true,
                ttl_safety: true,
                concurrency_certified: true,
            }
        );
    }

    #[test]
    fn recursive_choice_not_wellformed_core_for_absent_role() {
        // wellformed_core quirk (matches the F*-pinned predicate): this loop is well-formed over its OWN roles
        // {C,A,J}, but wellformed_core projects over the FIXED {C,A,J,D}; the absent role D cannot reconcile
        // Accept (terminate) vs Reject (loop back) ⇒ not projectable for D ⇒ wellformed_core = false.
        let src = "protocol P {\n  roles C, A, J;\n  rec Loop {\n    A -> J : Draft(x: Int);\n    choice at J -> C {\n      Accept: { J -> A : Done(); }\n      Reject: { J -> A : Retry(); continue Loop; }\n    }\n  }\n}";
        assert!(!check_text(src).unwrap().wellformed);
    }

    #[test]
    fn undeclared_tool_violates_containment() {
        // A uses `search` but declares no caps ⇒ Least-Privilege violation; still well-formed structurally
        let src = "protocol P {\n  roles C, A, J;\n  A -> J : Draft(x: Int) uses search;\n}";
        let r = check_text(src).unwrap();
        assert!(r.wellformed && !r.capability_contained);
    }
}
