//! # CASL reference engine (Rust)
//!
//! A **hand-written, idiomatic Rust** mirror of the CASL core: recursive,
//! string-labeled multiparty session types (the "nature of the language") with
//! the deterministic-hull analyses that are machine-verified in `fstar/CASL.fst`
//! and prototyped in `prototype/`:
//!
//!   * [`project`] + [`merge`]  — global type → local (endpoint) type (verified in F*)
//!   * [`wellformed`]           — MPST-projectability for every role
//!   * [`capability_check`]     — Least-Privilege containment (LH-Q-002 / LH-F-005)
//!
//! ## Status — read this
//!
//! This crate is **NOT** a machine extraction of the F* proof. The verified core
//! is string-labeled, recursive, `option`-returning algebraic data — which is the
//! *natural* fit for the OCaml extraction (`fstar/ocaml/`, done) and **not** for
//! the Low\*/`krml`/Eurydice → Rust pipeline (that path targets machine-integer,
//! GC-free, allocation-light code). Per `TBD-004`, OCaml carries the *verified
//! core*; **Rust is the engine.** This engine is faithful *by construction* to the
//! same types and algorithms, and its agreement with the verified core is pinned
//! by `cargo test` (the conformance suite cross-checks the canonical example and
//! the two deliberately-broken protocols against the Python/F* verdicts).
//!
//! It also dogfoods Rust's move/borrow (affine) semantics as the runtime analogue
//! of CASL's promise linearity (`LH-Q-003a`) and capability containment.

use std::collections::BTreeMap;

// --------------------------------------------------------------------------
// Payloads, contracts, capabilities  (mirror casl_core.py)
// --------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Field {
    pub name: String,
    pub sort: String, // Int | Real | Bool | Str
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Contract {
    /// Human-readable refinement, e.g. "cost <= budget". (The SMT relation lives
    /// in the F* core / Python Z3 spike; the engine carries the surface text.)
    pub text: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Capability {
    pub tool: String,
    pub params: Vec<String>,
    pub scope: String,
    pub ttl: i64,
    pub sigma: String,
}

/// Capability map: role → its capability set (upper bound = agent kind).
pub type CapMap = BTreeMap<String, Vec<Capability>>;

// --------------------------------------------------------------------------
// Global type AST (choreography)  (mirror casl_core.G)
// --------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Branch {
    pub label: String,
    pub fields: Vec<Field>,
    pub cont: Gtyp,
    pub contract: Option<Contract>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Gtyp {
    End,
    Var(String),
    Rec {
        var: String,
        body: Box<Gtyp>,
        measure: Option<String>,
        max_iters: Option<i64>,
    },
    Comm {
        sender: String,
        receiver: String,
        label: String,
        fields: Vec<Field>,
        cont: Box<Gtyp>,
        contract: Option<Contract>,
        uses_capability: Option<String>,
        from_oracle: bool,
        on_crash: Option<Box<Gtyp>>,
    },
    Choice {
        sender: String,
        receiver: String,
        branches: Vec<Branch>,
    },
}

// --------------------------------------------------------------------------
// Local (endpoint) type AST  (mirror spike_proj_mpst.L)
// --------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Ltyp {
    End,
    Var(String),
    Rec {
        var: String,
        body: Box<Ltyp>,
    },
    Send {
        to: String,
        label: String,
        fields: Vec<Field>,
        cont: Box<Ltyp>,
    },
    Recv {
        from: String,
        label: String,
        fields: Vec<Field>,
        cont: Box<Ltyp>,
    },
    /// internal choice (we decide & send)
    IntChoice {
        to: String,
        opts: Vec<(String, Vec<Field>, Ltyp)>,
    },
    /// external choice (we branch on the received label)
    ExtChoice {
        from: String,
        opts: Vec<(String, Vec<Field>, Ltyp)>,
    },
}

/// A role cannot locally determine which branch was taken.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct NonProjectable(pub String);

