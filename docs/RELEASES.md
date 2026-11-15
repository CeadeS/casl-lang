# Release runbook — tag the v0.31.1 … v0.36.0 batch

The CHANGELOG records v0.31.1 … v0.36.0 but only `v0.31.0` is tagged. These are **your** signed acts
(cryptographic identity is yours); this file is the exact, copy‑paste runbook. Anchors are verified merge
commits (all `%G?=G`).

Run from the repo root. `git tag -s` signs; swap to `git tag -a` for unsigned‑annotated.

## 1. Tag the commits already on `main`

```bash
git tag -s v0.31.1 0fadc63 -m "CASL v0.31.1 — Python reference parity (CEP-0076): the broker provider/capability gate, mirrored in the Python reference, pinned by a shared cross-impl corpus."
git tag -s v0.32.0 104bd6b -m "CASL v0.32.0 — the conductor (Layer 3, CEP-0077): casl run --project conducts a verified choreography through the broker."
git tag -s v0.33.0 0a8bdd8 -m "CASL v0.33.0 — capability providers + confinement (P2, CEP-0078): no ambient I/O authority; rung-3 seccomp verified on Linux."
git tag -s v0.34.0 6181137 -m "CASL v0.34.0 — Rust checker port begins (P4): casl-core with the full F* well-formedness, 412-protocol differential-pinned."
git tag -s v0.35.0 2db73ad -m "CASL v0.35.0 — CEP-0078 runtime side: the conductor routes confined callers to providers; no-ambient-authority at gate AND run time."
git push origin v0.31.1 v0.32.0 v0.33.0 v0.34.0 v0.35.0
```

## 2. Merge `feat/requirements-loop` (#1, the authoring loop), then tag v0.36.0

`feat/requirements-loop` touches `check.py` (a CODEOWNERS-guarded path), so sign the merge:

```bash
git checkout main
git merge --no-ff -S feat/requirements-loop \
  -m "Merge feat/requirements-loop: requirements → verified project (casl new, CEP-0079)"
git tag -s v0.36.0 -m "CASL v0.36.0 — the authoring front door (CEP-0079): casl new turns a requirement into a gate-accepted, conducted project. Fail-closed; soundness from the gate, never the proposer."
git push origin main v0.36.0
```

## 3. (optional) drop the stray branch I pushed by accident

```bash
git push origin --delete feat/synthesis-loop   # an ancient pre-v0.17 branch, accidentally re-pushed
```

## 4. Merge the productivity + real-execution branches, then tag v0.37.0

`feat/quickstart-e2e` (productivity layer — the E2E test, demo, quickstart, this runbook) touches no TCB path:

```bash
git checkout main
git merge --no-ff feat/quickstart-e2e -m "Merge feat/quickstart-e2e: end-to-end test + one-command demo + quickstart"
```

`feat/real-execution` (CEP-0080 — the activity executor + the live transport) is based on `feat/quickstart-e2e`
and touches `src/casl/check.py` (a CODEOWNERS path — CLI `--live` wiring only, no checker semantics), so **sign**
its merge:

```bash
git merge --no-ff -S feat/real-execution \
  -m "Merge feat/real-execution: activity executor + live transport (CEP-0080)"
git tag -s v0.37.0 -m "CASL v0.37.0 — real execution (CEP-0080): the conductor runs the project's own program/agent as a fail-closed, veto-never-vouch activity, and a stdlib live transport gives a real (no-key local Ollama) model. Two drivers on the one monitored seam; no new trust."
git push origin main v0.37.0
```

## 5. Merge feat/python-retirement (stacked) — the parser brick — then tag v0.38.0

`feat/python-retirement` (CEP-0081 — `casl-surface`, the first strangler-fig brick) is stacked on
`feat/real-execution`. It touches no TCB path (only `rust/`, `src/casl/surface_corpus.py`, tests, docs,
proposals), so an unsigned merge suffices:

