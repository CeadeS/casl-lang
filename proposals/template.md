---
cep: NNNN
requirement-id: LH-X-000        # Standards CEPs only; omit for Process/Informational
title: Short descriptive title
status: Draft                   # Draft|Accepted|Final|Rejected|Withdrawn|Deferred|Superseded
type: Standards                # Standards | Process | Informational
level: SHOULD                  # MUST|SHOULD|MAY (Standards CEPs)
verification: T                # B|S|M|T (Standards CEPs)
theses: [T2]
realized-by: []                # kernel building-block ids (Standards CEPs)
requires: []
supersedes: []
created: YYYY-MM-DD
version: 1.0
---

# CEP-NNNN — Title

## Summary

One paragraph: what this proposes and why.

## Motivation

The problem, and why the status quo is insufficient.

## Specification

The normative content. For a Standards CEP, this is the requirement and how it is checked.

## Realization

Which building block(s) realize it and at which verification stage (build / SMT / monitor /
test). The audit enforces that a `Final` Standards CEP's `realized-by` blocks exist and pass.

## Open questions / tensions

Link related `W*` tensions and other CEPs.
