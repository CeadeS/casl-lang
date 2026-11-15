---
cep: 2
title: Repository structure, English-everywhere, and the CEP process
status: Final
type: Process
created: 2026-06-18
version: 1.0
---

# Restructure, English-Everywhere, and the CEP Process — Design Proposal

> **Status:** Draft — awaiting approval. Nothing in this document has been executed.
> On approval this file becomes the seed of `proposals/cep-0001` (the CEP process)
> and `proposals/cep-0002` (repository structure).
>
> **Decisions already taken** (Martin, this session): deliver *proposal first, then execute*;
> *one decisive reorg* (not drawn-out); *all Markdown* to English (content **and** filenames).
>
> **Goal.** Make CASL delivery-ready: a developer who has never seen the project can open the
> repository and understand *what is product, what is proof, what is research, and what is
> required* — in English, with every requirement versioned and machine-checked ("proven").
> Five lenses are used to judge every option: **Maintainability · Understandability ·
> Security · Traceability · Delivery-readiness**.
>
> **Self-application (P0).** "Die Sprache lebt, was die Sprache macht." The repository should
> embody the same discipline the language enforces: deny-by-default, all authority derived
> from specifications, nothing vouched that the machine has not checked. The structure is not
> cosmetic — it is the system applied to itself.

---

## 1. Current state — assessment

Grounded in the repository as it stands (post v0.16.1).

| Area | Observation | Problem against the goals |
|---|---|---|
| `prototype/` | 33 flat `.py` modules, 6692 LOC. Ships the real library (`casl_core`, `kernel`, `casl_check`, `casl_run`, `casl_ide`, `casl_mcp`, `surface`, `semantics*`, `oracle`, `spec`, `authority`, `audit`) **next to** research spikes (`spike_*`, `ab_candidates`, `harden_equivalence`). | The folder name says "not production". A newcomer cannot tell product from experiment. (Understandability, Delivery) |
| Import model | Flat namespace (`import casl_core`, `import kernel`). `pyproject.toml` works around it with `package-dir={""="prototype"}` + an explicit `py-modules` list of 33 names. | Fragile, non-idiomatic, every new module must be hand-added to packaging. (Maintainability, Delivery) |
| God-modules | `kernel.py` 854 LOC, `casl_check.py` 491, `casl_ide.py` 388, `oracle.py` 375, `casl_surface.py` 361. | Hard to read, review, and test in isolation. (Maintainability, Understandability) |
| Docs | 18 Markdown files at the **root**, mixed audience (user guide vs. red-team reviews vs. analysis spikes vs. normative spec vs. changelog) and mixed language in filenames (`Pflichtenheft.md`, `Grundsaetze.md`, `Async-Analyse.md`, `L3_Semantik.md`, `C_Mechanisierung.md`, `Veredelungen-Analyse.md`, `Probe-LLM-Bedienbarkeit.md`). | No navigation; German filenames block non-German developers. (Understandability, Delivery) |
| Build artifacts in git | `fstar/ocaml/_build/`, `engine/target/`, `logs/` appear committed. | Noise, churn, larger clones, leaks local state. (Maintainability, Security) |
| Two version schemes | `CASL.md` changelog uses `0.1.x` (spec lifecycle); git tags use `v0.x.y` (releases); `pyproject` says `0.15.0` (stale); `casl_check.VERSION="0.1.0"`. | No single source of truth for "what version is this". (Traceability, Delivery) |
| Requirements | Live as a hand-maintained dict `spec.REQS = {id: (level, stage, theses)}`, a second layer `pflichtenheft.py` (PH items → LH), and `TENSIONS`/`ACCEPTED_GAPS`. Mirrored again in prose in `CASL.md` (RTM) and `Pflichtenheft.md`. | The same facts are written **three** times; drift is only caught by eye. No per-requirement document, version, or status lifecycle. (Traceability, Maintainability) |

