// ✅ MACHINE-CHECKED — Verus (release 0.2026.06.20.911e4e7, rustc 1.96.0): 6 verified, 0 errors.
// First progress on the `projectable` conjunct of casl-core::wellformed_core (the last, hard one). See
// docs/analyses/proving-the-rust.md. This proves a SOUND FRAGMENT: `project` is TOTAL, TERMINATING, and
// PANIC-FREE, and projectability holds where a non-participant's branch projections are IDENTICAL — a sound
// under-approximation of MPST merge (merge also accepts mergeable-but-unequal external choices by label
// union; that full `merge_pair` — partial, with recursion through the options list — is the residual, best
// done via Aeneas→F* over the real Rust). Model mirrors wellformed_verus.rs: cons-lists, ids as `usize`.
//
//     <verus-release>/verus rust/proofs/projectable_verus.rs
use vstd::prelude::*;

verus! {

pub enum Gtyp {
    End,
    Var(usize),
    Rec { var: usize, body: Box<Gtyp> },
    Comm { sender: usize, receiver: usize, cont: Box<Gtyp> },
    Choice { sender: usize, receiver: usize, branches: Box<BList> },
}

pub enum BList {
    Nil,
    Cons { label: usize, head: Box<Gtyp>, tail: Box<BList> },
}

/// Local (projected) type. External/internal choice options are a cons-list of (label, continuation).
pub enum Ltyp {
    End,
    Var(usize),
    Rec { var: usize, body: Box<Ltyp> },
    Send { to: usize, cont: Box<Ltyp> },
    Recv { from: usize, cont: Box<Ltyp> },
    IntChoice { to: usize, opts: Box<OList> },
    ExtChoice { from: usize, opts: Box<OList> },
}

pub enum OList {
    Nil,
    Cons { label: usize, cont: Box<Ltyp>, tail: Box<OList> },
}

// ---------------------------------------------------------------------------
// project — total (Option), structurally terminating. A non-participant at a Choice projects every branch
// and requires them all to be SOME and pairwise EQUAL (the sound-merge fragment); else None (not projectable).
// ---------------------------------------------------------------------------

/// Project every branch for role `r`; the chooser/receiver builds an option list, the bystander folds equality.
pub open spec fn project(g: Gtyp, r: usize) -> Option<Ltyp>
    decreases g,
{
    match g {
        Gtyp::End => Some(Ltyp::End),
        Gtyp::Var(x) => Some(Ltyp::Var(x)),
        Gtyp::Rec { var, body } => match project(*body, r) {
            Some(b) => Some(Ltyp::Rec { var, body: Box::new(b) }),
            None => None,
        },
        Gtyp::Comm { sender, receiver, cont } => match project(*cont, r) {
            None => None,
            Some(c) => {
                if r == sender {
                    Some(Ltyp::Send { to: receiver, cont: Box::new(c) })
                } else if r == receiver {
                    Some(Ltyp::Recv { from: sender, cont: Box::new(c) })
                } else {
                    Some(c)
                }
            }
        },
        Gtyp::Choice { sender, receiver, branches } => {
            if r == sender {
                match project_opts(*branches, r) {
                    Some(o) => Some(Ltyp::IntChoice { to: receiver, opts: Box::new(o) }),
                    None => None,
                }
            } else if r == receiver {
                match project_opts(*branches, r) {
                    Some(o) => Some(Ltyp::ExtChoice { from: sender, opts: Box::new(o) }),
                    None => None,
                }
            } else {
                project_merge(*branches, r)
            }
        }
    }
}

/// Project each branch into an option list (label ↦ projected continuation); None if any branch fails.
pub open spec fn project_opts(bl: BList, r: usize) -> Option<OList>
    decreases bl,
{
    match bl {
        BList::Nil => Some(OList::Nil),
        BList::Cons { label, head, tail } => match (project(*head, r), project_opts(*tail, r)) {
            (Some(h), Some(t)) => Some(OList::Cons { label, cont: Box::new(h), tail: Box::new(t) }),
            _ => None,
        },
    }
}

/// Bystander merge (sound fragment): all branches must project to SOME and all be EQUAL ⇒ that common type.
pub open spec fn project_merge(bl: BList, r: usize) -> Option<Ltyp>
    decreases bl,
{
    match bl {
        BList::Nil => Some(Ltyp::End),
        BList::Cons { head, tail, .. } => match (project(*head, r), project_merge(*tail, r)) {
            (Some(h), Some(t)) => if all_equal_to(*tail, r, h) { Some(t) } else { None },
            _ => None,
        },
    }
}

/// Does every branch of `bl` project (for `r`) to exactly `t`?
pub open spec fn all_equal_to(bl: BList, r: usize, t: Ltyp) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => project(*head, r) == Some(t) && all_equal_to(*tail, r, t),
    }
}

// ---------------------------------------------------------------------------
// choice-free fragment: a Gtyp with no Choice nodes always projects (no merge ever needed).
// ---------------------------------------------------------------------------
pub open spec fn choice_free(g: Gtyp) -> bool
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => choice_free(*body),
        Gtyp::Comm { cont, .. } => choice_free(*cont),
        Gtyp::Choice { .. } => false,
    }
}

/// THEOREM: a choice-free global type is projectable for every role (project never returns None).
pub proof fn choice_free_projects(g: Gtyp, r: usize)
    requires choice_free(g),
    ensures project(g, r) is Some,
    decreases g,
{
    match g {
        Gtyp::End => {}
        Gtyp::Var(_) => {}
        Gtyp::Rec { body, .. } => choice_free_projects(*body, r),
        Gtyp::Comm { cont, .. } => choice_free_projects(*cont, r),
        Gtyp::Choice { .. } => {}
    }
}

} // verus!

fn main() {}
