# CASL — L3 Formal Specification (Core)

**Version:** `0.1` (begun) · **Date:** 2026-06-15 · **Reference:** `CASL.md` v0.1.8, `prototype/{semantics,metatheory,spike_proj_mpst}.py`
**Status:** Operational semantics + metatheory as **proof-by-test** (randomized). Mechanized proofs (Lean 4/F*) → Direction C / `TBD-004`.
**Decision:** MPST as the normative backbone, MSC as a cross-check (`TBD-003` closed; equivalence hardened, `W2`).

---

## 1. Grammar

**Global type** (choreography):

```
G ::= p→q : l(τ̄) . G            communication
    | p→q : { lᵢ(τ̄ᵢ) : Gᵢ }     choice (p decides, sends label to q)
    | μt. G                       recursion (contractive: head of G is communication/choice)
    | t                           recursion variable
    | end
```

**Local (endpoint) type** = session type of a role:

```
L ::= q!l(τ̄) . L                 send
    | p?l(τ̄) . L                 receive
    | q⊕{ lᵢ : Lᵢ }              internal choice (select & send)
    | p&{ lᵢ : Lᵢ }              external choice (branch on label)
    | μt. L | t | end
```

Data level additionally: contracts `[φ]` (refinements, §`LH-Q-004`), capabilities `(tool,params,scope,ttl,σ)` (§`LH-F-005`), crash continuation `on_crash` (§`LH-F-007a`), ranking measure on `μ` (§`LH-Q-009`).

---

## 2. Projection  ⌊G⌋ᵣ  (`spike_proj_mpst.project`)

```
⌊p→q:l.G⌋ᵣ = q!l.⌊G⌋ᵣ           if r=p
           = p?l.⌊G⌋ᵣ           if r=q
           = ⌊G⌋ᵣ               otherwise

⌊p→q:{lᵢ:Gᵢ}⌋ᵣ = q⊕{lᵢ:⌊Gᵢ⌋ᵣ}   if r=p
              = p&{lᵢ:⌊Gᵢ⌋ᵣ}   if r=q
              = ⊔ᵢ ⌊Gᵢ⌋ᵣ        otherwise (merge)

⌊μt.G⌋ᵣ = μt.⌊G⌋ᵣ      ⌊t⌋ᵣ = t      ⌊end⌋ᵣ = end
```

**Merge ⊔** (hardened, `W2`): `L ⊔ L = L`; receives/external choices from the **same** partner unite their labels, **common** labels are merged recursively; everything else (e.g. a send at the divergence point) is **not** mergeable ⇒ not projectable. This means: a third-role branch is only admissible if the role can locally distinguish the branch at a receive.

---

## 3. Operational Semantics (synchronous, `semantics.py`)

**Global reduction**  G —(p→q:l)→ G′ :

```
(p→q:l.G) —(p→q:l)→ G          (p→q:{lᵢ:Gᵢ}) —(p→q:lⱼ)→ Gⱼ          μt.G ≡ G[μt.G/t]
```

**Configuration** Γ = { r ↦ Lᵣ }, initially Γ₀(G) = { r ↦ ⌊G⌋ᵣ }.

**Configuration reduction** (rendezvous):

```
   Lₚ ⊐ q!l.L′ₚ        L_q ⊐ p?l.L′_q
  ─────────────────────────────────────────   (⊐ = after μ-unfolding)
   Γ —(p→q:l)→ Γ[ p↦L′ₚ , q↦L′_q ]
```

(internal/external choice analogously via the chosen label).

---

## 4. Metatheorems (`metatheory.py`, proof-by-test)

For every **well-formed** (projectable) type G, checked at **every reachable** state (BFS, re-projection):

- **T1 — Operational correspondence / session fidelity** (`LH-Q-001a/c`): the events enabled by G agree with those enabled by Γ(G) — *soundness* (Γ does nothing extra) and *completeness* (Γ does everything). It follows that endpoint execution follows the choreography exactly.
- **T2 — Deadlock freedom / progress** (`LH-Q-001b`): a non-terminal reachable Γ always has a step.

**Evidence (as of v0.1.8):** 0 violations over the canonical examples (`G_OK`, `G_OK_TERM`, `G_OK_CRASH`) and 250 randomly generated well-formed protocols. *This does not replace a mechanized proof* — it is randomized falsification; the mechanization in Lean 4/F* is Direction C.

---

## 5. Open for L3 (next steps)

- Pull the data level into the semantics (contracts/promises as values; currently only communication structure).
- Model crash reduction (`on_crash`) operationally (so far a static tolerance check).
- Formulate subject reduction as *typability* (instead of only event correspondence) — Γ(G) is typed by G; after a step typed by G′ (up to subtyping/merge).
- Surface syntax (`TBD-006`) → parser → these cores.
- Mechanization of the metatheorems (Direction C).
```
