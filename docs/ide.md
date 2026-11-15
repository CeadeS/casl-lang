# CASL-IDE — Requirement-Driven Development Environment (Architecture & Approach)

**Date:** 2026-06-19 · **Reference:** `docs/vision.md`, `CASL.md` (L1), `prototype/` (substrate), `docs/guide.md`
**Status:** Draft for decision. New undertaking **above** the CASL core; the proven core and all gates remain untouched and are reused.

---

## 0. Mandate

> The user specifies **WHAT** (requirements, as authority). Oracles (Claude Code / Codex / local LLM) produce the **HOW** — artifacts that are either **deterministic programs** or **LLM boxes** — and wire them into **pipelines**. Everything non-requirement is **checked**; the oracles are **orchestrated**; the user has **heightened security**.

This is the operational form of the long-term goal (`docs/vision.md`): *requirements → verified choreographies; code/LLM/opaque uniformly behind the monitored oracle boundary; traceability enforced.* The IDE is the **interaction and orchestration layer** that makes the existing CASL core operable for precisely this flow.

---

## 1. What Already Holds (the substrate — ~70 %)

| Building block in the mandate | existing CASL part |
|---|---|
| Requirements as authority | `prototype/spec.py` (Single Source of Authority, `LH-*`); `authority.py` enforces them |
| LLM produces artifact behind a gate | `casl_synth.py` (NL → Spec → `casl check` → repair loop), backend-agnostic generator interface |
| Checking (deterministic, tool-assisted) | `casl_check.py` + `kernel.py` (projection, types, capabilities, SMT, approval dominance, concurrency, async) |
| Pipeline from nodes | CASL choreography (`casl_surface.py` → AST; roles/agents wired together) |
| Program vs. LLM box | "proven hull vs. monitored oracle boundary"; `oracle` marker + `verified` marker (Phase 4, realized) |
| Orchestrating oracles | `casl_run.py` (interpreter, tool broker, approval gates, out-of-band measurement) + `oracle.py` (backends) |
| Human gates the irreversible | approval dominance (`LH-Q-011`) + runtime default-deny + `GateDisclosure` |

The IDE thus **invents** little new; it **composes** what exists into a project/session workflow and adds two things: the **backend connection** (MCP + coder oracle) and the **Tier-2 agent review** under the monotonicity rule.

---

## 2. Guiding Decisions (fixed)

1. **Backend = MCP spine.** MCP is the open standard that Claude Code *and* Codex (and Cursor, Claude Desktop, Cowork) speak. This dissolves "independent vs. widespread":
   - **Core:** standalone CLI (runs without any proprietary program).
   - **Hull:** an **MCP server** that exposes the IDE tools (`requirements`, `check`, `synth`, `run`, `pipeline`) → every MCP client *uses* them without being bound to us.
   - **Generator oracle:** coder headless (`claude -p`, `codex exec`) or their own MCP mode, behind the existing interchangeable generator interface (Gemma/Claude/Codex/Mock).
   - **Adoption (optional):** thin Claude Code plugin / Codex snippet that registers the MCP server.
2. **MVP = interactive requirement session** (see §4).
3. **Gating = monotone layered gate** (see §3), invariant **"agents may veto, never vouch"**.

---

### Docking (MCP registration)

The MCP server (`prototype/casl_mcp.py`) is integrated vendor-neutrally via the open standard (`pip install mcp` for the transport):

```
# Claude Code
claude mcp add casl-ide -- python3 /ABS/PFAD/prototype/casl_mcp.py

# Codex  (~/.codex/config.toml)
[mcp_servers.casl-ide]
command = "python3"
args    = ["/ABS/PFAD/prototype/casl_mcp.py"]
```

Afterward Claude Code/Codex see the tools `casl_check`, `casl_gate`, `casl_synthesize`. Conversely, a local coder serves as an oracle: `oracle.CoderBackend("claude")` (or `"codex"`) as a generator (`casl_synth.ChatGenerator`) or as a Tier-2 reviewer (cross-model, generator ≠ reviewer).

## 3. Architecture — the monotone, layered gate

