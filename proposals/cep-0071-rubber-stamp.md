---
cep: 71
title: Rubber-stamp pressure — the honest position and its levers
status: Draft
type: Informational
created: 2026-06-24
version: 0.1
requires: [57, 65, 67]
realized-by: [human_attestation, obligation_gate]
---

# CEP-0071 — Rubber-stamp pressure

The Tier-0 gate is deny-by-default and **requires** a human signature on every unprovable artifact
(`generated`/`oracle`, LH-Q-016/018). That pressure can hollow the signature out: a human signs to make
the gate pass, without truly reviewing. This CEP states the honest position and the levers (D3).

## The honest truth

Rubber-stamping **cannot be mechanically prevented** — it is the same verification asymmetry that
forbids proving an arbitrary program correct (W17): you cannot prove a human *actually reviewed*. So the
design must attack the **incentive** and the **visibility**, never pretend to detect review. The
signature remains what P10 always said it was: a **liability anchor**, not proof of correctness. The
**cage** (capability containment + approval gate + boundary monitor) is the real safety; rubber-stamping
weakens the *blame chain*, never the *containment*.

## The levers

1. **Observability (primary, LH-G-005 — deferred).** Rubber-stamping thrives when review is opaque or
   expensive. Make the diff, the prompt→response of each oracle call, and the region-trace cheap to
   read. The D2 region view and the cockpit pull this way. This is the biggest mitigation and the
   honest place most of the work belongs.
2. **Risk surfacing (now).** `obligation_gate.signature_concentration` reports, per signer, how many
   unprovable artifacts they vouch for — a thin signature over a lot of machine-written surface becomes
   visible. Works with no git and for a solo maintainer.
3. **Second signer (now, opt-in).** A manifest `signers = N` (default 1) makes the gate require **N
   distinct valid human signatures** (primary `attestations/<name>.json` + co-signer sidecars
   `<name>.2.json`, …). Real defence-in-depth for high-stakes/effectful units, but it presumes a team —
   off by default; a solo repo leaves it at 1.
4. **Sampling audit (process, not code).** Periodically re-review a random sample of signed artifacts; a
   caught rubber-stamp costs reputation via the blame chain. A team practice, recorded here, not a gate.

## Decision (2026-06-24)

Implement levers 2 and 3 now (`signature_concentration` + the `signers` knob, default 1). Lever 1
(observability) is tracked as LH-G-005 and is where the real reduction lives. Lever 4 is process. The
gate headline and the per-artifact verdict are unchanged for `signers = 1`.

## Honest limit

None of this makes a signature *mean* "I reviewed". It lowers the cost of reviewing (1), raises the
visibility of a thin signature (2), and multiplies the humans on the hook for high stakes (3). The proof
we cannot have stays replaced by **containment** + **accountability**, exactly as P10 states.
