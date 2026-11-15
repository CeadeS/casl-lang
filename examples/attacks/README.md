# Red-team attack corpus

Specs that `casl check` **MUST reject** (exit 1). They come from the red-team reviews
v0.1.27/v0.1.28 and a **self-red-team on v0.7.4** (feature interactions) and are the
counterpart to the green self-audit: a regression guard against the safety gates being
torn open again. Enforced in the audit via the building block `kernel.redteam_attacks` (every file
here must be rejected).

| File | Finding | Why it is rejected |
|---|---|---|
| `deny_branch.casl` | C1 | irreversible action in the non-consent branch → not dominated |
| `silent_send.casl` | C2 | effectful capability (`mail:send`) without approval → deny-by-default |
| `approve_once_spam.casl` | M2 | effect in a loop, consent does not hold per iteration |
| `rw_naming.casl` | R-H1 (leak) | write scope `cal:read-write` without `mode read` → default `write` → effectful, no approval |
| `delete_readonly.casl` | R-H1 (spoof) | `purge` tool with scope `db:readonly` → scope is not safety-determining → default `write` → effectful |
| `stream_no_approval.casl` | v0.7.4 stream×approval | effectful action in the `stream` handler without an approval gate → approval dominance applies per handler |
| `concurrency_cross_rec.casl` | v0.7.4 concurrency×rec | role-disjoint concurrency across a recursion → not certifiable (`incomplete`), deny-by-default |
| `stream_not_env.casl` | v0.7.4 stream drive | `stream` dispatch not chosen by an `env` role → not productive → stream well-formedness |

Check:

```
for f in examples/attacks/*.casl; do ./casl check "$f" >/dev/null 2>&1; echo "$f -> exit $?  (1 = correctly rejected)"; done
```
