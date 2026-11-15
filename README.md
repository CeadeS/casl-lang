# CASL — Choreographic Agent Specification Language

A typed, agent-oriented, choreographic language for the specification,
orchestration, **verification**, and testing of parallel LLM agents.
Guiding principle: *prove the deterministic hull, treat the LLM as a nondeterministic oracle.*

> **Install → [`INSTALL.md`](INSTALL.md)** (`./scripts/install.sh` for the core, `./scripts/setup-ide.sh` for the MCP server). **Learn the language → [`docs/guide.md`](docs/guide.md)** (quickstart, tutorial, syntax/CLI reference, verdict model, async). This README is the concise **project overview** (architecture, formal core, security model).

## Refinement Ladder (docs-as-code, SemVer, traceable in Git)

| Doc | Level |
|---|---|
| `docs/vision.md` | Target picture & approach model (onion layer 0, above L0) |
| `CASL.md` | L0 coarse specification + L1 requirements spec (requirements `LH-*`) |
| `docs/requirements.md` | L2 design spec (realization per `LH` → `PH-*`) |
| `docs/semantics-l3.md` | L3 formal rules (grammar, projection, reduction, metatheorems) |
| `docs/principles.md` | First principles P0–P9 + consistency audit |
| `docs/mechanization.md` | Host-language workflow (F* + Rust) |
| `docs/reviews/casl-review-v0.1.0.md` | Review of the initial status |
| `docs/reviews/redteam-review-v0.1.27.md` | Adversarial review (attacks against the approval keystone; → hardening in v0.1.28) |
| `docs/analyses/refinements.md` / `docs/analyses/async.md` | Encapsulation principle for opt-in extensions; literature + design decision on the async enhancement (`LH-F-010`) |
| `docs/guide.md` | **User guide** (practical: tutorial, syntax, CLI, verdict model, async) |

## The living system (`src/casl/`)

`spec.py` (Single Source of Authority) → `kernel/` (authority-tagged building blocks) →
feature `compile_choreography` → `authority.py`/`audit.py` (authority chain + traceability).

```
PYTHONPATH=src python3 -m casl.audit     # traceability + coverage + design spec + feature run (CI exit code)
```

## Formal Core (F*)

`fstar/CASL.fst` — machine-verified (F* 2026.03.24, **0 admits**): projection/merge (with the
`W18` fuel-sufficiency result), the SMT data contract, and the safety metatheorems. **Subject
reduction is proven for the FULL calculus, recursion included** (`preservation_full` over
`GS_Msg`/`GS_Ch`/`GS_Rec`, assembled from `subst_g_wf`); to make this hold, well-formedness gained
two recursion side conditions — `gdistinct` (distinct branch labels) and `closed` (no free type
variables). Progress (`global_progress`) and operational correspondence
(`fidelity_complete`/`fidelity_sound`, `deadlock_free`) are proven for the head/recursion-free
fragment. Since v0.1.38 the calculus has **four roles** (`RD`): the permutation/swap rule (`cgstep`)
and the diamond lemmas (`diamond_indep`, `cstep_diamond`) are machine-proven (independent actions
commute at the global *and* endpoint level — the `W9` core); fully general inductive fidelity *under*
permutation for arbitrary concurrent protocols remains Direction C (by-test in `metatheory.py`).
The projection soundness/completeness resolution is **W19** (`CEP-0055`): the sound core never
accepts an unsafe protocol; completeness is *maximised* and the residual delegated behind the
monitored oracle boundary (`casl check --attest`), with the **completeness ratchet** (`CEP-0056`)
guarding that the disclosed residual never silently grows.

```
make -C fstar verify           # or fstar.exe fstar/CASL.fst
```

The verified core runs as extracted **OCaml** (`make -C fstar ocaml-run`) — that is the proven code itself.
**TCB differential bridge** (`make -C fstar tcb-bridge`, H1 sub-step): the extracted F\* core and the Python checker
agree on a projectability corpus — empirically bounds the divergence between the *proven* and the
*running* artifact (offline; full TCB unification remains blocked by the krml/Eurydice mismatch).

## Engine (Rust)