impl std::fmt::Display for NonProjectable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

// --------------------------------------------------------------------------
// Merge (hardened, W2): identical types merge to themselves; receives /
// external choices from the SAME partner merge by unioning labels and
// recursively merging the continuations of SHARED labels. Anything else —
// e.g. a send at the point of divergence — is non-mergeable.
// --------------------------------------------------------------------------

type Opts = Vec<(String, Vec<Field>, Ltyp)>;

fn as_options(t: &Ltyp) -> Option<(String, Opts)> {
    match t {
        Ltyp::Recv {
            from,
            label,
            fields,
            cont,
        } => Some((
            from.clone(),
            vec![(label.clone(), fields.clone(), (**cont).clone())],
        )),
        Ltyp::ExtChoice { from, opts } => Some((from.clone(), opts.clone())),
        _ => None,
    }
}

pub fn merge_pair(a: &Ltyp, b: &Ltyp) -> Result<Ltyp, NonProjectable> {
    if a == b {
        return Ok(a.clone());
    }
    if let (Some((pa, oa)), Some((pb, ob))) = (as_options(a), as_options(b)) {
        if pa == pb {
            let mut out: Opts = oa;
            for (lbl, flds, c) in ob {
                if let Some(slot) = out.iter_mut().find(|(l, _, _)| *l == lbl) {
                    let merged = merge_pair(&slot.2, &c)?; // shared label → recurse
                    slot.1 = flds;
                    slot.2 = merged;
                } else {
                    out.push((lbl, flds, c)); // disjoint label → keep both
                }
            }
            return Ok(Ltyp::ExtChoice {
                from: pa,
                opts: out,
            });
        }
    }
    Err(NonProjectable(
        "branches not mergeable (role cannot locally determine which branch was taken)".into(),
    ))
}

/// Merge the projections of a non-participating role across branches.
pub fn merge(types: &[Ltyp]) -> Result<Ltyp, NonProjectable> {
    let mut iter = types.iter();
    let first = match iter.next() {
        Some(t) => t.clone(),
        None => return Ok(Ltyp::End),
    };
    let mut result = first;
    for t in iter {
        result = merge_pair(&result, t)?;
    }
    Ok(result)
}

// --------------------------------------------------------------------------
// Projection  (mirror spike_proj_mpst.project)
// --------------------------------------------------------------------------

pub fn project(g: &Gtyp, r: &str) -> Result<Ltyp, NonProjectable> {
    match g {
        Gtyp::End => Ok(Ltyp::End),
        Gtyp::Var(x) => Ok(Ltyp::Var(x.clone())),
        Gtyp::Rec { var, body, .. } => Ok(Ltyp::Rec {
            var: var.clone(),
            body: Box::new(project(body, r)?),
        }),
        Gtyp::Comm {
            sender,
            receiver,
            label,
            fields,
            cont,
            ..
        } => {
            let c = project(cont, r)?;
            if r == sender {
                Ok(Ltyp::Send {
                    to: receiver.clone(),
                    label: label.clone(),
                    fields: fields.clone(),
                    cont: Box::new(c),
                })
            } else if r == receiver {
                Ok(Ltyp::Recv {
                    from: sender.clone(),
                    label: label.clone(),
                    fields: fields.clone(),
                    cont: Box::new(c),
                })
            } else {
                Ok(c)
            }
        }
        Gtyp::Choice {
            sender,
            receiver,
            branches,
        } => {
            if r == sender {
                let mut opts = Opts::new();
                for b in branches {
                    opts.push((b.label.clone(), b.fields.clone(), project(&b.cont, r)?));
                }
                Ok(Ltyp::IntChoice {
                    to: receiver.clone(),
                    opts,
                })
            } else if r == receiver {
                let mut opts = Opts::new();
                for b in branches {
                    opts.push((b.label.clone(), b.fields.clone(), project(&b.cont, r)?));
                }
                Ok(Ltyp::ExtChoice {
                    from: sender.clone(),
                    opts,
                })
            } else {
                let mut projs = Vec::with_capacity(branches.len());
                for b in branches {
                    projs.push(project(&b.cont, r)?);
                }
                merge(&projs)
            }
        }
    }
}

