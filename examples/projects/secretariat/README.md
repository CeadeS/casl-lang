# Worked example — a governed CASL project

This is a complete, readable CASL **project** that exercises the whole
artifact-trust layer end to end. It is deliberately small: one choreography, one
of **each** artifact class, one dependency, two attestations. Read it top to
bottom to see what the gate guarantees, what stays a monitored oracle, what needs
*your signature*, and where it honestly refuses.

> Status: this lives on branch `feat/artifact-trust` (the layer is an
> **Informational Draft**, CEP-0057 — mechanisms live, per-requirement promotion
> to `spec.REQS` pending maintainer sign-off). The `.casl` choreography layer it
> sits on is shipped.

## Layout

```
secretariat/
  casl.toml                 # MANIFEST: name, [attest] identity, [[artifact]] × 4
  requirements/             # LH-LOCAL-001..004 — the human authority
  casl/secretariat.casl     # the choreography SEAM (human-read, casl check ✓)
  artifacts/                # artifact BODIES (one file per owned artifact)
    conflict_check.py       #   verified  — decidable, proof-discharged (G0)
    draft_reply.py          #   generated — LLM-written, owned, must be signed
    classify_importance.py  #   oracle    — live LLM call behind an owned wrapper
  attestations/             # one content-bound human signature per unprovable unit
    draft_reply.json
    classify_importance.json
  deps.lock                 # dependency BURDEN ledger (the imap_client liability)
  .casl/attest.pub          # the recorded human signing identity (public part)
```

## The four classes, in one project

| artifact | kind | basis | grade | needs a human signature? |
|---|---|---|---|---|
| `imap_client` | **external** | accepted, pinned **burden** in `deps.lock` | G3 | no — one burden-acceptance |
| `conflict_check` | **verified** | discharged by **proof** (no double-booking) | **G0** | **no** — proof replaces it |
| `draft_reply` | **generated** | owned, line-traced, **content-bound signature** | G3 | **yes** |
| `classify_importance` | **oracle** | owned wrapper + monitored live call | G3 | **yes** |

Ownership — not who typed the characters — is the dividing line: the LLM wrote
`draft_reply.py`, but we committed it, so **we own it** (traced + signed). The
imported library we do **not** own: it is a burden we pin and contain, never
line-trace.

## Walk it

**1 — the seam type-checks (shipped layer).**

```
$ casl check examples/projects/secretariat/casl/secretariat.casl
  Result: ✓ ACCEPTED   ·   profile=core, assurance=G0
```

**2 — the ledger view: requirement → artifact → kind/grade/trace.**

```
$ casl project examples/projects/secretariat
CASL project: secretariat v0.1.0
  LH-LOCAL-002:
    - conflict_check  kind=verified  grade≥G0 trace=full   [owned]
  LH-LOCAL-003:
    - draft_reply     kind=generated grade≥G3 trace=full   [owned]
  ...
```

The **effective grade is ≥G3** — the weakest link (LH-Q-019). One proved unit
does not lift the system; the generated/oracle/external units floor at G3. That
is the honest end-to-end number, and it cannot be laundered upward.

**3 — the obligation gate refuses, deny-by-default.**

```
$ casl gate examples/projects/secretariat
Tier-0 obligation gate — secretariat v0.1.0 · effective grade ≥G3 (weakest link)
  ✗ artifact conflict_check: trace check failed (git blame ... exit 128)
  ✗ artifact draft_reply:    trace check failed (git blame ... exit 128)
  ✗ artifact draft_reply:    attestation NOT valid — record commit is not validly
                             signed (git %G?=N); 'humans sign as humans' (LH-Q-018)
  ✗ artifact classify_importance: attestation NOT valid — ... not validly signed
  → DENY (deny-by-default; agents may veto, never vouch)
```

**This refusal is the feature, not a bug.** Two human acts clear it — and only a
human can perform them:

1. **Commit the owned bodies, naming their requirement** (line-trace). An
   uncommitted file cannot be blamed, so the trace check fails; once committed
   with a `Requirement: LH-LOCAL-00x` (and `Provenance: llm`) trailer, every line
   traces to a requirement, an author, and a production mechanism.
2. **Sign the attestation records as a human** — `git commit -S attestations/…`.
   A plaintext key in the tree is rejected (an agent could read and forge it); the
   gate trusts only a GPG/SSH-signed commit by the recorded identity. The
   signature means *a human is accountable for exactly this content* — **not**
   that the content is correct. Edit the body and its hash changes, which
   **expires** the signature (re-review + re-sign).

`conflict_check` (verified) needs **neither** step: it is discharged by proof.
`imap_client` (external) needs only its pinned, accepted line in `deps.lock`.

## The point

Proof we cannot have *inside* unprovable code (an LLM module, an imported library)
is replaced by **containment outside** (capability cage + approval gate + boundary
monitor) plus **accountability** (line-trace + blame + a human signature). The
gate binds all of it deny-by-default: agents may veto, never vouch.