```
  User ── Requirement (authority) ──▶ Generator oracle (Claude/Codex/Gemma)
                                              │  proposes artifact
                                              ▼
                          Artifact = Program (hull)  |  LLM box (oracle)
                                              │
        ┌───────────────────────────── MONOTONE GATE ─────────────────────────────┐
        │ Tier 0  det. checker  (casl check: projection, types, caps, SMT, approval) │  ← only OPENER
        │ Tier 1  runtime checks (tests, monitors, tool broker, out-of-band measure) │  binding
        │ Tier 2  agent review  (Claude/Codex, different model)  → veto/escalate     │  NEVER release
        │ Tier 3  human         (irreversible/effectful action, by-exception)        │  approves
        └────────────────────────────────────────────────────────────────────────────┘
                                              │  only what passes ALL layers
                                              ▼
                              adopted artifact → Pipeline (choreography)
```

**Core invariant (monotonicity):** Each layer is a function that can only **shrink** the permitted set. The deterministic checker (Tier 0) is the **only opener**; agents (Tier 2) and the human (Tier 3) can only **revoke/escalate**. An agent vote can thus never release anything that the proven checker would not already permit — "**agents may veto, never vouch**".

**Why this way (literature, 2024–2026):**
- **Verification asymmetry:** checking is easier than generating, and the lead *grows* when the checker has tools that the generator does not (execution, types, SMT) → the checker is deterministic + tool-assisted, not an LLM judge.
- **LLM-as-judge unreliable** as a sole gate (self-preference, position, length bias; verdict flips; 60–68 % expert agreement) → agent verdict only restrictive, ideally from a *different* model than the generator.
- **HITL for the irreversible** established + regulated (EU AI Act Art. 14, NIST AI RMF), "by exception"; counter **automation bias** through concrete disclosure.

**Artifact model.** A pipeline node is:
- **Program** — deterministic, belongs in the *proven hull*; carries (in the future) the `verified` marker; is checked statically.
- **LLM box** — nondeterministic oracle; sits *behind the monitored boundary* (`oracle` marker); its output is checked at the edge against a contract (ok / Blame / Refusal), costs measured out-of-band.

**Pipeline = choreography.** Nodes are wired together via CASL messages/choices; the pipeline is well-formed as a global type (projectable, capability-contained, approval-dominated) — otherwise Tier 0 rejects.

---

## 4. MVP — interactive requirement session

A project-oriented CLI loop (working title `casl ide` or a dedicated `caslide`):

1. **Project** = a directory with `requirements` (authority), generated artifacts, a pipeline spec, a trace file.
2. **Session loop:**
   - User formulates/selects a requirement.
   - IDE asks the **generator oracle** for an artifact/a spec (reuses the `casl_synth` machinery including accumulated repair feedback).
   - **Tier 0** `casl check` gates (deterministically).
   - **Tier 2** (initially stub/optional): agent review reports findings, may escalate — never releases.
   - For an effectful/irreversible action: **Tier 3** human approves with disclosure.
   - On success: **adopt** the artifact into the project, write trace (requirement ↔ artifact ↔ verdict).
3. **Backend** initially the existing one (Mock/Gemma); coder oracle + MCP server in later phases.

The MVP is thus a **thin vertical slice** through the entire stack that orchestrates only what exists — no new core, no weakening of existing gates.

---

## 5. Approach (onion model, one PR each / gated)

