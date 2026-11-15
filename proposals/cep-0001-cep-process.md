---
cep: 1
title: CEP Purpose and Guidelines
status: Final
type: Process
created: 2026-06-18
version: 1.0
---

# CEP-0001 — CEP Purpose and Guidelines

A **CASL Enhancement Proposal (CEP)** is the unit in which CASL records a requirement or a
change to the language, its tooling, or its process. CEPs are modeled on Python's PEPs and
IETF RFCs — numbered, versioned, with a structured header and a lifecycle — with one
addition those processes do not have: **a CEP's status is enforced by the machine.**

## Why

CASL's first principle is self-application (P0) and docs-as-code traceability (P9). A
requirement that lives only as prose can drift from what the system actually does. So the
requirement log is not just documentation: the living audit (`casl/audit.py`) checks the
whole corpus on every run and fails the build on any inconsistency. Prose can *veto*, never
*vouch*.

## Anatomy

Each CEP is a Markdown file `proposals/cep-NNNN-slug.md` beginning with a frontmatter block:

```
---
cep:          7                 # unique number
requirement-id: LH-F-010        # alias to the spec requirement (Standards CEPs only)
title:        Bounded async sessions
status:       Final             # Draft|Accepted|Final|Rejected|Withdrawn|Deferred|Superseded
type:         Standards         # Standards (a requirement) | Process | Informational
level:        SHOULD            # MUST|SHOULD|MAY  (RFC 2119)   — Standards CEPs
verification: T                 # B|S|M|T          (build|SMT|monitor|test)
theses:       [T2, T3]          # which guiding theses it serves
realized-by:  [async_bounded, async_enhancement]   # kernel building blocks (Standards CEPs)
requires:     [1]               # other CEPs this depends on
supersedes:   []                # CEPs this replaces
created:      2026-06-18
version:      1.0                # this CEP's own revision
---
```

## Lifecycle

`Draft → Accepted → Final`, or `Rejected` / `Withdrawn`; a superseded CEP becomes
`Superseded` (with the replacement in the successor's `supersedes`). A requirement that is
knowingly not yet realized is `Deferred` (a tracked accepted gap).

## What the machine enforces (the "proven" part)

The audit (`casl.cep` + `casl/audit.py`) checks, every run:

1. **Schema** — required fields present; `status`/`type`/`level`/`verification` from their
   fixed vocabularies; CEP numbers and `requirement-id`s unique; `requires`/`supersedes`
   resolve to existing CEPs.
2. **Round-trip** — the requirement table derived from the CEP corpus equals the runtime
   spine `spec.REQS` exactly. The versioned log cannot drift from what the code uses.
3. **Proven status** — a `Standards` CEP may be `Final`/`Accepted` only if every
   `realized-by` building block exists in the kernel registry; the audit being green means
   those blocks pass their self-tests. A tracked accepted gap must be `Deferred`.

A CEP whose claim the machine cannot back fails the audit, and therefore the build.

## Authoring

The runtime spine is `src/casl/spec.py`. To add or change a requirement, edit the spec, then
regenerate the corpus:

```
PYTHONPATH=src python3 scripts/gen_ceps.py
```

This rewrites the requirement CEPs and `proposals/index.md`, and asserts the round-trip.
Hand-written CEPs (numbers 1–9: process and meta) are preserved. A future revision may make
the CEP corpus the sole source and generate the spine from it; the enforced round-trip makes
that flip safe.

See `proposals/template.md` for a starting point and `proposals/index.md` for the catalog.
