module CASL

/// CASL — formal core in F* (Direction C; TBD-004 = F* + Rust).
///
/// VARIANT A — N-ARY CHOICE. This branch generalizes the binary choice of the baseline to
/// an n-ary choice (a list of label×continuation): `GCh p q [(l1,G1);...;(ln,Gn)]`, with
/// n-ary local internal/external choices `LIntC`/`LExtC`. Projection, the full MPST merge,
/// substitution, the global/configuration step relations, and the metatheorems
/// (fidelity_complete/sound, deadlock_free) are all re-derived for the n-ary calculus and
/// machine-checked (0 admits). The W9 permutation/diamond results (over GMsg) are unchanged.
///
/// STATUS: VERIFIED with F* 2026.03.24 (RC=0, ZERO admits) for the n-ary head fragment.
/// Verify locally:   fstar.exe CASL.fst
/// Extract engine:   fstar.exe --codegen OCaml CASL.fst

module L = FStar.List.Tot
open FStar.Mul   // integer * (the core uses & for tuples, so this is unambiguous)

(* ------------------------------------------------------------------ *)
(* Syntax                                                              *)
(* ------------------------------------------------------------------ *)
type role = | RC | RA | RJ | RD
type label = string
type tvar  = string

type gtyp =
  | GEnd : gtyp
  | GVar : tvar -> gtyp
  | GRec : tvar -> gtyp -> gtyp
  | GMsg : role -> role -> label -> gtyp -> gtyp                 // p->q : l . G
  | GCh  : role -> role -> list (label & gtyp) -> gtyp           // p->q : {li : Gi}  (n-ary)

type ltyp =
  | LEnd  : ltyp
  | LVar  : tvar -> ltyp
  | LRec  : tvar -> ltyp -> ltyp
  | LSnd  : role -> label -> ltyp -> ltyp
  | LRcv  : role -> label -> ltyp -> ltyp
  | LIntC : role -> list (label & ltyp) -> ltyp                 // internal choice (n-ary)
  | LExtC : role -> list (label & ltyp) -> ltyp                 // external choice (n-ary)

type event = role & role & label

(* ------------------------------------------------------------------ *)
(* Size measures (for fuel-bounded merge)                              *)
(* ------------------------------------------------------------------ *)
let rec lsize (l:ltyp) : Tot nat (decreases l) =
  match l with
  | LEnd | LVar _ -> 1
  | LRec _ c -> 1 + lsize c
  | LSnd _ _ c -> 1 + lsize c
  | LRcv _ _ c -> 1 + lsize c
  | LIntC _ os -> 1 + lsize_opts os
  | LExtC _ os -> 1 + lsize_opts os
and lsize_opts (os:list (label & ltyp)) : Tot nat (decreases os) =
  match os with
  | [] -> 0
  | (_, c) :: t -> lsize c + lsize_opts t

(* ------------------------------------------------------------------ *)
(* Full MPST merge (third-role projection across a choice), mirroring  *)
(* src/casl/spike_proj_mpst.merge_pair: identical types merge to        *)
(* themselves; receives / external choices from the SAME partner merge  *)
(* by unioning labels and recursively merging shared-label conts; else  *)
(* not mergeable. Termination via a structural fuel = size of inputs.   *)
(* ------------------------------------------------------------------ *)
let opts_of (l:ltyp) : option (role & list (label & ltyp)) =
  match l with
  | LRcv p a c -> Some (p, [(a, c)])
  | LExtC p os -> Some (p, os)
  | _          -> None

let rec assoc_lbl (a:label) (os:list (label & ltyp)) : option ltyp =
  match os with
  | [] -> None
  | (l, c) :: t -> if l = a then Some c else assoc_lbl a t

let rec replace_lbl (a:label) (c:ltyp) (os:list (label & ltyp)) : list (label & ltyp) =
  match os with
  | [] -> []
  | (l, c0) :: t -> if l = a then (l, c) :: t else (l, c0) :: replace_lbl a c t

let rec merge_f (fuel:nat) (l1 l2:ltyp) : Tot (option ltyp) (decreases fuel) =
  if fuel = 0 then None
  else if l1 = l2 then Some l1
  else (match opts_of l1, opts_of l2 with
        | Some (p, o1), Some (q, o2) ->
            if p = q
            then (match merge_opts_f (fuel - 1) o1 o2 with
                  | Some o -> Some (LExtC p o)
                  | None   -> None)
            else None
        | _, _ -> None)
and merge_opts_f (fuel:nat) (o1 o2:list (label & ltyp))
  : Tot (option (list (label & ltyp))) (decreases fuel) =
  if fuel = 0 then None
  else match o2 with
       | [] -> Some o1
       | (a, c) :: t ->
           (match assoc_lbl a o1 with
            | None    -> merge_opts_f (fuel - 1) ((a, c) :: o1) t
            | Some c0 -> (match merge_f (fuel - 1) c0 c with
                          | None    -> None
                          | Some c' -> merge_opts_f (fuel - 1) (replace_lbl a c' o1) t))

// fuel = 2*(lsize l1 + lsize l2): the PROVEN-SUFFICIENT bound (>= the asymmetric target_f below, and
// >= the old lsize l1+lsize l2+1, so monotone-safe). See `merge_complete` (W18 closed).
let merge (l1 l2:ltyp) : option ltyp = merge_f (2 * (lsize l1 + lsize l2)) l1 l2

