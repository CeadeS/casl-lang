# CASL Enhancement Proposals (CEPs)

This directory is the **versioned, machine-checked log of CASL's requirements and changes**.
Each requirement or change is a numbered CEP. Unlike a normal proposal process, a CEP's
status is *enforced by the living audit*: a requirement cannot claim to be `Final` unless the
building block that realizes it exists and passes. Prose can veto, never vouch.

- **[cep-0001](cep-0001-cep-process.md)** — the process itself (start here).
- **[cep-0002](cep-0002-repository-structure.md)** — repository structure, English-everywhere, and this CEP system.
- **[index.md](index.md)** — auto-generated catalog of every CEP.
- **[template.md](template.md)** — starting point for a new CEP.

CEP numbers 1–9 are hand-written (process / meta). Numbers 10+ are the requirement CEPs,
generated from the runtime spine `src/casl/spec.py` by `scripts/gen_ceps.py`. The audit
(`src/casl/cep.py` + `src/casl/audit.py`) checks schema, the CEP↔spec round-trip, and the
proven-status rule on every run.