**What already works and must be preserved.** The authority chain is genuinely good and unusual:
`@building_block(...)` populates `kernel.REGISTRY` → `authority.py` *derives* requirement
coverage from the registry (not a hand list) → `audit.py` enforces (every block cites only real
spec items; every executable requirement is realized or a tracked gap; every thesis covered) and
*runs* each block's self-test, exiting non-zero on any gap. F\* gives a 0-admits core. This
"living audit" is the asset the whole restructure must keep green at every step — it is our proof
that traceability survived the move.

---

## 2. Theme A — English everywhere

Decision is set (*all Markdown*, content and filenames). Remaining German is now narrow: one
code identifier (`async_veredelung`), one module name (`pflichtenheft.py`), seven German doc
filenames, and the prose inside the analysis/review docs. The only real choice is *how* to rename
safely.

| Variant | Description | Trade-off |
|---|---|---|
| **A1 — pure rename** | `git mv` + mechanical reference rewrite, no shims. | Cleanest end state; highest momentary risk (a missed reference breaks import/audit/F\* build). |
| **A2 — rename + compat shims** | Keep `pflichtenheft.py` as a thin re-export of `requirements.py`, etc. | Lower transition risk; but leaves German aliases behind — defeats the goal. |
| **A3 — fold into the reorg** | Do every rename *inside* the one decisive move (Theme B), in a single mechanical pass with full verification. | One disruption instead of two; the reorg already rewrites every import, so renaming costs almost nothing extra. |

**Synthesis → A3, no shims.** Because we are doing one decisive reorg anyway, every import path
changes once; renames ride along for free, and we verify the whole gate (compile · audit · F\* ·
Rust · pip · CLI · MCP) at the end. No German aliases survive.

**Rename map (identifiers & files).**

| German | English | Kind |
|---|---|---|
| `async_veredelung` | `async_enhancement` | building-block id + function (audit text already says "enhancement") |
| `pflichtenheft.py` | `spec/requirements.py` | module |
| `Pflichtenheft.md` | `docs/requirements.md` | doc |
| `Grundsaetze.md` | `docs/principles.md` | doc |
| `Async-Analyse.md` | `docs/analyses/async.md` | doc |
| `Veredelungen-Analyse.md` | `docs/analyses/refinements.md` | doc |
| `Probe-LLM-Bedienbarkeit.md` | `docs/analyses/llm-operability.md` | doc |
| `L3_Semantik.md` | `docs/semantics-l3.md` | doc |
| `C_Mechanisierung.md` | `docs/mechanization.md` | doc |

**Deliberately kept** (proper nouns / standards): the author name *Függer* (citation); the German
standard title *VDI/VDE 3694* (its real name). A final mechanical scan (string literals **and**
identifiers, the AST-based scan already built) gates "zero German remaining" before release.

---

## 3. Theme B — Repository structure

| Variant | Shape | M | U | S | T | Delivery |
|---|---|:--:|:--:|:--:|:--:|:--:|
| **B1 — tidy in place** | Keep `prototype/`; move spikes to `prototype/spikes/`, docs to `docs/`, gitignore artifacts. | ◐ | ◐ | ○ | ○ | ◐ |
| **B2 — src-layout package** | Real `src/casl/` package (submodules), `tests/`, `docs/`, proof/engine as siblings. | ● | ● | ● | ● | ● |
| **B3 — polyglot monorepo** | `packages/casl-python/`, `proof/fstar/`, `engine-rust/`, `docs/`, `proposals/` as top-level workspaces. | ● | ◐ | ● | ● | ◐ |

(● strong · ◐ partial · ○ weak)

**Discussion.** B1 is the least work but keeps the two things that most hurt a newcomer: the
"prototype" misnomer and the flat namespace; it does not earn "delivery-ready". B3 is the cleanest
*separation* of the three artifacts (Python checker, F\* proof, Rust engine) and scales well, but
for a repo of this size it adds path depth and ceremony (the `audit ↔ fstar tcb-bridge` and
`examples/` cross-references get longer) without proportional benefit yet. B2 is the Python
standard, removes the packaging hack, draws a hard product/research line, and namespaces imports
(`from casl import core`) — while leaving proof and engine as clearly-named siblings.