(* ------------------------------------------------------------------ *)
(* Fuel MONOTONICITY (W18, SP-3): a successful merge is FUEL-STABLE —   *)
(* adding fuel never changes or loses a result. So a success at any     *)
(* fuel is a success at every larger fuel; the wrapper's fixed fuel     *)
(* therefore reproduces any reachable success (no oscillation). This is *)
(* the machine-checked half of fuel-sufficiency; see W18 for the open   *)
(* remaining half (that the size-based bound is always reached).        *)
(* ------------------------------------------------------------------ *)
let rec merge_f_mono (n:nat) (l1 l2:ltyp) (r:ltyp)
  : Lemma (requires merge_f n l1 l2 == Some r)
          (ensures  merge_f (n + 1) l1 l2 == Some r)
          (decreases n)
  = if n = 0 then ()
    else if l1 = l2 then ()
    else (match opts_of l1, opts_of l2 with
          | Some (p, o1), Some (q, o2) ->
              if p = q then
                (match merge_opts_f (n - 1) o1 o2 with
                 | Some o -> merge_opts_f_mono (n - 1) o1 o2 o
                 | None   -> ())
              else ()
          | _, _ -> ())
and merge_opts_f_mono (n:nat) (o1 o2:list (label & ltyp)) (o:list (label & ltyp))
  : Lemma (requires merge_opts_f n o1 o2 == Some o)
          (ensures  merge_opts_f (n + 1) o1 o2 == Some o)
          (decreases n)
  = if n = 0 then ()
    else (match o2 with
          | [] -> ()
          | (a, c) :: t ->
              (match assoc_lbl a o1 with
               | None    -> merge_opts_f_mono (n - 1) ((a, c) :: o1) t o
               | Some c0 ->
                   (match merge_f (n - 1) c0 c with
                    | Some c' ->
                        merge_f_mono (n - 1) c0 c c';
                        merge_opts_f_mono (n - 1) (replace_lbl a c' o1) t o
                    | None    -> ())))

// helpers: the option projection shrinks size by exactly 1; assoc/replace size arithmetic.
let opts_of_size (l:ltyp) (p:role) (o:list (label & ltyp))
  : Lemma (requires opts_of l == Some (p, o)) (ensures lsize_opts o + 1 == lsize l) = ()

let rec assoc_size (a:label) (os:list (label & ltyp)) (c0:ltyp)
  : Lemma (requires assoc_lbl a os == Some c0)
          (ensures  lsize c0 <= lsize_opts os) (decreases os)
  = match os with | (l, _) :: t -> if l = a then () else assoc_size a t c0

let rec replace_size (a:label) (c':ltyp) (os:list (label & ltyp)) (c0:ltyp)
  : Lemma (requires assoc_lbl a os == Some c0)
          (ensures  lsize_opts (replace_lbl a c' os) + lsize c0 == lsize_opts os + lsize c')
          (decreases os)
  = match os with | (l, _) :: t -> if l = a then () else replace_size a c' t c0

(* OUTPUT-SIZE BOUND (W18, SP-3): a successful merge's result is no larger than the sum of its  *)
(* inputs — so the union never blows up. With monotonicity this pins merge's behavior; the only  *)
(* remaining open piece of fuel-sufficiency is the recursion-DEPTH bound (tracked in W18).        *)
let rec merge_f_size (n:nat) (l1 l2:ltyp) (r:ltyp)
  : Lemma (requires merge_f n l1 l2 == Some r)
          (ensures  lsize r <= lsize l1 + lsize l2) (decreases n)
  = if n = 0 then () else if l1 = l2 then ()
    else (match opts_of l1, opts_of l2 with
          | Some (p, o1), Some (q, o2) ->
              if p = q then
                (match merge_opts_f (n - 1) o1 o2 with
                 | Some o -> opts_of_size l1 p o1; opts_of_size l2 q o2;
                             merge_opts_f_size (n - 1) o1 o2 o
                 | None   -> ())
              else ()
          | _, _ -> ())
and merge_opts_f_size (n:nat) (o1 o2:list (label & ltyp)) (o:list (label & ltyp))
  : Lemma (requires merge_opts_f n o1 o2 == Some o)
          (ensures  lsize_opts o <= lsize_opts o1 + lsize_opts o2) (decreases n)
  = if n = 0 then () else
    (match o2 with
     | [] -> ()
     | (a, c) :: t ->
        (match assoc_lbl a o1 with
         | None -> merge_opts_f_size (n - 1) ((a, c) :: o1) t o
         | Some c0 ->
            (match merge_f (n - 1) c0 c with
             | Some c' ->
                 merge_f_size (n - 1) c0 c c';
                 assoc_size a o1 c0;
                 replace_size a c' o1 c0;
                 merge_opts_f_size (n - 1) (replace_lbl a c' o1) t o
             | None -> ())))

(* ------------------------------------------------------------------ *)
(* FUEL-SUFFICIENCY (W18, SP-3 completed): the wrapper `merge` never     *)
(* returns a spurious None — its fuel is always enough. A symmetric size *)
(* bound is provably inconsistent for the induction; an ASYMMETRIC one   *)
(* (charge the 2nd argument double) closes all four branch inequalities. *)
(* See docs/analyses/w18-fuel-sufficiency.md.                            *)
(* ------------------------------------------------------------------ *)

// monotone-le: a success is preserved at any larger fuel (iterate the +1 monotonicity).
let rec merge_f_mono_le (a b:nat) (l1 l2:ltyp) (r:ltyp)
  : Lemma (requires merge_f a l1 l2 == Some r /\ b >= a)
          (ensures  merge_f b l1 l2 == Some r) (decreases (b - a))
  = if b = a then () else (merge_f_mono_le a (b - 1) l1 l2 r; merge_f_mono (b - 1) l1 l2 r)

let rec merge_opts_f_mono_le (a b:nat) (o1 o2 o:list (label & ltyp))
  : Lemma (requires merge_opts_f a o1 o2 == Some o /\ b >= a)
          (ensures  merge_opts_f b o1 o2 == Some o) (decreases (b - a))
  = if b = a then () else (merge_opts_f_mono_le a (b - 1) o1 o2 o; merge_opts_f_mono (b - 1) o1 o2 o)

// SUFFICIENCY: fuel = lsize l1 + 2*lsize l2 (resp. lsize_opts o1 + 2*lsize_opts o2 + 1) always
// reproduces any success reachable at any fuel. Strong induction on the witnessing fuel n.
let rec suff_f (n:nat) (l1 l2:ltyp) (r:ltyp)
  : Lemma (requires merge_f n l1 l2 == Some r)
          (ensures  merge_f (lsize l1 + 2 * lsize l2) l1 l2 == Some r)
          (decreases n)
  = if n = 0 then ()
    else if l1 = l2 then ()
    else (match opts_of l1, opts_of l2 with
          | Some (p, o1), Some (q, o2) ->
              if p = q then
                (match merge_opts_f (n - 1) o1 o2 with
                 | Some o ->
                     suff_opts (n - 1) o1 o2 o;
                     opts_of_size l1 p o1; opts_of_size l2 q o2;
                     merge_opts_f_mono_le (lsize_opts o1 + 2 * lsize_opts o2 + 1)
                                          (lsize l1 + 2 * lsize l2 - 1) o1 o2 o
                 | None -> ())
              else ()
          | _, _ -> ())
and suff_opts (n:nat) (o1 o2 o:list (label & ltyp))
  : Lemma (requires merge_opts_f n o1 o2 == Some o)
          (ensures  merge_opts_f (lsize_opts o1 + 2 * lsize_opts o2 + 1) o1 o2 == Some o)
          (decreases n)
  = if n = 0 then ()
    else (match o2 with
          | [] -> ()
          | (a, c) :: t ->
              (match assoc_lbl a o1 with
               | None ->
                   suff_opts (n - 1) ((a, c) :: o1) t o;
                   merge_opts_f_mono_le (lsize_opts ((a, c) :: o1) + 2 * lsize_opts t + 1)
                                        (lsize_opts o1 + 2 * lsize_opts ((a, c) :: t) + 1 - 1)
                                        ((a, c) :: o1) t o
               | Some c0 ->
                   (match merge_f (n - 1) c0 c with
                    | Some c' ->
                        suff_f (n - 1) c0 c c';
                        suff_opts (n - 1) (replace_lbl a c' o1) t o;
                        assoc_size a o1 c0;
                        replace_size a c' o1 c0;
                        merge_f_size (n - 1) c0 c c';
                        merge_f_mono_le (lsize c0 + 2 * lsize c)
                                        (lsize_opts o1 + 2 * lsize_opts ((a, c) :: t) + 1 - 1) c0 c c';
                        merge_opts_f_mono_le (lsize_opts (replace_lbl a c' o1) + 2 * lsize_opts t + 1)
                                             (lsize_opts o1 + 2 * lsize_opts ((a, c) :: t) + 1 - 1)
                                             (replace_lbl a c' o1) t o
                    | None -> ())))

// W18 — COMPLETENESS of the wrapper: if the merge succeeds at ANY fuel, `merge` succeeds (same
// result). I.e. `merge` never returns a spurious None due to fuel exhaustion (incompleteness closed;
// soundness was never in question). The bound 2*(lsize l1+lsize l2) >= the asymmetric target_f.
let merge_complete (n:nat) (l1 l2:ltyp) (r:ltyp)
  : Lemma (requires merge_f n l1 l2 == Some r) (ensures merge l1 l2 == Some r)
  = suff_f n l1 l2 r;
    merge_f_mono_le (lsize l1 + 2 * lsize l2) (2 * (lsize l1 + lsize l2)) l1 l2 r

// merge the projected continuations of all branches (third-role projection of a choice)
let rec merge_all (os:list (label & ltyp)) : Tot (option ltyp) (decreases os) =
  match os with
  | [] -> None
  | [(_, l)] -> Some l
  | (_, l) :: t -> (match merge_all t with
                    | None -> None
                    | Some m -> merge l m)

(* ------------------------------------------------------------------ *)
(* Projection  (LH-F-006)                                              *)
(* ------------------------------------------------------------------ *)
let rec project (g: gtyp) (r: role) : Tot (option ltyp) (decreases g) =
  match g with
  | GEnd       -> Some LEnd
  | GVar t     -> Some (LVar t)
  | GRec t g1  -> (match project g1 r with | Some l -> Some (LRec t l) | None -> None)
  | GMsg p q a g1 ->
      (match project g1 r with
       | None   -> None
       | Some l -> if r = p then Some (LSnd q a l)
                   else if r = q then Some (LRcv p a l)
                   else Some l)
  | GCh p q opts ->
      (match project_opts opts r with
       | None -> None
       | Some os ->
           if r = p then Some (LIntC q os)
           else if r = q then Some (LExtC p os)
           else merge_all os)
and project_opts (opts:list (label & gtyp)) (r:role)
  : Tot (option (list (label & ltyp))) (decreases opts) =
  match opts with
  | [] -> Some []
  | (l, g) :: t ->
      (match project g r, project_opts t r with
       | Some lt, Some rest -> Some ((l, lt) :: rest)
       | _, _ -> None)

// CONTRACTIVENESS / guardedness: every recursion variable occurrence must be guarded by a
// communication since its binder (rules out non-contractive loops like `GRec t (GVar t)` = μt.t,
// a silent divergence). `bound` tracks variables bound since the last communication; a GMsg/GCh
// is a communication and clears it. (Found by the W19 semantic safety oracle: such loops were
// projectable yet "unsafe" only as silent divergence — fixed here by excluding them.)
let rec contractive_chk (bound:list tvar) (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd        -> true
  | GVar t      -> not (L.mem t bound)
  | GRec t g1   -> contractive_chk (t :: bound) g1
  | GMsg _ _ _ k -> contractive_chk [] k
  | GCh _ _ opts -> contractive_opts opts
and contractive_opts (opts:list (label & gtyp)) : Tot bool (decreases opts) =
  match opts with
  | [] -> true
  | (_, g) :: t -> contractive_chk [] g && contractive_opts t

let contractive (g:gtyp) : bool = contractive_chk [] g

// NO SELF-COMMUNICATION: every communication has distinct endpoints (p <> q). A self-comm `GMsg p p`
// is projectable but the lone role projects to a send with no matching receive — a deadlock (a real
// over-acceptance, found while formalising W19-A). Required structurally everywhere, not just at the head.
let rec no_self (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd | GVar _ -> true
  | GRec _ g1     -> no_self g1
  | GMsg p q _ k  -> not (p = q) && no_self k
  | GCh p q opts  -> not (p = q) && no_self_opts opts
and no_self_opts (opts:list (label & gtyp)) : Tot bool (decreases opts) =
  match opts with
  | [] -> true
  | (_, g) :: t -> no_self g && no_self_opts t

(* ---- predicates used by `wellformed` (moved up): label keys, nodup, lexical closedness, gdistinct ---- *)
let rec keys (os:list (label & ltyp)) : list label =
  match os with | [] -> [] | (a, _) :: t -> a :: keys t

let rec nodup (ls:list label) : bool =
  match ls with | [] -> true | a :: t -> not (L.mem a t) && nodup t

let rec gkeys (opts:list (label & gtyp)) : list label =
  match opts with | [] -> [] | (a, _) :: t -> a :: gkeys t

let rec cl (lex:list tvar) (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd          -> true
  | GVar s        -> L.mem s lex
  | GRec s g1     -> cl (s :: lex) g1
  | GMsg _ _ _ k  -> cl lex k
  | GCh _ _ opts  -> cl_opts lex opts
and cl_opts (lex:list tvar) (opts:list (label & gtyp)) : Tot bool (decreases opts) =
  match opts with
  | [] -> true
  | (_, g) :: tl -> cl lex g && cl_opts lex tl

let closed (g:gtyp) : bool = cl [] g

let rec gdistinct (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd | GVar _ -> true
  | GRec _ g1     -> gdistinct g1
  | GMsg _ _ _ k  -> gdistinct k
  | GCh _ _ opts  -> nodup (gkeys opts) && gdistinct_opts opts
and gdistinct_opts (opts:list (label & gtyp)) : Tot bool (decreases opts) =
  match opts with | [] -> true | (_, g) :: t -> gdistinct g && gdistinct_opts t

unfold let wellformed (g: gtyp) : bool =
  contractive g && no_self g && gdistinct g && closed g &&
  Some? (project g RC) && Some? (project g RA) && Some? (project g RJ) && Some? (project g RD)

// [rfl] sanity lemmas
let _proj_end (r:role) : Lemma (project GEnd r == Some LEnd) = ()
let _wf_end () : Lemma (wellformed GEnd) = ()

// [rfl] PROJECTION-SKIP (Direction C, W9): the projection of a role r NOT involved in the
// head `GMsg p q` (r<>p /\ r<>q) ignores that head — it is the projection of the
// continuation. That is exactly why an action INDEPENDENT of the head is already fireable
// at the endpoints (permutation/swap soundness).
let proj_skip (p q:role) (a:label) (k:gtyp) (r:role)
  : Lemma (requires r <> p /\ r <> q)
          (ensures project (GMsg p q a k) r == project k r) = ()

(* ------------------------------------------------------------------ *)
(* Data-plane contracts via refinements + SMT  (LH-Q-004, stage S)     *)
(* ------------------------------------------------------------------ *)
let draft (budget:nat) (cost:nat{cost <= budget}) : nat = budget - cost
let retry_safe (b:nat) (c1:nat{c1 <= b}) (c2:nat{c2 <= b - c1})
  : Lemma (c1 + c2 <= b) = ()

(* ------------------------------------------------------------------ *)
(* Global reduction relation  G --(p->q:l)--> G'                       *)
(* ------------------------------------------------------------------ *)
let rec subst_g (g: gtyp) (t: tvar) (r: gtyp) : Tot gtyp (decreases g) =
  match g with
  | GEnd          -> GEnd
  | GVar s        -> if s = t then r else g
  | GRec s g1     -> if s = t then g else GRec s (subst_g g1 t r)
  | GMsg p q a g1 -> GMsg p q a (subst_g g1 t r)
  | GCh p q opts  -> GCh p q (subst_opts opts t r)
and subst_opts (opts:list (label & gtyp)) (t:tvar) (r:gtyp) : Tot (list (label & gtyp)) (decreases opts) =
  match opts with
  | [] -> []
  | (l, g) :: tl -> (l, subst_g g t r) :: subst_opts tl t r

noeq type gstep : gtyp -> event -> gtyp -> Type =
  | GS_Msg : p:role -> q:role -> a:label -> k:gtyp ->
             gstep (GMsg p q a k) (p, q, a) k
  | GS_Ch  : p:role -> q:role -> opts:list (label & gtyp) -> i:nat{i < L.length opts} ->
             gstep (GCh p q opts) (p, q, fst (L.index opts i)) (snd (L.index opts i))
  | GS_Rec : t:tvar -> g:gtyp -> e:event -> g':gtyp ->
             gstep (subst_g g t (GRec t g)) e g' ->
             gstep (GRec t g) e g'

(* ------------------------------------------------------------------ *)
(* Endpoint configuration + synchronous reduction                     *)
(* ------------------------------------------------------------------ *)
type config = { cC: ltyp; cA: ltyp; cJ: ltyp; cD: ltyp }

let cget (c:config) (r:role) : ltyp =
  match r with | RC -> c.cC | RA -> c.cA | RJ -> c.cJ | RD -> c.cD
let cset (c:config) (r:role) (l:ltyp) : config =
  match r with
  | RC -> { c with cC = l } | RA -> { c with cA = l }
  | RJ -> { c with cJ = l } | RD -> { c with cD = l }

// synchronous configuration reduction: a send matched by a receive, or an n-ary choice
// selection (chooser's internal choice + receiver's external choice agree on the i-th label).
noeq type cstep : config -> event -> config -> Type =
  | CS_Send : c:config -> p:role -> q:role -> a:label -> kp:ltyp -> kq:ltyp ->
              squash (cget c p == LSnd q a kp) -> squash (cget c q == LRcv p a kq) ->
              cstep c (p, q, a) (cset (cset c p kp) q kq)
  | CS_Sel  : c:config -> p:role -> q:role ->
              osp:list (label & ltyp) -> osq:list (label & ltyp) -> i:nat ->
              squash (cget c p == LIntC q osp) -> squash (cget c q == LExtC p osq) ->
              squash (i < L.length osp /\ i < L.length osq /\
                      fst (L.index osp i) == fst (L.index osq i)) ->
              cstep c (p, q, fst (L.index osp i))
                    (cset (cset c p (snd (L.index osp i))) q (snd (L.index osq i)))

let proj (g: gtyp) (r: role) : ltyp =
  match project g r with | Some l -> l | None -> LEnd

let init_config (g: gtyp{wellformed g}) : config =
  { cC = proj g RC; cA = proj g RA; cJ = proj g RJ; cD = proj g RD }

// the configuration entry of role r in init_config is exactly r's projection (by cases on r)
let cget_init (g:gtyp{wellformed g}) (r:role) : Lemma (cget (init_config g) r == proj g r) =
  match r with | RC -> () | RA -> () | RJ -> () | RD -> ()

(* ------------------------------------------------------------------ *)
(* Key projection lemma for n-ary choice: the chooser/receiver projects *)
(* a GCh to an internal/external choice whose i-th option is the        *)
(* projection of the i-th branch (same label, projected continuation).  *)
(* ------------------------------------------------------------------ *)
let rec project_opts_len (opts:list (label & gtyp)) (r:role)
  : Lemma (requires Some? (project_opts opts r))
          (ensures (let Some os = project_opts opts r in L.length os == L.length opts))
          (decreases opts) =
  match opts with
  | [] -> ()
  | (_, _) :: t -> project_opts_len t r

let rec project_opts_index (opts:list (label & gtyp)) (r:role) (i:nat)
  : Lemma (requires Some? (project_opts opts r) /\ i < L.length opts)
          (ensures (let Some os = project_opts opts r in
                    i < L.length os /\
                    fst (L.index os i) == fst (L.index opts i) /\
                    project (snd (L.index opts i)) r == Some (snd (L.index os i))))
          (decreases opts) =
  project_opts_len opts r;
  match opts with
  | (_, _) :: t -> if i = 0 then () else project_opts_index t r (i - 1)

(* ------------------------------------------------------------------ *)
(* METATHEOREMS (mirror metatheory.py). Proofs machine-checked by F*.  *)
(* ------------------------------------------------------------------ *)

unfold let head_ok (g:gtyp) : bool =
  match g with
  | GMsg p q _ _ -> not (p = q)
  | GCh p q _ -> not (p = q)
  | _ -> false

unfold let is_head_event (g:gtyp) (e:event) : bool =
  match g with
  | GMsg p q a _ -> e = (p, q, a)
  | GCh p q _ -> (let (x, y, _) = e in x = p && y = q)   // a head choice event is a p->q comm
  | _ -> false

unfold let indep (e1 e2:event) : bool =
  let (p1,q1,_) = e1 in let (p2,q2,_) = e2 in
  p1<>p2 && p1<>q2 && q1<>p2 && q1<>q2

// Fidelity / operational correspondence — completeness (LH-Q-001a/c):
// every global head step is matched by a configuration step.
val fidelity_complete (g:gtyp{wellformed g}) (e:event) (g':gtyp) (d: gstep g e g')
  : Lemma (requires head_ok g)
          (ensures  (exists (c':config). cstep (init_config g) e c'))
let fidelity_complete g e g' d =
  let c = init_config g in
  match d with
  | GS_Msg p q a k ->
    introduce exists (c':config). cstep c e c'
    with (cset (cset c p (proj k p)) q (proj k q))
    and FStar.Squash.return_squash (CS_Send c p q a (proj k p) (proj k q) () ())
  | GS_Ch p q opts i ->
    project_opts_index opts p i;
    project_opts_index opts q i;
    let Some osp = project_opts opts p in
    let Some osq = project_opts opts q in
    introduce exists (c':config). cstep c e c'
    with (cset (cset c p (snd (L.index osp i))) q (snd (L.index osq i)))
    and FStar.Squash.return_squash (CS_Sel c p q osp osq i () () ())
  | GS_Rec t g0 ev g'' d' -> ()

// Fidelity — soundness (LH-Q-001a/c): for a head communication/choice every configuration
// step is matched by a global step. Inverts the cstep derivation.
// the chooser's projection of an n-ary choice is the internal choice over the projected opts
let proj_chooser (p q:role) (opts:list (label & gtyp))
  : Lemma (requires Some? (project_opts opts p))
          (ensures project (GCh p q opts) p == Some (LIntC q (Some?.v (project_opts opts p)))) = ()

val fidelity_sound (g:gtyp{wellformed g}) (e:event) (c':config) (d: cstep (init_config g) e c')
  : Lemma (requires head_ok g /\ is_head_event g e)
          (ensures  (exists (g':gtyp). gstep g e g'))
let fidelity_sound g e c' d =
  match g with
  | GMsg p q a k ->
    cget_init g p;
    (match d with
     | CS_Send _ pp qq aa _ _ _ _ ->
       assert (pp == p /\ qq == q /\ aa == a);
       introduce exists (g':gtyp). gstep g e g'
       with k and FStar.Squash.return_squash (GS_Msg p q a k)
     | CS_Sel _ pp qq osp osq i _ _ _ ->
       assert (pp == p);
       cget_init g pp;
       false_elim ())
  | GCh p q opts ->
    (match d with
     | CS_Sel _ pp qq osp osq i _ _ _ ->
       assert (pp == p /\ qq == q);
       cget_init g pp;
       proj_chooser p q opts;
       project_opts_len opts p;
       assert (i < L.length opts);
       project_opts_index opts p i;
       introduce exists (g':gtyp). gstep g e g'
       with (snd (L.index opts i))
       and FStar.Squash.return_squash (GS_Ch p q opts i)
     | CS_Send _ pp qq aa _ _ _ _ ->
       assert (pp == p);
       cget_init g pp;
       false_elim ())
  | _ -> ()

// Progress / deadlock-freedom (LH-Q-001b): a head communication or choice with distinct
// endpoints can always take the matching step.
val deadlock_free (g:gtyp{wellformed g})
  : Lemma (requires head_ok g)
          (ensures  (exists (e:event) (c':config). cstep (init_config g) e c'))
let deadlock_free g =
  let c = init_config g in
  match g with
  | GMsg p q a k ->
    introduce exists (e:event) (c':config). cstep c e c'
    with (p, q, a) (cset (cset c p (proj k p)) q (proj k q))
    and FStar.Squash.return_squash (CS_Send c p q a (proj k p) (proj k q) () ())
  | GCh p q opts ->
    // a well-formed n-ary choice has a non-empty option list (otherwise the chooser would
    // project to LIntC _ [], but a step still needs an index; require non-empty here).
    project_opts_index opts p 0;
    project_opts_index opts q 0;
    let Some osp = project_opts opts p in
    let Some osq = project_opts opts q in
    introduce exists (e:event) (c':config). cstep c e c'
    with (p, q, fst (L.index osp 0))
         (cset (cset c p (snd (L.index osp 0))) q (snd (L.index osq 0)))
    and FStar.Squash.return_squash (CS_Sel c p q osp osq 0 () () ())
  | _ -> ()

// W19-A (Q) — GLOBAL PROGRESS (head): a well-formed protocol whose head is a communication/choice
// can always take a GLOBAL step. The global counterpart of `deadlock_free` (which is at the
// configuration level); together with fidelity they drive the multi-step safety theorem (W19-A).
val global_progress (g:gtyp{wellformed g})
  : Lemma (requires head_ok g)
          (ensures  (exists (e:event) (g':gtyp). gstep g e g'))
let global_progress g =
  match g with
  | GMsg p q a k ->
    introduce exists (e:event) (g':gtyp). gstep g e g'
    with (p, q, a) k and FStar.Squash.return_squash (GS_Msg p q a k)
  | GCh p q opts ->
    project_opts_index opts p 0;                       // wellformed ⇒ opts non-empty (0 < length)
    introduce exists (e:event) (g':gtyp). gstep g e g'
    with (p, q, fst (L.index opts 0)) (snd (L.index opts 0))
    and FStar.Squash.return_squash (GS_Ch p q opts 0)
  | _ -> ()

// ------------------------------------------------------------------
// W19-A (P) — SUBJECT REDUCTION (preservation of well-formedness under a global step) for the
// RECURSION-FREE fragment. The GS_Rec (unfolding) case needs a substitution-preservation lemma and
// is the remaining step (tracked, W19); the communication steps below are the bulk of the proof.
// ------------------------------------------------------------------
let rec rec_free (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd -> true
  | GVar _ -> false
  | GRec _ _ -> false
  | GMsg _ _ _ k -> rec_free k
  | GCh _ _ opts -> rec_free_opts opts
and rec_free_opts (opts:list (label & gtyp)) : Tot bool (decreases opts) =
  match opts with
  | [] -> true
  | (_, g) :: t -> rec_free g && rec_free_opts t

// extract the i-th branch's per-conjunct well-formedness from the list-wide conjunctions
let rec contractive_opts_index (opts:list (label & gtyp)) (i:nat)
  : Lemma (requires contractive_opts opts /\ i < L.length opts)
          (ensures contractive_chk [] (snd (L.index opts i))) (decreases opts)
  = match opts with | (_, _) :: t -> if i = 0 then () else contractive_opts_index t (i - 1)

let rec no_self_opts_index (opts:list (label & gtyp)) (i:nat)
  : Lemma (requires no_self_opts opts /\ i < L.length opts)
          (ensures no_self (snd (L.index opts i))) (decreases opts)
  = match opts with | (_, _) :: t -> if i = 0 then () else no_self_opts_index t (i - 1)

let rec rec_free_opts_index (opts:list (label & gtyp)) (i:nat)
  : Lemma (requires rec_free_opts opts /\ i < L.length opts)
          (ensures rec_free (snd (L.index opts i))) (decreases opts)
  = match opts with | (_, _) :: t -> if i = 0 then () else rec_free_opts_index t (i - 1)

let rec gdistinct_opts_index (opts:list (label & gtyp)) (i:nat)
  : Lemma (requires gdistinct_opts opts /\ i < L.length opts)
          (ensures gdistinct (snd (L.index opts i))) (decreases opts)
  = match opts with | (_, _) :: t -> if i = 0 then () else gdistinct_opts_index t (i - 1)

let rec cl_opts_index (lex:list tvar) (opts:list (label & gtyp)) (i:nat)
  : Lemma (requires cl_opts lex opts /\ i < L.length opts)
          (ensures cl lex (snd (L.index opts i))) (decreases opts)
  = match opts with | (_, _) :: t -> if i = 0 then () else cl_opts_index lex t (i - 1)

let preservation (g:gtyp) (e:event) (g':gtyp) (d:gstep g e g')
  : Lemma (requires wellformed g /\ rec_free g)
          (ensures  wellformed g' /\ rec_free g')
  = match d with
    | GS_Msg p q a k -> ()                                    // g = GMsg p q a k, g' = k
    | GS_Ch p q opts i ->                                     // g' = i-th branch continuation
        contractive_opts_index opts i;
        no_self_opts_index opts i;
        gdistinct_opts_index opts i;
        cl_opts_index [] opts i;
        rec_free_opts_index opts i;
        project_opts_index opts RC i; project_opts_index opts RA i;
        project_opts_index opts RJ i; project_opts_index opts RD i
    | GS_Rec t g0 ev g'' d' -> ()                             // vacuous: rec_free (GRec ..) = false

// W19-A progress invariant: a well-formed recursion-free protocol is final OR a head communication
// (so `global_progress`/`deadlock_free` apply). With `preservation` this yields run-safety
// (deadlock-freedom along every reduction) for the recursion-free fragment.
let progress_invariant (g:gtyp)
  : Lemma (requires wellformed g /\ rec_free g) (ensures g = GEnd \/ head_ok g) = ()

(* ------------------------------------------------------------------ *)
(* W19-A (recursion): substitution preserves well-formedness — the lemmas needed for the GS_Rec   *)
(* (unfolding) case of full subject reduction. Built bottom-up; the projection-under-substitution  *)
(* part is the fiddly one (it must commute with the n-ary merge).                                  *)
(* ------------------------------------------------------------------ *)

// (a) no_self is preserved by substituting a no_self term.
let rec no_self_subst (body:gtyp) (x:tvar) (r:gtyp)
  : Lemma (requires no_self body /\ no_self r)
          (ensures  no_self (subst_g body x r)) (decreases body)
  = match body with
    | GEnd | GVar _ -> ()
    | GRec s g1     -> if s = x then () else no_self_subst g1 x r
    | GMsg _ _ _ g1 -> no_self_subst g1 x r
    | GCh _ _ opts  -> no_self_subst_opts opts x r
and no_self_subst_opts (opts:list (label & gtyp)) (x:tvar) (r:gtyp)
  : Lemma (requires no_self_opts opts /\ no_self r)
          (ensures  no_self_opts (subst_opts opts x r)) (decreases opts)
  = match opts with
    | [] -> ()
    | (_, g) :: tl -> no_self_subst g x r; no_self_subst_opts tl x r

// (b) contractiveness is preserved by substituting an `r` that is contractive under EVERY bound set
// (a closed contractive recursion is such an `r`; see `rec_always_contractive`). Same `bnd` on both
// sides — the GMsg/GCh communication clears `bnd`, so no anti-monotonicity issue arises.
let rec subst_contractive (body:gtyp) (x:tvar) (r:gtyp) (bnd:list tvar)
  : Lemma (requires contractive_chk bnd body /\ (forall (b:list tvar). contractive_chk b r))
          (ensures  contractive_chk bnd (subst_g body x r)) (decreases body)
  = match body with
    | GEnd | GVar _ -> ()
    | GRec s g1     -> if s = x then () else subst_contractive g1 x r (s :: bnd)
    | GMsg _ _ _ g1 -> subst_contractive g1 x r []
    | GCh _ _ opts  -> subst_contractive_opts opts x r
and subst_contractive_opts (opts:list (label & gtyp)) (x:tvar) (r:gtyp)
  : Lemma (requires contractive_opts opts /\ (forall (b:list tvar). contractive_chk b r))
          (ensures  contractive_opts (subst_opts opts x r)) (decreases opts)
  = match opts with
    | [] -> ()
    | (_, g) :: tl -> subst_contractive g x r []; subst_contractive_opts tl x r

(* ---- W19-A recursion soundness, cont'd: unfolding `GRec t g0 --> subst_g g0 t (GRec t g0)` -------
   We prove that UNFOLDING preserves two of the three well-formedness conjuncts — contractiveness and
   no-self-communication — for CLOSED protocols (every real protocol is closed). The third conjunct,
   projectability-under-unfolding, is the genuine MPST research lemma: it needs projection to commute
   with substitution THROUGH the n-ary merge, and the merge-commutation is only true intertwined with
   projection-DEFINEDNESS (the corner where distinct branches `LVar t` / `LRec t c` collapse under the
   substitution is exactly the non-mergeable, hence `project = None`, vacuous case). Tracked as the
   open residual (docs/analyses/w19-projection-completeness.md; SP-5 proof-loop goal). ----------------*)

// MONOTONICITY of contractive_chk: a smaller running (since-guard) set is a WEAKER constraint.
let rec ctr_mono (b1 b2:list tvar) (g:gtyp)
  : Lemma (requires (forall (v:tvar). L.mem v b1 ==> L.mem v b2) /\ contractive_chk b2 g)
          (ensures  contractive_chk b1 g) (decreases g)
  = match g with
    | GEnd | GVar _ -> ()
    | GRec s g1     -> ctr_mono (s :: b1) (s :: b2) g1
    | GMsg _ _ _ _  -> ()
    | GCh _ _ _     -> ()

// UNFOLD: substituting an `r` contractive under EVERY running set preserves contractive_chk at the
// SAME set. A guard (GMsg/GCh) resets the running set to [] — exactly where the closed `r` is needed.
let rec unfold_ctr (g:gtyp) (t:tvar) (g0:gtyp) (bnd:list tvar)
  : Lemma (requires contractive_chk bnd g /\ (forall (b:list tvar). contractive_chk b (GRec t g0)))
          (ensures  contractive_chk bnd (subst_g g t (GRec t g0))) (decreases g)
  = match g with
    | GEnd          -> ()
    | GVar _        -> ()
    | GRec s g1     -> if s = t then () else unfold_ctr g1 t g0 (s :: bnd)
    | GMsg _ _ _ k  -> unfold_ctr k t g0 []
    | GCh _ _ opts  -> unfold_ctr_opts opts t g0
and unfold_ctr_opts (opts:list (label & gtyp)) (t:tvar) (g0:gtyp)
  : Lemma (requires contractive_opts opts /\ (forall (b:list tvar). contractive_chk b (GRec t g0)))
          (ensures  contractive_opts (subst_opts opts t (GRec t g0))) (decreases opts)
  = match opts with
    | [] -> ()
    | (_, g) :: tl -> unfold_ctr g t g0 []; unfold_ctr_opts tl t g0

// LEXICAL closedness: every free type variable of g lies in `lex` (accumulates ALL enclosing GRec
// binders; never resets — unlike contractive_chk's since-guard set). `closed g = cl [] g`.
// AGREEMENT: for a lexically-closed g, contractive_chk depends on the running set only via its
// restriction to `lex`; running sets agreeing on `lex` give the same verdict (both reset past guards).
let rec ctr_agree (g:gtyp) (r1 r2:list tvar) (lex:list tvar)
  : Lemma (requires cl lex g /\ contractive_chk r1 g
                 /\ (forall (v:tvar). L.mem v lex ==> (L.mem v r1 = L.mem v r2)))
          (ensures  contractive_chk r2 g) (decreases g)
  = match g with
    | GEnd | GVar _ -> ()
    | GRec s g1     -> ctr_agree g1 (s :: r1) (s :: r2) (s :: lex)
    | GMsg _ _ _ k  -> ctr_agree k [] [] lex
    | GCh _ _ _     -> ()

// COROLLARY: a closed contractive recursion is contractive under every running set.
let rec_all_ctr (t:tvar) (g0:gtyp) (b:list tvar)
  : Lemma (requires contractive_chk [t] g0 /\ cl [t] g0)
          (ensures  contractive_chk b (GRec t g0))
  = ctr_agree g0 [t] (t :: b) [t]

// (b′) CONTRACTIVENESS is preserved by unfolding a closed contractive recursion.
let unfold_contractive (t:tvar) (g0:gtyp)
  : Lemma (requires contractive (GRec t g0) /\ closed (GRec t g0))
          (ensures  contractive (subst_g g0 t (GRec t g0)))
  = ctr_mono [] [t] g0;
    let aux (b:list tvar) : Lemma (contractive_chk b (GRec t g0)) = rec_all_ctr t g0 b in
    FStar.Classical.forall_intro aux;
    unfold_ctr g0 t g0 []

// (a′) NO-SELF-COMMUNICATION is preserved by unfolding (immediate from no_self_subst).
let unfold_no_self (t:tvar) (g0:gtyp)
  : Lemma (requires no_self (GRec t g0))
          (ensures  no_self (subst_g g0 t (GRec t g0)))
  = no_self_subst g0 t (GRec t g0)


(* ============================================================================
   W19-A (c') — projectability preserved by unfolding GRec (ported from W19ProjSubst.fst,
   verified 0 admits). Powers subst_g_wf + the GS_Rec case of `preservation`.
   ============================================================================ *)
// substitution on LOCAL types (mirror of subst_g on globals; capture-avoiding at LRec).
let rec subst_l (l:ltyp) (x:tvar) (rl:ltyp) : Tot ltyp (decreases l) =
  match l with
  | LEnd          -> LEnd
  | LVar s        -> if s = x then rl else l
  | LRec s c      -> if s = x then l else LRec s (subst_l c x rl)
  | LSnd q a c    -> LSnd q a (subst_l c x rl)
  | LRcv p a c    -> LRcv p a (subst_l c x rl)
  | LIntC q os    -> LIntC q (subst_lopts os x rl)
  | LExtC p os    -> LExtC p (subst_lopts os x rl)
and subst_lopts (os:list (label & ltyp)) (x:tvar) (rl:ltyp) : Tot (list (label & ltyp)) (decreases os) =
  match os with
  | [] -> []
  | (l, c) :: t -> (l, subst_l c x rl) :: subst_lopts t x rl

// opts_of commutes with subst when defined (the only Some cases are LRcv / LExtC).
let opts_of_subst (l:ltyp) (x:tvar) (rl:ltyp) (p:role) (o:list (label & ltyp))
  : Lemma (requires opts_of l == Some (p, o))
          (ensures  opts_of (subst_l l x rl) == Some (p, subst_lopts o x rl)) = ()

// assoc_lbl commutes with subst (both Some and None cases).
let rec assoc_subst (a:label) (os:list (label & ltyp)) (x:tvar) (rl:ltyp)
  : Lemma (ensures (match assoc_lbl a os with
                    | None    -> assoc_lbl a (subst_lopts os x rl) == None
                    | Some c0 -> assoc_lbl a (subst_lopts os x rl) == Some (subst_l c0 x rl)))
          (decreases os)
  = match os with
    | [] -> ()
    | (l, _) :: t -> if l = a then () else assoc_subst a t x rl

// replace_lbl commutes with subst (structural; always).
let rec replace_subst (a:label) (c':ltyp) (os:list (label & ltyp)) (x:tvar) (rl:ltyp)
  : Lemma (ensures subst_lopts (replace_lbl a c' os) x rl
                == replace_lbl a (subst_l c' x rl) (subst_lopts os x rl)) (decreases os)
  = match os with
    | [] -> ()
    | (l, _) :: t -> if l = a then () else replace_subst a c' t x rl

(* ---- list / assoc / nodup algebra (what F* needs to thread lookups through prepend & replace) ---- *)
let rec assoc_not_mem (a:label) (os:list (label & ltyp))
  : Lemma (requires not (L.mem a (keys os))) (ensures assoc_lbl a os == None) (decreases os)
  = match os with | [] -> () | (_, _) :: t -> assoc_not_mem a t

let rec assoc_replace_other (a b:label) (c':ltyp) (os:list (label & ltyp))
  : Lemma (requires a <> b) (ensures assoc_lbl a (replace_lbl b c' os) == assoc_lbl a os) (decreases os)
  = match os with | [] -> () | (l, _) :: t -> if l = b then () else assoc_replace_other a b c' t

let rec assoc_replace_same (b:label) (c':ltyp) (os:list (label & ltyp))
  : Lemma (requires Some? (assoc_lbl b os)) (ensures assoc_lbl b (replace_lbl b c' os) == Some c') (decreases os)
  = match os with | [] -> () | (l, _) :: t -> if l = b then () else assoc_replace_same b c' t

(* ldistinct: every choice node has distinct branch labels (true of projections of well-formed,
   distinct-label global types; preserved by merge and by sub-term). *)
let rec ldistinct (l:ltyp) : Tot bool (decreases l) =
  match l with
  | LEnd | LVar _ -> true
  | LRec _ c | LSnd _ _ c | LRcv _ _ c -> ldistinct c
  | LIntC _ os | LExtC _ os -> nodup (keys os) && ldistinct_opts os
and ldistinct_opts (os:list (label & ltyp)) : Tot bool (decreases os) =
  match os with | [] -> true | (_, c) :: t -> ldistinct c && ldistinct_opts t

// KEY CHARACTERISATION: merge_opts_f folds o2 into acc; the result `o`, looked up at any label a, is
// determined by the lookups in acc and o2 — and where BOTH have a, the conts were merged (a witness
// exists). Stated about assoc lookups (which transform predictably under prepend/replace), so the
// induction GENERALISES over the rewritten accumulator — where value-equality inductions could not.
let rec merge_opts_lookup (n:nat) (acc o2 o:list (label & ltyp)) (a:label)
  : Lemma (requires merge_opts_f n acc o2 == Some o /\ nodup (keys o2))
          (ensures (match assoc_lbl a acc, assoc_lbl a o2 with
                    | None,    None    -> assoc_lbl a o == None
                    | Some c0, None    -> assoc_lbl a o == Some c0
                    | None,    Some c  -> assoc_lbl a o == Some c
                    | Some c0, Some c  -> Some? (assoc_lbl a o)
                                       /\ (exists (k:nat). merge_f k c0 c == Some (Some?.v (assoc_lbl a o)))))
          (decreases n)
  = if n = 0 then ()
    else (match o2 with
          | [] -> ()
          | (b, cb) :: t ->
              if a = b then assoc_not_mem b t else assoc_replace_other a b cb acc;
              (match assoc_lbl b acc with
               | None    -> merge_opts_lookup (n - 1) ((b, cb) :: acc) t o a
               | Some c0 ->
                   (match merge_f (n - 1) c0 cb with
                    | Some c' ->
                        (if a = b then assoc_replace_same b c' acc
                         else assoc_replace_other a b c' acc);
                        merge_opts_lookup (n - 1) (replace_lbl b c' acc) t o a
                    | None    -> ())))

// subst preserves assoc lookups up to subst on the looked-up continuations.
let rec subst_assoc (o1 o2:list (label & ltyp)) (a:label) (x:tvar) (rl:ltyp)
  : Lemma (requires subst_lopts o1 x rl == subst_lopts o2 x rl)
          (ensures (match assoc_lbl a o1, assoc_lbl a o2 with
                    | None,    None   -> True
                    | Some c0, Some c -> subst_l c0 x rl == subst_l c x rl
                    | _,       _      -> False)) (decreases o1)
  = match o1, o2 with
    | [], [] -> ()
    | (_, _) :: t1, (_, _) :: t2 -> subst_assoc t1 t2 a x rl
    | _ -> ()

// a nodup option list is determined by its labels-in-order and its assoc map; so subst-equal lists
// (same label order) with everywhere-equal assoc are equal.
let rec opts_eq_from_assoc (o1 o2:list (label & ltyp)) (x:tvar) (rl:ltyp)
  : Lemma (requires subst_lopts o1 x rl == subst_lopts o2 x rl /\ nodup (keys o1)
                 /\ (forall (a:label). (match assoc_lbl a o1, assoc_lbl a o2 with
                                        | Some c0, Some c -> c0 == c | _, _ -> True)))
          (ensures o1 == o2) (decreases o1)
  = match o1, o2 with
    | [], [] -> ()
    | (l1, c1) :: t1, (l2, c2) :: t2 ->
        assoc_not_mem l1 t1;                          // nodup => l1 not in t1 => assoc l1 o1 = Some c1
        opts_eq_from_assoc t1 t2 x rl
    | _ -> ()

// opts_of of an ldistinct local type yields a nodup, ldistinct option list.
let opts_of_ldistinct (l:ltyp) (p:role) (o:list (label & ltyp))
  : Lemma (requires ldistinct l /\ opts_of l == Some (p, o))
          (ensures  nodup (keys o) /\ ldistinct_opts o) = ()

let rec assoc_ldistinct (os:list (label & ltyp)) (a:label)
  : Lemma (requires ldistinct_opts os)
          (ensures (match assoc_lbl a os with Some c -> ldistinct c | None -> True)) (decreases os)
  = match os with | [] -> () | (l, _) :: t -> if l = a then () else assoc_ldistinct t a

// KEYSTONE: substitution is INJECTIVE on the success world. A collapse (subst l1 = subst l2 with
// l1 <> l2) would force a sub-merge of `LVar`/non-var (= None), contradicting merge-success.
// Measure is the TYPE SIZE (lexicographic with a tag) — fuel cannot decrease across the cross-calls,
// and the merge witness is taken existentially (any sufficient fuel works, by monotonicity).
let rec subst_inj (l1 l2:ltyp) (x:tvar) (rl:ltyp)
  : Lemma (requires (exists (k:nat) (m:ltyp). merge_f k l1 l2 == Some m) /\ ldistinct l1 /\ ldistinct l2)
          (ensures  subst_l l1 x rl == subst_l l2 x rl ==> l1 == l2)
          (decreases %[lsize l1 + lsize l2; 0])
  = if l1 = l2 then ()
    else (match opts_of l1, opts_of l2 with
          | Some (p, o1), Some (q, o2) ->
              if p = q then (
                opts_of_ldistinct l1 p o1; opts_of_ldistinct l2 q o2;
                opts_of_size l1 p o1; opts_of_size l2 q o2;          // lsize_opts oi + 1 = lsize li
                eliminate exists (k:nat) (m:ltyp). merge_f k l1 l2 == Some m
                returns (exists (k2:nat) (o:list (label & ltyp)). merge_opts_f k2 o1 o2 == Some o)
                with _. (
                  // k>=1 (else None), l1<>l2, opts Some, p=q  ==>  merge_opts_f (k-1) o1 o2 = Some _
                  introduce exists (k2:nat) (o:list (label & ltyp)). merge_opts_f k2 o1 o2 == Some o
                  with (k - 1) (Some?.v (merge_opts_f (k - 1) o1 o2)) and ());
                subst_opts_inj o1 o2 x rl
              ) else ()
          | _, _ -> ())
and subst_opts_inj (o1 o2:list (label & ltyp)) (x:tvar) (rl:ltyp)
  : Lemma (requires (exists (k:nat) (o:list (label & ltyp)). merge_opts_f k o1 o2 == Some o)
                 /\ nodup (keys o1) /\ nodup (keys o2) /\ ldistinct_opts o1 /\ ldistinct_opts o2)
          (ensures  subst_lopts o1 x rl == subst_lopts o2 x rl ==> o1 == o2)
          (decreases %[lsize_opts o1 + lsize_opts o2; 1])
  = let aux (a:label)
      : Lemma (subst_lopts o1 x rl == subst_lopts o2 x rl
               ==> (match assoc_lbl a o1, assoc_lbl a o2 with Some c0, Some c -> c0 == c | _, _ -> True))
      = if subst_lopts o1 x rl = subst_lopts o2 x rl then
          (match assoc_lbl a o1, assoc_lbl a o2 with
           | Some c0, Some c ->
               assoc_size a o1 c0; assoc_size a o2 c;        // lsize c0 <= lsize_opts o1, etc. (measure)
               subst_assoc o1 o2 a x rl;                     // subst c0 = subst c
               assoc_ldistinct o1 a; assoc_ldistinct o2 a;   // ldistinct c0, ldistinct c
               eliminate exists (k:nat) (o:list (label & ltyp)). merge_opts_f k o1 o2 == Some o
               returns (c0 == c)
               with _. (
                 merge_opts_lookup k o1 o2 o a;              // exists k'. merge_f k' c0 c = Some _
                 subst_inj c0 c x rl)                        // subst c0=subst c ==> c0=c
           | _, _ -> ())
        else () in
    FStar.Classical.forall_intro aux;
    if subst_lopts o1 x rl = subst_lopts o2 x rl then opts_eq_from_assoc o1 o2 x rl else ()

// ---- ldistinct is preserved by replace and by merge (so accumulators stay distinct-labelled). ----
let rec assoc_none_not_mem (a:label) (os:list (label & ltyp))
  : Lemma (requires assoc_lbl a os == None) (ensures not (L.mem a (keys os))) (decreases os)
  = match os with | [] -> () | (l, _) :: t -> if l = a then () else assoc_none_not_mem a t

let rec keys_replace (a:label) (c':ltyp) (os:list (label & ltyp))
  : Lemma (ensures keys (replace_lbl a c' os) == keys os) (decreases os)
  = match os with | [] -> () | (l, _) :: t -> if l = a then () else keys_replace a c' t

let rec ldistinct_replace (a:label) (c':ltyp) (os:list (label & ltyp))
  : Lemma (requires ldistinct_opts os /\ ldistinct c')
          (ensures  ldistinct_opts (replace_lbl a c' os)) (decreases os)
  = match os with | [] -> () | (l, _) :: t -> if l = a then () else ldistinct_replace a c' t

let rec merge_ldistinct (n:nat) (l1 l2 m:ltyp)
  : Lemma (requires merge_f n l1 l2 == Some m /\ ldistinct l1 /\ ldistinct l2)
          (ensures  ldistinct m) (decreases n)
  = if n = 0 then () else if l1 = l2 then ()
    else (match opts_of l1, opts_of l2 with
          | Some (p, o1), Some (q, o2) ->
              if p = q then
                (match merge_opts_f (n - 1) o1 o2 with
                 | Some o -> opts_of_ldistinct l1 p o1; opts_of_ldistinct l2 q o2;
                             merge_opts_ldistinct (n - 1) o1 o2 o
                 | None   -> ())
              else ()
          | _, _ -> ())
and merge_opts_ldistinct (n:nat) (o1 o2 o:list (label & ltyp))
  : Lemma (requires merge_opts_f n o1 o2 == Some o
                 /\ nodup (keys o1) /\ ldistinct_opts o1 /\ ldistinct_opts o2)
          (ensures  nodup (keys o) /\ ldistinct_opts o) (decreases n)
  = if n = 0 then ()
    else (match o2 with
          | [] -> ()
          | (a, c) :: t ->
              (match assoc_lbl a o1 with
               | None    -> assoc_none_not_mem a o1;          // a not in keys o1 => nodup ((a,_)::o1)
                            merge_opts_ldistinct (n - 1) ((a, c) :: o1) t o
               | Some c0 ->
                   (match merge_f (n - 1) c0 c with
                    | Some c' -> assoc_ldistinct o1 a; merge_ldistinct (n - 1) c0 c c';
                                 keys_replace a c' o1; ldistinct_replace a c' o1;
                                 merge_opts_ldistinct (n - 1) (replace_lbl a c' o1) t o
                    | None    -> ())))

// CORE: merge-success is preserved by substitution, and the result is the substituted merge.
// ldistinct l1/l2 lets the keystone subst_inj rule out the spurious `l1 = l2` short-circuit collapse.
let rec merge_subst (n:nat) (l1 l2:ltyp) (m:ltyp) (x:tvar) (rl:ltyp)
  : Lemma (requires merge_f n l1 l2 == Some m /\ ldistinct l1 /\ ldistinct l2)
          (ensures  merge_f n (subst_l l1 x rl) (subst_l l2 x rl) == Some (subst_l m x rl))
          (decreases n)
  = if n = 0 then ()
    else if l1 = l2 then ()                              // subst l1 = subst l2 -> equal branch
    else (subst_inj l1 l2 x rl;                          // l1<>l2 => subst l1 <> subst l2 (no collapse)
          match opts_of l1, opts_of l2 with
          | Some (p, o1), Some (q, o2) ->
              if p = q then
                (match merge_opts_f (n - 1) o1 o2 with
                 | Some o ->
                     opts_of_ldistinct l1 p o1; opts_of_ldistinct l2 q o2;
                     opts_of_subst l1 x rl p o1;
                     opts_of_subst l2 x rl q o2;
                     merge_opts_subst (n - 1) o1 o2 o x rl
                 | None   -> ())
              else ()
          | _, _ -> ())
and merge_opts_subst (n:nat) (o1 o2:list (label & ltyp)) (o:list (label & ltyp)) (x:tvar) (rl:ltyp)
  : Lemma (requires merge_opts_f n o1 o2 == Some o /\ ldistinct_opts o1 /\ ldistinct_opts o2)
          (ensures  merge_opts_f n (subst_lopts o1 x rl) (subst_lopts o2 x rl)
                 == Some (subst_lopts o x rl))
          (decreases n)
  = if n = 0 then ()
    else (match o2 with
          | [] -> ()
          | (a, c) :: t ->
              assoc_subst a o1 x rl;
              (match assoc_lbl a o1 with
               | None    -> merge_opts_subst (n - 1) ((a, c) :: o1) t o x rl
               | Some c0 ->
                   (match merge_f (n - 1) c0 c with
                    | Some c' ->
                        assoc_ldistinct o1 a;                 // ldistinct c0
                        merge_subst (n - 1) c0 c c' x rl;
                        merge_ldistinct (n - 1) c0 c c';      // ldistinct c' (for the replaced accumulator)
                        replace_subst a c' o1 x rl;
                        ldistinct_replace a c' o1;            // ldistinct_opts (replace_lbl a c' o1)
                        merge_opts_subst (n - 1) (replace_lbl a c' o1) t o x rl
                    | None    -> ())))

// substitution never shrinks size (LVar x, size 1, becomes rl, size >= 1) — so the wrapper fuel grows.
let rec lsize_pos (l:ltyp) : Lemma (ensures lsize l >= 1) (decreases l) =
  match l with
  | LEnd | LVar _ -> () | LRec _ c -> lsize_pos c | LSnd _ _ c -> lsize_pos c
  | LRcv _ _ c -> lsize_pos c | LIntC _ _ -> () | LExtC _ _ -> ()

let rec lsize_subst_ge (l:ltyp) (x:tvar) (rl:ltyp)
  : Lemma (requires lsize rl >= 1) (ensures lsize l <= lsize (subst_l l x rl)) (decreases l)
  = match l with
    | LEnd | LVar _ -> ()
    | LRec s c   -> if s = x then () else lsize_subst_ge c x rl
    | LSnd _ _ c -> lsize_subst_ge c x rl
    | LRcv _ _ c -> lsize_subst_ge c x rl
    | LIntC _ os | LExtC _ os -> lsize_subst_ge_opts os x rl
and lsize_subst_ge_opts (os:list (label & ltyp)) (x:tvar) (rl:ltyp)
  : Lemma (requires lsize rl >= 1) (ensures lsize_opts os <= lsize_opts (subst_lopts os x rl)) (decreases os)
  = match os with
    | [] -> ()
    | (_, c) :: t -> lsize_subst_ge c x rl; lsize_subst_ge_opts t x rl

// lift merge-subst from arbitrary fuel to the wrapper `merge` (fuel grows under subst; mono closes it).
let merge_wrap_subst (l1 l2 m:ltyp) (x:tvar) (rl:ltyp)
  : Lemma (requires merge l1 l2 == Some m /\ ldistinct l1 /\ ldistinct l2)
          (ensures  merge (subst_l l1 x rl) (subst_l l2 x rl) == Some (subst_l m x rl))
  = let n = 2 * (lsize l1 + lsize l2) in
    let n' = 2 * (lsize (subst_l l1 x rl) + lsize (subst_l l2 x rl)) in
    lsize_pos rl; lsize_subst_ge l1 x rl; lsize_subst_ge l2 x rl;   // n' >= n
    merge_subst n l1 l2 m x rl;                       // merge_f n (subst l1)(subst l2) = Some (subst m)
    merge_f_mono_le n n' (subst_l l1 x rl) (subst_l l2 x rl) (subst_l m x rl)

// merge_all preserves ldistinct (so the fold's accumulator stays distinct-labelled).
let rec merge_all_ldistinct (os:list (label & ltyp)) (m:ltyp)
  : Lemma (requires merge_all os == Some m /\ ldistinct_opts os) (ensures ldistinct m) (decreases os)
  = match os with
    | [(_, l)] -> ()
    | (_, l) :: t ->
        (match merge_all t with
         | Some mt -> merge_all_ldistinct t mt; merge_ldistinct (2 * (lsize l + lsize mt)) l mt m
         | None    -> ())

// merge_all over substituted options: success preserved with the substituted value.
let rec merge_all_subst (os:list (label & ltyp)) (m:ltyp) (x:tvar) (rl:ltyp)
  : Lemma (requires merge_all os == Some m /\ ldistinct_opts os)
          (ensures  merge_all (subst_lopts os x rl) == Some (subst_l m x rl)) (decreases os)
  = match os with
    | [(_, l)] -> ()
    | (_, l) :: t ->
        (match merge_all t with
         | Some mt -> merge_all_subst t mt x rl; merge_all_ldistinct t mt; merge_wrap_subst l mt m x rl
         | None    -> ())

// projection preserves the label sequence of a choice's options.
let rec proj_keys (opts:list (label & gtyp)) (r:role) (os:list (label & ltyp))
  : Lemma (requires project_opts opts r == Some os) (ensures keys os == gkeys opts) (decreases opts)
  = match opts with
    | [] -> ()
    | (a, g) :: t ->
        (match project g r, project_opts t r with
         | Some _, Some rest -> proj_keys t r rest
         | _, _ -> ())

// projection of a gdistinct global type is an ldistinct local type.
let rec project_ldistinct (g:gtyp) (r:role) (l:ltyp)
  : Lemma (requires gdistinct g /\ project g r == Some l) (ensures ldistinct l) (decreases g)
  = match g with
    | GEnd | GVar _ -> ()
    | GRec _ g1     -> (match project g1 r with | Some _ -> project_ldistinct g1 r (Some?.v (project g1 r)) | None -> ())
    | GMsg _ _ _ k  -> (match project k r with | Some _ -> project_ldistinct k r (Some?.v (project k r)) | None -> ())
    | GCh p q opts  ->
        (match project_opts opts r with
         | Some os ->
             proj_keys opts r os; project_opts_ldistinct opts r os;
             if r = p then () else if r = q then ()
             else (match merge_all os with | Some m -> merge_all_ldistinct os m | None -> ())
         | None -> ())
and project_opts_ldistinct (opts:list (label & gtyp)) (r:role) (os:list (label & ltyp))
  : Lemma (requires gdistinct_opts opts /\ project_opts opts r == Some os)
          (ensures  ldistinct_opts os) (decreases opts)
  = match opts with
    | [] -> ()
    | (a, g) :: t ->
        (match project g r, project_opts t r with
         | Some lg, Some rest -> project_ldistinct g r lg; project_opts_ldistinct t r rest
         | _, _ -> ())

// project commutes with substitution (definedness + value), the GCh third-role case using merge_all_subst.
let rec proj_subst (g:gtyp) (r:role) (l:ltyp) (x:tvar) (rg:gtyp) (lR:ltyp)
  : Lemma (requires project g r == Some l /\ project rg r == Some lR /\ gdistinct g)
          (ensures  project (subst_g g x rg) r == Some (subst_l l x lR)) (decreases g)
  = match g with
    | GEnd          -> ()
    | GVar s        -> ()                                 // s=x: lR; s<>x: LVar s unchanged
    | GRec s g1     -> if s = x then ()
                       else (match project g1 r with
                             | Some l1 -> proj_subst g1 r l1 x rg lR | None -> ())
    | GMsg p q a k  -> (match project k r with
                        | Some lk -> proj_subst k r lk x rg lR | None -> ())
    | GCh p q opts  ->
        (match project_opts opts r with
         | Some os ->
             proj_opts_subst opts r os x rg lR;
             if r = p then () else if r = q then ()
             else (match merge_all os with
                   | Some m -> project_opts_ldistinct opts r os; merge_all_subst os m x lR | None -> ())
         | None -> ())
and proj_opts_subst (opts:list (label & gtyp)) (r:role) (os:list (label & ltyp)) (x:tvar) (rg:gtyp) (lR:ltyp)
  : Lemma (requires project_opts opts r == Some os /\ project rg r == Some lR /\ gdistinct_opts opts)
          (ensures  project_opts (subst_opts opts x rg) r == Some (subst_lopts os x lR)) (decreases opts)
  = match opts with
    | [] -> ()
    | (lab, g) :: t ->
        (match project g r, project_opts t r with
         | Some lg, Some rest -> proj_subst g r lg x rg lR; proj_opts_subst t r rest x rg lR
         | _, _ -> ())

// FINAL: projectability is preserved by unfolding (the (c') conjunct) — for distinct-label protocols.
let unfold_projectable (t:tvar) (g0:gtyp) (r:role)
  : Lemma (requires Some? (project (GRec t g0) r) /\ gdistinct (GRec t g0))
          (ensures  Some? (project (subst_g g0 t (GRec t g0)) r))
  = match project g0 r with                             // project (GRec t g0) r = Some (LRec t l0)
    | Some l0 -> proj_subst g0 r l0 t (GRec t g0) (LRec t l0)
    | None    -> ()


(* ------------------------------------------------------------------ *)
(* W9 MECHANIZED — permutation + diamond/confluence of independent     *)
(* GMsg actions (unchanged from the baseline; choice-agnostic).        *)
(* ------------------------------------------------------------------ *)
noeq type cgstep : gtyp -> event -> gtyp -> Type =
  | CG_Head : p:role -> q:role -> a:label -> k:gtyp ->
              cgstep (GMsg p q a k) (p, q, a) k
  | CG_Swap : p:role -> q:role -> a:label -> k:gtyp -> e:event -> k':gtyp ->
              squash (indep e (p, q, a)) -> cgstep k e k' ->
              cgstep (GMsg p q a k) e (GMsg p q a k')

val diamond_indep (p:role) (q:role) (r:role) (s:role) (a:label) (b:label) (k:gtyp)
  : Lemma (requires r<>p /\ r<>q /\ s<>p /\ s<>q)
          (ensures
              squash (cgstep (GMsg p q a (GMsg r s b k)) (p,q,a) (GMsg r s b k))
           /\ squash (cgstep (GMsg r s b k) (r,s,b) k)
           /\ squash (cgstep (GMsg p q a (GMsg r s b k)) (r,s,b) (GMsg p q a k))
           /\ squash (cgstep (GMsg p q a k) (p,q,a) k))
let diamond_indep p q r s a b k =
  let inner : cgstep (GMsg r s b k) (r,s,b) k = CG_Head r s b k in
  let _ : squash (cgstep (GMsg p q a (GMsg r s b k)) (p,q,a) (GMsg r s b k)) =
    FStar.Squash.return_squash (CG_Head p q a (GMsg r s b k)) in
  let _ : squash (cgstep (GMsg r s b k) (r,s,b) k) =
    FStar.Squash.return_squash inner in
  let _ : squash (cgstep (GMsg p q a (GMsg r s b k)) (r,s,b) (GMsg p q a k)) =
    FStar.Squash.return_squash (CG_Swap p q a (GMsg r s b k) (r,s,b) k () inner) in
  let _ : squash (cgstep (GMsg p q a k) (p,q,a) k) =
    FStar.Squash.return_squash (CG_Head p q a k) in
  ()

// CONFIGURATION DIAMOND (Direction C): the permutation also holds at the ENDPOINT level.
// On the canonical independent 4-role pair (RC->RA  ∥  RJ->RD) the configuration fires
// both actions in BOTH orders — and both orders meet in the SAME state (confluence).
let cstep_diamond (a b:label) (kp kq kr ks:ltyp)
  : Lemma
      (ensures (
        let c   = { cC = LSnd RA a kp; cA = LRcv RC a kq; cJ = LSnd RD b kr; cD = LRcv RJ b ks } in
        let c1  = cset (cset c RC kp) RA kq in
        let c12 = cset (cset c1 RJ kr) RD ks in
        let c2  = cset (cset c RJ kr) RD ks in
        let c21 = cset (cset c2 RC kp) RA kq in
        c12 == c21
        /\ squash (cstep c  (RC,RA,a) c1)  /\ squash (cstep c1 (RJ,RD,b) c12)
        /\ squash (cstep c  (RJ,RD,b) c2)  /\ squash (cstep c2 (RC,RA,a) c21)))
  =
  let c   = { cC = LSnd RA a kp; cA = LRcv RC a kq; cJ = LSnd RD b kr; cD = LRcv RJ b ks } in
  let c1  = cset (cset c RC kp) RA kq in
  let c12 = cset (cset c1 RJ kr) RD ks in
  let c2  = cset (cset c RJ kr) RD ks in
  let c21 = cset (cset c2 RC kp) RA kq in
  let _ : squash (cstep c  (RC,RA,a) c1)  = FStar.Squash.return_squash (CS_Send c  RC RA a kp kq () ()) in
  let _ : squash (cstep c1 (RJ,RD,b) c12) = FStar.Squash.return_squash (CS_Send c1 RJ RD b kr ks () ()) in
  let _ : squash (cstep c  (RJ,RD,b) c2)  = FStar.Squash.return_squash (CS_Send c  RJ RD b kr ks () ()) in
  let _ : squash (cstep c2 (RC,RA,a) c21) = FStar.Squash.return_squash (CS_Send c2 RC RA a kp kq () ()) in
  ()   // c12 == c21 by concrete computation of the record updates

(* ------------------------------------------------------------------ *)
(* CONSERVATIVITY / GRADUAL GUARANTEE  (CEP-0003 C9, CEP-0004 C9).       *)
(*                                                                      *)
(* The n-ary choice is a CONSERVATIVE EXTENSION of binary choice: on a  *)
(* protocol whose every choice is binary (exactly two branches), the    *)
(* n-ary projection computes EXACTLY what a dedicated binary projector  *)
(* would. Hence enabling the `extended` capability level can never      *)
(* change the verdict (projectability / well-formedness) of a `core`    *)
(* (binary-only) protocol — the level model's deny-by-default ceiling   *)
(* is therefore sound: a `core` program is decided identically whether  *)
(* the n-ary feature is "on" or "off".                                  *)
(* ------------------------------------------------------------------ *)

// KEYSTONE: the ONLY computational difference between n-ary and binary
// projection is the third-role merge. For TWO branches the n-ary fold
// `merge_all` collapses to a single binary `merge` of the two projected
// continuations. (Definitional, but it pins the property against future
// drift in `merge_all`.)
let merge_all_binary (l1 l2:label) (m1 m2:ltyp)
  : Lemma (merge_all [(l1, m1); (l2, m2)] == merge m1 m2) = ()

// The binary fragment: every choice carries exactly two branches.
let rec is_bin_frag (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd | GVar _ -> true
  | GRec _ g1     -> is_bin_frag g1
  | GMsg _ _ _ g1 -> is_bin_frag g1
  | GCh _ _ [(_, g1); (_, g2)] -> is_bin_frag g1 && is_bin_frag g2
  | GCh _ _ _     -> false

// A dedicated BINARY projector, defined INDEPENDENTLY of `project`: it
// handles only two-branch choices and uses the binary `merge` directly
// (no n-ary fold). This is what a `core`-only calculus would ship.
let rec project_bin (g:gtyp) (r:role) : Tot (option ltyp) (decreases g) =
  match g with
  | GEnd      -> Some LEnd
  | GVar t    -> Some (LVar t)
  | GRec t g1 -> (match project_bin g1 r with | Some l -> Some (LRec t l) | None -> None)
  | GMsg p q a g1 ->
      (match project_bin g1 r with
       | None   -> None
       | Some l -> if r = p then Some (LSnd q a l)
                   else if r = q then Some (LRcv p a l) else Some l)
  | GCh p q [(l1, g1); (l2, g2)] ->
      (match project_bin g1 r, project_bin g2 r with
       | Some o1, Some o2 ->
           if r = p then Some (LIntC q [(l1, o1); (l2, o2)])
           else if r = q then Some (LExtC p [(l1, o1); (l2, o2)])
           else merge o1 o2
       | _, _ -> None)
  | GCh _ _ _ -> None

// CONSERVATIVITY THEOREM: on the binary fragment, the shipped n-ary
// `project` coincides with the independent binary projector `project_bin`.
let rec conserv (g:gtyp) (r:role)
  : Lemma (requires is_bin_frag g)
          (ensures  project g r == project_bin g r)
          (decreases g) =
  match g with
  | GEnd | GVar _ -> ()
  | GRec _ g1     -> conserv g1 r
  | GMsg _ _ _ g1 -> conserv g1 r
  | GCh p q [(l1, g1); (l2, g2)] -> conserv g1 r; conserv g2 r
  | GCh _ _ _     -> ()

// COROLLARY: a binary-fragment protocol is well-formed under the n-ary
// core iff it is well-formed under the binary projector — same verdict.
let conserv_wf (g:gtyp)
  : Lemma (requires is_bin_frag g)
          (ensures  wellformed g == (contractive g && no_self g && gdistinct g && closed g &&
                                     Some? (project_bin g RC) && Some? (project_bin g RA) &&
                                     Some? (project_bin g RJ) && Some? (project_bin g RD))) =
  conserv g RC; conserv g RA; conserv g RJ; conserv g RD

(* ------------------------------------------------------------------ *)
(* Non-vacuity sanity checks: the metatheorem preconditions ARE         *)
(* satisfiable (so the lemmas are not vacuously true), and              *)
(* fidelity_complete actually fires on a concrete 3-way (n-ary) choice. *)
(* ------------------------------------------------------------------ *)
let _ex_msg () : Lemma (wellformed (GMsg RC RA "m" GEnd) /\ head_ok (GMsg RC RA "m" GEnd)) = ()
let _ex_ch ()  : Lemma (let g = GCh RC RA [("l1", GEnd); ("l2", GEnd); ("l3", GEnd)] in
                        wellformed g /\ head_ok g) = ()
let _fid_demo () : Lemma
  (let g = GCh RC RA [("l1", GEnd); ("l2", GEnd); ("l3", GEnd)] in
   exists (c':config). cstep (init_config g) (RC, RA, "l1") c') =
  let opts = [("l1", GEnd); ("l2", GEnd); ("l3", GEnd)] in
  let g = GCh RC RA opts in
  fidelity_complete g (RC, RA, "l1") GEnd (GS_Ch RC RA opts 0)

// non-vacuity for conservativity: the binary fragment is inhabited and `conserv`
// fires on a real third-role merge (RJ ∉ {RC,RA}), giving a defined projection.
let _conserv_demo () : Lemma
  (let g = GCh RC RA [("l1", GEnd); ("l2", GEnd)] in
   is_bin_frag g /\ project g RJ == project_bin g RJ /\ Some? (project g RJ)) =
  conserv (GCh RC RA [("l1", GEnd); ("l2", GEnd)]) RJ

(* ============================================================================
   W19-A — FULL SUBJECT REDUCTION incl. recursion (GS_Rec). Assembles subst_g_wf
   from the proven unfold lemmas (a') no_self, (b') contractive, gdistinct, closed,
   (c') projectability; then `preservation_full` covers all three gstep cases.
   ============================================================================ *)

// cl is monotone in the lexical set: a larger allowed-set is a weaker constraint.
let rec cl_mono (l1 l2:list tvar) (g:gtyp)
  : Lemma (requires (forall (v:tvar). L.mem v l1 ==> L.mem v l2) /\ cl l1 g)
          (ensures  cl l2 g) (decreases g)
  = match g with
    | GEnd | GVar _ -> ()
    | GRec s g1     -> cl_mono (s :: l1) (s :: l2) g1
    | GMsg _ _ _ k  -> cl_mono l1 l2 k
    | GCh _ _ opts  -> cl_mono_opts l1 l2 opts
and cl_mono_opts (l1 l2:list tvar) (opts:list (label & gtyp))
  : Lemma (requires (forall (v:tvar). L.mem v l1 ==> L.mem v l2) /\ cl_opts l1 opts)
          (ensures  cl_opts l2 opts) (decreases opts)
  = match opts with
    | [] -> ()
    | (_, g) :: t -> cl_mono l1 l2 g; cl_mono_opts l1 l2 t

// substituting a CLOSED `r` for `t` preserves closedness at the same lexical set.
let rec cl_subst (g:gtyp) (t:tvar) (r:gtyp) (lex:list tvar)
  : Lemma (requires cl (t :: lex) g /\ closed r) (ensures cl lex (subst_g g t r)) (decreases g)
  = match g with
    | GEnd          -> ()
    | GVar s        -> if s = t then cl_mono [] lex r else ()
    | GRec s g1     -> if s = t then cl_mono (t :: t :: lex) (t :: lex) g1
                       else (cl_mono (s :: t :: lex) (t :: s :: lex) g1; cl_subst g1 t r (s :: lex))
    | GMsg _ _ _ k  -> cl_subst k t r lex
    | GCh _ _ opts  -> cl_subst_opts opts t r lex
and cl_subst_opts (opts:list (label & gtyp)) (t:tvar) (r:gtyp) (lex:list tvar)
  : Lemma (requires cl_opts (t :: lex) opts /\ closed r)
          (ensures  cl_opts lex (subst_opts opts t r)) (decreases opts)
  = match opts with
    | [] -> ()
    | (_, g) :: tl -> cl_subst g t r lex; cl_subst_opts tl t r lex

let closed_subst (t:tvar) (g0:gtyp)
  : Lemma (requires closed (GRec t g0)) (ensures closed (subst_g g0 t (GRec t g0)))
  = cl_subst g0 t (GRec t g0) []

// substitution preserves the choice-label sequence, hence gdistinct.
let rec gsubst_keys (opts:list (label & gtyp)) (t:tvar) (r:gtyp)
  : Lemma (ensures gkeys (subst_opts opts t r) == gkeys opts) (decreases opts)
  = match opts with | [] -> () | (_, _) :: tl -> gsubst_keys tl t r

let rec gdistinct_subst (g:gtyp) (t:tvar) (r:gtyp)
  : Lemma (requires gdistinct g /\ gdistinct r) (ensures gdistinct (subst_g g t r)) (decreases g)
  = match g with
    | GEnd | GVar _ -> ()
    | GRec s g1     -> if s = t then () else gdistinct_subst g1 t r
    | GMsg _ _ _ k  -> gdistinct_subst k t r
    | GCh _ _ opts  -> gsubst_keys opts t r; gdistinct_subst_opts opts t r
and gdistinct_subst_opts (opts:list (label & gtyp)) (t:tvar) (r:gtyp)
  : Lemma (requires gdistinct_opts opts /\ gdistinct r)
          (ensures  gdistinct_opts (subst_opts opts t r)) (decreases opts)
  = match opts with
    | [] -> ()
    | (_, g) :: tl -> gdistinct_subst g t r; gdistinct_subst_opts tl t r

// subst_g_wf: unfolding a well-formed recursion preserves well-formedness (all four conjuncts + 4 roles).
let subst_g_wf (t:tvar) (g0:gtyp)
  : Lemma (requires wellformed (GRec t g0))
          (ensures  wellformed (subst_g g0 t (GRec t g0)))
  = unfold_contractive t g0;
    unfold_no_self t g0;
    gdistinct_subst g0 t (GRec t g0);
    closed_subst t g0;
    unfold_projectable t g0 RC; unfold_projectable t g0 RA;
    unfold_projectable t g0 RJ; unfold_projectable t g0 RD

// FULL subject reduction: well-formedness is preserved by EVERY global step, including GS_Rec.
let rec preservation_full (g:gtyp) (e:event) (g':gtyp) (d:gstep g e g')
  : Lemma (requires wellformed g) (ensures wellformed g') (decreases d)
  = match d with
    | GS_Msg p q a k -> ()
    | GS_Ch p q opts i ->
        contractive_opts_index opts i; no_self_opts_index opts i;
        gdistinct_opts_index opts i; cl_opts_index [] opts i;
        project_opts_index opts RC i; project_opts_index opts RA i;
        project_opts_index opts RJ i; project_opts_index opts RD i
    | GS_Rec t g0 ev g'' d' ->
        subst_g_wf t g0;
        preservation_full (subst_g g0 t (GRec t g0)) ev g'' d'