/// Static well-formedness (MPST half): projectable for every role.
/// The MSC-realizability cross-check lives in the Python CLI (`casl check`);
/// here projectability already rejects non-local choices via [`merge`].
pub fn wellformed(g: &Gtyp, roles: &[String]) -> bool {
    roles.iter().all(|r| project(g, r).is_ok())
}

// --------------------------------------------------------------------------
// Full F* well-formedness (mirrors `wellformed` in fstar/CASL.fst):
//   contractive ∧ no_self ∧ gdistinct ∧ closed ∧ projectable for {C,A,J,D}.
// Faithful by construction to the verified definitions; pinned to the F*-extracted
// kernel's verdicts by the corpus differential (tests/differential.rs).
// --------------------------------------------------------------------------

/// The four roles of the verified n-ary core (RC, RA, RJ, RD).
pub const CORE_ROLES: [&str; 4] = ["C", "A", "J", "D"];

fn contractive_chk(bound: &[String], g: &Gtyp) -> bool {
    match g {
        Gtyp::End => true,
        Gtyp::Var(t) => !bound.iter().any(|b| b == t),
        Gtyp::Rec { var, body, .. } => {
            let mut b2 = bound.to_vec();
            b2.push(var.clone());
            contractive_chk(&b2, body)
        }
        // a communication clears the bound set (the variable is now guarded)
        Gtyp::Comm { cont, .. } => contractive_chk(&[], cont),
        Gtyp::Choice { branches, .. } => branches.iter().all(|b| contractive_chk(&[], &b.cont)),
    }
}

/// Guarded recursion: every recursion variable is guarded by a communication (rules out `μt.t`).
pub fn contractive(g: &Gtyp) -> bool {
    contractive_chk(&[], g)
}

/// No self-communication: every `p→q` has `p ≠ q`, structurally.
pub fn no_self(g: &Gtyp) -> bool {
    match g {
        Gtyp::End | Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => no_self(body),
        Gtyp::Comm {
            sender,
            receiver,
            cont,
            ..
        } => sender != receiver && no_self(cont),
        Gtyp::Choice {
            sender,
            receiver,
            branches,
            ..
        } => sender != receiver && branches.iter().all(|b| no_self(&b.cont)),
    }
}

/// Distinct branch labels at every choice.
pub fn gdistinct(g: &Gtyp) -> bool {
    match g {
        Gtyp::End | Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => gdistinct(body),
        Gtyp::Comm { cont, .. } => gdistinct(cont),
        Gtyp::Choice { branches, .. } => {
            let labels: Vec<&String> = branches.iter().map(|b| &b.label).collect();
            let uniq: BTreeMap<&String, ()> = labels.iter().map(|l| (*l, ())).collect();
            labels.len() == uniq.len() && branches.iter().all(|b| gdistinct(&b.cont))
        }
    }
}

fn cl(bound: &[String], g: &Gtyp) -> bool {
    match g {
        Gtyp::End => true,
        Gtyp::Var(t) => bound.iter().any(|b| b == t),
        Gtyp::Rec { var, body, .. } => {
            let mut b2 = bound.to_vec();
            b2.push(var.clone());
            cl(&b2, body)
        }
        Gtyp::Comm { cont, .. } => cl(bound, cont),
        Gtyp::Choice { branches, .. } => branches.iter().all(|b| cl(bound, &b.cont)),
    }
}

/// Closed: no free type variables (every recursion variable is bound by an enclosing `Rec`).
pub fn closed(g: &Gtyp) -> bool {
    cl(&[], g)
}

