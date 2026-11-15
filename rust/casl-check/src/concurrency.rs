//! Founded-concurrency gate (LH-Q-001d) — a faithful port of `semantics.correspondence_class` +
//! `kernel.concurrency_certified`. A protocol is `certified` iff, at every reachable state, the events the
//! GLOBAL type enables (head + role-disjoint prefix swaps) EXACTLY match those the endpoint CONFIGURATION
//! (the projected local types running together) enables. `global ⊋ config` = unsound (safety-critical),
//! `global ⊊ config` = incomplete (endpoints more concurrent than the soundly-underestimating global
//! semantics captures ⇒ deny-by-default reject), deadlock = unsound. The gate accepts ONLY `certified`.
//!
//! Operational substrate (BFS/DFS over (global, config) pairs, capped) mirrors `semantics.py` 1:1 and reuses
//! `casl-core::project` for the configuration. Characterization-pinned to the Python reference by the
//! casl-check verdict differential (no F\* proof — the operational metatheory stays in `metatheory.py`).
use casl_core as core;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

type Event = (String, String, String); // (sender, receiver, label)
type Cfg = BTreeMap<String, core::Ltyp>;

const MAX_STATES: i64 = 200;
const UNFOLD_CAP: i64 = 50;

// ---------- global substitution / unfolding ----------
/// Rebuild a `Comm` with a new continuation (mirrors `dataclasses.replace(g, cont=...)`; on_crash kept).
fn comm_with_cont(c: &core::Gtyp, new_cont: core::Gtyp) -> core::Gtyp {
    if let core::Gtyp::Comm {
        sender,
        receiver,
        label,
        fields,
        contract,
        uses_capability,
        from_oracle,
        on_crash,
        ..
    } = c
    {
        core::Gtyp::Comm {
            sender: sender.clone(),
            receiver: receiver.clone(),
            label: label.clone(),
            fields: fields.clone(),
            contract: contract.clone(),
            uses_capability: uses_capability.clone(),
            from_oracle: *from_oracle,
            on_crash: on_crash.clone(),
            cont: Box::new(new_cont),
        }
    } else {
        unreachable!("comm_with_cont on non-Comm")
    }
}

fn subst_global(g: &core::Gtyp, var: &str, repl: &core::Gtyp) -> core::Gtyp {
    match g {
        core::Gtyp::End => core::Gtyp::End,
        core::Gtyp::Var(x) => {
            if x == var {
                repl.clone()
            } else {
                core::Gtyp::Var(x.clone())
            }
        }
        core::Gtyp::Rec {
            var: v,
            body,
            measure,
            max_iters,
        } => {
            if v == var {
                g.clone()
            } else {
                core::Gtyp::Rec {
                    var: v.clone(),
                    body: Box::new(subst_global(body, var, repl)),
                    measure: measure.clone(),
                    max_iters: *max_iters,
                }
            }
        }
        // Python substitutes into `cont` only (not on_crash).
        core::Gtyp::Comm { cont, .. } => comm_with_cont(g, subst_global(cont, var, repl)),
        core::Gtyp::Choice {
            sender,
            receiver,
            branches,
        } => core::Gtyp::Choice {
            sender: sender.clone(),
            receiver: receiver.clone(),
            branches: branches
                .iter()
                .map(|b| core::Branch {
                    label: b.label.clone(),
                    fields: b.fields.clone(),
                    cont: subst_global(&b.cont, var, repl),
                    contract: b.contract.clone(),
                })
                .collect(),
        },
    }
}

fn unfold_global(g: &core::Gtyp) -> core::Gtyp {
    let mut cur = g.clone();
    let mut n = 0;
    while let core::Gtyp::Rec { var, body, .. } = &cur {
        let v = var.clone();
        let b = (**body).clone();
        let whole = cur.clone();
        cur = subst_global(&b, &v, &whole);
        n += 1;
        if n > UNFOLD_CAP {
            break;
        }
    }
    cur
}

// ---------- global reduction (with the LH-Q-001d swap rule) ----------
fn prefix_swaps(g: &core::Gtyp, blocked: &BTreeSet<String>) -> Vec<(Event, core::Gtyp)> {
    let mut out = Vec::new();
    if let core::Gtyp::Comm {
        sender,
        receiver,
        label,
        cont,
        ..
    } = g
    {
        if !blocked.contains(sender) && !blocked.contains(receiver) {
            out.push((
                (sender.clone(), receiver.clone(), label.clone()),
                (**cont).clone(),
            ));
            let mut b2 = blocked.clone();
            b2.insert(sender.clone());
            b2.insert(receiver.clone());
            for (ev2, res) in prefix_swaps(cont, &b2) {
                out.push((ev2, comm_with_cont(g, res)));
            }
        }
        // head shares a role with `blocked` ⇒ nothing behind it is independent either.
    }
    out
}

