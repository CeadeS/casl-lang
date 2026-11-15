// ✅ MACHINE-CHECKED — Verus (release 0.2026.06.20.911e4e7, rustc 1.96.0). See docs/analyses/proving-the-rust.md.
//
// "Prove the Rust" — the structural conjuncts of casl-core::wellformed_core, machine-proved in Verus: each
// hand-written exec checker REFINES its logical spec (`ensures`), TERMINATES (`decreases`), and is PANIC-FREE
// (Verus default). Functional correctness of the *implementations* against their meaning — NOT the MPST
// metatheory (that stays in fstar/CASL.fst). n-ary choice (arbitrary branches) modeled as a recursive
// cons-list (`BList`) to sidestep the documented Verus Vec-of-recursive-enum termination limitation
// (verus-lang/verus#1195/#1222); roles + labels are `usize` ids (the predicates inspect only identity).
//
//     <verus-release>/verus rust/proofs/wellformed_verus.rs
//
// Conjuncts mirror rust/casl-core/src/lib.rs: no_self, gdistinct, closed, contractive, and the combined
// wf_noproj (= wellformed_core MINUS the projectable conjunct, which needs project/merge — the next brick).
// Verus reports: 28 verified, 0 errors.

use vstd::prelude::*;

verus! {

pub enum Gtyp {
    End,
    Var(usize),
    Rec { var: usize, body: Box<Gtyp> },
    Comm { sender: usize, receiver: usize, cont: Box<Gtyp> },
    Choice { sender: usize, receiver: usize, branches: Box<BList> },
}

/// n-ary branch list: each branch carries a label + its continuation.
pub enum BList {
    Nil,
    Cons { label: usize, head: Box<Gtyp>, tail: Box<BList> },
}

// ===========================================================================
// no_self — every communication node has sender != receiver, structurally.
// ===========================================================================
pub open spec fn no_self(g: Gtyp) -> bool
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => no_self(*body),
        Gtyp::Comm { sender, receiver, cont } => sender != receiver && no_self(*cont),
        Gtyp::Choice { sender, receiver, branches } => sender != receiver && no_self_bl(*branches),
    }
}

pub open spec fn no_self_bl(bl: BList) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => no_self(*head) && no_self_bl(*tail),
    }
}

pub fn no_self_exec(g: &Gtyp) -> (r: bool)
    ensures r == no_self(*g),
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => no_self_exec(body),
        Gtyp::Comm { sender, receiver, cont } => *sender != *receiver && no_self_exec(cont),
        Gtyp::Choice { sender, receiver, branches } => *sender != *receiver && no_self_bl_exec(branches),
    }
}

pub fn no_self_bl_exec(bl: &BList) -> (r: bool)
    ensures r == no_self_bl(*bl),
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => no_self_exec(head) && no_self_bl_exec(tail),
    }
}

// ===========================================================================
// gdistinct — distinct branch labels at every choice (+ recurse into branches).
// ===========================================================================
pub open spec fn label_present(bl: BList, l: usize) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => false,
        BList::Cons { label, tail, .. } => label == l || label_present(*tail, l),
    }
}

pub open spec fn labels_distinct(bl: BList) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { label, tail, .. } => !label_present(*tail, label) && labels_distinct(*tail),
    }
}

pub open spec fn gdistinct(g: Gtyp) -> bool
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => gdistinct(*body),
        Gtyp::Comm { cont, .. } => gdistinct(*cont),
        Gtyp::Choice { branches, .. } => labels_distinct(*branches) && gdistinct_bl(*branches),
    }
}

pub open spec fn gdistinct_bl(bl: BList) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => gdistinct(*head) && gdistinct_bl(*tail),
    }
}

pub fn label_present_exec(bl: &BList, l: usize) -> (r: bool)
    ensures r == label_present(*bl, l),
    decreases bl,
{
    match bl {
        BList::Nil => false,
        BList::Cons { label, tail, .. } => *label == l || label_present_exec(tail, l),
    }
}

pub fn labels_distinct_exec(bl: &BList) -> (r: bool)
    ensures r == labels_distinct(*bl),
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { label, tail, .. } => !label_present_exec(tail, *label) && labels_distinct_exec(tail),
    }
}

pub fn gdistinct_exec(g: &Gtyp) -> (r: bool)
    ensures r == gdistinct(*g),
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(_) => true,
        Gtyp::Rec { body, .. } => gdistinct_exec(body),
        Gtyp::Comm { cont, .. } => gdistinct_exec(cont),
        Gtyp::Choice { branches, .. } => labels_distinct_exec(branches) && gdistinct_bl_exec(branches),
    }
}

pub fn gdistinct_bl_exec(bl: &BList) -> (r: bool)
    ensures r == gdistinct_bl(*bl),
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => gdistinct_exec(head) && gdistinct_bl_exec(tail),
    }
}

// A self-communication is rejected; duplicate labels are rejected — sanity lemmas the verifier discharges.
proof fn self_comm_is_rejected(cont: Gtyp)
    ensures !no_self(Gtyp::Comm { sender: 0, receiver: 0, cont: Box::new(cont) }),
{
}

proof fn duplicate_labels_rejected(g0: Gtyp, g1: Gtyp, rest: BList)
    ensures !labels_distinct(BList::Cons {
        label: 7,
        head: Box::new(g0),
        tail: Box::new(BList::Cons { label: 7, head: Box::new(g1), tail: Box::new(rest) }),
    }),
{
}

