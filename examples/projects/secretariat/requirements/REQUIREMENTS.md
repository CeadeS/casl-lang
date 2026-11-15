# Secretariat — project requirements (local)

These are **project-local** requirements (`LH-LOCAL-*`), distinct from the CASL
**standard** `LH-*` in `src/casl/spec.py`. Each artifact in `casl.toml` realises
exactly one. They are the human authority this project hangs on; every artifact
line traces back to one of them.

- **LH-LOCAL-001 — Email ingest.** Load mail via an imported IMAP client.
  *Class: dependency (burden).* We accept and carry it; pinned in `deps.lock`,
  contained at runtime by the `mail:*` capability. Not line-traced, not
  body-attested — that would be dishonest for code we did not write.

- **LH-LOCAL-002 — No double-booking.** A proposed calendar slot must not overlap
  a booked one. *Class: verified (decidable predicate)* → discharged by **proof**,
  reaches **G0**, needs no signature. This is the property behind the
  choreography's `[conflicts <= 0]` contract.

- **LH-LOCAL-003 — Reply drafting.** Produce a polite reply body.
  *Class: generated (LLM-written, owned)* → **line-traced + human-attested**,
  advisory (**G3**). The actual send is **approval-gated** in the choreography.

- **LH-LOCAL-004 — Importance classification.** Tag an incoming mail urgent/
  normal/low. *Class: oracle (live LLM call behind an owned wrapper)* →
  **monitored at the boundary**, human-attested, advisory (**G3**).
