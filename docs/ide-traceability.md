# CASL-IDE — Traceability Layer (Requirement ↔ Line ↔ Author ↔ Commit ↔ Bug)

**Date:** 2026-06-23 · **Reference:** `docs/ide.md` (the IDE substrate), `docs/vision.md`, `spec.py` (authority), `src/casl/trace.py` (existing line↔commit↔requirement), `src/casl/cep.py` (the audit-enforced governance pattern this mirrors).
**Status:** Draft for decision. New layer **above** the CASL core and **above** the existing CASL-IDE monotone gate. The proven core, all gates, and `spec.py` authority remain untouched and are reused.

> **Framing decision (2026-06-23):** we start *not* from "VS Code vs. Jupyter" but from the **platform-neutral traceability core** plus an MCP tool surface. The editor (VS Code extension or Jupyter) is a **deferred thin client** over those tools — §6. This matches the existing MCP-spine philosophy (`docs/ide.md` §2): the core is a standalone CLI/library, the hull is an MCP server, clients are interchangeable.

---

## 0. Mandate

> Humans generate code with an LLM. **CASL owns everything safety-critical** (the proven hull + the monotone gate). In the IDE, a human **follows every change** and **maps concrete lines to requirements and issues**. The graph the user named:
>
> - a **requirement** yields **lines**;
> - **lines** carry **authors** and **commits**;
> - **bugs** carry **lines**, and those carry **commits** and **affected requirements**.

This is the operational form of principle **P9** (`spec.py`: *"traceability & docs-as-code"*) and of **P0** (*self-application*): the traceability layer is itself checked, the same way the IDE checks itself (`ide_self_audit`). It extends the existing requirement **LH-P-005** (code↔commit↔requirement traceability, already realized by `trace.py`) from *coarse* (commit-level) to *line-level + bugs-as-first-class*.

---

## 1. What already holds (the substrate — ~60 %)

| Piece of the mandate | existing CASL part |
|---|---|
| line → commit → requirement | `trace.py --blame FILE` (git `blame --line-porcelain`; commit→`LH-*` from the message convention) |
| requirement → commits | `trace.py LH-F-003`; `build_index()` (`req2c`) |
| authority of requirements | `spec.py` `REQS` (single source); `authority.py` enforces it |
| commit → requirement convention | `CONTRIBUTING.md` (every commit names the `LH-*` it touches); `trace.py` verifies no commit cites a non-existent ID |
| audit-enforced governance artifact | `cep.py` + `proposals/` (schema-valid, round-trip-exact, status↔realization consistent) — **the exact pattern the `bugs/` store will copy** |
| "no untraceable artifact" discipline | the IDE's Tier-0 precondition: every adopted artifact hangs on a requirement (`docs/ide.md` §6.7) |

**What is genuinely new (the ~40 %):** (a) **authors** surfaced as a node; (b) a **line-level** requirement↔line projection that survives edits; (c) the **bug/issue entity** as an in-repo, audit-enforced artifact with **impact analysis** to affected requirements; (d) an **editor-neutral MCP tool surface** over all of it.

---

## 2. The graph (data model)

**Nodes.** `Requirement` (`LH-*`, from `spec.py`) · `Commit` (git hash) · `Author` (git identity) · `Line` (file + position — **derived, never stored as truth**, see §4) · `Bug` (`bugs/bug-NNNN.md`) · *(existing)* `Block` (kernel building block) · `Artifact` (generated unit in an IDE session).

**Edges.**

| edge | direction | source of truth |
|---|---|---|
| `realizes` | Commit → Requirement* | commit message `LH-*` (convention, verified) |
| `authored-by` | Commit → Author | git |
| `touches` | Commit → Line* | git diff / blame |
| `realizes-line` | Requirement → Line* | **derived**: lines whose blame-commit `realizes` the requirement |
| `implicated-in` | Bug → Line* | bug **anchors** (drift-resolved, §4) |
| `introduced-by` | Bug → Commit | optional, best-effort (blame/bisect of the anchors) |
| `fixed-by` | Bug → Commit* | filled on close; `status: fixed` ⇒ ≥1 |
| `affects` | Bug → Requirement* | **declared ⊇ derived** (audit-checked, §3) |
| *(existing)* `realized-by` | Requirement → Block | `cep.py` / kernel registry |

The user's three sentences map exactly: `realizes-line` (requirement→lines), `authored-by`+`touches` (lines→authors,commits), and `implicated-in`→`fixed-by`/`introduced-by`→`affects` (bug→lines→commits→affected requirements).

**Derived vs. declared.** Everything reconstructable from git is **derived on demand** (never stored, never drifts). Only *intent that git cannot know* is **stored**: a bug's identity, its declared severity/status, and its declared affected-requirements (which the audit forces to be a **superset** of the derived set — you may over-declare impact for caution, never under-declare it).

