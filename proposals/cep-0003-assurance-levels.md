---
cep: 3
title: CASL Assurance Levels — a layered, opt-in, integrity-graded core
status: Accepted
type: Process
created: 2026-06-22
version: 0.1
authors: [Martin]
---

# CEP-0003 — CASL Assurance Levels (layered, opt-in, integrity-graded core)

## Summary

Organize the CASL core as concentric **levels** (an onion): an innermost, smallest,
maximally-verified kernel that is always on, surrounded by **opt-in** capability rings that
*never weaken* the inner levels and can be **switched off** (down to compiled-out) when a
deployment does not want to carry their code or assurance cost. Capability (*what constructs*)
and assurance (*how strongly verified*) are treated as **two orthogonal axes**.

This dissolves the A-vs-B question: **B (binary core) is Level 0; A (n-ary choice) is a
Level-1 opt-in feature.** Both ship, layered.

## Motivation and normative grounding

Graded integrity/assurance levels are standard practice, and the layering idea has a direct
normative home:

- **ISO/IEC/IEEE 15026-3 — System Integrity Levels** (the primary anchor): defines *integrity
  levels*, each with *integrity-level requirements* that must be satisfied to claim the level,
  supported by an **assurance case** (claims → argument → evidence). CASL's per-level proof
  obligations and the living audit *are* such an assurance case.
- **IEC 61508 (SIL 1–4)** and **ISO 26262 (ASIL A–D)**: graded safety integrity. Key lesson:
  there is **no automatic cross-level mapping** — a SIL-3 element cannot be claimed ASIL-D
  without *separate evidence*. ⇒ each CASL level needs its *own* proof; a lower-level proof does
  not silently transfer (our conservativity obligation, below).
- **DO-178C (DAL A–E)** and **ISO/IEC 15408 / Common Criteria (EAL 1–7)**: graded design
  assurance (safety) and evaluation assurance (security / *justified trust*) — two different
  axes, mirroring our capability vs. assurance split.
- **ISO/IEC 25010** (product quality: security incl. integrity, reliability, maintainability,
  safety): the qualities each CASL level is meant to *raise* as one moves inward.
- CASL's existing RE norm base — **ISO/IEC/IEEE 29148** (requirements), **ISO/IEC/IEEE 12207**
  (lifecycle), **DIN 69901**, **VDI/VDE 3694** (Lastenheft/Pflichtenheft) — already documented
  in `docs/language-spec.md` and checked by `kernel.norms`.

PL analogues that supply the *mechanism*: **Racket `#lang` levels** (BSL ⊂ ISL ⊂ ASL — named,
cumulative, per-unit, additive); **Safe Haskell** (`Safe`/`Trustworthy`/`Unsafe`, inferred,
`Trustworthy` = author attestation, `safe` imports propagate trust); **Cargo `#[cfg(feature)]`**
+ **seL4** (build-time feature selection → genuinely smaller TCB); the **F\* effect lattice**
(`Tot ⊆ Div ⊆ …`) and **Agda `--safe`** (a no-axioms floor); and the **gradual guarantee**
(Siek et al.) — the type-world name for "turning a feature on/off does not change the verdict
of programs that don't use it."

## Specification

### Two axes

- **Capability** — which constructs a protocol may use: `GMsg`, recursion, binary choice
  (Level 0); n-ary choice, async (Level 1); pipeline / `oracle` / `verified` nodes (Level 2).
- **Assurance grade** — how strongly a feature is backed: **G0** F\*-proven (0 admits) ·
  **G1** bounded model-checked (exhaustive ≤ k) · **G2** by-test / property-checked ·
  **G3** human-attested (Trustworthy). A feature carries a grade; a configuration's effective
  grade is the **minimum** over its enabled features (à la 61508 "weakest link").

### Profiles (presets) over a feature lattice

Named, cumulative profiles for ergonomics (Racket), over an additive feature set (Cargo):

| Profile | adds | assurance (min) |
|---|---|:--:|
| `core` (always on) | GMsg, recursion, **binary** choice, projection + safe merge, head-step fidelity/deadlock + W9 | **G0** |
| `extended` | + **n-ary choice** (G0) + **async** (G1) | G1 |
| `advisory` | + pipeline / `oracle` / `verified` nodes | G3 (attested) |

The checker **infers** the minimum profile a protocol needs from the constructs it uses
(Safe Haskell). Individual features may be toggled to override a profile (e.g. n-ary on, async
off ⇒ stays G0).

### Declaration and enforcement (deny-by-default)

- **Per protocol:** a header marker (generalizing the existing `async [k N];`) declares the
  features used; absent ⇒ inferred.
- **Per project / per invocation:** a ceiling — project config default **and** a CLI override
  (`casl check --profile core` / `--assurance G0`), the invocation overriding the project (like
  compiler flags). A protocol using a feature **above** the ceiling, or **below** the required
  assurance floor, is **rejected** (deny-by-default; monotone — Bell–LaPadula).