/// The full F* `wellformed` (the authoritative checker verdict): contractive ∧ no_self ∧
/// gdistinct ∧ closed ∧ projectable for the four core roles {C,A,J,D}.
pub fn wellformed_core(g: &Gtyp) -> bool {
    contractive(g)
        && no_self(g)
        && gdistinct(g)
        && closed(g)
        && CORE_ROLES.iter().all(|&r| project(g, r).is_ok())
}

// --------------------------------------------------------------------------
// Capability containment (Least Privilege)  (mirror spike_capability)
// --------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct CapViolation {
    pub sender: String,
    pub tool: String,
    pub label: String,
}

pub fn capability_check(g: &Gtyp, caps: &CapMap) -> Result<(), Vec<CapViolation>> {
    fn has(caps: &CapMap, role: &str, tool: &str) -> bool {
        caps.get(role)
            .is_some_and(|set| set.iter().any(|c| c.tool == tool))
    }
    fn walk(n: &Gtyp, caps: &CapMap, out: &mut Vec<CapViolation>) {
        match n {
            Gtyp::Comm {
                sender,
                label,
                cont,
                uses_capability,
                on_crash,
                ..
            } => {
                if let Some(tool) = uses_capability {
                    if !has(caps, sender, tool) {
                        out.push(CapViolation {
                            sender: sender.clone(),
                            tool: tool.clone(),
                            label: label.clone(),
                        });
                    }
                }
                walk(cont, caps, out);
                if let Some(oc) = on_crash {
                    walk(oc, caps, out);
                }
            }
            Gtyp::Choice { branches, .. } => {
                for b in branches {
                    walk(&b.cont, caps, out);
                }
            }
            Gtyp::Rec { body, .. } => walk(body, caps, out),
            Gtyp::End | Gtyp::Var(_) => {}
        }
    }
    let mut out = Vec::new();
    walk(g, caps, &mut out);
    if out.is_empty() {
        Ok(())
    } else {
        Err(out)
    }
}

// --------------------------------------------------------------------------
// Pretty-printing  (mirror spike_proj_mpst.local_pretty)
// --------------------------------------------------------------------------

pub fn fields_str(fs: &[Field]) -> String {
    fs.iter()
        .map(|f| format!("{}:{}", f.name, f.sort))
        .collect::<Vec<_>>()
        .join(", ")
}

pub fn local_pretty(l: &Ltyp) -> String {
    match l {
        Ltyp::End => "end".to_string(),
        Ltyp::Var(x) => x.clone(),
        Ltyp::Rec { var, body } => format!("μ{}. {}", var, local_pretty(body)),
        Ltyp::Send {
            to,
            label,
            fields,
            cont,
        } => {
            format!(
                "{}!{}({}) . {}",
                to,
                label,
                fields_str(fields),
                local_pretty(cont)
            )
        }
        Ltyp::Recv {
            from,
            label,
            fields,
            cont,
        } => {
            format!(
                "{}?{}({}) . {}",
                from,
                label,
                fields_str(fields),
                local_pretty(cont)
            )
        }
        Ltyp::IntChoice { to, opts } => {
            let inner = opts
                .iter()
                .map(|(l, f, c)| format!("{}({}): {}", l, fields_str(f), local_pretty(c)))
                .collect::<Vec<_>>()
                .join("  ");
            format!("{}⊕{{ {} }}", to, inner)
        }
        Ltyp::ExtChoice { from, opts } => {
            let inner = opts
                .iter()
                .map(|(l, f, c)| format!("{}({}): {}", l, fields_str(f), local_pretty(c)))
                .collect::<Vec<_>>()
                .join("  ");
            format!("{}&{{ {} }}", from, inner)
        }
    }
}

// --------------------------------------------------------------------------
// Canonical fixtures — byte-for-byte the same protocols as examples/*.casl
// --------------------------------------------------------------------------

pub mod examples {
    use super::*;

    fn f(name: &str, sort: &str) -> Field {
        Field {
            name: name.into(),
            sort: sort.into(),
        }
    }