`rust/casl-core` — hand-written Rust crate that mirrors the verified core structurally
(`gtyp/ltyp`, `project`, hardened `merge`, well-formedness, capability containment). **No**
machine extraction: per `TBD-004` OCaml carries the verified core, Rust is the engine.
`cargo test` pins the verdicts to F*/Python. The other crates under `rust/` (parser, checker, broker,
conductor, CLI) are ported from the Python reference one component at a time, each behind a conformance differential.
Why not extracted: the string/ADT core does not fit into the Low\* model of krml/Eurydice — see `docs/mechanization.md`.

```
cargo test --manifest-path rust/Cargo.toml       # the whole Rust workspace
```

## Surface Syntax + CLI

`examples/*.casl` + `src/casl/surface.py` — Scribble-like concrete syntax → `casl_core` AST
(round-trip-validated: `budgeted_qa.casl == G_OK`).

The frontend `casl check` checks a `.casl` file against its **own** role/capability/crash declarations (not the BudgetedQA fixture). **MUST gates** (Exit 1 on violation): well-formedness (projection + MSC realizability), concurrency certification (`LH-Q-001d`, deny-by-default), least-privilege containment, promise linearity, approval dominance (`LH-Q-011`); **SHOULD hints**: termination, ttl safety, crash tolerance, branch contracts. Every verdict stems from an authority-tagged kernel building block. With the opt-in marker `async [k N];`, the buffered async gate (`LH-F-010`, deny-by-default) applies instead of the synchronous concurrency check. **What each check means and how to fix rejections is explained by the [user guide](docs/guide.md) (§5–§6).**

**Honest security model (Red-Team v0.1.27/.28):** CASL is **safe-by-lint on a
verified core** — not "safe-by-construction". Machine-proven (F\*) is the
head-fragment core (projection/merge/progress); the capability and approval guarantees are
static checks over the spec. Approval is additionally enforced **at runtime**
(default-deny at the gate, `--approve`; `C3` closed), and the effect of a capability follows
from the structured `mode` field instead of the free-text `scope` (`R-H1` closed). Tool usage
is **broker-mediated** at runtime (undeclared tools → `tool_denied`; `H3` closed), and the
budget monitor checks the **out-of-band measured** costs instead of the oracle's self-report (`H4` closed).
What remains in the core is the **TCB unity** (running Python checker ↔ proven F\* artifact, `H1`/`W11`,
bounded by the krml/Eurydice mismatch). Regression protection: the attack corpus `examples/attacks/` MUST be rejected in the audit.

```
for f in examples/attacks/*.casl; do ./casl check "$f"; done   # each file → Exit 1 (correctly rejected)
```

```
./casl check examples/budgeted_qa.casl          # ✓ accepted (Exit 0) + projected local types
./casl check examples/reschedule_bad.casl       # ✗ rejected (Exit 1): irreversible without approval
./casl check FILE.casl --json                   # machine-readable report (for CI)
```

Complete example, syntax, and CLI reference: **[`docs/guide.md`](docs/guide.md)**.

## Oracle Boundary (Direction A)

`src/casl/oracle.py` brings the LLM as a real, nondeterministic oracle to the
**monitored** boundary: agent A produces a real response, the monitor synthesized from the contract
decides `cost<=budget` → **ok** (Accept), **violation** (Blame A),
or **Refusal** (typed, no Blame). This is the guiding principle in operation: *hull proven,
LLM monitored as an oracle.* The endpoint (OpenAI-compatible) comes from `.env`
(`OLLAMA_URL`, default model `google/gemma-4-31b-it`); in the
living system (`audit.py`, building block `oracle_boundary`) a deterministic mock runs,
so offline-green.

Beyond the structural contract, `spike_judge` (`LH-Q-007`) checks the **content**
quality: metamorphic invariants over the oracle scenarios + a content judge (`MockJudge`
deterministic in the audit, `OllamaJudge` live). `PYTHONPATH=src python3 -m casl.spike_judge [--live]`.

```
PYTHONPATH=src python3 -m casl.oracle            # 3 mock scenarios (ok / blame A / refusal)
PYTHONPATH=src python3 -m casl.oracle --live     # real Gemma oracle (.env endpoint)
```

## Running (`casl run`)

