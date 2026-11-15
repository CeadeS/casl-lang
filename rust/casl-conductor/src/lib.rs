//! casl-conductor — the deterministic CASL interpreter core, ported from `src/casl/run.run_protocol`.
//!
//! "Prove the hull, then EXECUTE it." The interpreter walks the verified-shape global type and:
//!   · oracle step  → asks the (deterministic mock) backend for a cost, then checks the step's contract with
//!     the budget/refusal monitor (the verdict drives the next branch);
//!   · choice        → monitor-verdict branch policy (ok → a terminating branch, else → a looping branch);
//!     an `approval` choice routes to a consent branch only on an external release (deny-by-default);
//!   · capability    → the tool broker interposes (`uses` must be carried at runtime; revoked ⇒ denied);
//!   · forwarding    → a forwarded field's source must already be produced upstream (A1, LH-F-012);
//!   · recursion     → bounded by `max_loops` so every run terminates.
//!
//! This is the `dispatch=None` deterministic path (the proven single-file interpreter). The live-LLM and
//! broker-PROCESS dispatch paths are out of scope (key-gated; the Rust broker is a separate, at-parity
//! crate). Pinned to the Python authority (`run.run_protocol` with `oracle.MockBackend`) by a single-sourced
//! run-trace differential over the STRUCTURED result: outcome / loops / last verdict / accepted label /
//! honored forwards. Walks the `casl-surface` AST directly.
#![forbid(unsafe_code)]

use casl_surface as surf;
use std::collections::{BTreeMap, BTreeSet};

/// The structured result of a run (the prose trace + observability capture are rendering detail, omitted).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunResult {
    pub outcome: String, // completed | loop_bound_reached | tool_denied | forward_violation | approval_denied
    pub loops: i64,
    pub last_verdict: Option<String>, // "ok" | "violation" | "refusal"
    pub accepted_label: Option<String>,
    pub forwards: Vec<String>, // A1 forwarding edges honored (only on completed / forward_violation, per the ref)
}

// -- the deterministic mock oracle (mirrors oracle.MockBackend) --
struct Mock {
    scenario: String,
    calls: i64,
}
struct OracleOut {
    cost: Option<i64>,
    measured: Option<i64>,
    refused: bool,
}
impl Mock {
    fn generate(&mut self, budget: i64) -> OracleOut {
        self.calls += 1;
        match self.scenario.as_str() {
            "refusal" => OracleOut {
                cost: None,
                measured: None,
                refused: true,
            },
            "overspend" => {
                let c = budget + 25;
                OracleOut {
                    cost: Some(c),
                    measured: Some(c),
                    refused: false,
                }
            }
            "underreport" => OracleOut {
                cost: Some(budget.min(10)),
                measured: Some(budget + 25),
                refused: false,
            },
            "retry_then_ok" if self.calls == 1 => {
                let c = budget + 25;
                OracleOut {
                    cost: Some(c),
                    measured: Some(c),
                    refused: false,
                }
            }
            _ => {
                let c = budget.min(10);
                OracleOut {
                    cost: Some(c),
                    measured: Some(c),
                    refused: false,
                }
            }
        }
    }
}

fn operand_name(o: &surf::Operand) -> String {
    match o {
        surf::Operand::Sym(s) => s.clone(),
        surf::Operand::Int(n) => n.to_string(),
        surf::Operand::Null => "null".to_string(),
    }
}

fn resolve(o: &surf::Operand, menv: &BTreeMap<String, i64>) -> i64 {
    match o {
        surf::Operand::Int(n) => *n,
        surf::Operand::Sym(s) => menv.get(s).copied().unwrap_or(0),
        surf::Operand::Null => 0,
    }
}

