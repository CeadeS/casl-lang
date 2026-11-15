# CASL — The Auditable Orchestration Cockpit (Design)

**Date:** 2026-06-23 · **Reference:** `docs/vision.md` (target picture), `docs/ide.md` (monotone gate), `docs/ide-traceability.md` (line↔requirement↔commit↔bug), `src/casl/levels.py` (assurance G0–G3), `src/casl/run.py` / `src/casl/synth.py` / `src/casl/oracle.py` (the orchestration substrate).
**Status:** Draft for decision. New product-level layer that **unifies** the IDE, the traceability layer, and the oracle boundary into one auditable surface. The proven core and all gates remain untouched and are reused.

---

## 0. Mandate (in the user's words)

> *"I ask my LLM for a program and it produces artifacts. I want every line in the artifacts — **the language may be irrelevant to me** — to be traceable to a requirement and to do what I actually want; that I check it, or it is checked automatically. I want to see the code lines easily and check them myself. And I want to see the prompts and return values of the orchestrated LLM calls."*

The decisive turn: **the artifact's programming language is incidental.** The product is **not** CASL-as-a-programming-language. It is the **auditable loop**

```
requirement ──▶ LLM produces artifact ──▶ checked (auto where decidable │ human where not)
            ──▶ every line traceable to its requirement
            ──▶ every LLM call (prompt → return value) observable
```

CASL is the **harness and the spec of that loop**, not the language the artifacts are written in. This document designs the surface — the *cockpit* — that makes the loop visible and checkable.

---

## 1. The four wants → capabilities (and what already exists)

| Want | Capability | Substrate today | Gap to build |
|---|---|---|---|
| every artifact line ← requirement | line-level traceability, language-agnostic (git blame → commit → `LH-*`) | `trace.py` (`--blame`), `docs/ide-traceability.md` Phase A | author node + `realizes-line` + `untraceable` flag |
| "does what I want", auto **or** by me | per-unit **assurance grade** G0–G3 (proved/bounded/tested/attested) | `levels.py` (`ASSURANCE`, `assurance_mode`, `min_assurance`) | grade attached to *artifact units*, not only protocol features |
| see lines easily, check them myself | a **review surface**: line → {requirement, author, grade}; attested/untraced lines highlighted | — (new) | the cockpit view + an attestation action |
| see prompts & return values of LLM calls | a **structured transcript** of every call (design-time + run-time) | `run.py` (human-readable `trace`), `synth.py` (`(iter,status,feedback)`), `oracle.py` (`OracleResult.answer/cost/measured_cost/refused/raw`) | a **machine-structured, verbatim capture** of `{prompt, response, cost, verdict}` linked to step + requirement |

**Key finding (the gap is narrow and specific).** The orchestration *already happens and is already monitored*; what is missing is **structured, persisted, verbatim capture**. Today `run.py` emits a prose trace (`"• A→J: Draft ⟨oracle⟩ … → OK"`) and `OracleResult` holds the response (`raw`) and both costs — but the **prompt that was sent is not stored**, the record is **strings, not data**, and nothing links a call to the **requirement** it served or to the **artifact line** it produced.

---

## 2. The honest envelope (what "checked automatically" can and cannot mean)

Because the artifact may be in **any** language, CASL cannot *prove* that an arbitrary generated block "does what you want" — that is the verification asymmetry (`spec.py` W17: a machine cannot prove an arbitrary external program). State it plainly so the cockpit never implies more than it delivers:

**Automatic and sound:**
1. every line is **traced** to a requirement (or flagged `untraceable`);
2. the **choreography/structure** is checked by the proven gate — capabilities contained (least privilege), oracle outputs monitored at the boundary, irreversible actions approval-dominated, interface contracts SMT-checked;
3. **tests / monitors** run at the boundaries (cost metered out-of-band, blame/refusal typed);
4. each unit carries an **assurance grade** (G0–G3).

**Not automatic for arbitrary-language artifacts:** the *internal* logic of a generated block. It lands at **G2 (tested)** or **G3 (attested — you read it and sign off)**. The cockpit's whole job is to make that human check **cheap and focused**: surface *exactly* the lines that are merely attested or untraced, each next to its requirement and the prompt that produced it. "Checked automatically **or** by me" is therefore literally the **G0–G3 ladder**: the machine discharges what it can; everything else is routed to your eyes, minimised and localised.

