# CASL quickstart — run it, test it

CASL specifies parallel LLM/agent workflows as a *verified* choreography, then conducts them through one
mediated broker. This is the 5‑minute tour from a clean checkout. No network, no API keys, no Rust needed
for the core loop.

## 0. Requirements

Python 3.10+. (Optional: F\* + OCaml to re‑verify the proof; Rust/cargo for the `casl-core` differential;
Linux for the rung‑3 seccomp self‑test. All optional — the loop below needs only Python.)

## 1. See the whole thing run

```bash
./scripts/demo.sh
```

It checks a choreography, turns a natural‑language requirement into a **gate‑accepted, conducted project**,
re‑runs that project standalone through the broker, and (on Linux) shows the rung‑3 confinement self‑test.
One command, the whole loop.

## 2. The five verbs

```bash
./casl check examples/budgeted_qa.casl       # spec → gate: is this choreography admissible? (exit 0/1)
./casl new my-proj "Triage email, classify importance, send an approved reply"
                                             # requirements → verified, conducted project (CEP-0079)
./casl run --project my-proj                 # conduct a project end-to-end through the broker
./casl gate my-proj                          # build-time obligation gate (attestations, provenance, grades)
./casl run examples/budgeted_qa.casl --scenario overspend   # run a single .casl with the mock oracle
```

(`./casl` is a shim for `PYTHONPATH=src python -m casl.check`; after `pip install -e .` the `casl` command
is on your PATH.)

The oracle for a project can be the **mock** (default, offline), the project's **own program/agent** (bind an
executable artifact to an oracle site → it runs as a monitored *activity*, no key), or a **live model**
(`casl run --project DIR --live`, defaulting to local Ollama at `http://localhost:11434`, no key). All three
cross the same monitored boundary (contract + cost + blame); a program/model is **fail-closed** and **cannot
vouch for itself** — the trusted monitor decides the verdict.

## 3. Test it

```bash
PYTHONPATH=src python -m pytest -q       # the full suite
PYTHONPATH=src python -m casl.audit      # the living audit (admits, ratchet, requirement coverage)
PYTHONPATH=src python -m pytest tests/test_end_to_end.py -v   # the whole loop in one file
```

On the Mac/CI also: `(cd rust && cargo test)` — the broker, the rung‑3 policy, and the `casl-core` ↔ F\*
412‑protocol differential. To re‑verify the proof: `./run.sh` (needs F\*).

## 4. What is enforced, and where (read this)

CASL grades honestly — every layer is only as strong as it actually enforces:

- **Proved** — the MPST core (`fstar/CASL.fst`, 0 admits): projection, well‑formedness, the deterministic hull.
- **Gate (build‑time)** — `casl check`/`casl gate`: well‑formedness, capability containment, approval‑dominance,
  no‑ambient‑authority, provenance + human attestation.
- **Conductor (run‑time)** — `casl run`: every model/tool call crosses the one broker; the contract monitor
  catches violations (e.g. an oracle overspend); confined callers may act only through signed providers. The
  oracle backend may be the mock, a **live model** (`--live`), or the project's own **program/agent** run as
  a monitored *activity* (fail‑closed; veto‑never‑vouch; CEP‑0080).
- **Confinement** — rung‑2 (gate‑time, by construction) is enforced; the rung‑3 seccomp egress cut is
  verified on Linux (`python -m casl.host`); the OS‑level Rust host + WASI are the hardening still **staged**
  for a Rust+Linux runner.

**The honest limit:** `casl new` certifies the generated spec is *safe*, not that it is *what you meant*
(validation ≠ verification). Read the proposed `.casl`; the emitted project's unprovable artifacts carry
human‑attestation **obligations** you sign — CASL never vouches on the LLM's behalf. See `docs/synthesis.md`,
`docs/conductor.md`, `docs/confinement.md`, and the CEPs under `proposals/`.