`casl run` runs a protocol **end-to-end**: first the static check (MUST gate), then operationally — the interpreter steps through the global type, calls the LLM at each `oracle` site, monitors every step (contract/Blame/Refusal), and follows the `choice` according to the verdict. At the **approval gate** it does not choose a silent default but demands an external decision (default-deny without TTY; the concrete action is disclosed per gate). Tool usage is broker-mediated (undeclared → `tool_denied`).

```
./casl run examples/budgeted_qa.casl            # mock: Reject → Loop → Accept
./casl run examples/budgeted_qa.casl --live     # real Gemma oracle (.env endpoint)
```

The default oracle is **Gemma** (`google/gemma-4-31b-it`); `--model`/`--endpoint` (or `.env`) target any OpenAI-compatible endpoints. The building block `kernel.interpreter` runs the same run deterministically (mock) in the audit — offline-green. All flags, scenarios, and exit codes: **[user guide §7–§8](docs/guide.md)**.

## Synthesis (`casl synth`, `LH-G-004`)

The vision core: **NL → Spec → code → test → feedback loop.** An LLM proposes a `.casl`
from a wish, **`casl check` decides** (gate), derived tests run, on rejection
the diagnostics go back (repair loop) — the human takes over at the end. The design-time oracle
is thus fenced in just like the runtime oracle.

The loop is **feedback-driven**: the repair hinges on the content of the verifier diagnostic (building block `kernel.synthesis_repair` — a draft without an approval gate is rejected, exactly this diagnostic adds the gate → accepted).

```
./casl synth "Budgeted QA with retry"             # mock generator: broken → corrected → accepted
./casl synth "..." --live                          # real Gemma as generator
```

## Project / Governance Layer (`casl gate`)

A real deliverable is more than a choreography: it has artifact **bodies** (some LLM-written, some
imported, some verified), dependencies, and the question of *who is accountable for each line*. The
project layer adds a `casl.toml` manifest over a canonical layout, checked by a Tier-0 **obligation
gate**. Each artifact declares a **kind** — `external` \| `generated` \| `oracle` \| `verified` — and the
unprovable kinds **floor at grade G3**; only a `verified` unit reaches G0, and the project's effective
grade is the **weakest link** (laundering upward is impossible, `LH-Q-016/019`). `casl gate` is the
single, deny-by-default opener: it refuses until every obligation holds — including the two acts only a
human can perform: committing the owned bodies (so every line traces to a requirement) and `git commit -S`
on the attestations. *Agents may veto, never vouch.*

The **typed seam** (`implements="Proto:Label"`, `LH-F-012`) binds each artifact to a choreography site,
turning the protocol's message order into a *checkable* dependency graph: `casl flow` reports a grade
**per site** (a site upstream of a weak artifact keeps its strong grade) and soundly **re-bases** a site
that *forwards* a value from a `verified` boundary (`field = Src.field`, capped at G2). `casl observe`
replays the captured prompt→response of each `oracle` call (`LH-G-005`). Full walkthrough + the worked
`examples/projects/secretariat/`: **[user guide §10](docs/guide.md)**.

```
./casl init myproject                            # scaffold the canonical layout
./casl gate myproject                            # Tier-0 obligation gate (deny-by-default)
./casl seam myproject ; ./casl flow myproject    # typed seam + per-site grade flow
```

## Traceability (`trace.py`, `LH-P-005`)

Every commit references the requirement IDs it touches (`CONTRIBUTING.md`). `trace.py`
makes this machine-usable — code↔commit↔requirement across the entire history:

```
PYTHONPATH=src python3 -m casl.trace                # per requirement the commits + verification (unknown IDs → Exit 1)
PYTHONPATH=src python3 -m casl.trace LH-F-003       # all commits (hash, subject, files) for a requirement
PYTHONPATH=src python3 -m casl.trace --blame FILE   # each line → commit → requirement IDs
```

## Full Run

```
./run.sh                       # versions, F* verification, audit, Ollama check → logs/
```

## Host interface (AI-OS pilot)

One approved action through the broker — signed approval, request binding, outcome journal:
[`docs/os-pilot.md`](docs/os-pilot.md).

## License

MIT — see [`LICENSE`](LICENSE).
