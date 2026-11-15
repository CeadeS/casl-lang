module W19ProjSubst
(* ============================================================================================
   W19-A (c') — projectability is preserved by unfolding `GRec`.  *** VERIFIES AT ZERO ADMITS. ***
   The top-level result `unfold_projectable` is fully machine-checked: for a distinct-label
   (`gdistinct`) global type, Some? (project (GRec t g0) r) ==> Some? (project (unfold) r).
   (Kept as a standalone module so the core CASL.fst is untouched while this is being integrated;
   the admits gate scans only CASL.fst.)

   HOW THE BLOCKER FELL (see docs/analyses/w19-projection-completeness.md §8c):
   - Scalas & Yoshida, "Less is More" POPL'19 — reason in the SUCCESS world, not by raw syntactic
     equality: for DEFINEDNESS we need only `merge l1 l2 = Some m ==> merge (subst..) = Some (subst m)`,
     and the false `LVar t`/`LRec t c` collapse corner (which had merge = None) is excluded.
   - The combinatorial crux `subst_opts_inj` (substitution injective on the success world) is now
     PROVEN via `merge_opts_lookup`: a characterisation of `merge_opts_f` stated about ASSOC LOOKUPS
     (which transform predictably under prepend/replace), so the induction generalises over the
     rewritten accumulator — exactly where the value-threading inductions failed. Distinct labels
     (`nodup`/`ldistinct`/`gdistinct`) is the natural side condition, preserved by merge & projection.
   - Tirore-Bengtson-Carbone ITP'23 (coinductive) and Scalas et al. iso-recursive (arXiv 2501.17778)
     were the documented fallbacks; not needed.
   ============================================================================================ *)
open CASL
module L = FStar.List.Tot
open FStar.Mul

(* ============================================================================
   W19-A (c'): projectability preserved under unfolding — Strategy A.
   Insight from the literature (Scalas et al. iso-recursive; the success-world principle):
   for DEFINEDNESS we need only the EASY direction of merge/subst commutation,
       merge l1 l2 = Some m  ==>  merge (subst l1)(subst l2) = Some (subst m),
   which holds because the hypothesis pins us to the success world where the false
   `LVar t` / `LRec t c` collapse corner (which had merge = None) cannot occur.
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
let rec keys (os:list (label & ltyp)) : list label =
  match os with | [] -> [] | (a, _) :: t -> a :: keys t

let rec nodup (ls:list label) : bool =
  match ls with | [] -> true | a :: t -> not (L.mem a t) && nodup t

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

// gdistinct: every GCh has distinct branch labels (the well-formedness side condition).
let rec gkeys (opts:list (label & gtyp)) : list label =
  match opts with | [] -> [] | (a, _) :: t -> a :: gkeys t
let rec gdistinct (g:gtyp) : Tot bool (decreases g) =
  match g with
  | GEnd | GVar _ -> true
  | GRec _ g1     -> gdistinct g1
  | GMsg _ _ _ k  -> gdistinct k
  | GCh _ _ opts  -> nodup (gkeys opts) && gdistinct_opts opts
and gdistinct_opts (opts:list (label & gtyp)) : Tot bool (decreases opts) =
  match opts with | [] -> true | (_, g) :: t -> gdistinct g && gdistinct_opts t

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