---

## 3. The `bugs/` store — in-repo, audit-enforced (mirrors `proposals/`)

A bug is a numbered Markdown file with structured frontmatter, loaded and validated by a new dependency-free `bugs.py` built as a twin of `cep.py`.

```
---
bug: 0001
title: merge drops a branch on duplicate label
status: open                      # open | fixed | wontfix | duplicate
severity: high                    # low | medium | high | critical
affected-requirements: [LH-F-006, LH-Q-001a]
introduced-commit: bbbad18        # optional, best-effort
fixing-commits: []                # status:fixed requires >= 1
anchors:                          # stable, drift-tolerant (see §4) — NOT raw line numbers as truth
  - file: src/casl/kernel/checks.py
    commit: bbbad18               # blob context at filing time
    lines: 120-134
    fingerprint: 9f3a1c…          # content hash of the anchored region
---
## Symptom / Repro
…
## Impact (derived at audit time from blame(anchors))
…
```

**Audit checks (extend `audit.py`, exactly like the CEP block):**

1. **schema** — required fields present, enums (`status`/`severity`) valid, `bug` number unique;
2. **no dangling requirement** — every `affected-requirements` ∈ `spec.REQS`;
3. **real commits** — `introduced-commit` / `fixing-commits` resolve to actual git objects;
4. **status↔fix consistency** — `status: fixed` ⇒ `fixing-commits` non-empty (and each fixing commit names the bug-id or an affected requirement, by convention — the same "machine-enforced, not prose-asserted" rule CEPs use);
5. **impact completeness** — `affected-requirements ⊇ derived(blame(anchors))`: you cannot silently under-state which requirements a bug touches;
6. **round-trip** — open bugs per requirement are surfaced in the living audit, so a requirement's risk is visible on every run.

Because `bugs.py` is dependency-free and lives in the **governance ring** (like `proposals/`), the pip-installed package never needs `bugs/` — same property `cep.py` already guarantees.

---

## 4. Line identity under edits (the crux — a decision, not hand-waving)

Absolute line numbers drift on every edit. **Decision: derive, never store, working-tree line numbers.** Stored state is stable IDs only (requirement-id, commit-hash, bug-id, file-path, content-fingerprint).