```bash
git checkout main
git merge --no-ff feat/python-retirement \
  -m "Merge feat/python-retirement: casl-surface parser at parity (CEP-0081)"
git tag -s v0.38.0 -m "CASL v0.38.0 — retiring Python begins (CEP-0081): a zero-dependency Rust .casl parser at parity with the Python reference, pinned by a 28-protocol parse-differential. Rust authoritative one component at a time; F* stays the proof."
git push origin main v0.38.0
```

Stacked merge order if doing them individually: `feat/quickstart-e2e` → `feat/real-execution` →
`feat/python-retirement` (merging the tip lands all three, since each contains its predecessors).

## 6. Merge feat/casl-check (stacked) — checker brick 2 — then tag v0.39.0

`feat/casl-check` (CEP-0081 brick 2 — `casl-check`, well-formedness + capability containment end-to-end) is
stacked on `feat/python-retirement`. No TCB path (only `rust/`, `src/casl/check_corpus.py`, tests, docs):

```bash
git checkout main
git merge --no-ff feat/casl-check \
  -m "Merge feat/casl-check: Rust checker brick 2 at parity (CEP-0081)"
git tag -s v0.39.0 -m "CASL v0.39.0 — retiring Python, brick 2 (CEP-0081): casl-check runs well-formedness + Least-Privilege capability containment end-to-end from .casl text, at parity with the Python checker (28-protocol verdict differential)."
git push origin main v0.39.0
```

Full stacked order: `feat/quickstart-e2e` → `feat/real-execution` → `feat/python-retirement` →
`feat/casl-check` (merging the tip lands all four).

## 7. Merge feat/overnight (stacked) — overnight hardening — then tag v0.40.0

`feat/overnight` (stacked on `feat/prove-the-rust`) bundles: the full structural well-formedness Verus proofs,
the approval-dominance `casl-check` port, and the secure-product status doc. No TCB path → unsigned merge:

```bash
git checkout main
git merge --no-ff feat/overnight \
  -m "Merge feat/overnight: structural well-formedness proofs + approval-dominance + status"
git tag -s v0.40.0 -m "CASL v0.40.0 — overnight hardening: machine-proved Rust structural well-formedness (Verus); approval-dominance ported to casl-check (differential-pinned); honest secure-product status."
git push origin main v0.40.0
```

Full stacked order: `feat/quickstart-e2e` → `feat/real-execution` → `feat/python-retirement` →
`feat/casl-check` → `feat/prove-the-rust` → `feat/overnight` (merging the tip lands all six).

## 8. Merge feat/casl-cli — the `casl` single binary + sync-complete checker — then tag v0.41.0

`feat/casl-cli` (off the current `main` tip) adds the `casl-cli` crate (the single `casl` binary), the
`concurrency_certified` port in `casl-check`, the version bump + CHANGELOG, and the `rust.yml` CI fix. No TCB
path (only `rust/`, `src/casl/{cli,check}_corpus.py` test oracles, tests, docs, `__init__.py`, `.github/`),
so an unsigned `--no-ff` merge; the tag is signed:

```bash
git checkout main
git merge --no-ff feat/casl-cli \
  -m "Merge feat/casl-cli: the casl single binary (front-end) + concurrency_certified (11th MUST check)"
git tag -s v0.41.0 -m "CASL v0.41.0 — the single use-ready \`casl\` binary (casl-cli) wiring the at-parity crates (surface/core/check/project/conductor), and the static checker completed on the synchronous fragment: concurrency_certified ported (11 of 11 always-run gate checks), sync verdict at parity, only async (async_bounded) deferred. 20-case CLI exit-code differential + 37-protocol verdict differential."
git push origin main v0.41.0
```

`feat/casl-cli` branched off the current `main` tip and `main` has not moved, so the merge is clean.

## Verify after

```bash
git tag | sort -V | tail -8          # v0.31.0 … v0.36.0 present
PYTHONPATH=src python -m pytest -q   # green
PYTHONPATH=src python -m casl.audit  # ✓ PASSED
```

After this, `main` is tagged through v0.36.0 and the program **3 → 2 → 1** is fully merged. The only build
item left is **#4** (rung‑3 netns + the Rust `casl-host` syscall port + rung‑4 WASI), which needs a
Rust+Linux runner / CI — see `docs/confinement.md` §5 and `docs/engineering-plan.md`.