**Synthesis → B2 as the spine, borrowing two ideas from B3:** a top-level `proposals/` (the CEP
corpus) and a `proof/` directory that renames `fstar/` to a role name (room for a second prover
later). Target tree in §6.

---

## 4. Theme C — Maintainability & understandability of files and functions

Five practices, each a small variant set; the recommendation combines them.

**C1 — Split god-modules along seams that already exist.** `kernel.py` is a registry plus themed
building blocks; split into a `kernel/` package: `registry.py` (the `@building_block` decorator +
`REGISTRY`), `compose.py` (`compile_choreography`), then `projection/resilience/capability/
approval/async_/ide/pipeline.py`. `kernel/__init__.py` imports every submodule so the decorators
still register on import (preserving `authority`/`audit` behavior) and re-exports the names those
modules call (`kernel.REGISTRY`, `kernel.compile_choreography`, `kernel.pipeline`, …).
`casl_check.py` splits into `cli.py` (arg parsing/exit codes) + `check.py` (the pipeline).
*Risk, called out:* the registry relies on import side-effects and `audit.py` looks blocks up by
string name — the split must keep both intact; the audit being green afterward is the proof it did.

**C2 — Self-applied maintainability gates (on brand).** Add audit checks that hold *our own*
source to a standard: no module over ~400 LOC without justification, every public function has a
docstring and type hints, every `@building_block` cites a live CEP. The language already audits
itself; this extends P0 to code hygiene and makes "understandable" a *checked* property, not a
hope.

**C3 — Explicit public API.** `casl/__init__.py` exports the supported surface; internal helpers
are clearly internal. Developers learn the entry points in one file.

**C4 — Drop redundant prefixes.** Inside the `casl` package, `casl_core → core`, `casl_surface →
surface`, etc. (the package name already says "casl").

**C5 — Tests vs. the living audit — keep both, with distinct jobs.** Convert the `spike_*`,
`run_all`, `harden_equivalence`, `ab_candidates` files into a real `pytest` suite under `tests/`
(behavioral checks), and keep `audit.py` as the **authority/traceability gate**. Add one bridging
test, `test_audit_green.py`, asserting `audit.main() == 0` so CI fails loudly on any authority gap.
Core stays dependency-light (z3 only at runtime; `pytest`/`ruff`/`mypy` are dev-only extras).

**Synthesis → C1+C2+C3+C4+C5 together.** This is where "understandability" is won: smaller named
modules, a visible API, English names, and — crucially — *machine-enforced* hygiene so it cannot
rot.

---

## 5. Theme D — The CEP process (CASL Enhancement Proposals)

The centerpiece of your request: log requirements like Python's **PEPs** — numbered, versioned,
and, uniquely for us, **proven**.

**Background.** PEP (Python) and RFC (IETF) both give each change a *number*, a *structured
header* (status, type, author, created, requires/replaces/superseded-by), and a *lifecycle*
(Draft → Accepted/Rejected/Withdrawn → Final → Superseded/Deferred). PEP 0 is the generated index;
PEP 1 defines the process; PEP 12 is the template. RFCs add "obsoletes/updates" links. What neither
has — and what fits CASL exactly — is a *machine-checkable* link from the proposal to the evidence
that it actually holds.

| Variant | Description | Trade-off |
|---|---|---|
| **D1 — docs-only** | CEP Markdown files + template + hand-maintained index and status. | Simple; but status is unverified prose → the very drift we fight. Not "proven". |
| **D2 — frontmatter + validator (proven core)** | Each CEP carries structured frontmatter; a loader builds the requirement table; the audit **enforces** status ↔ realizing building block ↔ proof. | Machine-enforced traceability; kills the triple-bookkeeping; some migration work. |
| **D3 — full lifecycle tooling** | D2 + a `casl cep` CLI (new/list/show/lint/render-index) and guarded status transitions. | Best ergonomics; most build effort. |

**Synthesis → D2 now, D3 as a fast-follow.** D2 makes the CEP the *single source of truth*:
`spec.REQS`, the `pflichtenheft` PH layer, and `TENSIONS` become **generated** from the CEP corpus,
so the facts are written **once**. The existing audit already does most of the enforcement; we add
the "proven status" rule. The `casl cep` CLI (D3) follows once the format is stable.