fn step_global(g: &core::Gtyp) -> Vec<(Event, core::Gtyp)> {
    let g = unfold_global(g);
    match &g {
        core::Gtyp::Comm {
            sender,
            receiver,
            label,
            cont,
            ..
        } => {
            let mut out = vec![(
                (sender.clone(), receiver.clone(), label.clone()),
                (**cont).clone(),
            )];
            let mut blocked = BTreeSet::new();
            blocked.insert(sender.clone());
            blocked.insert(receiver.clone());
            for (ev, res) in prefix_swaps(cont, &blocked) {
                out.push((ev, comm_with_cont(&g, res)));
            }
            out
        }
        core::Gtyp::Choice {
            sender,
            receiver,
            branches,
        } => branches
            .iter()
            .map(|br| {
                (
                    (sender.clone(), receiver.clone(), br.label.clone()),
                    br.cont.clone(),
                )
            })
            .collect(),
        _ => Vec::new(),
    }
}

// ---------- roles + configuration ----------
fn roles_of(g: &core::Gtyp, out: &mut BTreeSet<String>) {
    match g {
        core::Gtyp::Comm {
            sender,
            receiver,
            cont,
            on_crash,
            ..
        } => {
            out.insert(sender.clone());
            out.insert(receiver.clone());
            roles_of(cont, out);
            if let Some(oc) = on_crash {
                roles_of(oc, out);
            }
        }
        core::Gtyp::Choice {
            sender,
            receiver,
            branches,
        } => {
            out.insert(sender.clone());
            out.insert(receiver.clone());
            for b in branches {
                roles_of(&b.cont, out);
            }
        }
        core::Gtyp::Rec { body, .. } => roles_of(body, out),
        core::Gtyp::End | core::Gtyp::Var(_) => {}
    }
}

/// `config(g)` = {role: project(g, role)} over all roles (≥4 supported); Err if a role is non-projectable.
fn config(g: &core::Gtyp) -> Result<Cfg, core::NonProjectable> {
    let mut rs = BTreeSet::new();
    roles_of(g, &mut rs);
    if rs.is_empty() {
        for r in ["C", "A", "J", "D"] {
            rs.insert(r.to_string());
        }
    }
    let mut cfg = BTreeMap::new();
    for r in rs {
        cfg.insert(r.clone(), core::project(g, &r)?);
    }
    Ok(cfg)
}

// ---------- local unfolding + endpoint reduction ----------
fn subst_local(l: &core::Ltyp, var: &str, repl: &core::Ltyp) -> core::Ltyp {
    match l {
        core::Ltyp::End => core::Ltyp::End,
        core::Ltyp::Var(x) => {
            if x == var {
                repl.clone()
            } else {
                core::Ltyp::Var(x.clone())
            }
        }
        core::Ltyp::Rec { var: v, body } => {
            if v == var {
                l.clone()
            } else {
                core::Ltyp::Rec {
                    var: v.clone(),
                    body: Box::new(subst_local(body, var, repl)),
                }
            }
        }
        core::Ltyp::Send {
            to,
            label,
            fields,
            cont,
        } => core::Ltyp::Send {
            to: to.clone(),
            label: label.clone(),
            fields: fields.clone(),
            cont: Box::new(subst_local(cont, var, repl)),
        },
        core::Ltyp::Recv {
            from,
            label,
            fields,
            cont,
        } => core::Ltyp::Recv {
            from: from.clone(),
            label: label.clone(),
            fields: fields.clone(),
            cont: Box::new(subst_local(cont, var, repl)),
        },
        core::Ltyp::IntChoice { to, opts } => core::Ltyp::IntChoice {
            to: to.clone(),
            opts: opts
                .iter()
                .map(|(lb, f, c)| (lb.clone(), f.clone(), subst_local(c, var, repl)))
                .collect(),
        },
        core::Ltyp::ExtChoice { from, opts } => core::Ltyp::ExtChoice {
            from: from.clone(),
            opts: opts
                .iter()
                .map(|(lb, f, c)| (lb.clone(), f.clone(), subst_local(c, var, repl)))
                .collect(),
        },
    }
}