This is not a weakness to hide — it is the product's honesty, and the reason a human-in-the-loop cockpit exists at all.

---

## 3. Data model — the Orchestration Record

One **append-only, verbatim** record per `casl run` / `casl synth` invocation (JSONL on disk; the LLM I/O is stored *exactly as sent/received* — no paraphrase, that is the point of trust).

**`OrchestrationRecord`** — `run_id`, `kind: run|synth`, `source` (the `.casl` file / project), `model`, `git_commit` (HEAD at capture), `requirement_context` (`LH-*` the run serves), `started/ended`, `status`, `events[]`.

**`CallEvent`** — one per LLM call (design-time `generate` or run-time `oracle`):

```
id, kind: generate|oracle
step           : choreography node            e.g. "A→J:Draft"
requirements   : [LH-*]                       the requirement(s) this step/artifact realizes
request        : { system, prompt, model, params }     # VERBATIM
response        : { raw, parsed:{answer,cost,refused} } # VERBATIM
cost           : { claimed, measured }        # measured = out-of-band (H4)
monitor        : { verdict: ok|blame|refusal, blame_role? }
assurance      : "G3"                         # an oracle box is G3 by construction
timing, redactions[]
```

**`ArtifactUnit`** — a generated artifact or a region of it:

```
path, anchor:{file,commit,fingerprint}        # drift-tolerant, from the trace layer
language       : "python" | …                 # incidental
produced_by    : CallEvent.id                 # PROVENANCE — the σ field (spec.py W8) put to use
requirements   : [LH-*]
assurance      : G0|G1|G2|G3
checks         : [verdict…]
review         : unreviewed|attested|rejected
```

The cockpit is the **join** of these: *per line* → requirement + grade + the `CallEvent` (prompt→response) that produced it; *per run* → the call timeline; *per requirement* → its lines, their grades, the calls behind them.

---

## 4. Architecture — capture → store → query → view

```
   casl run / casl synth                 (INSTRUMENTED — emit structured events, not just prose)
            │  CallEvent / ArtifactUnit
            ▼
   Orchestration Record  (JSONL, append-only, verbatim)         ← .casl-runs/  (gitignored by default; redaction-aware)
            │
            ▼
   trace + assurance join   (tracegraph.py + levels.py)         ← line→req→grade→producing-call
            │
            ▼
   MCP tools  (read-only over the record)                       ← editor-neutral surface
            │
            ▼
   Cockpit view   (HTML now; VS Code / Jupyter later — thin clients)
```

- **Capture** instruments the *existing* `_oracle_step` (`run.py`) and the synth loop (`synth.py`) to emit `CallEvent`s alongside the current human trace — additive, no behaviour change, gate untouched.
- **Store** is a plain JSONL run-log (`.casl-runs/<run_id>.jsonl`). Gitignored by default (it can contain prompt/response data); see §6.
- **Query** extends the trace MCP tools (`docs/ide-traceability.md` §6) with `run_record(id)`, `call(step)`, `units_by_assurance(floor)`, `needs_review()`.
- **View** is a self-contained HTML cockpit first (open-in-browser, zero install), the same data later rendered by a VS Code panel or a Jupyter widget. The editor stays a **deferred thin client** — nothing above depends on the choice.

