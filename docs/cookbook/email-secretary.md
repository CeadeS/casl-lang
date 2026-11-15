# Case Study — "Email Secretary" in CASL

**Date:** 2026-06-23 · **Reference:** `docs/cockpit.md`, `docs/ide.md`, `docs/guide.md`, examples `email_assistant.casl` / `meeting_scheduler.casl` / `expense_approval.casl`.
**Status:** Worked example. Two core flows are **machine-checked** (`casl check`, ✓ ACCEPTED, 2026-06-23); the remaining flows are CASL sketches in the same idiom.

This takes one real, messy request and plays it through the CASL approach end to end — what the proven gate *guarantees*, what stays a *monitored oracle*, what needs *your button*, and the honest *gaps* it surfaces.

---

## 0. The request (verbatim, then decomposed)

> A web server that loads my email from several providers; a push notification via Telegram/WhatsApp/Mattermost when important mail arrives; mail auto-sorted into folders on my webmail; short summaries; on reply, an LLM drafts an answer depending on which button I click — a *reject* button, an *accept* button, an *analyze-the-work, measure it against my standards, and produce a short reply* button, and a *direct reply* button; if I answer a Telegram/WhatsApp/Mattermost message, the answer is turned into a proper email with salutation and sent; a served calendar auto-reconciled with my committed emails; and I want to be **prevented from confirming slots that are already booked**.

| # | Feature | CASL mechanism | Assurance |
|---|---|---|---|
| R1 | Multi-provider email ingest (web server) | **hull** programs (IMAP connectors) as roles behind `mail:readonly` caps | G2/G3 (tested/attested) |
| R2 | Push on *important* mail | `oracle` classify + **hull** push behind `msg:send` cap | oracle G3 |
| R3 | Auto-file into folders | `oracle` suggests folder + `mail:move` (mode write) effect | oracle G3 + gate |
| R4 | Short summaries | `oracle` summarize, bounded by a `[size <= cap]` contract | oracle G3 |
| R5 | **Four-button reply** | `choice at U->S` (4 buttons) + `oracle` draft + **approval-gated** `mail:send` | **✓ checked** |
| R6 | Chat→email with salutation | `oracle` convert + **approval-gated** `mail:send` | sketch (same shape as R5) |
| R7 | Calendar reconciled with commitments | `oracle` detects commitment + `cal:write` | oracle G3 + gate |
| R8 | **No double-booking** | data contract `[conflicts <= 0]` + **approval-gated** `cal:write` | **✓ checked** |

---

## 1. What CASL is — and is *not* — in this app

CASL is **not** the web server, the IMAP/SMTP client, the Telegram bot, or the calendar server. Those are **deterministic "hull" programs** (or external services) that sit behind **capabilities**. CASL is the **choreography + safety harness** over them: it specifies *who may do what, in what order, with which effect, gated by whom* — and treats every LLM step as a **monitored oracle**. The artifact code for the connectors can be in **any language** (that is the point of `docs/cockpit.md`): CASL gates the *structure* and traces every line to a requirement; the connector's internal logic is tested (G2) or attested (G3), not proven.

So "use CASL for it" = **CASL owns the dangerous seams** (sending mail, moving mail, booking calendar, spending budget, pushing notifications) and orchestrates the LLM; the plumbing is hull code under least-privilege capabilities.

---

## 2. The cast (roles, agents, capabilities — least privilege)

