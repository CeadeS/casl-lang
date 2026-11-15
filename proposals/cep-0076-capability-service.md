---
cep: 76
title: Capability service — the broker as an opt-in capability provider; capabilities as declarations
status: Draft
type: Informational
created: 2026-06-25
version: 0.1
requires: [57]
realized-by: []
---

# CEP-0076 — Capability service (opt-in broker; capabilities as declarations)

Books the **posture** decided in `docs/engineering-plan.md` §0.5 and realized by the broker (P1/P1.5): CASL
does **not** mandate confinement; the **broker is an opt-in capability *service***, and **capability flags
are declarations**. Supersedes the "complete-mediation-mandatory" framing of `docs/architecture.md` §3.

## Summary

- **Opt-in service, not a cage.** The broker provides unified, **monitored** capabilities an artifact OPTS
  INTO: LLM connectors (OpenAI-compatible / Ollama / vLLM · Anthropic Claude · Google Gemini), tool-call
  monitoring, and (later) an optional network/websocket capability. An artifact may also do its own efficient
  native I/O — CASL is a supervisor, not a jail. A programmer controls their own program.
- **Capability flags = declarations.** Each artifact *declares* the broker capabilities it uses
  (`llm:claude`, `websocket`, `tool:mail`) at `initialize`. The declaration drives grade + monitoring; an
  `oracle` with a `provider` is **gated** on the matching `llm:<provider>` flag (deny-by-default, `-32011`).
- **Honesty rule (= "agents may veto, never vouch").** A declaration is trusted as an *attestation* for a
  **human-authored** artifact; for **untrusted / LLM-generated** code it is believed only if **enforced**
  (confinement) or statically checked. The grade reflects which: declared/attested < monitored-through-broker
  < enforced-by-confinement < proved.
- **Confinement (rung-3/rung-4) is OPT-IN** — a way to *raise* an artifact's grade, alongside proof and
  attestation — never a requirement.

## Realization

- Reference monitor + gating: `rust/casl-broker` (the reference impl) and `src/casl/broker.py` (the Python
  reference) — capability declaration at `initialize`; `oracle` provider-gating (`-32011`).
- Connectors: `rust/casl-broker/src/provider.rs` and `src/casl/providers.py` — multi-provider request-build /
  response-parse (token usage = the H4 measured cost; the live HTTP send is a thin `Transport` seam).
- Cross-impl pinning: `tests/test_conformance.py` — one shared corpus drives both brokers, so the gating is
  covered by the conformance differential (not Rust-only).

## Status

Informational decision record. Realized for the model/tool capabilities (declaration + gating + connectors,
pinned cross-impl). The optional network/websocket capability and *enforced* confinement (rung-3/4) are
tracked increments. The live provider HTTP send awaits a key + network.