/// Ask the mock for a cost, then the budget/refusal monitor's verdict ("ok"/"violation"/"refusal").
/// Mirrors `run._oracle_step` + `spike_resilience.synth_refusal_monitor` + `synth_monitor`.
fn oracle_verdict(
    contract: Option<&surf::Contract>,
    env: &BTreeMap<String, i64>,
    mock: &mut Mock,
) -> String {
    let is_le = matches!(contract, Some(c)
        if c.relation.len() >= 3 && c.relation.first() == Some(&surf::Operand::Sym("le".to_string())));
    // (lhs_key for menv, rhs operand) — for a `le` contract from the relation, else the cost/budget default.
    let (lhs_key, rhs_op) = if is_le {
        let c = contract.unwrap();
        (operand_name(&c.relation[1]), c.relation[2].clone())
    } else {
        ("cost".to_string(), surf::Operand::Sym("budget".to_string()))
    };
    let bound = match &rhs_op {
        surf::Operand::Sym(n) => env.get(n).copied().unwrap_or(0),
        _ => 0,
    };
    let out = mock.generate(bound);
    let measured = out.measured.or(out.cost);
    let _produced = measured.unwrap_or(bound + 1);
    match contract {
        None => "ok".to_string(),
        Some(c) => {
            if out.refused {
                return "refusal".to_string();
            }
            let mut menv: BTreeMap<String, i64> = BTreeMap::new();
            menv.insert(lhs_key, _produced);
            if let surf::Operand::Sym(n) = &rhs_op {
                menv.insert(n.clone(), bound);
            }
            let kind = operand_name(&c.relation[0]);
            let ok = if kind == "le" {
                resolve(&c.relation[1], &menv) <= resolve(&c.relation[2], &menv)
            } else if kind == "nonempty" {
                menv.contains_key(&operand_name(&c.relation[1]))
            } else {
                true
            };
            if ok { "ok" } else { "violation" }.to_string()
        }
    }
}

fn contains_tvar(g: &surf::Gtyp) -> bool {
    match g {
        surf::Gtyp::Var(_) => true,
        surf::Gtyp::Comm { cont, on_crash, .. } => {
            contains_tvar(cont) || on_crash.as_ref().is_some_and(|oc| contains_tvar(oc))
        }
        surf::Gtyp::Choice { branches, .. } => branches.iter().any(|b| contains_tvar(&b.cont)),
        surf::Gtyp::Rec { body, .. } => contains_tvar(body),
        surf::Gtyp::End => false,
    }
}

fn tool_allowed(
    sender: &str,
    uses: &Option<String>,
    caps: &BTreeMap<String, Vec<String>>,
    revoked: &BTreeSet<String>,
) -> bool {
    match uses {
        None => true,
        Some(tool) => {
            if revoked.contains(tool) {
                return false;
            }
            caps.get(sender)
                .is_some_and(|ts| ts.iter().any(|t| t == tool))
        }
    }
}

fn pick_branch(branches: &[surf::Branch], verdict: Option<&str>) -> usize {
    if verdict == Some("ok") {
        branches
            .iter()
            .position(|b| !contains_tvar(&b.cont))
            .unwrap_or(0)
    } else {
        branches
            .iter()
            .position(|b| contains_tvar(&b.cont))
            .unwrap_or(branches.len() - 1)
    }
}

fn pick_approval_branch(branches: &[surf::Branch], decision: bool) -> Option<usize> {
    if decision {
        // a consent branch if any, else the first branch (cand = consent or all)
        branches
            .iter()
            .position(|b| b.consent)
            .or(if branches.is_empty() { None } else { Some(0) })
    } else {
        // deny-by-default: a non-consent branch, else abort
        branches.iter().position(|b| !b.consent)
    }
}

