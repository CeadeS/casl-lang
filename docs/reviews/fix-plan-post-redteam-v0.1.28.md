# CASL Fix Plan — after RedTeam Review v0.1.28

**Status:** `main` @ v0.6.3 · PR #19 (`feat/runtime-approval` — C3 runtime approval + residual-risk tracking) built & verified, **waiting for `approved`**.
**Source:** `docs/reviews/redteam-review-v0.1.28.md` (re-test) + open items from `docs/reviews/redteam-review-v0.1.27.md`.
**Guiding principle:** ordering by *severity × shell × dependency*. Every phase keeps the discipline: attack spec in `examples/attacks/`, audit green, prose honest, tension `W*` → resolved.

## Finding → Fix → PR

| Finding | Severity | Shell | Fix (core) | PR | Tension |
|---|---|---|---|---|---|
| **R-H1** Effect classifier leaky/spoofable (scope substring) | high (NEW) | 1 (effect keystone) | structured, validated `mode`/`effect` capability field, default-effectful; no substring | **#20** | W14 |
| **R-N1** `--approve` blanket, not bound to the disclosed gate message | minor | 1 (gate meaning) | bind `on_approval` to a per-gate prompt (shows message + concrete action); bare `--approve` demo only | **#21** | W15 |
| **H3** Capability is a lint, not runtime confinement | medium | 1 (effect runtime) | real tool broker: runner interposes on tool calls, refuses undeclared ones | **#22** | W12 |
| **H1** TCB inversion: running Python checker ≠ proven F\* artifact | medium | meta (TCB) | bind checker to the extracted core / single source of truth | **#23** | W11 |
| **H4** Oracle self-reports the cost it is judged on | low | monitor integrity | measure cost/effects out-of-band; oracle number = unchecked claim | **#24** | W13 |
| H2 Proof reach vs. claims | — | — | already framed honestly (`LH-Q-001b`) | done | — |

## Ordering & rationale

**Phase 0 — Honesty at merge (tiny).** Register R-H1 (W14) + R-N1 (W15) as tracked tensions in `spec.py`. **Recommendation:** fold into PR #19 so the v0.6.4 claim ("approval static + runtime enforced") is not overstated — R-H1 is then visible as a known, tracked residual gap.

**Phase 1 — Merge PR #19 (C3).** `--no-ff`, tag `v0.6.4`. C3 was the load-bearing runtime gap, is finished, verified and R-H1-independent → no reason to wait.

**Phase 2 — PR #20: R-H1 (top priority).** The *only* remaining keystone bypass. No longer infer effect from free text:
- `casl_core.Capability`: field `mode: read|write|admin` (default `write`) or `effect`, default-effectful.
- `spike_approval.effectful()`: reads the structured field; deny-by-default keeps; if a free-text scope remains → exact allow-list (`==`), never `in`.
- `casl_surface`: parse the field; migrate existing specs.
- `examples/attacks/`: `rw_naming.casl` (`cal:read-write`) + `delete_readonly.casl` (`db:readonly` on `purge`) → MUST be rejected.
- W14 → resolved. Tag `v0.6.5`. *Only then is the keystone closed "for real".*

**Phase 3 — PR #21: R-N1 (gate meaning).** Bind `on_approval` to a per-gate prompt (disclosed message + concrete action); consent per gate instead of blanket. Closes the "approve X, branch does Y" gap — prerequisite for the "autonomous secretary" use case. After R-H1, because default-deny already holds (lower severity).

**Phase 4 — PR #22: H3 tool broker.** Runtime mediation: the runner interposes on `uses` capabilities and refuses undeclared/out-of-set tools. Turns the capability *lint* into real *confinement*. **Depends on R-H1** — confinement is pointless as long as the "dangerous?" classification is spoofable.

**Phase 5 — PR #23/#24: architecture gaps.** H1 (bind checker to the proven core) and H4 (cost out-of-band) — harder, less urgent; they bound how much "safe" can ever mean. Plan them explicitly, but after the keystone.

## Short form of the ordering

> **PR #19 (C3, +tracking) → R-H1 → R-N1 → H3 → H1 → H4.**
> Severity and shell pull R-H1 right to the front; H3 hangs on R-H1; H1/H4 are architecture and come last.