- **Two enforcement stages:** runtime ceiling (default) **and** a build profile that
  *compiles out* higher levels (a `core` build does not contain the n-ary/async modules) for a
  genuinely smaller TCB (seL4 / Cargo `#[cfg]`).

### The soundness law — conservative extension (machine-checked)

Each outer feature must be a **conservative extension**: a protocol that does *not* use feature
F gets the **identical verdict** whether F is enabled or not (ISO 15026-3 "the level claim rests
on its own evidence"; the *gradual guarantee*). Where feasible this is a machine-checked F\*
obligation — e.g. **"the n-ary core restricted to binary choices ≡ the binary core."** This is
the actual hardening of the onion: switching a ring on cannot perturb the proven kernel, and
switching it off cannot lose a kernel guarantee. `async` already satisfies this (without the
marker, nothing changes).

### Integration with what exists

- `async [k N]` marker → the first instance of a per-protocol feature declaration.
- `verified` / `oracle` nodes + Tier-3 attestation → `Trustworthy` (G3): trust is *attested*,
  not machine-granted.
- The monotone IDE gate ("agents may veto, never vouch") + deny-by-default → the lattice's
  monotonicity.
- The CEP system → each feature is a CEP carrying `level` + assurance grade; the living audit
  enforces the level's proven status (and, per this CEP, the conservativity obligations).

## How A and B map

`core` = the binary, synchronous, F\*-proven kernel = **Variant B** (smallest TCB, G0).
`extended` = + **Variant A**'s n-ary choice (G0) + async (G1). Merge B as the floor; bring A's
n-ary in as the first `extended` feature, gated and proven-conservative over `core`.

## Migration / implementation plan

1. **Taxonomy + gate (decision-independent):** `casl/levels.py` — feature→(profile, assurance);
   `features_used(proto)`; `profile_ok(proto, ceiling)` deny-by-default; tests; audit visibility.
   Works today over existing features (async, oracle, verified) without needing A or B merged.
2. **Surface + CLI:** parse a `level/profile` marker; `casl check --profile/--assurance`;
   project-config default.
3. **Land the cores as levels:** merge B as `core`; add A's n-ary as `extended` (opt-in).
4. **Conservativity proof (F\*):** `nary↾binary ≡ binary` (and per-feature as added).
5. **Build profiles:** a `core` build that compiles out outer rings (minimal TCB).
6. **CEPs per feature** with `level` + assurance, audit-enforced.

## Implementation status

- **Step 1 ✓** `src/casl/levels.py` + `tests/test_levels.py`.
- **Step 2 ✓** `casl check --profile/--assurance` ceiling + `$CASL_PROFILE`/`$CASL_ASSURANCE`
  config default, per-invocation override; `tests/test_check_levels.py`. (v0.18.0)
- **Step 3 ✓** n-ary core landed; binary is the `core` fragment, n-ary the first `extended`
  feature (v0.18.0).
- **Step 4 ✓** conservativity **proven** in F\*: `is_bin_frag` + an independent binary projector
  `project_bin`, with `conserv : project g r == project_bin g r` on the binary fragment and
  corollary `conserv_wf` (same well-formedness verdict). 0 admits. Enabling `extended` cannot
  change a `core` protocol's verdict.
- **Step 5 ✓ (precondition) / ◐ (physical split deferred)** `src/casl/profiles.py` assigns each
  module a ring (0 core / 1 extended / 2 advisory) and an AST guard (`layering_violations`)
  proves **no module-level inner→outer import** — the precondition that makes compiling out an
  outer ring sound; the living audit (`[5b]`) fails on any violation. `tcb_modules(profile)`
  reports the per-profile TCB (core = 24 modules). **Core path cleaned (backlog B1):** the two feature
  checks that used to load on every check (`spike_pipeline`, `semantics_async`) are now imported
  *dynamically* only when the protocol actually uses oracle/verified/async — so `check_protocol` has
  zero static dependency on an outer-ring module (regression-tested in `tests/test_profiles.py`). The
  only remaining deferred edges are the advisory CLI *command* handlers
  (`check→{oracle,synth,ide,run}` in `cmd_run`/`cmd_synth`/`cmd_ide`), which correctly load advisory
  code only when you invoke that command. Remaining: ship separate `casl-core`/`casl[full]` wheels
  (packaging only — the dependency direction is now sound).
- **Step 6** per-feature CEPs — in progress.

## Open points (to confirm before step 2+)

- Assurance floor location: project-config default **and** per-invocation override (recommended) —
  confirm precedence.
- How far the **F\* effect lattice** should *natively* enforce capability levels vs. the
  Python checker + CEP audit doing enforcement (recommended: checker + audit now; F\* effects
  as a later, deeper option).
- Profile boundaries (is `async` `extended` or its own G1 ring distinct from n-ary's G0?).