    fn comm(sender: &str, receiver: &str, label: &str, fields: Vec<Field>, cont: Gtyp) -> Gtyp {
        Gtyp::Comm {
            sender: sender.into(),
            receiver: receiver.into(),
            label: label.into(),
            fields,
            cont: Box::new(cont),
            contract: None,
            uses_capability: None,
            from_oracle: false,
            on_crash: None,
        }
    }

    /// A's only capability is `search` (matches examples/budgeted_qa.casl).
    pub fn agent_caps() -> CapMap {
        let mut m = CapMap::new();
        m.insert(
            "A".into(),
            vec![Capability {
                tool: "search".into(),
                params: vec!["query".into()],
                scope: "web:readonly".into(),
                ttl: 3,
                sigma: "sig-A1".into(),
            }],
        );
        m.insert("C".into(), vec![]);
        m.insert("J".into(), vec![]);
        m
    }

    pub fn roles() -> Vec<String> {
        vec!["C".into(), "A".into(), "J".into()]
    }

    /// examples/budgeted_qa.casl  ==  casl_core.G_OK
    pub fn budgeted_qa() -> Gtyp {
        let accept = Branch {
            label: "Accept".into(),
            fields: vec![],
            contract: None,
            cont: comm("J", "A", "Done", vec![], Gtyp::End),
        };
        let reject = Branch {
            label: "Reject".into(),
            fields: vec![f("reason", "Str")],
            contract: Some(Contract {
                text: "len(reason) > 0".into(),
            }),
            cont: comm("J", "A", "Retry", vec![], Gtyp::Var("Loop".into())),
        };
        let draft = Gtyp::Comm {
            sender: "A".into(),
            receiver: "J".into(),
            label: "Draft".into(),
            fields: vec![f("answer", "Str"), f("cost", "Int")],
            contract: Some(Contract {
                text: "cost <= budget".into(),
            }),
            uses_capability: Some("search".into()),
            from_oracle: true,
            on_crash: None,
            cont: Box::new(Gtyp::Choice {
                sender: "J".into(),
                receiver: "C".into(),
                branches: vec![accept, reject],
            }),
        };
        comm(
            "C",
            "A",
            "Request",
            vec![f("question", "Str"), f("budget", "Int")],
            Gtyp::Rec {
                var: "Loop".into(),
                body: Box::new(draft),
                measure: None,
                max_iters: None,
            },
        )
    }

    /// examples/non_projectable.casl — bystander A cannot tell the J→C branches apart.
    pub fn non_projectable() -> Gtyp {
        let accept = Branch {
            label: "Accept".into(),
            fields: vec![],
            contract: None,
            cont: Gtyp::End,
        };
        let reject = Branch {
            label: "Reject".into(),
            fields: vec![f("reason", "Str")],
            contract: None,
            cont: comm("J", "A", "Retry", vec![], Gtyp::End),
        };
        let draft = comm(
            "A",
            "J",
            "Draft",
            vec![f("answer", "Str"), f("cost", "Int")],
            Gtyp::Choice {
                sender: "J".into(),
                receiver: "C".into(),
                branches: vec![accept, reject],
            },
        );
        comm(
            "C",
            "A",
            "Request",
            vec![f("question", "Str"), f("budget", "Int")],
            draft,
        )
    }

    /// examples/cap_violation.casl — A uses `delete` ∉ {search}.
    pub fn cap_violation() -> Gtyp {
        let draft = Gtyp::Comm {
            sender: "A".into(),
            receiver: "J".into(),
            label: "Draft".into(),
            fields: vec![f("answer", "Str"), f("cost", "Int")],
            contract: Some(Contract {
                text: "cost <= budget".into(),
            }),
            uses_capability: Some("delete".into()),
            from_oracle: true,
            on_crash: None,
            cont: Box::new(comm("J", "A", "Done", vec![], Gtyp::End)),
        };
        comm(
            "C",
            "A",
            "Request",
            vec![f("question", "Str"), f("budget", "Int")],
            draft,
        )
    }
}
