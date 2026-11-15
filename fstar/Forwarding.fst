module Forwarding
(* ============================================================================================
   CERT-FID — FORWARDING FIDELITY.  *** TARGET: VERIFIES AT ZERO ADMITS. ***

   The A1 frontier (docs/analyses/forwarding-fidelity-a1.md): lift the forwarding re-base from the
   capped G2 (structural lineage under the spec-conformance assumption) to a PROOF-backed grade by
   machine-checking that a forwarded payload is delivered UNCHANGED, so a refinement proved at the
   verified source transfers to the destination value *by proof* — never re-checked by a monitor.

   WHY A COMPANION MODULE.  CASL.fst is deliberately FIELD-BLIND: `GMsg : role->role->label->gtyp`
   carries no payload, and the step relations range over `event = role & role & label`. Value
   identity therefore cannot even be STATED there. Rather than perturb the 0-admits metatheorems and
   the field-blind differential bridge, this module models the payload layer the core omits — a
   write-once value store with forward edges — exactly as W19ProjSubst.fst is kept standalone. The
   admits gate (scripts/check_admits.sh) scans this module too.

   LITERATURE (see the analysis doc for the full briefs):
   - Identity forwarding transfers a proved predicate FOR FREE: where-provenance is *defined* so the
     source and copied values are equal (Cheney, Chiticariu & Tan, FnT DB 2009; Buneman, Khanna & Tan
     ICDT 2001). Value-equality transports any value-predicate verbatim.
   - The fidelity lemma is LIGHT: value forwarding is the easy, NON-LINEAR case of session-type
     metatheory — a first-order equality invariant over the reduction, not a logical relation and not
     delegation/linearity (Honda-Yoshida-Carbone JACM 2016 substitution lemma shape; the value case is
     the routine reduction case in every subject-reduction proof, incl. the ECOOP 2025 mechanisation).
   - The re-base is an ENDORSEMENT, sound iff the decision rests only on high-integrity data and the
     boundary's proved contract ENTAILS the consumer's (Askarov-Myers ESOP 2010; Liquid Types PLDI 2008).
     Here the forward edge and the `verified` source come from the parsed protocol, not the oracle.
   ============================================================================================ *)

module L = FStar.List.Tot

(* ------------------------------------------------------------------ *)
(* Payload layer: a write-once value store over payload slots.         *)
(* A `slot` is a payload field of a site (each is a FRESH binding in    *)
(* MPST — modelled as write-once / SSA). Values are the contract-DSL    *)
(* domain (integers). The store is a total function compared POINTWISE  *)
(* (no functional extensionality needed anywhere below).                *)
(* ------------------------------------------------------------------ *)
let slot = nat
let valu = int

let store = slot -> Tot (option valu)
let empty : store = fun _ -> None
let upd (s:store) (k:slot) (v:valu) : store = fun j -> if j = k then Some v else s j

(* An event of the value-passing reduction:
   - Produce d v : an ordinary/oracle production — site binds `d := v` (v arbitrary).
   - Forward d src : a FORWARD — site binds `d := store[src]`, the value carried unchanged. *)
noeq type ev =
  | Produce : slot -> valu -> ev
  | Forward : slot -> slot -> ev

let dst_of (e:ev) : slot = match e with | Produce d _ -> d | Forward d _ -> d

