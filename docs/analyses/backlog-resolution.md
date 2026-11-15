# Backlog resolution (autonomous) — plan, options, synthesis

Resolving the real backlog (tracked tensions + CEP hygiene + compile-out engineering) after W18.
Method per item: enumerate options **a/b/…**, compare, synthesize the applied solution, verify, commit.
Non-blocking research (W19) and inherent-undecidability items (W16/W17) are documented, not forced.

| Item | Kind | Plan | Status |
|------|------|------|--------|
| C. status hygiene | doc/spec | W11 drift → reflect SP-2; promote stable CEPs; reconcile CEP-13 | … |
| B1. plugin-ize core-path checks | refactor | feature checks as a profile-keyed registry; core path imports no outer ring | … |
| B2. packaging extras | packaging | `full` extra; ring-0 core-import test; honest note on physical split | … |
| A-W8. provenance σ | cleanup | wire or remove the unused field | … |
| A-W9. concurrency ≥4 | assess | deepen vs document scope | … |
| W16/W17 | inherent | confirm honest mitigation wording (undecidable / human-attested) | … |
| W19 | research | keep tracked, non-blocking (automata route) | n/a |
| D. GitHub push | user action | prepare commands; user executes | n/a |

---

## C — status hygiene

### Options
- **a. Leave as-is.** Honest-but-stale (W11 says "mitigated" though SP-2 closed it in-fragment; CEPs Draft).
- **b. Update statuses to match the proven reality**, carefully and per-item (don't over-claim).

### Synthesis (applied)
b, conservatively: W11 → "resolved in-fragment (SP-2) + bridge for the rest"; CEP-0003 (levels, all 6
steps shipped) and CEP-0009 (extraction authoritative, implemented+tested) → **Accepted**; CEP-0004
(integrity *case*, an evolving argument) and CEP-0054 (proof loop; targets still-open W19) stay
**Draft** (honest — they are living/aspirational). CEP-13 (LH-C-004) note: SP-2 discharges it
in-fragment; keep Deferred with a pointer (the general cross-language unification remains future).

(attempts/results recorded below)

## B1 — plugin-ize the core-path feature checks
### Options
- **a. Lazy imports only** (today): the imports are function-local, but they still fire on the core
  check path, so a `core` build cannot omit `spike_pipeline`/`semantics_async`.
- **b. Feature-check registry**: each feature registers a checker keyed by its profile; `check_protocol`
  runs only checks at/below the active profile (default: all). A `core` run never imports the outer
  modules. Removes the two deferred layering edges; lets audit `[5b]` tighten.
### Synthesis: (tbd by implementation)

## B2 — packaging extras + core-import test
### Options
- **a. Full physical split** into separate distributions/subpackages — invasive, risks the tree.
- **b. Scoped**: declare `[project.optional-dependencies] full=…`; add a test that the ring-0 modules
  import with no ring-1/2 import; document the remaining physical split as future.
### Synthesis: b (honest, low-risk increment; physical wheels deferred).

## A — W8 / W9
### W8 (σ provenance unused)
- **a. Wire it** into the checker (real feature) — scope creep, no current consumer.
- **b. Remove the dead field** (economy of mechanism; smaller surface) or mark intentionally-reserved.
### W9 (concurrency soundness ≥4 roles)
- **a. Deepen the F\* proof** (general n-role confluence) — sizeable.
- **b. Document the scope** (canonical pair proven + by-test general) honestly; defer the generalization.
### Synthesis (applied)
- **W8 → b/c hybrid (intentionally reserved).** σ is a documented field of the §3 capability tuple
  (LH-F-005), not dead code; wiring an unmotivated provenance check would be scope creep, deleting a
  spec element is wrong. Resolution: annotate it RESERVED in `core.py` and mark W8 RESOLVED
  (intentionally reserved). Economy of mechanism — no unmotivated gate.
- **W9 → b (documented, deferred).** The F\* diamond/permutation is proven for the canonical
  independent 4-role pair (`cgstep`/`diamond_indep`/`cstep_diamond`) and general n-role correspondence
  is by-test (`LH-Q-001d`). General n-role confluence in F\* is a sizeable proof with low marginal
  value (sync head-step fidelity already covers the guarantees) — kept as an honest `prototype`
  tension, a candidate for the SP-5 loop alongside W19, not grinded here.

## Status (final)
C ✅ · B1 ✅ · B2 ✅ (and caught/fixed a deeper kernel→spike_judge→oracle leak) · W8 ✅ ·
W9 ◐ documented/deferred · W16/W17 ✅ honest mitigation (inherent undecidability / human attestation) ·
W19 ◐ research, non-blocking · D ⏳ user action (GitHub push).
