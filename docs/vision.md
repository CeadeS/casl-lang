# CASL — Vision & Process Model (Onion Layer 0)

**Project:** CASL (*Choreographic Agent Specification Language*)
**Document type:** Vision / process model — **outermost layer** (above L0/L1)
**Version:** `0.1.0` · **Status:** Draft · **Date:** 2026-06-17

> This document is the **coarsest** level of an onion/pyramid model. It records the goal and what we still need **deliberately coarsely**. The level of detail is only increased once the respective outer layer is complete (§4). More concrete levels lie further inward: `CASL.md` (L0/L1) → `docs/requirements.md` (L2) → `docs/semantics-l3.md` (L3) → `.casl`/code/tests.

---

## 1. Vision (coarse)

A developer describes a wish in natural language. Developer **and LLM co-develop** a requirements and specification document from it. From this a **strictly derived, intrinsically well-formed "program"** (working name: *choreography* / *choreo*) is generated — written by an LLM, but mechanically checked against the specification. Through the user's follow-up questions and tests, the requirements are refined until the program is finished.

The goal is **not** "the LLM writes code that we trust", but rather: *the LLM proposes, the verifier decides, the human approves what is irreversible* — at every level.

## 2. Guiding Principle & Generalization

CASL separates the **proven deterministic hull** from the **nondeterministic, monitored oracle boundary**. This principle applies at **two** places (two-oracle principle):

- **Design time:** the LLM writes the specification and `.casl` program → gated by `casl check` (only what is well-formed is accepted).
- **Runtime:** the LLM performs an `oracle` step → monitored by monitor/contract/blame.

**Generalization (artifact as box):** what sits behind a tool call is always a *box* — regardless of whether it is (a) deterministic code, (b) an LLM call, or (c) an **opaque program written by an LLM** whose internals we cannot know. CASL treats all three **identically**: typed, capability-bounded (least privilege), contract-monitored, blame-localized. The **enforced traceability** (every box hangs on ≥1 requirement; every dangerous action on a gate) makes development safe — **independent of the transparency** of the artifact. This is exactly the lever that makes the process model general and future-proof.

## 3. What We Still Need (coarse)

- **NL → specification:** a generator that proposes a requirements/specification document + `.casl` from the wish — with `casl check` as the **acceptance filter** and the human as co-author.
- **Richer contracts + a real tool layer:** beyond budget contracts; capabilities that map onto real connectors (mail, calendar, …).
- **Event-driven, long-running sessions:** an inbox is a *stream*, not a single run (beyond the proven synchronous core).
- **Approval & effects as first-class, audited constructs:** the invariant "**effectful action ⇒ dominated by an approval node (consent branch)**" (deny-by-default, `LH-Q-011`). Statically checked (safe-by-lint) AND enforced at runtime: human at the gate (`LH-Q-011`, default-deny) and the tool broker (`LH-Q-014`) are implemented (`C3`/`H3` closed since v0.x).
- **Semantic checking (content quality):** metamorphic tests / LLM judge (`LH-Q-007`) — which proofs fundamentally cannot deliver.

## 4. The Onion Model (process)

We work from the outside inward and **only increase the level of detail after completing the respective outer layer**:

- **Layer 0 — Vision (this document):** goal + coarse gaps + guiding principle. *(now)*
- **Layer 1 — Load-bearing concepts/invariants:** the few ideas on which everything rests (artifact-as-box; two-oracle; approval dominates effects (deny-by-default); NL→spec with check gate) — still without detailed requirements.
- **Layer 2 — Requirements (L1):** coarse, checkable requirements per concept (to be hooked into `CASL.md`).
- **Layer 3 — Specification (L2):** realization per requirement (fragment/contract/monitor/capability/generator).
- **Layer 4 — Formal + code:** `.casl`, rules, engine, tests; the living audit as a regression gate.

Each layer remains **traceable** outward and is released via the existing **PR/approval workflow**. Thus, what the process model produces also holds for the process model itself: strictly derived, traceable, gated.

## 5. Honest Limits

CASL is **safe-by-lint on a verified core** — *not* "safe-by-construction" and certainly not content-correct-by-construction (Red-Team v0.1.27, honest assessment). **Mechanically proven** (F\*, 0 admits) is the structural **hull**: projection/merge, well-formedness/realizability, numeric contracts, and SUBJECT REDUCTION for the full calculus incl. recursion (`preservation_full`); progress + operational correspondence are head/rec-free-scoped. **Statically checked, but not proven** (Python lint over the spec) are least-privilege containment, promise linearity, termination, and **approval dominance**. **Enforced at runtime** is approval since v0.6.4 (default-deny at the gate, human/`--approve`); tool confinement (broker, `LH-Q-014`) is implemented; the running checker is bound to the proven artifact by the authoritative extracted F\* checker (`CEP-0009`, in-fragment) cross-checked by the TCB differential bridge (412/412) — full extraction-to-Rust TCB unification remains open (`TBD-004`). Whether a generated mail is *good* or a reschedule is *sensible* remains a semantic property of the oracle — secured by monitors, tests, and human approval, not by proofs. The decisive lever for autonomous agents: the feared error (sending/rescheduling without being asked) is **denied default-deny at the gate**, instead of being permitted by a structural default — while quality rises iteratively.

## 6. Motivating Example (coarse)

An **autonomous secretariat**: reads mail, knows the calendar/contacts/notes; drafts, checks, and sends mail when the user is not needed; updates the calendar; reaches out **only** via messenger when appointments are to be rescheduled (with consequences) and waits for approve/deny; upon consent, tries to reach the participants and reschedules; fends off spam/callers; raises the quality of the scheduling. From this wish, requirements and specification documents are derived and gradually refined into a checked, executable choreography.

## 7. Open Decisions (Layer 0)

- **`TBD-V-001` Name** of the "programs": *choreography* (technical term) vs. *choreo* / *procedure* / *protocol*.
- **`TBD-V-002` Place of the human:** approval for *every* irreversible action, or only above a risk/cost threshold (which would itself be a contract)?
- ~~**`TBD-V-003` First concrete building block:** the invariant "irreversible ⇒ dominated by approval" as a checkable well-formedness rule~~ — **done** as `LH-Q-011` (static: `kernel.approval_safety`; runtime: `kernel.runtime_approval`, default-deny). Generalized to *effectful* (deny-by-default).

*End of Layer 0 (v0.1.0).*
