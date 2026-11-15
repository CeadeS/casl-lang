# Requirement checker (Layer 1) + approval-binding (A)

Status: implemented (this branch). Date: 2026-06-29. Follows
`docs/analyses/confinement-by-default-llm-artifacts.md` (the A/B/C framing).

## Problem

A verified `.casl` proves *approval dominates an irreversible effect*, but that binds the running app only
if the app is **driven** by the spec (the conductor, B) or the rule is **re-checked at an always-invoked
monitor** (the broker). scriptorium's live Flask app does neither for calendar: it calls
`seam.capability("Appointments:Book","calendar")` (which passes — `calendar` is granted) and then books,
with no approval gate. A forgotten `gate()` call **failed open**, because the only enforced check
(capability presence) still passed. Approval and capability were two *unlinked* checks, and approval was an
*opt-in* caller-side call.

## A — approval-binding in the broker (runtime, fail-closed)

`src/casl/broker.py`: an **irreversible** capability now requires a fresh, broker-minted, **one-shot consent
token** bound to `(cap, site)`. New `consent` method mints a token iff the human approved the disclosed
effect; `_effect` denies an irreversible cap unless a matching, unused token is presented (and consumes it).

- A forgotten approval gate ⇒ no token ⇒ **DENY** (deny-by-default). The speed-bump becomes a wall.
- Reversible caps are unaffected (backward compatible).
- Honest limit: `approved` is the UI's assertion that a human consented. A closes the *forgotten-gate*
  class; binding the human directly to the monitor is the conductor/confinement increment (B/C).

Tokens: `secrets.token_hex(16)`, single-use, matched on `(cap, site)`. Tests: `tests/test_broker_approval.py`.

## Layer-1 requirement checker (build-time, deterministic)

`src/casl/requirecheck.py`: the static twin of A, fast enough per-commit. Over the app/host source it checks
every effect call site (`seam.effect` / `seam.capability`):

- **Provenance** — the call's `site` (`Protocol:Label`) must resolve to an artifact carrying a
  `requirement`. An effect that traces to no requirement is rejected ("kommt die Funktion aus einem
  Requirement?"). A non-literal `site` ⇒ can't trace ⇒ flagged.
- **Approval-dominance** — an effect whose site is `irreversible` must pass an `approval=` token.

Deliberately **unsound** for bypasses (it keys on the seam funnel); raw I/O outside providers is caught by
`casl.importlint`, and physical containment by the runtime cage (A/C). The three layers compose.

Per-commit: `python -m casl.requirecheck PROJECT FILE.py …` (exit 1 on violation) +
`scripts/pre-commit-requirecheck.sh` (runs on staged `*.py`). Tests: `tests/test_requirecheck.py`.

This is **Layer 1 (formal)**. **Layer 2 (semantic)** — the LLM review that judges whether the code actually
*fulfils* its requirement, vetoes-never-vouches, run incrementally on a diff — is the next increment.

## scriptorium wiring

`casl_runtime/seam.py` gains the **effect funnel**: `effect(site, cap, approval=None)`; `gate()` now mints
and returns the broker consent token (backward compatible with `if not seam.gate(...)`); `_irreversible_caps()`
derives the irreversible caps from the verified `.casl`. Enforcement is behind `SCRIPTORIUM_ENFORCE_APPROVAL`
(default off during route migration; `=1` makes every irreversible effect fail-closed without a token).

Remaining (mechanical): route the three confirmed-booking paths through
`seam.effect("Appointments:Book","calendar", approval=seam.gate(...))`, then flip the flag on. The Layer-1
checker already flags the un-migrated sites at commit time.

## B / C (next)

- **B** — run effects through the conductor (`casl run`) so the verified ordering *is* what executes; the
  bypass becomes unrepresentable rather than re-checked.
- **C** — confinement (rung-3/WASI) so the app reaches the provider only through the broker. Needs a Linux runner.