| Role | Who | Capabilities (mode → effect) |
|---|---|---|
| `U` | You (the human) | — (you decide at gates / press buttons) |
| `S` | Secretary agent (LLM-backed) | `inspect mail:readonly` (read), `compose llm:compose` (read), `send mail:send` (**write**), `lookup cal:readonly` (read), `calendar cal:write` (**write**), `move mail:move` (**write**), `push msg:send` (**write**) |
| `M` | Mail connector(s) (hull, per provider) | — (receives S's effect requests) |
| `K` | Calendar (hull) | — |
| `N` | Messenger (Telegram/WhatsApp/Mattermost, hull) | — |

Every **write** capability is a place CASL forces an **approval gate** in front of an irreversible action (R-H1: effect follows from the structured `mode` field, never from a free-text scope string — that was the W14 vulnerability). Least privilege is a MUST check: `S` literally cannot use a capability it did not declare, and at runtime the tool broker (`LH-Q-014`) denies any undeclared tool.

---

## 3. The punchline: your **buttons are the approval gates**

The most important mapping in this whole example: **every button that triggers an irreversible effect is a CASL approval gate** (`LH-Q-011`, "approval dominance"). The send, the booking, the folder move — none can happen on a structural default; each demands an explicit `consent` decision that you make. CASL *statically rejects* any protocol where an effect-bearing action is reachable without a dominating approval gate. You don't have to remember to add the confirmation — the checker refuses the file without it.

---

## 4. R5 — the four-button reply (machine-checked)

`examples/email_secretary_reply.casl` — `S` summarizes (monitored oracle, bounded), then you press one of four buttons; the three reply buttons each draft via the LLM and put the **irreversible send behind an approval gate**:

```
M -> S : Arrived(subject: Str, cap: Int);
S -> U : Brief(summary: Str, size: Int) [size <= cap] uses inspect oracle;
choice at U -> S {                              // ← the four buttons
  Reject:  { S -> M : FileAway(); }
  Accept:  { S -> U : Draft(text: Str, size: Int) [size <= cap] uses compose;
             choice approval at U -> S { Send consent: { S -> M : Deliver() uses send irreversible; }
                                         Hold:         { S -> M : Keep(); } } }
  Analyze: { S -> U : Short(text: Str, size: Int) [size <= cap] uses compose;
             choice approval at U -> S { Send consent: { S -> M : Deliver() uses send irreversible; }
                                         Hold:         { S -> M : Keep(); } } }
  Direct:  { S -> U : Reply(text: Str, size: Int) [size <= cap] uses compose;
             choice approval at U -> S { Send consent: { S -> M : Deliver() uses send irreversible; }
                                         Hold:         { S -> M : Keep(); } } }
}
```

**Real `casl check` verdict (2026-06-23):** ✓ **ACCEPTED**. The checker projects each role's local view automatically — note how `M` (the mail connector) sees a clean external choice, which is *why* the 4-way choreography is realizable:

```
M: S?Arrived(subject,cap) . S&{ FileAway(): end  Deliver(): end  Keep(): end }
```

All MUST checks pass, including **Approval dominance (LH-Q-011)**, **Capability containment (LH-F-005)**, **Promise linearity** (the summary oracle resolves exactly once), and **Well-formed (projectable + MSC-realizable)**. Footer: `profile=advisory, assurance=G3, features={nary_choice, oracle}, Trust budget: oracle:attested` — i.e. the *structure* is gate-proven; the residual trust is the LLM content, which lands on **you** (the buttons).

> A real bug this surfaced: I first named a field `len`, which collides with the `len(...)` keyword — `casl check` rejected it instantly (`parse error: Expected '(', found '<='`). Exactly the kind of thing the planned LSP would underline inline.

---

## 5. R8 — refuse to confirm an already-booked slot (machine-checked)

`examples/calendar_guard.casl` — the double-booking guard is the data contract `[conflicts <= 0]`: `S` reads the calendar and reports the conflict count for the requested slot; the flow only stays well-formed when the slot is free, and the booking is *also* behind an approval gate:

```
U -> S : Commit(detail: Str);
S -> U : Slot(conflicts: Int) [conflicts <= 0] uses lookup oracle;   // ← double-booking guard
choice approval at U -> S {
  Book consent: { S -> K : Reserve() uses calendar irreversible; }
  Hold:         { S -> K : Pass(); }
}
```

**Real `casl check` verdict (2026-06-23):** ✓ **ACCEPTED**; `[conflicts <= 0]` is checked as an SMT data contract, **Approval dominance** passes (the irreversible `Reserve` is gated), `K` receives a distinguishing label on both paths (`Reserve`/`Pass`). So you are prevented from confirming a booked slot two ways at once: the contract makes "confirm with conflicts" ill-formed, and the booking still needs your consent.

---

## 6. R6 — chat → proper email (sketch, same shape as R5)

Answering on a messenger and having it become a salutation-correct email is *structurally identical* to a reply button: an `oracle` converts the chat text, the **send is approval-gated**. It therefore inherits R5's guarantees verbatim:

```
N -> S : ChatReply(text: Str, cap: Int);
S -> U : AsEmail(body: Str, size: Int) [size <= cap] uses compose oracle;
choice approval at U -> S {
  Send consent: { S -> M : Deliver() uses send irreversible; }
  Hold:         { S -> M : Keep(); }
}
```

---

## 7. What the cockpit shows for this app

Running any of these against the real oracle (`casl run --live`, betty/Gemma) produces, per `docs/cockpit.md`, a structured record where **every LLM call is captured verbatim and tied to its requirement and your button**:

- the **summarize** call (R4) → `{prompt, response, cost}` under R4;
- the **draft / short / convert** call (R5/R6) → the exact prompt and the produced draft, *next to the Send/Hold button you pressed*;
- the **conflict lookup** (R8) → the calendar read and the reported count.

So "I want to see the prompts and return values of the orchestrated LLM calls" is literally the cockpit's call timeline; "I want to check the lines myself" is the review surface where each drafted reply waits for your attestation (G3) before the gate can open.

---

## 8. Honest gaps this example surfaces (useful — they drive the roadmap)

1. **Contracts can't talk about external state.** The double-booking guard is encoded as a *count* `[conflicts <= 0]`; it relies on the hull `lookup` returning an honest count. CASL cannot *statically* prove "the calendar has no conflict" — that is dynamic state. This motivates a richer (still SMT-decidable) **predicate library** and a `verified` guard node, not a bigger trusted base.
2. **Only `Str`/`Int` today.** Real email metadata (addresses, lists of recipients, folders) wants `Bool`/`List`/`Record`. Until then, fields are flattened (a summary is a `Str`, a conflict set is a count). A small, decidable **value layer** is the language-side work.
3. **"Important" is an LLM judgment.** R2's classification is a G3 oracle verdict, not a proof — it is monitored (blame/refusal) and surfaced, never trusted blindly.
4. **Multi-provider = multiple connector roles** (or one parametric `M`); the choreography is already role-parametric (see `secretariat.casl`, 4 roles), so this scales, but per-provider auth/quirks live in hull code.
5. **The plumbing is hull/attested.** The web server, IMAP/SMTP, the Telegram/WhatsApp/Mattermost bridges, the calendar server — generated code in any language, **traced** to a requirement (`docs/ide-traceability.md`) and **tested/attested**, not proven. CASL guarantees the *seams*, not the internals of an arbitrary program (the W17 honesty).

---

## 9. Summary — what "use CASL for it" actually buys you

- **No mail is sent and no slot is booked without your explicit consent** — guaranteed structurally (approval dominance is a MUST check; the checker refuses any file that violates it).
- **The secretary can only touch what it declared** — least-privilege capabilities, runtime-brokered.
- **Every LLM step is monitored and metered**, and **captured verbatim** for you to inspect.
- **Every artifact line traces to a requirement**, language-incidental.
- **The double-booking guard is explicit and checkable.**

What CASL does *not* do is prove the LLM's content or the connectors' internals — those are tested or attested by you, and the cockpit's job is to make that review cheap and focused. Two of these flows are not a promise — they are `✓ ACCEPTED` on your machine today (`examples/email_secretary_reply.casl`, `examples/calendar_guard.casl`).