// ===========================================================================
// closed — no free recursion variables (every μ-variable is bound). The bound
// environment is a cons-list `NList` of in-scope variable ids (kept a cons-list,
// like BList, to stay in clean structural recursion — no Vec).
// ===========================================================================
pub enum NList {
    Nil,
    Cons(usize, Box<NList>),
}

pub open spec fn mem(l: usize, ns: NList) -> bool
    decreases ns,
{
    match ns {
        NList::Nil => false,
        NList::Cons(h, t) => h == l || mem(l, *t),
    }
}

pub fn mem_exec(l: usize, ns: &NList) -> (r: bool)
    ensures r == mem(l, *ns),
    decreases ns,
{
    match ns {
        NList::Nil => false,
        NList::Cons(h, t) => *h == l || mem_exec(l, t),
    }
}

/// A verified structural clone — `r == *ns` — so the bound can be extended at a binder without aliasing.
pub fn nlist_clone(ns: &NList) -> (r: NList)
    ensures r == *ns,
    decreases ns,
{
    match ns {
        NList::Nil => NList::Nil,
        NList::Cons(h, t) => NList::Cons(*h, Box::new(nlist_clone(t))),
    }
}

pub open spec fn closed_rec(bound: NList, g: Gtyp) -> bool
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(t) => mem(t, bound),
        Gtyp::Rec { var, body } => closed_rec(NList::Cons(var, Box::new(bound)), *body),
        Gtyp::Comm { cont, .. } => closed_rec(bound, *cont),
        Gtyp::Choice { branches, .. } => closed_bl(bound, *branches),
    }
}

pub open spec fn closed_bl(bound: NList, bl: BList) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => closed_rec(bound, *head) && closed_bl(bound, *tail),
    }
}

pub open spec fn closed(g: Gtyp) -> bool {
    closed_rec(NList::Nil, g)
}

pub fn closed_rec_exec(bound: &NList, g: &Gtyp) -> (r: bool)
    ensures r == closed_rec(*bound, *g),
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(t) => mem_exec(*t, bound),
        Gtyp::Rec { var, body } => {
            let b2 = NList::Cons(*var, Box::new(nlist_clone(bound)));
            closed_rec_exec(&b2, body)
        }
        Gtyp::Comm { cont, .. } => closed_rec_exec(bound, cont),
        Gtyp::Choice { branches, .. } => closed_bl_exec(bound, branches),
    }
}

pub fn closed_bl_exec(bound: &NList, bl: &BList) -> (r: bool)
    ensures r == closed_bl(*bound, *bl),
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => closed_rec_exec(bound, head) && closed_bl_exec(bound, tail),
    }
}

pub fn closed_exec(g: &Gtyp) -> (r: bool)
    ensures r == closed(*g),
{
    closed_rec_exec(&NList::Nil, g)
}

// ===========================================================================
// contractive — guarded recursion (rules out μt.t): a recursion variable may not
// recur before a communication. The bound is CLEARED at every communication.
// ===========================================================================
pub open spec fn contr_rec(bound: NList, g: Gtyp) -> bool
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(t) => !mem(t, bound),
        Gtyp::Rec { var, body } => contr_rec(NList::Cons(var, Box::new(bound)), *body),
        Gtyp::Comm { cont, .. } => contr_rec(NList::Nil, *cont),
        Gtyp::Choice { branches, .. } => contr_bl(*branches),
    }
}

pub open spec fn contr_bl(bl: BList) -> bool
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => contr_rec(NList::Nil, *head) && contr_bl(*tail),
    }
}

pub open spec fn contractive(g: Gtyp) -> bool {
    contr_rec(NList::Nil, g)
}

pub fn contr_rec_exec(bound: &NList, g: &Gtyp) -> (r: bool)
    ensures r == contr_rec(*bound, *g),
    decreases g,
{
    match g {
        Gtyp::End => true,
        Gtyp::Var(t) => !mem_exec(*t, bound),
        Gtyp::Rec { var, body } => {
            let b2 = NList::Cons(*var, Box::new(nlist_clone(bound)));
            contr_rec_exec(&b2, body)
        }
        Gtyp::Comm { cont, .. } => contr_rec_exec(&NList::Nil, cont),
        Gtyp::Choice { branches, .. } => contr_bl_exec(branches),
    }
}

pub fn contr_bl_exec(bl: &BList) -> (r: bool)
    ensures r == contr_bl(*bl),
    decreases bl,
{
    match bl {
        BList::Nil => true,
        BList::Cons { head, tail, .. } => contr_rec_exec(&NList::Nil, head) && contr_bl_exec(tail),
    }
}

pub fn contractive_exec(g: &Gtyp) -> (r: bool)
    ensures r == contractive(*g),
{
    contr_rec_exec(&NList::Nil, g)
}

// ===========================================================================
// wf_noproj — the structural well-formedness predicate: contractive ∧ no_self ∧
// gdistinct ∧ closed (= casl-core::wellformed_core MINUS the `projectable` conjunct,
// which pulls in project/merge — the next, harder brick).
// ===========================================================================
pub open spec fn wf_noproj(g: Gtyp) -> bool {
    contractive(g) && no_self(g) && gdistinct(g) && closed(g)
}

pub fn wf_noproj_exec(g: &Gtyp) -> (r: bool)
    ensures r == wf_noproj(*g),
{
    contractive_exec(g) && no_self_exec(g) && gdistinct_exec(g) && closed_exec(g)
}

} // verus!

fn main() {}
