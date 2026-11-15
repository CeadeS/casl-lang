# The AI-OS pilot — one approved action through CASL

**Status:** runnable (Rust `casl`), pinned by `tests/test_os_pilot_act.py`. **Scope:** the smallest slice in
which CASL earns its place under a host that contains an LLM agent: the agent may *propose* an action, a
human *approves exactly that action*, and only the broker can *perform* it.

## Roles

| Who | Does | Holds |
|---|---|---|
| Host (OS agent, untrusted) | builds the request, shows it to the user, calls `casl` | nothing that authorizes |
| User | reads the concrete action, signs the approval | the signing key (not reachable by the agent) |
| `casl` / broker | checks program + approval, performs the request, journals it | target credentials, trust store, journal |

## Flow

```sh
# 1. what must be signed for this action (program hash, capability, site, request digest)
casl prepare --program create_task.casl --site Create --request request.json

# 2. the user's approval UI adds {"nonce": <unique>, "exp": <unix seconds>} to "sign", serializes it,
#    and signs  b"casl-approval-v1\n" + payload  with the user's Ed25519 key:
#    approval.json = {"payload": "<that JSON text>", "sig": "<hex>", "key": "<pubkey hex>"}

# 3. perform it
casl act --program create_task.casl --site Create --request request.json \
         --approval approval.json --approvers approvers --journal journal.sqlite \
         --allow-hosts graph.microsoft.com --auth-env TASKS_TOKEN
```

`request.json` is `{method, url, headers, body}` — the target system is whatever that request addresses
(Microsoft Graph, CalDAV, a local service); CASL has no target-specific code. `approvers` lists the trusted
keys, one `<pubkey-hex>=<human|personal>` per line. `--auth-env VAR` makes the broker add
`Authorization: Bearer $VAR` on the wire; the request itself must not carry that header.

`act` prints one JSON object (`status`, `consent`, `effect`) and exits `0` performed · `1` denied ·
`3` ran but not performed (`rejected`, `not_sent`, `unknown`) · `2` usage/IO.

## What is enforced

- The program must pass `casl check` on every call; the irreversible site must be approval-dominated.
- The approval names the program hash, the site, the capability and the request digest. A different
  program version, or a request that differs in any byte of method/URL/headers/body, is refused.
- An approval is single-use (nonce) and expires; both hold across restarts (journal).
- Without a valid signature from a trusted key nothing is sent — an `approved: true` assertion is not an input.
- Destination: `https://` to an allowlisted DNS name only; no redirects, no environment proxy; a name
  resolving to a non-public address is never contacted.
- **Unknown outcome ⇒ no repeat.** If the request may have reached the target (timeout, dropped connection,
  5xx, TLS failure) the outcome is `unknown` and the same request is blocked — even with a fresh approval —
  until the host has looked it up at the target and recorded the finding:
  `casl resolve --journal journal.sqlite --effect <id> --outcome performed|not_performed --note "..."`.
  Put a client-generated id into the request so the lookup is possible.
- Journal: `run`, `approval` (with payload and signature), `intent` (before the send), `result`, `resolve`;
  hash-chained; `casl journal verify journal.sqlite`.

## What is not (yet)

- `act` executes one effect site; it does not conduct the whole choreography.
- `resolve` is not signed: the host can record a wrong finding. A retry still needs a new human approval.
- The journal chain does not detect truncation of its tail or a full rewrite (needs a signed head).
- The trust store is a local key list: no validity windows, no revocation, no issuer-signed credentials.
  A fixed `human` key is pseudonymous, not anonymous.
- Credentials: a static bearer token from the environment; no OAuth refresh.
- The approval UI and the key store are the host's. If the agent can reach the signing key, nothing above holds.
