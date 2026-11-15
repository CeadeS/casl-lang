# CASL project structure & module organization — alternatives, discussion, synthesis

**Date:** 2026-06-24 · **Status:** design analysis (feeds the artifact-trust CEPs 0057+). Anchored in
`docs/artifact-trust-requirements.md` (P10: accountability + containment), CEP-0003 (assurance
G0–G3), CEP-0004 (integrity case), CEP-0055/0056 (sound core + completeness ratchet), and the
standing invariants: **deny-by-default**, **agents may veto, never vouch**, **traceability is
authority**, **humans sign as humans**, **dependencies are an accepted, contained burden**.

This answers three open questions and commits to a design, *without weakening the verified core*
(the F\* core, the `casl check` gates, and the assurance ladder are untouched; everything here is the
governance/IDE layer — rings 1–2 in `profiles.py`).

---

## The three questions

1. **How should modules/artifacts be organized in CASL?**
2. **Where is which program, and how is it assembled so it is human-verifiable & readable *and*
   LLM-writable?** ("LLMs may write a lot, as long as it is easy to read.")
3. **What structure should a CASL *project* have, and how is it organized?**

## The governing constraint (what "optimal" means here)

A design is optimal for CASL iff it maximises **human verifiability per unit of reading** while
maximising **LLM write-throughput** — *and* every byte we own stays accountable (traced + blamed +
signed) and every byte we don't own stays contained (caged + pinned). Concretely:

- **Locality of reasoning.** A human should verify the *system* by reading a small, dense, declarative
  layer — never by reading the (large, LLM-written) bodies. The reviewer reads **seams and obligations**;
  the bodies are black boxes behind them.
- **One unit = one obligation = one signature.** Accountability must attach to a *nameable* thing.
- **Ownership splits the world.** First-party (we committed it) ⇒ traced/blamed/signed. Dependency
  (we imported it) ⇒ pinned/owned-as-burden/caged. The line is *ownership*, not who typed the chars.

These rule out any design where verification requires reading bodies, or where an artifact has nowhere
to carry its obligation.

---

## Q1 — Module / artifact organization

**A. Flat / inline.** Encode artifacts inside the `.casl` choreography (bodies inline). *Rejected:*
conflates spec with implementation, bodies cannot be separately owned/signed/traced, choreography
becomes unreadable, and an LLM editing one body churns the whole file.

**B. Spec/impl split.** The `.casl` choreography names artifacts and wires them; each artifact body is a
separate source file (any language) with a declared interface and an obligation record. *Strong:* the
seam (human-owned authority) is separated from the body (LLM-written, contained); matches the on-disk
picture in `artifact-trust-requirements.md` §1.3.

**C. Box-as-directory.** Each artifact is a self-contained directory: `interface.casl` + body + obligation
+ contract-tests + attestation. *Strong on encapsulation* (everything about one box in one place) but
heavy: directory explosion, and the choreography that wires boxes is still separate.

**Synthesis — B with C's unit discipline ("the box").** An **artifact** is a first-class *named unit*
with four faces, but **not** a directory — to keep locality without explosion:

1. **Seam** — a typed interface `(args) -> T | ()` + pre/post contract, declared in the choreography
   (`.casl`). *Human-owned authority.* (LH-F-012)
2. **Body** — one source file per artifact (`artifacts/<name>.<ext>`). *LLM-writable; contained.*
3. **Obligation** — one record per artifact (`attestations/<name>.json`): kind/provenance, required
   grade, trace regime, content-hash + human signature. (LH-F-013, LH-Q-016/017/018, LH-P-009)
4. **Tests** (optional) — contract/property tests pinned to the seam.

> **The rule: one artifact ⇒ one body file ⇒ one obligation record ⇒ one signature.** This is the
> locality that makes an LLM-written 800-line body *reviewable*: you review its **seam + obligation +
> the diff + the prompt that produced it** (LH-G-005), not its 800 lines. The body may be large; the
> *reviewed surface* is bounded and constant.

`oracle` and `verified` stop being ad-hoc booleans on a message and become two artifact **kinds**
(LH-F-013), unifying the producer model: every value is "produced by an artifact at some provenance
and grade."

---

## Q2 — Project structure / layout

**A. Convention-only.** A documented directory layout, no enforcement. *Rejected:* drifts; obligations
that aren't materialised aren't checked (contradicts P0/P9 inspectability).

**B. Manifest-driven.** A project manifest (`casl.toml`) declares the project, its artifacts (→
requirements → grades → trace regime), its dependencies (pinned), and the recorded signing identity.
`casl init` scaffolds it; the Tier-0 gate reads it. *Strong:* enforceable, queryable, the single place
the obligation ledger lives.

**C. Requirement-rooted.** Organize the tree *around requirements* — each requirement owns its realizing
artifacts. *Most philosophy-aligned* (requirement = authority) but rigid on disk (one artifact serving
two requirements is awkward) and unfamiliar.

