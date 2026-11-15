// ✅ MACHINE-CHECKED — Verus (release 0.2026.06.20.911e4e7, rustc 1.96.0). See docs/analyses/proving-the-rust.md §5.
//
// Brick of the "prove the Rust" spike: a machine proof that the hand-written `no_self` checker (the simplest
// `wellformed_core` conjunct in rust/casl-core/src/lib.rs) REFINES its logical spec, TERMINATES (decreases),
// and is PANIC-FREE (Verus default). Functional correctness of the *implementation* against its meaning — it
// does NOT re-prove the MPST metatheory (that stays in fstar/CASL.fst).
//
// FIDELITY: this proves the predicate over an **n-ary** choice (arbitrary number of branches), recursing into
// EVERY branch — closing the earlier binary-choice simplification. The branch list is modeled as a recursive
// cons-list (`BList`) rather than casl-core's `Vec<Branch>`: same predicate meaning, and it sidesteps a
// documented Verus limitation — recursion through a `Vec` of a recursive enum fails the termination checker
// (verus-lang/verus#1195/#1222). Roles are `usize` ids (no_self inspects only role IDENTITY).
//
// Checked with the Verus toolchain (NOT plain cargo — uses the `verus!` macro + vstd):
//     <verus-release>/verus rust/proofs/no_self_verus.rs      # → "5 verified, 0 errors"

use vstd::prelude::*;

verus! {

pub enum Gtyp {
    End,
    Var(usize),
    Rec(Box<Gtyp>),
    Comm { sender: usize, receiver: usize, cont: Box<Gtyp> },
    Choice { sender: usize, receiver: usize, branches: Box<BList> },
}

/// An n-ary branch list (each branch carries its continuation; no_self ignores labels/payloads/contracts).
pub enum BList {
    Nil,
    Cons { head: Box<Gtyp>, tail: Box<BList> },
}

/// The MEANING of `no_self`: every communication node (Comm/Choice) has `sender != receiver`, structurally —
/// and a choice's predicate holds for EVERY branch continuation.
pub open spec fn no_self_spec(g: Gtyp) -> bool
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec(body) => no_self_spec(*body),
        Gtyp::Comm { sender, receiver, cont } => sender != receiver && no_self_spec(*cont),
        Gtyp::Choice { sender, receiver, branches } => sender != receiver && no_self_blist(*branches),
    }
}

pub open spec fn no_self_blist(bl: BList) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail } => no_self_spec(*head) && no_self_blist(*tail),
    }
}

/// The CHECKER (executable): same structural recursion, returning a runtime `bool`. Proven EQUAL to the spec
/// (`ensures`), TOTAL/terminating (`decreases`), and panic-free (Verus default).
pub fn no_self_exec(g: &Gtyp) -> (r: bool)
    ensures
        r == no_self_spec(*g),
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec(body) => no_self_exec(body),
        Gtyp::Comm { sender, receiver, cont } => *sender != *receiver && no_self_exec(cont),
        Gtyp::Choice { sender, receiver, branches } => *sender != *receiver && no_self_blist_exec(branches),
    }
}

pub fn no_self_blist_exec(bl: &BList) -> (r: bool)
    ensures
        r == no_self_blist(*bl),
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail } => no_self_exec(head) && no_self_blist_exec(tail),
    }
}

/// A self-communication is rejected — a sanity lemma the verifier discharges from the definitions.
proof fn self_comm_is_rejected(cont: Gtyp)
    ensures
        !no_self_spec(Gtyp::Comm { sender: 0, receiver: 0, cont: Box::new(cont) }),
{
}

} // verus!

fn main() {}