**CEP frontmatter (proposed schema).** Dependency-free (a ~30-line `key: value` parser, or
stdlib `tomllib`) so the core keeps only z3 at runtime.

```
cep:          0007
title:        Bounded asynchronous sessions
status:       Final        # Draft | Accepted | Final | Rejected | Withdrawn | Deferred | Superseded
type:         Standards    # Standards | Process | Informational
level:        SHOULD       # MUST | SHOULD | MAY   (RFC 2119)
verification: T            # B | S | M | T          (existing stage codes)
created:      2026-06-17
version:      1.2          # the CEP's own revision (versioned!)
authors:      [Martin]
theses:       [T2, T3]
principle:    P2
requires:     [0001]
supersedes:   []
realized-by:  [async_bounded, async_enhancement]   # building-block ids
proof:        fstar:Async.bounded_safe             # or  audit:<block>  or  none
tensions:     [W16]
```

**The "proven" audit gate (deny-by-default).** For every CEP the audit additionally checks:

- status `Final`/`Accepted` ⇒ **every** `realized-by` id exists in `REGISTRY` *and* its self-test
  is green; if `proof:` names an F\* lemma, the F\* build must discharge it (or the tcb-bridge
  corpus passes).
- any CEP with a verification stage ⇒ at least one `realized-by`.
- a building block realizing no CEP ⇒ flagged (orphan authority).
- unknown status, missing realization where required, or a claimed-but-red proof ⇒ **audit fails**.

This is the exact embodiment of "agents may veto, never vouch": a CEP's prose can *claim* Final, but
only the machine green-lights it. Versioning is twofold — each CEP has its own `version:` and
history section (git-tracked), and the product has one release version (§6).

**Migration (loses nothing, provably).** Generate one CEP per `LH-*` from `spec.REQS` +
`pflichtenheft` PH items + `TENSIONS`, then curate prose. Flip the loader so CEP → `REQS` is the
source. Add a **round-trip equivalence check**: the `REQS` generated from CEPs must equal the
current hand-written `REQS` — a metamorphic proof that the migration preserved every fact. (`W*`
tensions become a field on the relevant CEP plus a generated tensions registry; `ACCEPTED_GAPS`
become status `Deferred`.)

---

## 6. Synthesized end-state

Combining A3 + B2(+proposals/+proof/) + C1–C5 + D2:

```
LLang/
├── README.md                  # concise English overview → docs/
├── CHANGELOG.md               # generated from CEP status changes + release tags
├── pyproject.toml             # real package; __version__ single-sourced; py-modules hack gone
├── casl                       # CLI shim → python -m casl.cli   (check / run / ide / cep)
├── .github/workflows/ci.yml   # full gate on every push (NEW)
├── src/casl/
│   ├── __init__.py            # __version__  (the one product version)
│   ├── cli.py  core.py  surface.py  semantics.py  semantics_async.py
│   ├── run.py  ide.py  mcp.py  synth.py  oracle.py  trace.py
│   ├── authority.py  audit.py
│   ├── kernel/                # was kernel.py (854 LOC) → themed submodules
│   │   ├── __init__.py        # imports submodules (decorators register); re-exports REGISTRY, compile_choreography
│   │   ├── registry.py compose.py projection.py resilience.py
│   │   ├── capability.py approval.py async_.py ide.py pipeline.py
│   └── spec/
│       ├── __init__.py        # exposes THESES, PRINCIPLES, REQS, TENSIONS (loaded from CEPs)
│       ├── theses.py  principles.py
│       └── cep.py             # CEP loader + validator + round-trip check
├── proposals/                 # the CEP corpus (versioned, proven)
│   ├── README.md  cep-template.md  index.md (CEP-0000, generated)
│   ├── cep-0001-cep-process.md
│   ├── cep-0002-repository-structure.md      # this document, executed
│   └── cep-0003…00NN-*.md                     # one per migrated requirement
├── tests/                     # pytest (was spike_*, run_all, harden_equivalence, ab_candidates)
│   └── … + test_audit_green.py (asserts audit.main()==0)
├── proof/fstar/               # CASL.fst, Makefile, ocaml/   [_build gitignored]
├── engine/                    # Rust reference engine        [target/ gitignored]
├── examples/                  # .casl + attacks/
├── docs/                      # ALL prose, English
│   ├── guide.md architecture.md language-spec.md vision.md
│   ├── principles.md semantics-l3.md mechanization.md
│   ├── analyses/{async,refinements,llm-operability}.md
│   └── reviews/                # red-team reviews + fix-plan (history)
├── plugin/casl-ide/
└── scripts/                   # install.sh, setup-ide.sh
```

