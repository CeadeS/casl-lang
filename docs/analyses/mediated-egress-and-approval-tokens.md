# Mediated egress (b) + approval-binding tokens (a) — a unified capability-mediated I/O model

Status: design (this analysis). Date: 2026-06-29. Rust is the target runtime.
Follows `requirement-checker-and-approval-binding.md` and `confinement-by-default-llm-artifacts.md`.

## 0. The directive

CASL must **not** prescribe plugins or contain domain logic (calendar, mail). It provides **generic,
mediated network/tool interfaces** and the verification around them; programs build calendar/mail/whatever
*themselves* on top. And the runtime is **Rust** (Python is the reference, retired at parity).

So two things, unified:
- **(a) approval-binding** — an irreversible effect needs a one-shot consent token (built in Python; must
  reach the Rust broker + the shared conformance corpus).
- **(b) generic mediated egress** — the broker *performs* I/O on a program's behalf under an abstract
  capability, so the program does **no raw I/O** and CASL never names a domain.

## 1. Formalization

The broker is a **capability-mediated I/O reference monitor** (Anderson: always-invoked, tamperproof,
small). Every effect is one request:

```
effect(site, capability, request, consent?) -> response | DENY
```

with invariants:
1. **Complete mediation** — the program holds no endpoint/socket; it can only ask the broker. *(Holds by
   construction only under the cage V2/V3; under V1 it is a convention enforced by review + the import-lint,
   bypassable by raw I/O — see §8.)*
2. **Deny-by-default** — `capability ∉ granted ⇒ DENY`.
3. **Approval-dominance (a)** — `capability ∈ irreversible ⇒ DENY unless consent is a fresh, matching,
   one-shot token` minted only by the approval gate.
4. **Mediated performance (b)** — for a *mediated* capability the broker **performs** `request` via a
   registered transport (HTTP today; a WASI host-import tomorrow), meters it, and emits a signed receipt.
   The program receives only the `response`.
5. **Domain-agnostic** — `capability` is `net:http` / `tool:<id>`, **never** `calendar`. Domain meaning
   lives in the program's `.casl`/manifest, opaque to the broker.

Note CASL already has the seed of (b): `providers.Transport.send(HttpReq)->(status,body)` performs a real
HTTPS POST for the LLM oracle path. (b) = lift that from LLM-only to a generic, capability-keyed transport.
And (a)'s token is a degenerate **macaroon** (one-shot, caveats = {cap, site}).

## 2. Findings (literature)

- **WASI Preview 2 / component model** — the by-construction gold standard: a component has **no ambient
  authority**; capabilities are *resources the host constructs and passes* — "the component cannot conjure a
  capability the host did not provide." Critically, **`wasi:http/outgoing-handler` is separate from raw
  `wasi:sockets`**, so "the host can intercept outgoing HTTP, check the target URL, and reject before
  connecting" — application-layer mediation without granting raw TCP. This is exactly invariant 4, and it's
  domain-agnostic. [wasi-status], [wasip3-sec]
- **Macaroons** — attenuable bearer capability tokens: chained-HMAC **caveats** ("easy to add, impossible to
  remove"), first-party (expiry, read-only, prefix, single-use) and third-party (predicate certified
  elsewhere). "What can you do" in the token, not "who are you." **Biscuit** is the Rust-native equivalent.
  This is the principled generalization of (a)'s consent token. [macaroons], [biscuit]
- **Mediated egress proxies** — Pipelock: an agent egress reference monitor "outside the agent process and
  its credentials" that scans outbound traffic and emits **mediator-signed action receipts — verifiable
  audit evidence**. Validates broker-as-egress + signed receipts (invariant 4). [pipelock]
- **OCap at the OS** — Capsicum (capabilities = delegable refined file descriptors), CloudABI (capsicum as a
  portable ABI), Fuchsia (a component acts only through capabilities in its namespace + numbered handles).
  Grounds the confinement/handle option. [capsicum], [fuchsia]

The external consensus and CASL's own no-ambient-authority design agree; the gap is implementation
completeness (Rust + generic transport), not direction.

## 3. Variants

| # | Variant | Essence |
|---|---------|---------|
| **V1** | JSON-RPC mediated egress + **transport registry** | Generalize `effect` to carry a request spec; broker has `{capability → transport}` (the `Transport.send` seam lifted beyond LLM); it gates + **performs** + meters. Subprocess/any-language guests over stdio. |
| **V2** | **WASI** component host-imports | Guests are WASM components; host grants `wasi:http/outgoing-handler` (or a custom `wit`). By-construction no ambient authority. The endgame. |
| **V3** | OCap **handles** (Capsicum/Fuchsia) | Broker passes an unforgeable, attenuated egress fd to the confined guest; native perf; OS-specific. |
| **V4** | **Macaroon/Biscuit tokens** | Capability = attenuable, one-shot bearer token with caveats; broker mints (post-approval) + verifies. The *token model* for consent + attenuation + delegation — rides on V1/V2/V3. |
| **V5** | Sidecar **egress proxy** (Pipelock) | Out-of-process proxy intercepts all egress; OS-confinement (netns) forces it; signed receipts. Deployment-level, per-connection (coarser). |