fn unfold_local(l: &core::Ltyp) -> core::Ltyp {
    let mut cur = l.clone();
    let mut n = 0;
    while let core::Ltyp::Rec { var, body } = &cur {
        let v = var.clone();
        let b = (**body).clone();
        let whole = cur.clone();
        cur = subst_local(&b, &v, &whole);
        n += 1;
        if n > UNFOLD_CAP {
            break;
        }
    }
    cur
}

/// Possible sends of an (unfolded) local type → [(to, label, cont)].
fn sends(l: &core::Ltyp) -> Vec<(String, String, core::Ltyp)> {
    match unfold_local(l) {
        core::Ltyp::Send {
            to, label, cont, ..
        } => vec![(to, label, *cont)],
        core::Ltyp::IntChoice { to, opts } => opts
            .into_iter()
            .map(|(lb, _f, c)| (to.clone(), lb, c))
            .collect(),
        _ => Vec::new(),
    }
}

/// If the (unfolded) local type can receive `label` from `frm`, return the continuation.
fn recv_cont(l: &core::Ltyp, frm: &str, label: &str) -> Option<core::Ltyp> {
    match unfold_local(l) {
        core::Ltyp::Recv {
            from,
            label: lb,
            cont,
            ..
        } if from == frm && lb == label => Some(*cont),
        core::Ltyp::ExtChoice { from, opts } if from == frm => opts
            .into_iter()
            .find(|(l2, _f, _c)| l2 == label)
            .map(|(_l2, _f, c)| c),
        _ => None,
    }
}

fn step_config(cfg: &Cfg) -> Vec<(Event, Cfg)> {
    let mut steps = Vec::new();
    for p in cfg.keys() {
        for (q, label, cont_p) in sends(&cfg[p]) {
            if let Some(cont_q) = cfg.get(&q).and_then(|lq| recv_cont(lq, p, &label)) {
                let mut new = cfg.clone();
                new.insert(p.clone(), cont_p.clone());
                new.insert(q.clone(), cont_q);
                steps.push(((p.clone(), q.clone(), label.clone()), new));
            }
        }
    }
    steps
}

fn terminal_config(cfg: &Cfg) -> bool {
    cfg.values()
        .all(|l| matches!(unfold_local(l), core::Ltyp::End))
}

/// The concurrency class of `g`: "certified" | "incomplete" | "unsound". DFS over (global, config) pairs
/// (frontier = stack, matching Python `list.pop()`); capped at MAX_STATES ⇒ "certified".
fn correspondence_class(g: &core::Gtyp) -> &'static str {
    let cfg0 = match config(g) {
        Ok(c) => c,
        Err(_) => return "incomplete", // not projectable (well-formedness applies separately)
    };
    let mut seen: HashSet<String> = HashSet::new();
    let mut frontier: Vec<(core::Gtyp, Cfg)> = vec![(g.clone(), cfg0)];
    let mut n: i64 = 0;
    while let Some((gs, cs)) = frontier.pop() {
        let key = format!("{gs:?}|{cs:?}");
        if !seen.insert(key) {
            continue;
        }
        n += 1;
        if n > MAX_STATES {
            return "certified"; // capped
        }
        let gsteps = step_global(&gs);
        let csteps = step_config(&cs);
        let eg: BTreeSet<Event> = gsteps.iter().map(|(e, _)| e.clone()).collect();
        let ec: BTreeSet<Event> = csteps.iter().map(|(e, _)| e.clone()).collect();
        if eg.difference(&ec).next().is_some() {
            return "unsound";
        }
        if ec.difference(&eg).next().is_some() {
            return "incomplete";
        }
        if !terminal_config(&cs) && ec.is_empty() {
            return "unsound"; // deadlock
        }
        let mut cmap: HashMap<Event, Cfg> = HashMap::new();
        for (e, c2) in &csteps {
            cmap.insert(e.clone(), c2.clone());
        }
        for (ev, gs2) in gsteps {
            if let Some(c2) = cmap.get(&ev) {
                frontier.push((gs2, c2.clone()));
            }
        }
    }
    "certified"
}

/// LH-Q-001d gate: accept only a `certified` concurrency class (deny-by-default).
pub fn concurrency_certified(g: &core::Gtyp) -> bool {
    correspondence_class(g) == "certified"
}
