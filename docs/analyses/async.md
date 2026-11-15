# CASL — Async Sessions: Literature, Proposals, Assessment

**Date:** 2026-06-18 · **Reference:** `docs/analyses/refinements.md` (encapsulation principle), `prototype/semantics.py` (synchronous core), `CASL.md` from v0.1.43
**Status:** Draft for decision. Implementation of the recommended path in `prototype/semantics_async.py` (encapsulated, opt-in, deny-by-default), synchronous proven core **untouched**.

---

## 0. Question

CASL today has a **synchronous** semantics: `send`/`receive` rendezvous (one step `GMsg p q a k`). This is exactly the world in which the metatheorems (fidelity, deadlock-freedom, diamond) are proven in F*. **Async** means: `send` does not block, messages land in a queue, the receiver reads later. This is the realistic world for "multiple LLM agents at the same time, responses arriving in arbitrary order". The question is: **how do we build this in without losing provability?**

Guideline (Martin): *retain maximal safety and provability, check when in doubt, stay general — do not restrict to the secretary.* Translated: deny-by-default, encapsulated, can never weaken the default (`docs/analyses/refinements.md`).

---

## 1. Literature (synthesized)

### 1.1 Baseline — async MPST
Honda–Yoshida–Carbone (*Multiparty Asynchronous Session Types*, JACM 2016): each role pair communicates over a **FIFO queue**; `send` = enqueue + continue (non-blocking), `receive` = blocking dequeue. Four safety properties that must be preserved:
1. **Communication safety** — at dequeue the type matches (no label/type mismatch),
2. **Protocol fidelity (fidelity)** — the run follows the projected local type,
3. **Progress / deadlock-freedom** — no role waits forever,
4. **Orphan-freedom** — no message remains in a queue forever.

### 1.2 The hard wall — async subtyping is **UNDECIDABLE**
Bravetti–Carbone–Zavattaro (2017, arXiv:1611.05026) and Lange–Yoshida (2017): the asynchronous session subtyping relation is **undecidable in general** (reduction from the halting problem; unbounded FIFO queues encode a Turing-powerful counter/queue automaton). **Consequence:** a complete, terminating "is this async refinement safe?" checker **cannot exist**. This is the central fact that shapes everything — we must not promise a general async safety oracle.

### 1.3 Decidable islands (the fragments)
- **k-bounded buffers (bounded async):** every queue ≤ k. The state space becomes **finite** (for finite protocols) → reachability, orphan-freedom, deadlock-freedom all **decidable**. Price: *sound but conservative* — a protocol that is safe with unbounded buffers may be rejected at bound k, but nothing unsafe at k is accepted.
- **k-synchronizability** (Bouajjani et al. 2018; Lange–Yoshida): a system is k-synchronizable if every run is reorderable into "exchange phases" of ≤ k sends followed by their receives. Decision **PSPACE-complete**; for k-synchronizable systems, safety/reachability is decidable. This is the **principled formalization** of "async that secretly corresponds to bounded batch behavior".
- **Existential boundedness** (Genest–Kuske–Muscholl): MSC/communicating-automata view — every run has an equivalent k-bounded run. The bridge MPST ↔ communicating finite automata.
- **single-in / single-out + alternating** (Mostrous–Yoshida–Honda): syntactic fragments in which *async subtyping* IS decidable (choices are singletons / I/O alternates). Cheap to check, but very restrictive.
- **Implementability via MSCs decidable** (2023, arXiv:2302.11272): the global-type implementability question is decidable with message-sequence-chart techniques — theoretically sharper, heavier machinery.

### 1.4 Orphan messages — the design fork
Mostrous–Yoshida's async subtyping **permits** orphans (a refinement may leave messages unconsumed); Chen–Dezani et al. **forbid** them (orphan-freedom as a safety condition). For a *safety-first* language: **orphan-freedom is mandatory.**

### 1.5 How others build it
- **Scribble / mpst-Go / Rust `rumpsteak`/`sesh`:** generate FSM endpoints, async over channels; they **do not attempt** full async subtyping, but monomorphize + rely on well-formed projection + bounded channels.
- **Erlang/Akka (actors):** unbounded mailboxes, **no** static guarantee — the opposite of our goal (anti-pattern: maximal nondeterminism).
- **TLA+ / bounded model checking:** bounded search of the message buffers — exactly the "bounded reachability" tactic at the spec-tool level.

**Finding:** Nobody solves the full problem statically (because undecidable). All practical systems **bound** (buffer/fragment) or **model-check boundedly**. This is exactly our "hard barrier" path.

---

## 2. Synthesis — break down / derive / hard barrier

Martin's directive: *synthesize solutions by breaking them down or deriving them — or by building in hard barriers.* Mapping literature → CASL:

> The undecidability (§1.2) is a **hard wall**. We build **no** general async safety oracle — it provably cannot exist. The only honest options are **(a)** restrict to a decidable fragment or **(b)** bound the problem. Both are "hard barriers" in the sense of the directive. The proposals are the different barriers.

This fits the existing discipline 1:1: `metatheory.py` already does **bounded BFS** over `(gstate, config)` pairs; `stream_safe`/`concurrency_certified` reject the non-certifiable deny-by-default. Async is the same pattern, only with buffers in the state.

