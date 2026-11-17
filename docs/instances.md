# Workflow instances — a checked choreography across user decisions and restarts

`casl act` and `casl access` perform ONE site. A real flow has several: a message, a search, a model
call, a decision of the user, a write — with waits in between that may last days and survive restarts.
An **instance** is one such run. The host starts it, delivers one message at a time, and asks where it
stands. Every call is a fresh process; the journal is the only memory.

```
casl instance start   --program F --journal J [--id ID]
casl instance status  --program F --journal J --instance I
casl instance deliver --program F --journal J --instance I --label L [--fields F.json]  [flags of act | access]
casl instance decide  --journal J --instance I --decision denied|cancelled [--request RID]
```

All four print one JSON object. Exit codes: `0` done / delivered · `1` refused · `2` usage or IO ·
`3` the step ran but is not complete (the target rejected it, it was not sent, or the outcome is unknown) ·
`4` the step waits for a grant.

## What an instance is

A program version (the hash of the `.casl` text) plus the steps the journal says are complete. Where the
instance stands is found by walking the program's checked global type along those steps. No code is
replayed and no effect is repeated to find the position.

The instance is bound to its program version: a call with a changed file is refused (`program_changed`).
A changed program is a new instance.

## Steps

`status` lists what the instance accepts next. Only one of those messages can be delivered; anything else
is refused (`unexpected_label`) and leaves no trace. Fields are checked against the declared names and
sorts (`Int`, `Real`, `Bool`, `Str`). Field values are not stored — the journal keeps their hash.
The host therefore keeps what the values refer to (the mail, the file): CASL restores the position and the
pending request, not the inputs.

| step (`kind`) | how it is delivered | complete when |
|---|---|---|
| `message`, `choice` | `deliver --label L [--fields]` | the `step` entry is written |
| `effect` | `deliver` + the flags of `casl act` | reversible: the broker performed it. Irreversible: its attempt was performed (`result`, or `resolve` after an unknown outcome) |
| `context` | `deliver` + the flags of `casl access` | the access was granted (host-performed) or granted and performed |

Completion is a journal fact, never the caller's word. The entry that completes a step is written only
while the instance stands at that step, in the same journal transaction as the check. Of several
concurrent deliveries of one step, one completes it; the others are refused (`stale_step`).

## Approvals

An irreversible step needs a signed approval, as with `casl act`. Inside an instance the approval also
names the instance and the step:

```
casl prepare --program F --site File --request R --instance I --journal J
→ "sign": {…, "instance": "I", "step": 7}
```

The broker compares both at consent (`binding_mismatch`). An approval for step 7 of instance I performs
nothing in another instance, at another step, or outside an instance — and an approval without an
instance performs no instance step.

The choice at an approval gate (`Keep` / `Drop`) is delivered by the host as a plain step. What the
user's signature covers is the irreversible action behind it.

## Waiting

**For a grant.** A context step without a live grant returns `needs_grant` (exit 4). The instance stays
at that step; `status` reports `waiting_grant` and lists the pending request: its id, the step, and the
scope asked for. The request id is stable for the same ask at the same step. When the grant is on record,
deliver the step again. The decision is made afresh on every delivery, so a grant that expired or was
revoked meanwhile unlocks nothing, and expiry needs no timer.

The user's no: `decide --decision denied --request RID` ends the instance. The request must be pending
at the instance's current step (`stale_request` otherwise). The same decision twice is one decision;
a different one after the end is refused (`ended`). `--decision cancelled` ends an instance without a
request.

**For an unknown outcome.** If an irreversible step's request may have reached the target, the instance
is `blocked` and `status` names the attempt. No other attempt of that step starts — not with a fresh
approval, not with a changed request. Clarify at the target, then `casl resolve --attempt N`:
`performed` completes the step without a second request; `not_performed` opens it again.

## Journal

| kind | body |
|---|---|
| `instance` | `{id, program, name}` |
| `step` | `{instance, step, label, kind, fields_sha256, program}` |
| `instance_end` | `{instance, state, request}` |
| `intent`, `access`, `approval` | gain `instance`, `step` (and `label`) when they belong to a step |

## What this does not do yet

- **Sequential programs only.** `async` programs are not certified by the Rust front-end and are refused.
- **No oracle sites.** A program with an oracle message is refused at `start`.
- **No timers, by decision.** Nothing fires on its own. A pending grant request stays pending; showing it
  and reminding the user is the host's job. A grant that expires is noticed at the next access. A workflow
  that must react to a deadline will say so in its program, as an explicit timeout branch — not as a
  timer of the runtime. That branch does not exist yet.
- **Crash handlers are not walked.**
- **A reversible effect is not at-most-once.** If the process dies between the send and the `step` entry,
  the step is delivered again. The same holds for a broker-performed context access that was granted twice
  concurrently. Irreversible effects are at-most-once per step.
- **`decide`, `resolve` and `start` are unsigned.** They add no authority, but the invoker of `casl` must
  be trusted host code.
- **Rust only.** The Python reference checks the approval binding but does not perform instance steps.
