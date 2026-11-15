# Enhancements — Implications, Encapsulation, Switchability (Analysis)

**As of:** v0.7.5. This analysis examines the three remaining, **optional** enhancements without implementing them. Goal: understand *what they cost*, *how to isolate them*, *how to switch them on only when needed*, and *what they are for*.

## Guiding Principle of Encapsulation

The **proven/checked safe core remains the default**. Every enhancement is an **opt-in extension** that (a) lives in isolation (its own module / its own marker), (b) **cannot weaken** the default path, and (c) carries its **own, honestly labeled** (possibly weaker) guarantees. This mirrors CASL's basic stance: *safe-by-default, deny-by-default, explicit opt-in for risk*.

Three possible **switching levels**:

1. **Verification depth** — offline, no runtime effect (e.g. F\* proof, differential test).
2. **Per-protocol marker** — a keyword selects the extension per spec (e.g. `async stream`), default specs untouched.
3. **Global mode/flag** — the extension is not even parseable until explicitly enabled, with its own set of gates.

---

## 1. Direction C — Full Inductive Fidelity Under Permutation (F\*)

- **Implications:** purely **proof**, no behavioral/semantic effect. Lifts `W9` from "by-test + diamond" to "fully mechanically proven". The prototype already implements the swap rule + gate; the proof is merely *additional evidence*. The only risk: the inductive F\* proof may not land cleanly (research). Cannot break the rest.
- **Encapsulation:** already maximal — lives entirely in `fstar/CASL.fst`, offline; touches neither runtime nor audit.
- **Switchable:** no runtime switch needed (level 1). "On/off" = whether one maintains the proof (`make -C fstar verify`).
- **What for:** certification/high-assurance, where "mechanically proven" is required for ≥4-role concurrency. For the everyday secretariat, by-test + diamond suffices.
- **Assessment:** safest enhancement (cannot break anything), pure proof risk. Low urgency, high elegance.

## 2. Async Stream Semantics (Variant B) — the Trickiest

- **Implications:** **new operational regime** — FIFO buffers, non-blocking sends, several sessions in flight at once. New error classes: **orphan messages** (never consumed), **unbounded buffer growth**, **async deadlock**. **Lowers provability** (async subtyping partly undecidable → more by-test/reject). Built in place, it would contaminate the clean synchronous core.
- **Encapsulation (the crux):**
  - separate module `semantics_async.py` — the proven synchronous `semantics.py` stays **untouched**;
  - per-protocol marker `async stream` (analogous to the existing `stream` flag on `Rec`) — only protocols marked this way get the buffered semantics;
  - **its own set of gates**: orphan-freedom, buffer-boundedness, async progress — all **deny-by-default** (non-certifiable async is rejected, exactly as non-certifiable concurrency is today);
  - the safety invariants (approval/capability/effect) remain valid **per handler** (as already shown for the synchronous stream).
- **Switchable:** three stages — (a) default synchronous (safe, proven); (b) `async stream` opt-in per protocol; (c) optionally an enabling flag, without which the parser rejects `async`. Weaker guarantees clearly labeled.
- **What for:** real **in-flight** concurrency — the secretary sends a reschedule to three participants, processes replies in arbitrary order, and handles new mail in parallel; real connectors (mail/calendar) **are** async (fire-and-forget, late reply). The synchronous event loop cannot "wait for an async reply in the middle of a handler" and cannot express multiple open sessions.
- **Assessment:** highest expressiveness gain, highest risk — justifiable **only** with strict encapsulation + opt-in. If built, then exactly this way.

## 3. TCB Unification / H1 — Running Checker ↔ Proven Artifact

- **Implications:** about **trust**, not behavior. Full unification (running the extracted F\* core *as* the checker) is **blocked** by the krml/Eurydice Low\* mismatch (string/ADT core) — large effort, partial benefit.
- **Encapsulation (pragmatic sub-step):** **differential test bridge** — the F\*-extracted OCaml core (`make -C fstar ocaml-run` already extracts) and the Python checker run on the **same** protocol corpus; assertion: same accept/reject verdicts. It does not unify the TCB, but **bounds** its divergence empirically (any deviation = bug in one of them). Separate offline harness, runtime untouched.
- **Switchable:** offline/CI check (level 1, like `make verify`).
- **What for:** when one must claim "the verifier you **run** is the proven one" (certification). The bridge delivers "both agree on N protocols" — a pragmatic middle ground.
- **Assessment:** the bridge = a good, encapsulated sub-step; full unification remains blocked/research.

---

## Summary & Recommendation

| Enhancement | Implication | Encapsulation | Switching level | Risk |
|---|---|---|---|---|
| Direction C | proof depth only | already isolated (`fstar/`) | 1 (offline) | proof may not land |
| Async streams | new regime, − provability | `semantics_async.py` + `async` marker + own deny-by-default gates | 2/3 (opt-in) | high — core contamination if not isolated |
| TCB bridge | trust only | separate differential harness | 1 (offline) | low (bridge); unification blocked |

**In general:** all three strictly **opt-in & isolated**; the default remains today's proven/checked safe core, which no enhancement may weaken.

**Order by safety/effort:** (i) **Direction C** (cannot break anything, pure proof risk) — if one wants proof depth; (ii) **TCB differential bridge** (encapsulated, high assurance value, medium effort); (iii) **async streams** only with the sketched strict encapsulation + `async` marker, and only once a real use case (multiple in-flight sessions) demands it.

**None is needed now** — the safe core + synchronous streams cover the secretariat. This analysis makes them buildable "on demand", without endangering the core.