---

## 7. Migration plan — one decisive reorg, internally audit-green

A single branch, `feat/restructure-v1`, executed decisively but committed in a **bisectable
sequence** where each commit leaves the gate green (so if anything regresses we know exactly which
step). Merge with a tag (`v0.17.0`).

1. **Hygiene.** Add `.gitignore` entries; `git rm -r --cached` the committed `fstar/ocaml/_build`,
   `engine/target`, `logs/`. *(gate: audit green)*
2. **Package move.** `git mv prototype → src/casl`; drop `casl_` prefixes; fix imports; rewrite
   `pyproject.toml` to a real package (drop `py-modules`); update the `casl` shim. *(gate: pip
   clean-venv install + `casl check` + audit + MCP selftest)*
3. **Split god-modules.** `kernel/`, `cli.py`/`check.py` split. *(gate: audit green — proves the
   registry/lookup survived)*
4. **English pass.** `async_veredelung → async_enhancement`; final AST scan = zero German in code.
   *(gate: compile + audit)*
5. **Docs move + translate.** All `.md` → `docs/` with English names and content; fix references.
   *(gate: link-check; F\* untouched)*
6. **CEP system.** `spec/cep.py` loader + schema + the proven-status audit gate; generate CEPs from
   current spec; flip source to CEP; **round-trip equivalence** `REQS_from_CEP == REQS_today`.
   *(gate: audit green incl. new CEP checks)*
7. **Tests + CI.** Spikes → `tests/`; add `test_audit_green.py`; add GitHub Actions running
   compile · ruff · mypy(dev) · pytest · audit · F\* · cargo. *(gate: CI green)*
8. **Verify + tag.** Full gate (compile · audit exit 0 · F\* 0 admits · `cargo test` · pip install
   · CLI smoke · MCP selftest · plugin.json valid); merge; tag `v0.17.0`.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| A missed reference breaks import / audit / F\* build during the move | Bisectable commits, each gated by the living audit; the audit *is* the regression detector. |
| Splitting `kernel.py` breaks the import-time registry or string lookups | `kernel/__init__.py` imports all submodules; audit green is the acceptance test for this step specifically. |
| CEP migration silently drops a requirement | Round-trip equivalence check (`REQS_from_CEP == REQS_today`) — fails the build if any fact changed. |
| New runtime dependency creeps in (e.g. PyYAML) | Frontmatter parsed by a tiny in-repo parser or stdlib `tomllib`; core stays z3-only; dev tools in an optional extra. |
| History lost on moved files | Use `git mv` throughout (preserves blame/history). |
| Structural change is itself effectful/irreversible | This is exactly a Tier-3 action in your own model → human attestation: this proposal *is* that gate. |

---

## 9. Open questions for you

1. **Repo/package name.** Keep the repo folder `LLang` (Living Language) with the Python package
   `casl`? Or rename the repo to `casl` too?
2. **`proof/` rename.** Rename `fstar/ → proof/fstar/` (room for a second prover), or leave `fstar/`
   at root?
3. **CEP numbering.** Reuse the existing IDs (CEP titled by `LH-F-010`, etc.) or assign fresh
   sequential CEP numbers with the `LH-*` id kept as an alias field? (Recommend: sequential number +
   `requirement-id:` alias, so existing references in F\*/docs keep resolving.)
4. **Target release tag** for the merged reorg: `v0.17.0` (suggested).

On approval (with any answers to the above), I will execute §7 step by step and report the gate
result after each, finishing with the tagged release.
