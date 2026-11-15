---
cep: 78
title: Capability providers — no ambient I/O authority; confined callers delegate to single-purpose signed providers
status: Draft
type: Informational
created: 2026-06-26
version: 0.1
requires: [76, 77]
realized-by: []
---

# CEP-0078 — Capability providers (no-ambient-authority confinement)

Books the **P2 confinement** design realized by `docs/confinement.md`, `src/casl/capability.py`, the
conductor routing, and the `rust/casl-host` scaffold. Extends the opt-in capability service ([CEP-0076]) and
the conductor ([CEP-0077]) with the rule that makes orchestrating **untrusted / LLM-generated** artifacts
safe.

## Summary

- **No ambient I/O authority** (object-capability law; POLA). Raw I/O lives **only** in **capability
  provider** artifacts; everything else gets I/O only by *invoking* a granted provider.
- **A provider is single-purpose + human-signed + enforced to one egress.** Single-purpose defeats the
  *confused deputy* (it takes a capability, not a free-form target). Human-signed anchors trust ("agents
  veto, never vouch"). Enforced-to-one-egress means the human signs *which* door and confinement guarantees
  *only that door*.
- **Confinement is opt-in per artifact, enforced for those that opt in.** A `confined` artifact has zero
  ambient I/O and may act only through granted providers. This is the rung that lets an untrusted/LLM
  artifact's capability claim be *believed*, promoting it above *attested*.
- **The broker is the built-in provider;** humans author additional single-purpose providers under the same
  discipline. The whole I/O TCB (broker + providers) stays small + signed (the seL4 small-TCB lesson).

## Rules (deny-by-default, gate-time — rung-2 "by construction")

1. **Single-purpose** — a provider declares exactly one `provides = "<capability>"`.
2. **Signed** — a provider requires a valid human attestation (content-bound, non-self, key-authorized;
   reuses the existing obligation gate).
3. **Sound narrowing** — the provided capability *attenuates* a broker/parent capability (reuses
   `attenuation.attenuates`).
4. **No ambient authority** — every capability a `confined` artifact `uses` must resolve to a granted
   provider (or the broker); an unprovided capability is rejected.

## Enforcement ladder + decisions

Rung-2 (gate-time, by construction; this branch) → **rung-3** OS sandbox (`casl-host`: empty network
namespace + seccomp-bpf allow-list + broker reachable only via an inherited `socketpair` fd; **Landlock as a
filesystem layer only, never the egress cut**) → **rung-4** WASI component (by construction). `casl-host` is
**pure Rust** (`nix`/`seccompiler`/`landlock`). Research-rated on security + understandability + feasibility
(speed not a priority); see `docs/confinement.md` §5.

## Honest claim

"A confined artifact has no authorized egress except the broker and its granted providers — conditional on
the monitor/launcher + kernel/seccomp being sound, and modulo timing/covert channels." NOT "no leakage." A
by-convention boundary is not confinement.

## Status

Informational decision record. This branch realizes **rung-2** end-to-end (the manifest fields, the
capability gate, the audit check, tests) — fully verified. **Rung-3's seccomp egress cut is verified on real
Linux**: `src/casl/host.py` installs the seccomp-bpf filter and `tests/test_host.py` executes the
bypass-fails test (a confined child's `socket()` → `EPERM`, the inherited broker fd still works; Linux
aarch64), mirroring `rust/casl-host`'s policy. Still staged for a Rust+Linux runner: the empty network
namespace layer and the Rust `casl-host` syscall port. Rung-4 (WASI) is tracked.

**Runtime side wired (v0.35.0).** The conductor (`conductor.py`) now routes a confined caller's effect
through its bound single-purpose provider and refuses at dispatch when none exists — so no-ambient-authority
is enforced at *both* the gate (build-time, `casl gate`) and the conductor (run-time). `examples/projects/
triage` dogfoods it (`notify` provides `mail`); `tests/test_conductor.py` pins the delegation + the run-time
deny.
