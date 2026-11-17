# Context grants — scoped search, read and disclosure

**Status:** contract + reference + Rust port, pinned by one shared corpus (`casl.context_corpus`,
`tests/test_context_grants.py`, `rust/casl-broker/tests/context_differential.rs`). Runtime enforcement at
the broker is the next step (casl-lang#7); nothing here performs I/O.

## The problem

`mode read|write|admin` (LH-Q-012) says whether a capability has an effect. It does not say *which data* a
capability may touch: which mailbox, which folder, and to whom the content may be passed on. An
agent-authored workflow needs exactly that boundary, and the user should decide it once per batch, not
once per item.

## Three things, kept apart

| | Who writes it | What it says | Authorizes? |
|---|---|---|---|
| **Declaration** | the workflow (`context` clause in the `.casl`) | the data scope each capability *requests* | nothing |
| **Grant** | the user, or the OS policy key inside a user-signed frame | one operation, one account, one source/resource scope, optionally one receiver, until `exp` | yes |
| **Request** | resolved by the broker from trusted inputs at each access | the concrete account, source, resource, receiver | — |

A request is allowed iff it lies within the declaration **and** a live grant covers it. The effective
authority is always *declared ∩ granted*: a grant wider than the declaration adds nothing, a declaration
without a grant does nothing.

A context grant never authorizes a write. Context capabilities must be `mode read`; an irreversible effect
keeps its own exact-request approval (`docs/os-pilot.md`).

## Operations

| Operation | Meaning |
|---|---|
| `search` | discovery: listing, querying, anything that returns names, snippets, counts or scores |
| `read` | retrieving content |
| `disclose` | passing protected content on to a receiver (a model endpoint, another workflow) |

They are distinct: a `read` grant does not allow `search`, and neither allows `disclose`. An embedding or
indexing call that sends content to an endpoint is a `disclose` to that endpoint. Building a local index
from content is a `read`; the index inherits the restrictions of what it was built from.

## Declaration

```
agent R caps {
  find(query)  scope "mail:search" mode read context search   source "graph.microsoft.com" resource "/v1.0/me/mailFolders/seminar" ttl 50 sig "sr-1";
  fetch(item)  scope "mail:read"   mode read context read     source "graph.microsoft.com" resource "/v1.0/me/mailFolders/seminar" ttl 50 sig "sr-2";
  review(text) scope "llm:review"  mode read context disclose receiver "endpoint:api.anthropic.com/v1/messages#claude-sonnet-5-5" from fetch ttl 50 sig "sr-3";
}
```

```
Context := 'context' ('search'|'read') 'source' Str 'resource' Str
         | 'context' 'disclose' 'receiver' Str 'from' Id (',' Id)*
```

`from` names the search/read capabilities of the same agent whose content the disclosure may carry. The
free-text `scope` stays descriptive and is never consulted. Checked example:
`examples/os_pilot/seminar_review.casl`.

The account is deliberately absent from the declaration. Whose mailbox `/me` is depends on the credential
the broker holds; the grant names it.

## Selectors

Small on purpose. Anything not exactly of these forms is unsupported and fails closed: the program does
not parse, the grant does not verify, the request is denied.

| Selector | Form | Covers |
|---|---|---|
| source | a lower-case DNS host name; no IP literal, no port | equal hosts only |
| resource | an absolute path of non-empty segments; no query, fragment, wildcard, percent-escape, `.`/`..`, trailing slash | itself and everything below it, segment-wise: `/a/b` covers `/a/b/c`, not `/a/bc` |
| receiver | `endpoint:<host><path>[#<model>]` or `workflow:<Name>` | the same workflow; or the same host, a covering path and, if a model is named, exactly that model |
| account | the identity of the broker-held credential (`docs/os-pilot.md`, "Target account") | equal identities only |

Matching is case-sensitive. A differently spelled path is not covered, even where the target system would
treat it as the same resource: the error is on the denying side.

## Grant

A signed envelope `{payload, sig, key}`; the signature is Ed25519 over `"casl-grant-v1\n" + payload`.

```json
{"v": 1, "kind": "grant", "id": "g-7", "program": "sha256:…", "instance": "run-1",
 "op": "read", "account": "jwt:iss=…;tid=…;sub=…", "source": "graph.microsoft.com",
 "resource": "/v1.0/me/mailFolders/seminar", "exp": 1800003600, "uses": null}
```

- `program`: the hash of the workflow the grant is for. `instance`: one run of it, or `null` for any run.
- `receiver` is required for `disclose` and forbidden otherwise. For a disclosure, account/source/resource
  describe where the content came from.
- `exp` bounds the lifetime, `uses` (or `null`) the number of accesses. One grant per operation covers a
  batch; the next decision is needed only when a request falls outside it.

### Who may issue

1. **A user key** from the broker's trust store signs the grant directly.
2. **The OS policy key** signs the grant and attaches a **frame**: a user-signed upper bound
   (`"casl-frame-v1\n" + payload`) that names this policy key.

```json
{"v": 1, "kind": "frame", "id": "f-1", "policy_key": "<hex>", "ops": ["search", "read", "disclose"],
 "account": "…", "source": "graph.microsoft.com", "resource": "/v1.0/me/mailFolders/seminar",
 "receivers": ["endpoint:api.anthropic.com/v1/messages#claude-sonnet-5-5"], "program": null, "exp": 1800086400}
```

A policy-key grant is valid only inside its frame: an operation the frame lists, the same account and
source, a resource at or below the frame's, a receiver one of the frame's covers, no later expiry, and the
frame's program if it names one. The policy key appears in no trust store; without a frame it is an
unknown key. Revoking the frame revokes everything issued under it.

3. **Derived grants (delegation).** A grant may carry a `parent` grant envelope. It is valid only if the
   parent is and it lies within the parent: same operation, account and source; a resource at or below;
   a receiver the parent's covers; no later expiry; no more uses; the parent's instance if it names one.
   The program may differ — that is the delegation. Only the parent's issuer or a user key may derive.
   Revoking or exhausting a parent stops every grant derived from it. Chains are at most four links deep.

A delegated step therefore receives the intersection of its own declared scope and its caller's authority
(`context.intersect`): asking for more than the caller has yields what the caller has; disjoint scopes
yield nothing.

## Decision

`decide(declared, request, grants, now, revoked, used)` returns one of

| Decision | Meaning | Codes |
|---|---|---|
| `granted` | proceed; `grants` lists the ids relied on | `ok` |
| `needs_grant` | within the declared scope but not covered: the host may ask for authorization; `missing` lists the uncovered units | `no_grant`, `expired`, `revoked`, `exhausted` |
| `denied` | no grant can fix it | `undeclared`, `outside_declared_scope`, `unsupported` |

A search/read is one unit (account, source, resource). A disclosure has one unit per origin, and every
origin needs its own covering disclosure grant towards the requested receiver.

A grant matches a unit iff program equal · instance `null` or equal · operation equal · account equal ·
source equal · the grant's resource covers the unit's · (disclose) the grant's receiver covers the
request's. A matching grant is live iff neither it nor any ancestor or its frame is revoked, `now < exp`,
and no use bound along its chain is reached.

Grant verification codes: `ok`, `unsigned`, `malformed`, `bad_signature`, `unknown_key`,
`class_insufficient`, `frame_malformed`, `frame_bad_signature`, `frame_untrusted`, `frame_key_mismatch`,
`frame_revoked`, `outside_frame`, `parent_invalid`, `parent_revoked`, `outside_parent`.

## What this does not do yet

- **No enforcement.** These are pure functions. Checking a grant at each access, counting uses, recording
  revocations and audit events, and refusing a context capability outside this path is casl-lang#7.
- **Resource scopes are path prefixes.** That fits APIs whose path names the container. A target where a
  query parameter widens the result beyond the path is not expressible; such a request must be modelled
  as a wider resource or not at all.
- **Provenance is declared, not traced.** A disclosure names its origins. That an excerpt really stems
  from them is checked against the journal of reads at run time (casl-lang#7), not by following the data.
- **The frame's policy key** is as safe as the place the OS keeps it. A compromised OS process can issue
  any grant inside the frames it holds, and nothing outside them.
- **Not yet a gated requirement.** The declaration is validated by the parser (an unsupported clause is a
  parse error) and the example passes `casl check`; booking it as an `LH-*` requirement with a kernel
  block and a CEP touches the trust base and needs the owner's signed review.
