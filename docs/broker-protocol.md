# CASL broker protocol (P1)

The wire contract between an artifact's thin language binding and the CASL **broker** (the reference
monitor). One small schema; many dumb clients. See `docs/architecture.md` §3.

## Trust model

The **broker** holds all config/policy/trust (the model connector, the tool grants, the per-site contracts)
and is the only component that may touch a capability. A **binding** (client stub) is an *untrusted courier*:
it can only marshal a request and read the typed reply — it carries no model endpoint and no tool. "All
access is mediated by the broker" is a *convention* at this layer; it becomes an *enforced* guarantee only
when the artifact is **confined** so the broker is its sole reachable channel (OS sandbox / WASM — the next
increment). The binding being untrusted is by design ("never trust the client").

## Transport

- **In-process:** `Broker.handle(request_dict) -> response_dict` (embedding / tests).
- **Subprocess (the polyglot boundary):** newline-delimited **JSON-RPC 2.0**, one message per line, over
  stdio (MCP/LSP style). Launch `python -m casl.broker`; write a request line to stdin, read a response line
  from stdout. A socket transport is a later option.

## Methods

| Method | Params | Result | Notes |
|---|---|---|---|
| `initialize` | `{client, version, capabilities[]}` | `{server, version, capabilities[]}` | Capability negotiation: the broker advertises its methods; unknown client capabilities are ignored; absence = unsupported. Must be called first. |
| `oracle` | `{site, question, budget, producer?, provider?}` | `{verdict, answer, cost, measured_cost, blame, reason, branch}` | A model call **through the monitored boundary**. `verdict ∈ {ok, violation, refusal}`; a contract breach blames the producer; the cost checked is the **measured** one (H4 — for a real provider, the output tokens), never the model's claim. Optional `provider` (`openai`\|`claude`\|`gemini`) routes to that connector and **requires the artifact declared `llm:<provider>`** at `initialize`, else `-32011`. Every call is recorded as an observation (LH-G-005). |
| `effect` | `{site, tool, args}` | `{allowed, tool, site, reason?}` | A tool/effect request. **Deny-by-default**: granted only if the capability is in the broker's grant set. (P2: real tool dispatch + the human approval gate for irreversible effects + runtime re-attestation.) |
| `shutdown` | — | `{ok:true}` | Ends a subprocess session. |

## Errors (JSON-RPC `error.code`)

`-32700` parse error · `-32601` method not found · `-32002` not initialized · `-32010` no model connector in
the broker (the model lives only here — a client cannot conjure one) · `-32011` capability not declared (the
artifact requested `llm:<provider>` it did not flag at `initialize`) · `-32603` internal. A binding with no
broker connection can reach nothing — that is the design.

## Capability negotiation = versioning

Following LSP/DAP: there is no brittle version gate. Each side advertises capabilities at `initialize`; both
operate on the intersection; unknown fields are ignored, never fatal; absence means unsupported. This lets
bindings and broker evolve independently.

The `initialize` `capabilities[]` also carry the **artifact's declared capability flags** (`llm:claude`,
`llm:gemini`, `llm:openai`, `websocket`, `tool:*` — engineering-plan §0.5). The broker records them and
**gates** provider use: an `oracle` with a `provider` requires the matching `llm:<provider>` flag (else
`-32011`). The declaration drives grade + monitoring; it is trusted as an *attestation* for human-authored
artifacts and must be *enforced* (confinement / static check) for untrusted / LLM-generated ones.

## Per-language bindings

The Python binding (`casl.client`) is the reference. The C/Java/JS bindings are the *same* ~100-line courier
shape, **generated from this one schema** — the trusted core is the broker, not the stubs. (Generation +
the additional language packages are a later increment; Python validates the protocol first.)

## Signed approvals, effect outcomes, `resolve` (OS pilot)

**`consent` — signed mode.** When the broker is configured with a trust store, `consent` ignores `approved`
and requires `signed`:

```json
{"site": "Create", "tool": "tasks",
 "signed": {"payload": "<JSON text>", "sig": "<hex, 64 bytes>", "key": "<hex, 32 bytes>"}}
```

The signature is Ed25519 over `"casl-approval-v1\n" + payload` (the exact payload text). Payload:
`{"v":1,"kind":"action","program":…,"cap":…,"site":…,"request":<request digest>,"nonce":…,"exp":<unix s>}`.
Result: `{granted, token?, code, class?, reason?}` with `code` one of `ok`, `unsigned`, `malformed`,
`unknown_key`, `bad_signature`, `program_mismatch`, `binding_mismatch`, `expired`, `class_insufficient`,
`replayed`. The token is bound to the signed request digest and is one-shot.

**`effect` — request and outcome.** `request` = `{method, url, headers, body}`; its digest is
`sha256(json.dumps({"m","u","h","b"}, sort_keys=True, separators=(",", ":")))` (`h` = sorted `[k, v]` pairs,
`m` upper-cased, ASCII-escaped). For a capability the broker performs, the result carries
`outcome`: `performed` (2xx) · `rejected` (4xx) · `not_sent` · `unknown` (timeout, reset, other status), plus
`effect` (= the request digest), `performed`, and `status`/`body`/`receipt` when a response arrived. A denial
with `outcome: "unresolved"` means an earlier attempt of this exact request is still `unknown`.

**`resolve`.** `{effect, outcome: "performed"|"not_performed", note}` → `{resolved, …}`. Records the outcome
clarified at the target system; only then can the request be attempted again (with a new approval).

**Journal.** Every signed approval, every irreversible intent (before the send) and its result are appended
to the broker-owned journal (`src/casl/journal.py` documents the format).