**Synthesis — B as the spine, C as a *view*.** The on-disk layout is manifest-driven (B); the
requirement-centrality of C is expressed *in the manifest* (every artifact links its requirement) and
rendered as the **cockpit/ledger view** (requirement → artifacts → grade → signer → traced?). You get C's
authority-rooted inspectability without C's rigid tree. Canonical layout:

```
myproject/
  casl.toml                 # MANIFEST: name, version, [attest] pubkey, [deps], [[artifact]] → requirement/grade/trace
  requirements/             # project requirements (LH-style or local) — human-owned AUTHORITY
  casl/                     # choreographies (*.casl) — the seams + wiring, read top-to-bottom by a human
  artifacts/                # artifact BODIES (one file per artifact; LLM-written, contained)
  attestations/             # one obligation+signature record per artifact (content-hash + human sig)
  deps.lock                 # dependency BURDEN ledger (pinned version+hash + accepted-by human)
  .casl/attest.pub          # recorded human signing identity (CODEOWNERS-protected)
  tests/
```

Reading order for a human reviewer (top of the verifiability pyramid → down):
`casl.toml` (what exists, at what grade) → `requirements/` (why) → `casl/` (how it is wired) →
per-artifact: seam + obligation + diff + prompt. **A reviewer never has to open `artifacts/` bodies to
verify the system's *shape*** — only to spot-check a body they choose to.

First-party = everything under the project except `deps.lock`'s targets; it is all line-traced
(LH-P-006/007). Dependencies live only as pinned entries in `deps.lock` (LH-Q-020) — never line-traced.

---

## Q3 — Human-verifiable & readable AND LLM-writable (the assembly)

The two goals are usually in tension; CASL resolves it by **stratifying by who reads vs. who writes**:

| layer | who writes | who reads/verifies | size | accountability |
|---|---|---|---|---|
| manifest + requirements | human | human | tiny | authority |
| choreography (seams + wiring) | human (LLM may draft, human owns) | human | small, declarative | `casl check` (proven gates) |
| artifact bodies | **LLM** (mostly) | **machine + spot human** | large OK | traced + caged + signed |
| dependencies | nobody (imported) | machine (pin) | huge | burden + cage |

The mechanisms that make a large LLM-written body *easy to read* (the user's actual ask):

1. **The seam is the contract you read, not the body.** A human reads `(args) -> T` + pre/post; the
   gate enforces the seam even though it cannot prove the body (P10).
2. **One artifact = one file.** No cross-cutting churn; an LLM edit is localized and its diff is the
   review surface. Blame resolves any line to a requirement + a human + `human|llm` (LH-P-007).
3. **The choreography is declarative wiring**, not imperative glue — it reads like a table of contents.
4. **The cockpit renders the whole project as one inspectable table** — the human verifies coverage and
   grades at a glance, then drills only where they choose.
5. **Deny-by-default at Tier 0** means *reading = checking the seam + obligations*; an unmet obligation
   blocks regardless of how the body looks, so the human's reading effort is spent on the right layer.

> Net: LLMs may write as much body as they like; readability comes from **bounding the reviewed surface
> to the seam + obligation + diff**, and from **one-artifact-one-file locality**, not from shrinking the
> body. This is exactly "LLMs can write a lot, as long as it is easy to read."

---

## Chosen design (commitment)

- **Artifact** = first-class named unit: seam (in `.casl`) + body (`artifacts/<name>.<ext>`) +
  obligation (`attestations/<name>.json`). One artifact ⇒ one body ⇒ one obligation ⇒ one signature.
- **Project** = manifest-driven (`casl.toml`) with the canonical layout above; requirement-centrality is
  a *view*, not a rigid tree. `casl init` scaffolds; `casl project` introspects; the Tier-0 gate enforces.
- **Ownership split** = first-party (traced/blamed/signed) vs. dependency (`deps.lock`: pinned + owned
  burden + caged). LLM-written-and-committed code is **first-party**.
- **Assembly** = stratified read/write layers; the human verifies the thin authoritative layer, the LLM
  fills the thick contained layer, the gate binds them deny-by-default.

This realizes `artifact-trust-requirements.md` groups A–E and keeps the verified core untouched:
the new machinery is checker/IDE-layer (rings 1–2), and the F\* core / `wellformed` / assurance ladder
are unchanged. The completeness ratchet (CEP-0056) and the trust budget (CEP-0003) already give the
"disclosed residual" view; this design gives that residual a *home* (the per-artifact obligation record).

## Implementation plan (this branch, each step green)

1. `project.py` — manifest model (`casl.toml`) + canonical layout + `casl init`/`casl project`.
2. artifact unit + provenance kind (LH-F-012/013) in the manifest + model + gate.
3. `deps.lock` burden ledger (LH-Q-020): pin + accepted-by + deny unpinned.
4. line traceability + author/provenance/blame (LH-P-006/007) over git.
5. human-identity attestation verify + obligation gate (LH-Q-016/017/018, LH-G-006) + monotone grade.
6. CEPs 0057+ + `spec.REQS` round-trip + audit gates + tests; verify-all; PR.