/// Run a verified-shape global type to a structured result (deterministic mock oracle, `dispatch=None`).
/// `scenario` ∈ {ok, overspend, refusal, retry_then_ok, underreport}; `caps` is role→tools carried at
/// runtime; `revoked` are revoked tool names; `approve` is the external release decision (None ⇒ deny).
pub fn run_protocol(
    g: &surf::Gtyp,
    scenario: &str,
    env: &BTreeMap<String, i64>,
    max_loops: i64,
    approve: Option<bool>,
    caps: &BTreeMap<String, Vec<String>>,
    revoked: &BTreeSet<String>,
) -> RunResult {
    let mut mock = Mock {
        scenario: scenario.to_string(),
        calls: 0,
    };
    let mut rec_env: BTreeMap<String, &surf::Gtyp> = BTreeMap::new();
    let mut produced: BTreeSet<String> = BTreeSet::new();
    let mut forwards: Vec<String> = Vec::new();
    let mut loops = 0i64;
    let mut last_verdict: Option<String> = None;
    let mut accepted_label: Option<String> = None;
    let mut node = g;

    loop {
        match node {
            surf::Gtyp::End => {
                return RunResult {
                    outcome: "completed".into(),
                    loops,
                    last_verdict,
                    accepted_label,
                    forwards,
                };
            }
            surf::Gtyp::Rec { var, body, .. } => {
                rec_env.insert(var.clone(), body.as_ref());
                node = body.as_ref();
            }
            surf::Gtyp::Var(v) => {
                loops += 1;
                if loops > max_loops {
                    return RunResult {
                        outcome: "loop_bound_reached".into(),
                        loops,
                        last_verdict,
                        accepted_label,
                        forwards: Vec::new(), // ref: this return path does not carry forwards
                    };
                }
                node = rec_env.get(v).copied().expect("bound recursion variable");
            }
            surf::Gtyp::Comm {
                sender,
                uses,
                from_oracle,
                fields,
                contract,
                label,
                cont,
                ..
            } => {
                if !tool_allowed(sender, uses, caps, revoked) {
                    return RunResult {
                        outcome: "tool_denied".into(),
                        loops,
                        last_verdict,
                        accepted_label,
                        forwards: Vec::new(), // ref: tool_denied does not carry forwards
                    };
                }
                // A1: a forwarded field's source must be produced upstream (before this node).
                for f in fields {
                    if let Some(src) = &f.source {
                        if !produced.contains(src) {
                            return RunResult {
                                outcome: "forward_violation".into(),
                                loops,
                                last_verdict,
                                accepted_label,
                                forwards,
                            };
                        }
                        forwards.push(format!("{}.{} = {}", label, f.name, src));
                    }
                }
                if *from_oracle {
                    last_verdict = Some(oracle_verdict(contract.as_ref(), env, &mut mock));
                }
                for f in fields {
                    produced.insert(format!("{}.{}", label, f.name));
                }
                node = cont.as_ref();
            }
            surf::Gtyp::Choice {
                approval, branches, ..
            } => {
                let idx = if *approval {
                    let decision = approve.unwrap_or(false); // on_approval=None ⇒ explicit approve, else deny
                    match pick_approval_branch(branches, decision) {
                        Some(i) => i,
                        None => {
                            return RunResult {
                                outcome: "approval_denied".into(),
                                loops,
                                last_verdict,
                                accepted_label,
                                forwards: Vec::new(), // ref: approval_denied does not carry forwards
                            };
                        }
                    }
                } else {
                    pick_branch(branches, last_verdict.as_deref())
                };
                let br = &branches[idx];
                if !contains_tvar(&br.cont) {
                    accepted_label = Some(br.label.clone());
                }
                node = &br.cont;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(src: &str, scenario: &str, budget: i64, approve: Option<bool>) -> RunResult {
        let p = surf::parse(src).unwrap();
        let mut env = BTreeMap::new();
        env.insert("budget".to_string(), budget);
        let caps: BTreeMap<String, Vec<String>> = p
            .caps
            .iter()
            .map(|(r, cs)| (r.clone(), cs.iter().map(|c| c.tool.clone()).collect()))
            .collect();
        run_protocol(
            &p.gtype,
            scenario,
            &env,
            5,
            approve,
            &caps,
            &BTreeSet::new(),
        )
    }

    const LOOP: &str = "protocol P {\n  roles A, J, C;\n  rec Loop {\n    A -> J : Draft(cost: Int) [cost <= budget] oracle;\n    choice at J -> C {\n      Accept: { J -> A : Done(); }\n      Reject: { J -> A : Retry(); continue Loop; }\n    }\n  }\n}";

    #[test]
    fn ok_completes_first_pass() {
        let r = run(LOOP, "ok", 100, None);
        assert_eq!(r.outcome, "completed");
        assert_eq!(r.loops, 0);
        assert_eq!(r.last_verdict.as_deref(), Some("ok"));
        assert_eq!(r.accepted_label.as_deref(), Some("Accept"));
    }

    #[test]
    fn overspend_loops_to_bound() {
        let r = run(LOOP, "overspend", 100, None);
        assert_eq!(r.outcome, "loop_bound_reached");
        assert_eq!(r.last_verdict.as_deref(), Some("violation"));
    }

    #[test]
    fn retry_then_ok_takes_one_loop() {
        let r = run(LOOP, "retry_then_ok", 100, None);
        assert_eq!(r.outcome, "completed");
        assert_eq!(r.loops, 1);
    }

    #[test]
    fn underreport_caught_by_meter() {
        // claim ≤ budget but measured overspends ⇒ violation (loops to bound)
        let r = run(LOOP, "underreport", 100, None);
        assert_eq!(r.outcome, "loop_bound_reached");
        assert_eq!(r.last_verdict.as_deref(), Some("violation"));
    }
}