## 4. Comparison

▲ strong / ◧ partial / ▽ weak.

| Variant | By-construction | Domain-agnostic | Rust fit | TCB | Perf | Attenuation/approval | Confinement fit | Effort vs now | Guest lang-agnostic |
|---|---|---|---|---|---|---|---|---|---|
| V1 transport-registry | ▽ (convention until cage) | ▲ | ▲ | ◧ | ▲ | ◧ (+V4) | ◧ | ▲ low | ▲ |
| V2 WASI host-imports | ▲▲ | ▲ | ▲ (wasmtime) | ◧ runtime | ◧ | ◧ (+V4) | ▲ | ▽ high | ▲ |
| V3 ocap handles | ▲ | ▲ | ◧ | ◧ kernel | ▲▲ | ▽ | ▲ (Linux) | ▽ | ◧ |
| V4 macaroon/biscuit | n/a (token layer) | ▲ | ▲ (biscuit) | ▲ small | ▲ | ▲▲ | ▲ | ◧ | ▲ |
| V5 sidecar proxy | ◧ (needs netns) | ◧ (HTTP-ish) | ◧ | ▽ large | ◧ | ▽ | ▲ | ◧ | ▲▲ |

V1 alone is convention until the cage (C) lands. V2 is the by-construction endgame but a big lift. V4 is not
a transport — it's the token model that makes consent/attenuation principled and rides on the others. V3/V5
are confinement/deployment options. None is sufficient alone; they **layer**.

## 5. Synthesis — the recommended design

**The broker is a capability-mediated I/O reference monitor; the transport is registered per capability; the
consent is a one-shot, caveat-bound token; the cage makes it by-construction.** Concretely, layered:

1. **Now — V1 + V4-lite (Python + Rust at parity).** Generalize `effect` to
   `effect(site, capability, request, consent?)`. Add a **transport registry** `{capability → transport}`
   (the `Transport.send` seam lifted out of the LLM path). The broker: deny-by-default → approval-binding
   (a) → **performs** `request` via the transport → meters → returns `response` (+ a logged/signed receipt).
   `request` is a generic spec (`method,url,headers,body` for `net:http`); **no domain** in the broker.
   Consent stays the one-shot token of (a), with a clear path to a real **caveat** token (Biscuit in Rust):
   caveats = {cap, site, single-use, expiry, destination-prefix}.
2. **Endgame — V2 (WASI).** Re-express the same capability as a `wasi:http/outgoing-handler`-style host
   import so a WASM guest **cannot** do raw I/O by construction. Same broker policy, stronger substrate.
3. **Confinement — V3/V5** as the OS/deployment cage that makes V1 non-bypassable before V2 lands.

This serves the directive exactly: CASL provides a **generic, mediated `net:http` interface** (programs send
request specs; the broker performs + gates + meters), never a calendar/mail connector; and it lands in the
**Rust** broker, pinned to the Python reference by the conformance corpus (Python retired at parity).

For domains: a program's provider declares it `uses net:http` (a generic, mediated, possibly irreversible
capability) and builds "calendar" by sending CalDAV/Graph/MCP requests **through** the broker — zero socket
code, zero calendar logic in CASL.

## 6. Verification plan

- **Threat model**: (i) program reaches the network without the broker — closed only by the cage (C/V2/V3);
  V1 is convention, stated honestly. (ii) forged/replayed consent — one-shot + broker-minted + caveat-bound
  (a, → Biscuit). (iii) domain leak into CASL — enforced by review + the rule that the broker never parses
  `capability` semantics. (iv) SSRF/destination policy — a caveat/host policy on `net:http` (mediation point).
- **Parity**: every new broker behavior added to BOTH brokers and pinned in `tests/test_conformance.py`
  (the existing cross-impl corpus).
- **Adversarial review** (subagent) on the synthesized design before/with implementation.

## 7. Implementation plan