- **requirement → lines** needs *no* storage: compute live from `git blame` over the working tree and keep the lines whose blame-commit `realizes` the requirement (this is today's `trace.py` logic, just inverted and cached). Always current by construction.
- **bug → lines** stores an **anchor** = `(file, commit, line-range, fingerprint)` captured at filing time. Resolution to the *current* tree:
  1. forward-track the region with `git blame --reverse <commit>..HEAD` / `git log -L`;
  2. if edits broke the track, **re-locate by `fingerprint` + surrounding context**;
  3. if still not unique, mark the anchor **`stale → needs human re-anchor`** — **never silently point at the wrong line.**
- **renames/moves:** rely on git `-M/-C`. **History rewrites** (rebase/squash) change hashes, so anchors are keyed *also* by fingerprint and survive; a `bug_reanchor` maintenance tool refreshes stale hashes.

This keeps the audit-enforced `bugs/` artifact **drift-free**: editing code can never corrupt a bug→line link silently; staleness is *surfaced*, resolution happens at query time.

**Requirement→line granularity.** Baseline is the commit convention (every line of a commit's hunks inherits that commit's `LH-*` — zero extra burden). Optional refinement (opt-in, deny-by-default to the coarse mapping): **hunk-level requirement tags** in a commit trailer (`Trace: src/casl/kernel/checks.py:L120-134 LH-F-006`), resolved through the same anchor mechanism — chosen over inline code comments, which pollute and drift.

---

## 5. How it ties into the monotone gate (the safety invariant)

The traceability layer is **outer-ring and monotone**: it can **flag (veto / inform)** but can **never open Tier 0**. Concretely (mirrors `docs/ide.md` §6, *"agents may veto, never vouch"*):

- a **line with no realizing requirement** is *surfaced* (`untraceable`) and may **block adoption** of a generated unit — it can never *grant* trust;
- a **requirement with an open `critical` bug** is *surfaced* and may **gate** a release — never *open* one;
- the deterministic Tier-0 `casl check` remains the **only opener**; traceability/bugs sit alongside Tier 1–3 as *restrictors*.

The checkable property added here — **"no untraceable line"** (every working-tree line resolves to a commit naming ≥1 existing requirement; the rest are reported) — is the line-level analogue of the existing "every artifact hangs on a requirement." Advisory in the audit first; promotable to a Tier-0 adoption precondition later (§7 plan).

---

## 6. Editor-neutral MCP surface — and the deferred client

Extend the existing MCP server (`src/casl/mcp.py`, today `casl_check`/`casl_gate`/`casl_synthesize`) with **read-only trace tools** and two guarded write tools:

```
trace_line(file, line)        -> {commit, author, date, requirements[]}
trace_requirement(id)         -> {lines[], blocks[], open_bugs[]}
trace_bug(id)                 -> {anchors_resolved[], commits[], affected_requirements[], status}
trace_impact(bug_id)          -> affected_requirements[]          # derived ∪ declared
trace_untraceable(path?)      -> [{file, line, commit}]
bug_file(title, anchors, …)   -> writes bugs/bug-NNNN.md (a PROPOSAL; human adopts)
bug_resolve(id, commits)      -> sets status:fixed (human-gated, like a Tier-3 effect)
```

The same tools back **any** front-end identically — that is the whole point of deferring the platform pick:

- **VS Code** (thin client): gutter decorations from `trace_line`; a requirements tree from `trace_requirement`; a "bug lens" webview from `trace_bug`/`trace_impact`; a diagnostics provider from `trace_untraceable`. Best fit for cross-file line-level work.
- **Jupyter** (thin client): a `%trace` magic + `ipywidgets` over the identical tools; natural if the workflow is notebook-centric.

**Decision criteria for the eventual pick (deferred):** primary surface (codebase vs. notebooks), need for cross-file gutter mapping (favors VS Code), and where the human reviewer actually sits. Nothing in §2–§5 depends on the answer.

---

## 7. Approach (onion model — one gated PR each, core + F\* untouched)

| Phase | Content | new requirement (→ CEP) |
|---|---|---|
| **A** | Traceability backend: lift `trace.py` into a queryable `tracegraph.py` (author node surfaced, `realizes-line` cached, `untraceable` report) + JSON API. Kernel block `line_traceability`; audit check *advisory*. No UI. | **LH-P-006** (line-level traceability) |
| **B** | `bugs/` store + dependency-free `bugs.py` (twin of `cep.py`) + audit wiring (§3). Kernel block `bug_traceability`. | **LH-P-007** (bug entity + impact analysis) |
| **C** | MCP trace tools (§6) added to `mcp.py` — still editor-neutral. Boundary invariant unchanged: the server **reports**, never releases, executes nothing. | *(realizes existing LH-G-001 IDE reqs)* |
| **D** | Editor thin client — **decide VS Code or Jupyter here**, build the view layer over Phase-C tools. | *(deferred)* |
| **E** | Self-application: the IDE traces *itself* (bugs/ + line-traceability green on this repo), the way `ide_self_audit` already dogfoods the gate. | *(P0)* |

**New requirements become CEPs you approve.** `CODEOWNERS` protects `spec.py` and `proposals/` — so LH-P-006/007 are *proposed* here and only become authority once you adopt them as `proposals/cep-00NN-*.md` with matching `spec.REQS` entries; the audit's round-trip then enforces them. This doc enacts nothing.

Suggested CEP seeds (subject to your call on level/stage):

- **LH-P-006** — *line-level traceability*: every working-tree line maps to ≥1 requirement via its commit; untraceable lines flagged. Level `SHOULD` (path to `MUST`), verif `T`, theses `[T5]`. Realized-by `line_traceability`.
- **LH-P-007** — *bug entity + impact analysis*: bugs are audit-enforced artifacts; declared affected-requirements ⊇ derived; status↔fix consistency. Level `SHOULD`, verif `T`, theses `[T5, T3]`. Realized-by `bug_traceability`.

---

## 8. Open questions / risks

- **Hunk-level granularity ergonomics** — commit-trailer tags are precise but add author burden; is the coarse commit-level mapping enough for the first cut? (Proposal: yes; refine only where a requirement's lines must be pinpointed.)
- **Squash/rebase** — fingerprint-keyed anchors survive hash changes, but a noisy `git config` (e.g. `rerere`, heavy `-C`) can confuse re-anchoring; needs a `bug_reanchor` cron and a "stale anchors" audit line.
- **Author identity** — git `author` vs. `committer` vs. mailmap; co-authors (`Co-authored-by`) for LLM-generated hunks. Decision needed: does an LLM-produced line get attributed to the human operator (likely yes, with a `Generated-by:` trailer for provenance — ties to the reserved `σ` provenance field, `spec.py` W8).
- **"No untraceable line" as a hard gate** — promoting it from advisory to a Tier-0 adoption precondition is a real tightening; stage it behind a profile flag first.
- **Bug ↔ requirement when the bug is in the *spec*** — some bugs are requirement defects, not code defects (no anchor lines). The schema must allow an anchor-free bug whose `affects` is purely declared.

---

## 9. Status

**Draft.** Nothing built yet; this is the design to react to. The substrate (`trace.py`, `cep.py`, the MCP server, the monotone gate) already carries ~60 % of the machinery; the new work is authors-as-node, line-stable anchoring, the `bugs/` artifact, and the MCP tool surface — the editor itself is deliberately the *last*, swappable phase.