---

## 3. Proposals

### Proposal A — k-bounded buffers + bounded reachability gate *("k-bounded model-checking" barrier)*
- New `semantics_async.py`: async operational semantics with a FIFO queue per directed role pair, bounded by a declared **k**. `send` non-blocking (enqueue if `|queue|<k`, otherwise the protocol is rejected as *bound-exceeding*), `receive` blocking.
- Gate `async_safe(g, k)` enumerates the **finite** bounded async state space and certifies: (1) **boundedness** (no queue ever needs to grow > k), (2) **orphan-freedom** (no run ends with a non-empty queue), (3) **progress/deadlock-freedom** (every non-final reachable configuration can step). **Deny-by-default** if any check fails or the state space exceeds `max_states`.
- Prototype-feasible, literature-canonical (k-bounded). Mirrors the existing BFS pattern exactly.

### Proposal B — k-synchronizability certificate *("exchange phases" barrier)*
- Same module, but the gate certifies the stronger, named property: the protocol is **k-synchronizable** (every async run reorders into ≤k-send exchange phases). For k-synchronizable systems, the **async behavior provably coincides with the synchronous semantics up to reordering** — i.e., we **inherit the already-proven guarantees of the synchronous core**.
- Most elegant "derive from existing" option: k-synchronizability ⇒ sync safety. Harder to implement correctly (checking reordering-into-phases, not just reachability), but highest payoff.

### Proposal C — only syntactic decidable fragment (single-in/out + alternating) *("narrow gate" barrier)*
- No semantic exploration: the checker admits `async` only for protocols in the syntactically decidable subtyping fragment (singleton choices / alternating I/O); everything else is rejected by a cheap syntactic lint.
- Cheapest, obviously decidable option — but very restrictive (singleton choices), barely captures the interesting "multiple messages in flight" cases. Low payoff.

### Proposal D — no async semantics; reject the marker *("closed gate" / deferral)*
- Keep only the synchronous event loop (streams already cover long-running, event-sourced sessions). The `async` marker parses but is always rejected with a reference to streams. Zero new TCB, zero risk, zero new expressiveness.

---

## 4. Assessment

Criteria: safety/provability (primary directive), expressiveness gained, implementation cost/TCB growth, fit with deny-by-default + encapsulation, honesty (no faked proofs).

| | Safety/provability | Expressiveness | Cost/TCB | Fit (deny/encaps) | Honesty |
|---|---|---|---|---|---|
| **A** k-bounded + reachability | high (sound, conservative) | good (any bounded protocol) | medium (BFS pattern reused) | excellent | clean (by-test, F* later) |
| **B** k-synchronizability | **highest** (reduces to the proven sync core) | good | **high** (k-sync subtle, easily wrong) | excellent | clean, but overestimation **risk** if the reduction is not actually mechanized |
| **C** syntactic fragment | high (decidable) | **low** (singletons) | low | ok | clean |
| **D** no async | trivially max | **none new** | ~zero | ok | max |

Core tension: **B** is the best *theory* (directly inherits the F* proofs) but carries the greatest *risk* of a subtle prototype bug that fakes a strong guarantee. **A** is sound and conservative and fits exactly the existing by-test discipline. **C** is too narrow to justify a new module. **D** does not build what the user wants.

---

## 5. Recommendation

**A as the operative substrate + gate, structured so that B is a strictly stronger optional certificate layer on top**, with **C** as a cheap syntactic pre-lint (fast failure before expensive exploration) and **D** as the state into which the gate falls *deny-by-default*.

Concretely:
- `async` is a **per-protocol marker** (opt-in). Handled **exclusively** in `semantics_async.py` — the proven synchronous core remains **untouched**.
- Gate `async_safe(g, k)` is **deny-by-default**: a protocol runs async **only if** it is certified as *bounded-k + orphan-free + deadlock-free* (A).
- The gate **additionally reports** whether the protocol is **k-synchronizable** (B) — the stronger, sync-equivalent class whose guarantees stem from the proven core. Verdict levels: `async-rejected` < `async-bounded-safe` (A) < `async-synchronizable` (B).
- **Own, labeled guarantee** (`docs/analyses/refinements.md`): "async-bounded-safe" or "async-synchronizable" — can never weaken the default.
- **By-test** like the rest of the prototype. **F* mechanization of bounded async = tracked MAY-future, not faked.**

This is exactly the encapsulation design from `docs/analyses/refinements.md`: separate module, own labeled guarantee, opt-in marker, cannot weaken the default.

---

## 6. Requirement & Anchoring

- **LH-F-010** (SHOULD, Stage T): "async, buffered sessions — boundedly certifiable (bounded + orphan-free + deadlock-free), deny-by-default; k-synchronizability reported as the stronger class." Sources T2 (session types), T3 (runtime/resilience).
- **W16** (tension): "async subtyping undecidable (§1.2) — mitigated by bounded certification (A) + deny-by-default; full unbounded async deliberately remains out of scope."
- **Building block** `async_bounded` (kernel.py, realizes LH-F-010, principle P1/P3).
- **Audit check**: `async_safe` on the corpus — bounded-safe accepted, orphan/unbounded rejected.
- **docs/mechanization.md**: async = tracked MAY-future (F* bounded async later).