| Phase | Content | new vs. reused |
|---|---|---|
| **1 (MVP)** ✅ | Project model + interactive requirement session + monotone orchestrator (Tier 0/1/3; Tier 2 = stub). Standalone CLI. | *realized v0.10.0* — `casl_ide.py`, `casl ide`, `kernel.ide_monotone_gate` |
| **2** ✅ | Tier-2 agent review real: LLM reviewer (`casl ide --review`, cross-model via `--reviewer-model`/`--reviewer-endpoint`). The reviewer oracle is DETERMINISTICALLY clamped to `{PASS,VETO,ESCALATE}` (`parse_tier2`) — an "APPROVE" never opens; on unreachability FAIL-CLOSED → ESCALATE (more human oversight). | *realized v0.11.0* — `casl_ide.llm_review`/`make_llm_reviewer`, `oracle.OllamaBackend.chat`, `kernel.ide_tier2_review`; checked live against betty |
| **3** ✅ | **MCP server** (`casl_mcp.py`: `casl_check`/`casl_gate`/`casl_synthesize` for every MCP client) + **coder backend** (`oracle.CoderBackend`: `claude -p`/`codex exec` as a generator via `casl_synth.ChatGenerator` OR as a Tier-2 reviewer, cross-model). BOUNDARY INVARIANT: the server checks/reports, never releases, executes nothing. | *realized v0.13.0* — `kernel.ide_mcp_tools`; coder checked live (claude); MCP SDK optional (`pip install mcp` only for transport) |
| **4** ✅ | **Pipeline composition**: node trichotomy (program \| LLM box \| `verified`), `verified` marker, pipeline gate `pipeline_safe` (R1 oracle⊕verified exclusive, R2 oracle monitored, deny-by-default). `verified` trust is attested by a human in the IDE (Tier 3, W17). | *realized v0.12.0* — `casl_core.verified`, `spike_pipeline`, `kernel.pipeline(_safe)`, `examples/pipeline_mixed.casl` + 2 attacks |
| **5** ✅ | Packaging (`scripts/setup-ide.sh` one-command registration; Claude Code plugin `plugin/casl-ide/`) + **self-audit** (`examples/casl_ide_pipeline.casl`: the IDE as a CASL pipeline, passes its own gate; `kernel.ide_self_audit`). | *realized v0.14.0* — P0 dogfood: the IDE checks itself with its own means |

---

## 6. Safety Invariants (carried over from CASL, central here)

1. **Monotonicity:** no layer opens beyond Tier 0 (agents veto, never vouch).
2. **Deterministic opener:** only `casl check` releases; on the proven hull.
3. **Human gates the irreversible**, by-exception, with **concrete** disclosure (against automation bias).
4. **Deny-by-default** for everything non-certifiable.
5. **Oracle output always monitored at the edge** (contract/Blame/Refusal, out-of-band costs).
6. **Cross-model review** (reviewer ≠ generator) against self-preference bias.
7. **Traceability enforced:** every artifact hangs on a requirement (Tier-0 precondition).

Desirable (research goal): **monotonicity itself** as a *checked* property of the orchestrator — the proven core decides, additional layers can provably only restrict.

---

## 7. Open Questions / Risks

- **Requirement form:** free-text (NL) vs. structured (`LH-*`-like). Proposal: NL as input, but every adopted unit gets an ID + trace (authority stays structured).
- **Generalize vs. reuse `casl_synth`:** the loop fits, but "artifact" must be extended from "choreography only" to "program | LLM box" (Phase 4).
- **Coder oracle ergonomics:** the betty retest showed that smaller models oscillate on full regeneration — for coder backends possibly patch-/diff-based editing (a separate lever).
- **Securing monotonicity mechanically:** how do we prevent a Tier-2 adapter from accidentally "opening"? (Typing the orchestrator interface: review yields only `Veto | Escalate | Pass`, no `Approve`.)
- **Naming/placement:** dedicated CLI vs. `casl` subcommand; dedicated repo directory `ide/`.

---

## 8. Status

**All Phases 1–5 realized** (v0.10.0–v0.14.0), each as a dedicated gated PR, core + proven gates untouched, audit green throughout, F\* 0 admits:

- **1** monotone gate (Tier 0–3) + requirement session (`casl_ide.py`, `casl ide`).
- **2** Tier-2 LLM review, clamped to `{PASS,VETO,ESCALATE}`, fail-closed (`casl ide --review`).
- **3** MCP server (`casl_mcp.py`) + coder backend (`oracle.CoderBackend`, claude/codex) — checked live.
- **4** pipeline node trichotomy (program | LLM box | `verified`), `pipeline_safe`.
- **5** packaging (`scripts/setup-ide.sh`, `plugin/casl-ide/`) + self-audit (P0).

**Open research edges (no blocker):** patch-/diff-based editing in the synth loop (against oscillation of smaller models); machine-checkable backing of `verified` (compositional verification instead of human attestation, W17); F\* mechanization of the monotonicity invariant.