**Two observability planes, one surface.** Design-time (`synth`: which prompt produced this artifact, which repair iterations, why accepted) and run-time (`run`: each `oracle` step's prompt→return, monitor verdict, cost). Same `CallEvent` schema for both.

---

## 5. How it stays inside the safety model

- **Monotone, outer-ring.** The cockpit *observes and routes*; it can **flag and demand review** (veto/escalate) but can **never open** the deterministic Tier-0 gate — "agents may veto, never vouch" (`docs/ide.md` §6). An attestation is a **human Tier-3** act (G3), recorded, never auto-granted.
- **Deny-by-default for review.** A unit is `unreviewed` until proven (G0/G1), tested (G2), or **attested by you** (G3). Untraced or unreviewed effect-bearing lines **block adoption**, never enable it.
- **Verbatim, append-only capture.** Trust requires you see *exactly* what was sent and returned; the record is never rewritten, only appended.
- **Assurance floor is enforceable.** `assurance_ok(proto, floor)` already exists; the cockpit exposes it per artifact — e.g. "release requires every effect-bearing unit ≥ G2, or an explicit G3 attestation with your name on it."

---

## 6. Open questions / risks (decide before building)

- **Secrets / PII in transcripts.** Prompts and responses may contain sensitive data; the `.env` endpoint and tokens must never land in a record. → redaction-on-capture (pattern + capability-scope aware), `.casl-runs/` gitignored by default, an explicit opt-in to share a record. **This is the first thing to get right.**
- **Provenance for arbitrary-language lines.** Linking an artifact *line* back to the `CallEvent` that produced it needs a provenance trailer (`Generated-by: <run_id>#<call_id>`) at adoption time — exactly the reserved **σ** field (`spec.py` W8). Without it, line→call is best-effort (diff heuristic).
- **Volume & non-determinism.** Long runs produce large records; full-fidelity vs. truncated, and how to re-run reproducibly (seed/model pinning) for an audit.
- **Attestation UX & decay.** A G3 attestation is bound to a specific line content (fingerprint); when the line changes, the attestation must **expire** (re-review), like a stale anchor in the trace layer.
- **"Any language" linting depth.** How much per-language static help (LSP passthrough to the artifact's own tools) we surface vs. staying language-agnostic.

---

## 7. Approach (onion model — one gated PR each; core + F\* untouched)

| Phase | Content | proposed requirement (→ CEP) |
|---|---|---|
| **A** | **Capture**: instrument `run`/`synth` to emit the Orchestration Record (`CallEvent` verbatim) + `casl run --trace out.jsonl`. Redaction-on-capture. No behaviour change. | **LH-G-005** (observable oracle boundary) |
| **B** | **Viewer**: self-contained HTML cockpit — call timeline, each `{prompt, response, cost, verdict}` expandable. Tangible first win. | *(realizes LH-G-005)* |
| **C** | **Trace + assurance join**: artifact units carry `requirement` + grade + `produced_by`; `needs_review()` lists attested/untraced lines; review/attest action. | **LH-P-008** (auditable artifact units) + Phase A of `ide-traceability.md` (LH-P-006) |
| **D** | **Editor thin client**: VS Code panel or Jupyter widget over the Phase-B/C tools — *decide platform here*. | *(deferred)* |
| **E** | **Self-application**: the cockpit records *its own* generation runs; CASL dogfoods the audit trail (P0). | *(P0)* |

**Smallest first slice (recommended):** Phase **A + B** — capture every LLM call verbatim and show it. It is the most concrete want, decoupled from every language/execution question, and immediately demoable: *you see exactly what the choreography says to your LLM and what comes back*.

**New requirements are proposals.** `CODEOWNERS` protects `spec.py` and `proposals/`; **LH-G-005 / LH-P-008** become authority only when you adopt them as `cep-0057 / cep-0058` with matching `spec.REQS` entries (the audit's round-trip then enforces them). Suggested seeds:

- **LH-G-005** — *observable oracle boundary*: every orchestrated LLM call is captured verbatim (prompt→response), with cost (claimed+measured), monitor verdict, choreography step, and realized requirement. Level `MUST`, verif `T`, theses `[T3, T5]`. Realized-by `orchestration_record`.
- **LH-P-008** — *auditable artifact units*: every adopted artifact unit carries requirement(s), an assurance grade (G0–G3), and provenance to the producing call; untraced/unreviewed effect-bearing units block adoption. Level `SHOULD`, verif `T`, theses `[T5, T4]`. Realized-by `artifact_units`.

---

## 8. Status

**Draft — nothing built.** The substrate is ~70 % present (orchestration runs and is monitored; assurance grades, costs, verdicts, and line↔commit↔requirement all exist). The genuinely new work is small and sharp: **structured verbatim capture**, the **artifact-unit ↔ requirement ↔ grade ↔ provenance** join, and the **cockpit view** — with the editor as the last, swappable phase. The product is the auditable loop; the artifact's language is, deliberately, beside the point.