(* One reduction step over the store. Forwarding copies the source slot's current value. *)
let step (s:store) (e:ev) : store =
  match e with
  | Produce d v   -> upd s d v
  | Forward d src -> (match s src with | Some v -> upd s d v | None -> s)

let rec run (s:store) (es:list ev) : Tot store (decreases es) =
  match es with
  | [] -> s
  | e :: t -> run (step s e) t

(* ------------------------------------------------------------------ *)
(* Well-formedness of an event list relative to the already-bound      *)
(* slots `bound`: every produced slot is FRESH (write-once / SSA) and   *)
(* every Forward's source is ALREADY bound (forwarding is defined).     *)
(* ------------------------------------------------------------------ *)
let rec mem (k:slot) (xs:list slot) : Tot bool (decreases xs) =
  match xs with | [] -> false | h :: t -> h = k || mem k t

let rec wf (bound:list slot) (es:list ev) : Tot bool (decreases es) =
  match es with
  | [] -> true
  | Produce d _ :: t   -> not (mem d bound) && wf (d :: bound) t
  | Forward d src :: t -> not (mem d bound) && mem src bound && wf (d :: bound) t

(* ------------------------------------------------------------------ *)
(* Helper lemmas.                                                       *)
(* ------------------------------------------------------------------ *)

(* If k is bound but d is not, they differ (the write-once disjointness used everywhere). *)
let rec mem_neq (k:slot) (d:slot) (bound:list slot)
  : Lemma (requires mem k bound /\ not (mem d bound)) (ensures d <> k) (decreases bound)
  = match bound with
    | [] -> ()
    | h :: t -> if h = k then () else mem_neq k d t

(* The store's Some-set is exactly `bound`, preserved by one wf step (write-once). *)
let inv_step (s:store) (bound:list slot) (d:slot) (v:valu)
  : Lemma (requires (forall (k:slot). mem k bound <==> Some? (s k)))
          (ensures  (forall (k:slot). mem k (d :: bound) <==> Some? (upd s d v k)))
  = ()

(* STABILITY: a slot already in `bound` keeps its value under any further wf run — it is never
   re-produced (write-once), so no later step can overwrite it. Pointwise; no extensionality. *)
let rec stable (s:store) (bound:list slot) (es:list ev) (k:slot)
  : Lemma (requires wf bound es /\ mem k bound)
          (ensures  (run s es) k == s k)
          (decreases es)
  = match es with
    | [] -> ()
    | e :: t ->
        (match e with
         | Produce d v ->
             mem_neq k d bound;                       // d <> k, so step leaves k untouched
             stable (step s (Produce d v)) (d :: bound) t k
         | Forward d src ->
             mem_neq k d bound;
             stable (step s (Forward d src)) (d :: bound) t k)

(* ------------------------------------------------------------------ *)
(* FIDELITY (generalised, for induction): starting from any store whose *)
(* Some-set is exactly `bound`, after a wf run containing the forward    *)
(* edge `Forward d src`, the destination holds the SAME (defined) value  *)
(* as the source.                                                        *)
(* ------------------------------------------------------------------ *)
let rec fidelity_gen (s:store) (bound:list slot) (pfx sfx:list ev) (d:slot) (src:slot)
  : Lemma (requires wf bound (L.append pfx (Forward d src :: sfx)) /\
                    (forall (k:slot). mem k bound <==> Some? (s k)))
          (ensures  (let s' = run s (L.append pfx (Forward d src :: sfx)) in
                     Some? (s' src) /\ s' d == s' src))
          (decreases pfx)
  = match pfx with
    | [] ->
        // list = Forward d src :: sfx ; wf gives: d fresh, src already bound, sfx wf under (d::bound).
        // src bound => Some? (s src). Let s1 = step; s1 src == s src (d<>src), s1 d == s src.
        mem_neq src d bound;                                  // d <> src
        let v = Some?.v (s src) in                            // s src = Some v
        let s1 = step s (Forward d src) in                    // = upd s d v
        // src and d are bound after this step; stability pins both across sfx.
        stable s1 (d :: bound) sfx src;
        stable s1 (d :: bound) sfx d
    | e :: pfx' ->
        (match e with
         | Produce d0 v0 ->
             inv_step s bound d0 v0;
             fidelity_gen (step s (Produce d0 v0)) (d0 :: bound) pfx' sfx d src
         | Forward d0 src0 ->
             // wf gives src0 already bound => Some? (s src0); step writes that value into d0.
             let v0 = Some?.v (s src0) in
             inv_step s bound d0 v0;
             fidelity_gen (step s (Forward d0 src0)) (d0 :: bound) pfx' sfx d src)

(* FIDELITY (top level): from the empty store, a wf run delivers at the forwarded destination
   exactly the source's (defined) value. The empty-store invariant holds (nothing bound, nothing Some). *)
let fidelity (pfx sfx:list ev) (d:slot) (src:slot)
  : Lemma (requires wf [] (L.append pfx (Forward d src :: sfx)))
          (ensures  (let s = run empty (L.append pfx (Forward d src :: sfx)) in
                     Some? (s src) /\ s d == s src))
  = fidelity_gen empty [] pfx sfx d src

(* ------------------------------------------------------------------ *)
(* RE-BASE SOUNDNESS — the theorem that licenses the proof-backed grant. *)
(* A contract is a predicate on the payload value; entailment is pointwise *)
(* implication (the SMT VC `phi_src ==> phi_dst` of the checker).         *)
(*                                                                        *)
(*   IDENTITY FORWARDING (fidelity)  +  phi_src ENTAILS phi_dst           *)
(*        ==>  the destination value satisfies its contract BY PROOF.     *)
(*                                                                        *)
(* This is the where-provenance "free transfer" (value-equality transports *)
(* the predicate) made machine-checked: no monitor re-checks phi_dst.      *)
(* ------------------------------------------------------------------ *)
let contract = valu -> bool
let entails (phi:contract) (psi:contract) = forall (v:valu). phi v ==> psi v

let rebase_sound (pfx sfx:list ev) (d:slot) (src:slot) (phi_src:contract) (phi_dst:contract)
  : Lemma (requires wf [] (L.append pfx (Forward d src :: sfx)) /\
                    entails phi_src phi_dst /\
                    (let s = run empty (L.append pfx (Forward d src :: sfx)) in
                     (match s src with | Some v -> phi_src v | None -> False)))
          (ensures  (let s = run empty (L.append pfx (Forward d src :: sfx)) in
                     (match s d with | Some v -> phi_dst v | None -> False)))
  = fidelity pfx sfx d src

(* ------------------------------------------------------------------ *)
(* Sanity: the NON-forwarded case has NO such guarantee (no lineage).   *)
(* A fresh Produce can hold any value, so the source's contract does     *)
(* NOT transfer — this is exactly why entailment ALONE (without a        *)
(* forward edge) stays a candidate, never an applied grant.             *)
(*   We witness it: two runs that differ only in a Produce'd value give   *)
(*   different destination values — no transfer is derivable.            *)
(* ------------------------------------------------------------------ *)
let no_transfer_without_forward (d:slot) (v1:valu) (v2:valu)
  : Lemma (ensures (run empty [Produce d v1]) d == Some v1 /\
                   (run empty [Produce d v2]) d == Some v2)
  = ()