- **a (Rust parity, first):** port the consent/irreversible enforcement to `rust/casl-broker` (mirror
  `broker.py`'s `consent` + `_effect` token check); add approval cases to `tests/test_conformance.py`. Build
  + test via **cargo on the Mac** (desktop-commander) — Rust is not built blind.
- **b (first slice):** generalize `effect` + the transport registry + a `net:http` capability in the Python
  reference broker (with a `MockTransport` for offline tests), then mirror in Rust; pin in the corpus.
  Keep it domain-agnostic; the LLM path becomes one transport among others.
- **Endgame:** V2 (WASI host-import) + V3/V5 confinement — separate, larger efforts (Linux/WASM runners).

## 8. Verification findings (red-team) — incorporated

An adversarial review split the design into the two postures it really is and found that **(a) is a clean,
monotone authority-*reduction* (ship now); (b) is not "the broker, bigger" — it is a credentialed egress
*service* that turns the monitor into an SSRF/confused-deputy engine unless guarded.** Two Criticals + two
Highs must be addressed *with* (b), before any "the monitor performs your I/O safely" claim:

- **Critical — SSRF / credential confused-deputy (b).** Generic `net:http` over an unvalidated transport
  hands a confined body a credentialed, monitor-blessed request-anywhere primitive (cloud metadata,
  loopback, `file://`, redirect-to-internal). *Fix → new invariant 6a: destination policy enforced **before
  connect**; `https`-only; **no redirect-following**; host/CIDR allowlist blocking link-local/loopback. The
  egress performer is a separate, minimal, audited component on the supervised-merge path — not "the broker."*
- **Critical — consent must bind the request under mediation.** A `(cap, site)` token lets the broker
  perform a *concrete* request the human never saw (approve "create event" → broker does `DELETE /all`).
  *Fix → the consent record binds a **request digest** (method+host+path-prefix or hash); `_effect`
  recomputes and rejects on mismatch. This is present-tense the moment (b) lands, not a future Biscuit nicety.*
- **High — destination-policy provenance.** If the program declares its own allowlist at runtime it
  self-grants (the anti-pattern prior red-teams killed). *Fix → invariant 6b: the policy is **manifest data
  loaded broker-side, human-attested for untrusted kinds**, never a runtime program value.*
- **High — bypass + false audit under V1.** Raw `urllib`/`ctypes`/C-ext I/O evades the (unsound) import-lint;
  receipts then attest only the voluntary subset. *Fix → state plainly: under V1 receipts evidence **broker
  actions only, not program behavior**; mediation is non-bypassable **only** under the cage (V2/V3).*
- **Med — TCB growth / token model.** (b) pulls an HTTP client (+TLS, redirects, maybe a credential store)
  into the *trusted, unverified* part — separate it from the verifiable monitor and route it supervised.
  Keep the **one-shot token** + a request-digest caveat as plain data; **defer Biscuit** until real offline
  delegation is needed (its verifier would be TCB in both languages).

**Decision:** ship **(a)** now (done — Rust parity below). For **(b)**, an **offline-safe Python REFERENCE**
is now implemented + tested (`src/casl/egress.py` + the broker `transports` registry + `tests/
test_mediated_egress.py`): the destination policy (https-only, host allowlist, loopback/link-local/private
**blocked before connect**), **request-bound** one-shot consent (Crit-2), and a `MockTransport` (no live
network). Still DEFERRED to a supervised build: the **live HTTPS transport** (the audited leaf), **Rust
parity** for the egress path, manifest-sourced policy wiring, and the WASI host-import endgame. (a) verified:
the Rust broker gained `consent` + irreversible enforcement at parity with Python, pinned by 5 new
cross-impl corpus cases (`tests/test_conformance.py`): irreversible-needs-token, withheld, consent→effect,
one-shot, site-mismatch — **28 conformance cases green across both brokers**; workspace `cargo test` +
`clippy -Dwarnings` + `fmt --check` clean.

## Sources

- WASI / component model status: https://eunomia.dev/blog/2025/02/16/wasi-and-the-webassembly-component-model-current-status/ `[wasi-status]`
- WASIp3 security roadmap: https://www.systemshardening.com/articles/wasm/wasip3-security-roadmap/ `[wasip3-sec]`
- Macaroons (Birgisson et al.): https://theory.stanford.edu/~ataly/Papers/macaroons.pdf `[macaroons]`
- Biscuit (Rust capability tokens): https://www.clever.cloud/blog/engineering/2021/04/12/introduction-to-biscuit/ `[biscuit]`
- Pipelock (mediated agent egress, signed receipts): https://github.com/luckyPipewrench/pipelock `[pipelock]`
- Capsicum (practical capabilities for UNIX): https://www.usenix.org/legacy/event/sec10/tech/full_papers/Watson.pdf `[capsicum]`
- Fuchsia capabilities: https://fuchsia.dev/fuchsia-src/concepts/components/v2/capabilities `[fuchsia]`
