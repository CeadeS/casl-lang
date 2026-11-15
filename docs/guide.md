# CASL — User Guide

This guide takes you from "nothing installed" to "wrote, checked, and ran your own choreography". It is the **practical** documentation; the formal specification lives in `CASL.md` (requirements spec) and `docs/semantics-l3.md` (rules).

> **What is CASL?** A typed, choreographic language for specifying, **verifying**, and executing multiple (LLM) agents. You describe the global interplay of all roles *once*; CASL projects from it the local view of each role, statically checks that the protocol is safe and realizable, and runs it against a real or simulated oracle. Guiding principle: **prove the deterministic hull, treat the LLM as a nondeterministic oracle.**

## Contents

1. [Prerequisites](#1-prerequisites)
2. [In 60 Seconds](#2-in-60-seconds)
3. [Tutorial: Your First Choreography](#3-tutorial-your-first-choreography)
4. [Syntax Reference](#4-syntax-reference)
5. [The Verdict Model: What `casl check` Checks](#5-the-verdict-model-what-casl-check-checks)
6. [Async: Buffered Sessions](#6-async-buffered-sessions)
7. [CLI Reference](#7-cli-reference)
8. [Running Against an Oracle](#8-running-against-an-oracle)
9. [Example Catalog](#9-example-catalog)
10. [Projects & Artifacts](#10-projects--artifacts)
11. [When a File Is Rejected](#11-when-a-file-is-rejected)
12. [Further Reading](#12-further-reading)

---

## 1. Prerequisites

CASL runs on **Python 3** and the SMT solver **Z3**:

```bash
pip install z3-solver --break-system-packages --only-binary :all:
```

The CLI frontend is the shim `./casl` in the project root. A quick test:

```bash
./casl check examples/budgeted_qa.casl
```

Optional (only for the formal core or the engine, **not** needed to write/check protocols): `fstar.exe` for `make -C fstar verify`, `cargo` for the Rust engine. A real LLM oracle (`casl run --live`) needs an OpenAI-compatible endpoint in `.env` — see [§8](#8-running-against-an-oracle).

---

## 2. In 60 Seconds

A CASL file describes a protocol. Check it with `casl check` — exit `0` means accepted, `1` means rejected:

```bash
./casl check examples/budgeted_qa.casl     # ✓ ACCEPTED (Exit 0) + projected local types
./casl check examples/cap_violation.casl   # ✗ REJECTED  (Exit 1): least-privilege violation
```

For each role, `casl check` prints the **projected local type** (that role's view: what it sends/receives) and then a list of checks, each with `PASS`/`FAIL`/`WARN` and the spec requirement the verdict stems from. A single `FAIL` on a MUST gate ⇒ file rejected.

Running (a run against a simulated oracle) works with `casl run`:

```bash
./casl run examples/budgeted_qa.casl       # mock oracle: Reject → Loop → Accept
```

---

## 3. Tutorial: Your First Choreography

We build a small protocol step by step: a **client** `C` asks an **agent** `A` a question, `A` answers. Create `examples/hello.casl`.

### Step 1 — Body and Roles

Every protocol has a name and declares its roles:

```casl
protocol Hello {
  roles C, A;

  C -> A : Frage(text: Str);
  A -> C : Antwort(text: Str);
}
```

A message is `Sender -> Receiver : Label(payload);`. The payload fields carry simple sorts (`Str`, `Int`, `Real`, `Bool`). The protocol end is implicit (no `end` keyword needed). Check:

```bash
./casl check examples/hello.casl
```

`casl check` shows the projected local types — for instance `C: A!Frage(text:Str) . A?Antwort(text:Str) . end` (C sends `Frage`, receives `Antwort`) and the mirror image for `A`.

### Step 2 — A Decision (Choice)

Let `A` decide whether it can answer. In a `choice`, the **sender** decides, and the receiver learns the chosen label:

```casl
protocol Hello {
  roles C, A;

  C -> A : Frage(text: Str);
  choice at A -> C {
    Antwort(text: Str): { }
    Ablehnung(grund: Str) [len(grund) > 0]: { }
  }
}
```

Important for **well-formedness**: every role that still acts afterward must be able to locally distinguish the chosen branch (MPST *mergeability*). In this two-party case, `C` learns the choice directly from the label — fine. (If a third party kept acting after the choice without being informed about the outcome, `casl check` would reject — see `examples/non_projectable.casl`.)

### Step 3 — A Loop (rec)

If `C` should ask again on rejection, you need recursion. `rec X { … continue X; }` forms the loop; a **ranking measure** makes termination provable (SHOULD):

```casl
protocol Hello {
  roles C, A;

  C -> A : Frage(text: Str, versuche: Int);
  rec Loop measure versuche bound 3 {
    choice at A -> C {
      Antwort(text: Str): { }
      Ablehnung(grund: Str) [len(grund) > 0]: {
        C -> A : Frage(text: Str, versuche: Int);
        continue Loop;
      }
    }
  }
}
```

`measure versuche bound 3` says: the loop terminates because `versuche` strictly decreases and at most 3 iterations are possible. Without `measure`, the check still passes, but you get a **SHOULD hint** (`WARN`) that termination is not guaranteed.

### Step 4 — Tools and Effects (Capabilities + Approval)

As soon as a role uses a **tool** or performs an **irreversible** action (sending mail, rescheduling an appointment), two safety gates kick in. Tools are declared as capabilities; effectful actions must lie behind an **approval gate** with a `consent` branch:

```casl
protocol Termin {
  roles U, S, K;
  agent S caps { kalender(slot) scope "cal:write" mode write ttl 1 sig "s1"; }

  S -> U : Vorschlag(detail: Str);
  choice approval at U -> S {
    Zustimmen consent: { S -> K : Verschiebe() uses kalender irreversible; }
    Ablehnen:          { S -> K : Belasse(); }
  }
}
```

Here `Verschiebe` is irreversible and uses the tool `kalender` (`mode write` ⇒ effectful). It lies in the `consent` branch of an `approval` choice — exactly what the **approval-dominance** gate requires. If you removed `consent` or moved the action ahead of the gate, `casl check` would reject (cf. `examples/reschedule_bad.casl`).

Note that `K` receives a message in **both** branches (`Verschiebe` or `Belasse`) — this is the mergeability rule from Step 2 in action: if `K` got something only in the Zustimmen branch, it could not tell which case occurred, and `casl check` would reject as not well-formed.

That covers all the core constructs. The full grammar follows in [§4](#4-syntax-reference), and the meaning of each check in [§5](#5-the-verdict-model-what-casl-check-checks).

---

## 4. Syntax Reference

### Protocol Body

```casl
protocol Name {
  roles A, B, C;          // mandatory: declare all roles used
  env  Quelle;            // optional: environment/event-source role (for stream)
  async k 2;              // optional: opt-in async, buffer bound k (see §6)
  agent A caps { … }      // optional: capability declarations per agent
  crash A;                // optional: role may crash (for on_crash)

  <stmt>*                 // the choreography body
}
```

`async` without `k N` sets the default bound `k = 1`. Multiple `agent`/`crash` declarations are allowed.

### Capability Declaration

```casl
agent S caps {
  werkzeug(param1, param2) scope "frei:text" mode write ttl 3 sig "sig-1";
}
```

- `mode` ∈ `read | write | admin` — **default `write`**. Only `read` counts as non-effectful. An action's effect follows from this structured field, **not** from the free-text `scope`.
- `ttl` — lifetime (max uses); within a loop, `ttl ≥` the proven iteration bound must hold (SHOULD: ttl safety).
- `scope`, `sig` — descriptive strings (scope, provenance signature).

### Message

```casl
Sender -> Receiver : Label(name: Sort, …) <attribute>* ;
```

Sorts: `Int`, `Real`, `Bool`, `Str`. Attributes (freely combinable, before the `;`):

| Attribute | Meaning |
|---|---|
| `[a <= b]` / `[a >= b]` | data contract: comparison; operands are payload variables **or** integer literals (e.g. `[size <= 500]`) |
| `[len(x) > 0]` | contract: field `x` non-empty |
| `uses werkzeug` | this action uses the named capability |
| `oracle` | the payload comes from the LLM oracle (monitor boundary) |
| `irreversible` | real-world, non-reversible effect |
| `on_crash { … }` | fallback choreography if a crash-prone sender stops |

**Data forwarding (lineage).** A field may carry an earlier site's value *unchanged*, written
`name = SrcLabel.field` (or `name: Sort = SrcLabel.field`):

```casl
A -> B : Check(n: Int) [n >= 0] verified;
B -> C : Relay(n = Check.n) [n >= 0];   // Relay.n IS Check.n — carries the proved property
```

This makes the **data lineage** explicit and statically checked. When a forwarded value comes from a
`verified` site whose proved contract entails what the downstream site relies on, the grade flow-graph
(`casl flow`) soundly **re-bases** that downstream site upward (capped at G2 — the lineage is structural,
not an F\* proof). Without forwarding, the same entailment is only a *candidate* (no lineage).

### Choice (Branching)

```casl
choice at Sender -> Receiver {
  LabelA(…) [contract]?: { <body> }
  LabelB(…): { <body> }
}
```

The **sender decides**, the receiver gets the label. As an approval gate:

```casl
choice approval at U -> S {
  Zustimmen consent: { <effectful body> }
  Ablehnen:          { <safe body> }
}
```

`approval` marks the gate, `consent` marks the branch representing human consent. Effectful actions must, on every path, be dominated by such a `consent` branch.

### Recursion, Stream, Continuation

```casl
rec X measure feld bound N { … continue X; }   // loop with termination measure
rec X { … continue X; }                          // loop without measure (SHOULD hint)
stream X { choice at Env -> S { … continue X; } } // event-driven stream (§below)
continue X;                                       // back to the binder X
```

A `stream` is a **deliberately unbounded**, env-driven loop (e.g. an inbox). It is exempt from the termination obligation, but every **handler must terminate** and the loop must be driven by an `env` role (dispatch choice). See `examples/inbox.casl`.

### Language Edges (as of v0.8.x)

Three deliberate restrictions that even an LLM author must abide by — they are real boundaries of today's surface, not of the semantics:

1. **`rec`/`stream` are in tail position.** After a `rec { … }` or `stream { … }` block, **no** further statement follows. What should happen after the loop belongs in the loop's exit branches (the branches without `continue`).
2. **Contracts are exactly three forms:** `[a <= b]`, `[a >= b]` (operands each a variable or integer literal), and `[len(x) > 0]`. No other operators, no compound expressions, no `contract` keyword.
3. **No `oracle` in a `stream` handler.** An oracle promise must be redeemed exactly once on *every* path per loop iteration (promise linearity); an LLM draft in an event-conditioned stream branch violates this. Model the oracle site outside the dispatch branch.

---

## 5. The Verdict Model: What `casl check` Checks

`casl check` derives **all** roles/capabilities/crash sets from *your* file (not from a fixture) and runs authority-tagged checks. There are two classes:

**MUST gates** — a violation rejects the file (Exit 1):

| Gate | Meaning |
|---|---|
| Roles declared | every role used is declared under `roles` |
| Well-formed | projectable for every role (MPST mergeability) **and** MSC-realizable |
| Concurrency certified | role-disjoint actions commute; the global semantics (with swap rule) captures the endpoint behavior **completely** — otherwise rejection (deny-by-default). *With an `async` marker, the async gate applies instead, see §6.* |
| Stream well-formedness | only if `stream` is used: env-driven + handlers terminate |
| Capability containment | every tool use lies within the sender's capability set (least privilege) |
| Promise linearity | every oracle promise is redeemed exactly once per loop iteration |
| Approval dominance | every effectful action (`irreversible` or capability with `mode ≠ read`) is dominated by an `approval`/`consent` gate |

**SHOULD hints** — reported as `WARN`, but do **not** reject:

Termination (ranking measure) · ttl safety under recursion · crash tolerance (`on_crash`) · branch contracts enforceable.

**Basic stance "deny-by-default, when in doubt, check":** what is not certifiable is rejected — not waved through. This applies to uncapturable concurrency as well as to non-certifiable async.

> **Honest safety model.** CASL is *safe-by-lint on a verified core* — not "safe-by-construction". Machine-proven in F\* is the head-fragment core (projection/merge/progress); the capability and approval guarantees are static checks over the spec, additionally enforced at runtime (`casl run`: default-deny at the approval gate, broker-mediated tool use). Details: `README.md` and `RedTeam-Review_*.md`.

---

## 6. Async: Buffered Sessions

By default, CASL is **synchronous**: send and receive rendezvous in one step. With the opt-in marker `async [k N];`, you add a **buffered** semantics: sending does not block, messages land in a per-receiver FIFO inbox, and the receiver reads later. This is the realistic world for concurrent agents whose answers arrive in arbitrary order.

**Why opt-in and bounded?** Async subtyping is in general *undecidable* — a complete safety checker cannot exist. CASL therefore builds a **hard barrier**: a deny-by-default gate enumerates the **k-bounded** state space and assigns one of three levels:

| Level | Meaning |
|---|---|
| `async-synchronizable` | at most ≤ 1 message in flight at a time ⇒ behavior = synchronous core ⇒ **inherits** its proven guarantees |
| `async-bounded-safe` | genuinely concurrent (several in flight), but **bounded + orphan-free + deadlock-free** at bound k |
| `async-rejected` | not certifiable (reorder/deadlock, orphan, buffer > k, state explosion) ⇒ **rejected** |

The synchronous, proven core stays **untouched** — without the marker, nothing changes.

```bash
./casl check examples/async_request.casl     # async-synchronizable (sync-equivalent)
./casl check examples/async_fanout.casl      # async-bounded-safe (2 in flight, safe)
./casl check examples/async_fanin_bad.casl   # ✗ async-rejected: reordering answers → deadlock
```

**The typical trap** (`async_fanin_bad`): a client asks `A` and `B` and expects the answers in order `A`, then `B` — but both write into *one* inbox, and `B` may answer first. Then `B`'s message is at the inbox head, but the client expects `A` → blocks → deadlock → rejected. Lesson: async answers do **not** come back in request order, guaranteed. The safe pattern is fan-out to workers with **disjoint** receivers (`async_fanout`).

---

## 7. CLI Reference

All commands run through the shim `./casl` (delegating to `python -m casl.check`).

### `casl check`

```
./casl check FILE.casl [--json] [--quiet]
```

Checks the file. `--json` emits a machine-readable report (for CI), `--quiet` omits the projected local types. **Exit codes:** `0` accepted · `1` rejected (MUST violation) · `2` file not found / parse error.

### `casl run`

```
./casl run FILE.casl [--scenario S] [--budget N] [--question Q] [--max-loops N]
                     [--approve] [--live] [--model M] [--endpoint URL]
```

Checks first (MUST gate), then runs. `--scenario` ∈ `ok | overspend | refusal | retry_then_ok` (default, mock only). `--approve` is a **blanket, non-interactive** approval of all approval gates; without the flag an interactive per-gate prompt asks, and **without a TTY, default-deny applies**. `--live`/`--model`/`--endpoint` switch to a real oracle. **Exit codes:** `0` ran through · `1` rejected by the check · `2` oracle/runtime error · `3` did not reach the end.

### `casl synth`

```
./casl synth "wish in natural language" [--max-iters N] [--live] [--model M] [--endpoint URL]
```

NL → spec → `casl check` → repair loop. A generator proposes a `.casl`, the check decides, diagnostics drive the repair. **Exit codes:** `0` accepted · `1` did not converge.

---

## 8. Running Against an Oracle

`casl run` runs through the global type, calls the LLM at every `oracle` site, monitors each step (contract/blame/refusal), and follows the `choice` according to the verdict, bounded by `--max-loops`.

```bash
./casl run examples/budgeted_qa.casl                       # mock: Reject → Loop → Accept
./casl run examples/budgeted_qa.casl --scenario overspend  # oracle fails → loop bound
./casl run examples/reschedule.casl                        # approval gate: without approval → no effect
./casl run examples/reschedule.casl --approve              # with approval → consent branch runs
```

**Real oracle.** With `--live`, CASL targets an OpenAI-compatible endpoint. The default model is Gemma (`google/gemma-4-31b-it`); `--endpoint`/`--model` or the variables in `.env` (`OLLAMA_URL`) override this:

```bash
./casl run examples/budgeted_qa.casl --live
./casl run examples/budgeted_qa.casl --live --endpoint http://HOST:PORT/v1 --model NAME
```

At the **approval gate**, the interpreter never picks a silent default: it discloses the concrete action (the triggering message + the effectful step) and decides per gate. Tool use is broker-mediated — a tool not carried at runtime is denied (`tool_denied`).

**Cost/budget (H4).** The oracle reports a `cost` value itself, but this **claim** is not believed: what gets checked is the **out-of-band measured** quantity — the `completion_tokens` from the server usage. The `budget` of a `[cost <= budget]` contract is therefore a **completion-token budget**. If the claim deviates from the measurement, the trace reports both and checks against the measurement (`cost=… (gemessen; …) [Claim …≠gemessen …: Fehlmeldung]`). Choose `--budget` accordingly, on the order of expected answer tokens, otherwise the contract practically never triggers.

---

## 9. Example Catalog

All files live in `examples/`. Good for learning: first `summarize.casl` (annotated tutorial protocol), then the safety and concurrency examples.

| File | Verdict | Shows |
|---|---|---|
| `summarize.casl` | ✓ | annotated beginner protocol (budgeted summarization with check loop) |
| `budgeted_qa.casl` | ✓ | canonical: 3 roles, retry loop, data contract, oracle boundary |
| `budgeted_qa_term.casl` | ✓ | as above, with termination measure (no SHOULD hint) |
| `secretariat.casl` | ✓ | 4 roles (U/S/Kalender/Mail) with approval gate |
| `concurrent.casl` | ✓ | role-disjoint concurrency `P→Q ∥ R→S`, certified |
| `inbox.casl` | ✓ | event **stream** (`stream`), approval in the handler |
| `reschedule.casl` | ✓ | irreversible action correctly behind an approval gate |
| `async_request.casl` | ✓ | async, sync-equivalent (`async-synchronizable`) |
| `async_fanout.casl` | ✓ | async, genuinely concurrent + safe (`async-bounded-safe`) |
| `reschedule_bad.casl` | ✗ | irreversible **without** approval → rejected |
| `cap_violation.casl` | ✗ | least-privilege violation |
| `non_projectable.casl` | ✗ | not well-formed (role cannot distinguish branch) |
| `async_fanin_bad.casl` | ✗ | async reorder → deadlock → rejected |
| `attacks/*.casl` | ✗ (all) | red-team corpus: must be rejected throughout |

```bash
for f in examples/attacks/*.casl; do ./casl check "$f" --quiet; done   # every file → Exit 1
```

A full **project** — manifest + artifacts + dependency ledger + attestations, not just a single choreography — is in `examples/projects/secretariat/`; see [§10](#10-projects--artifacts).

---

## 10. Projects & Artifacts

Everything above is the **choreography layer** (`.casl` files, checked by `casl check`) — *what* happens between roles. A real deliverable is more than a choreography: it has artifact bodies (some LLM-written, some imported), dependencies, and the question of *who is accountable for each line*. That is the **project / governance layer**: a `casl.toml` manifest over a canonical layout, checked by `casl gate`.

> This layer lives on branch `feat/artifact-trust` (CEP-0057, **Informational Draft**): the mechanisms below are implemented and tested, but promoting their requirements into `spec.REQS` is a maintainer sign-off still pending. The `.casl` layer it builds on is shipped.

The governing idea (principle **P10 — accountability where proof is impossible**): for an imported library or an LLM-written module, safety never rests on a marker or on author free-text. It rests on **containment** (capability cage + approval gate + boundary monitor) plus **accountability** (line-trace + blame + a human signature bound to exact content). Proof of the *inside* is replaced by control of the *outside* and a chain of responsibility.

### Layout

`casl init <dir>` scaffolds the canonical project:

```
myproject/
  casl.toml          # MANIFEST: name, version, [attest] identity, [[artifact]] units
  requirements/      # project requirements — the human authority
  casl/              # choreographies (*.casl) — the seams, human-read
  artifacts/         # artifact bodies (one file per owned artifact, LLM-writable)
  attestations/      # one signed obligation record per unprovable artifact
  deps.lock          # dependency burden ledger
  .casl/attest.pub   # the recorded human signing identity (public part)
```

A full worked example is `examples/projects/secretariat/` — read its `README.md`.

### The manifest and the four artifact kinds

An **artifact** is a first-class named unit: a typed seam (declared in `casl/*.casl`), a body file, and an obligation record. Its `kind` (provenance) is **structured and validated** — never inferred from a name or free text:

```toml
name = "secretariat"
version = "0.1.0"

[attest]
pubkey = ".casl/attest.pub"

[[artifact]]
name        = "draft_reply"
kind        = "generated"          # external | generated | verified | oracle
requirement = "LH-LOCAL-003"
grade       = "G3"
body        = "artifacts/draft_reply.py"
```

| kind | meaning | basis | trace regime | needs a human signature |
|---|---|---|---|---|
| `external` | an imported dependency | **accepted burden** (pinned in `deps.lock`) | burden — *not* line-traced | no — one burden-acceptance |
| `verified` | a decidable property | **proof** | full | **no** — proof discharges it |
| `generated` | LLM-written, **committed by us** | **accountability** (we own it) | full | **yes**, content-bound |
| `oracle` | a live LLM call behind an owned wrapper | **accountability + monitor** | full | **yes**, content-bound |

Two rules fall out, and neither can be gamed:

- **Grade floor (LH-Q-016).** The unprovable kinds (`external`/`generated`/`oracle`) floor at **G3** whatever grade you declare — only a `verified` unit can reach G0. The project's effective grade is the **weakest link** (`casl gate` prints it): one proved unit never lifts the whole system, and laundering upward is impossible.
- **Trace follows ownership (LH-P-009), not choice.** Anything we own is line-traced; an imported package is a burden we pin and *never* line-trace. Declaring an owned artifact as a `burden` to dodge tracing is rejected. The LLM writing a file does not move it into the burden class — the human who commits it owns it.

### The dependency burden ledger (`deps.lock`)

The moment you import a library you trust it, and you cannot verify each transitive import. CASL makes that trust **visible and owned** instead of silent:

```
# name version sha256 accepted-by date
imap_client 3.0.1 sha256:6f1ed0…7d8e accepted-by:Martin date:2026-06-24
```

Every entry must be **pinned** (version + hash, so supply-chain drift becomes detectable) and **owned** (a named human accepted the burden). Unpinned or unowned ⇒ `casl deps` blocks deny-by-default; a changed hash **expires** the acceptance (re-accept required). This is deliberately *not* body attestation — that would be dishonest for code we did not write. Containment (the capability cage) is the only real lever over a dependency's internals.

### Attestation — humans sign as humans

An unprovable owned artifact (`generated`/`oracle`) carries a record in `attestations/<name>.json`:

```json
{ "artifact": "draft_reply", "sha256": "sha256:…",
  "requirement": "LH-LOCAL-003", "producer": "llm",
  "signer": "Martin", "sig_kind": "git" }
```

It is checked deny-by-default on three layers:

1. **Content-bound (LH-Q-017).** Bound to the body's `sha256`; edit the body and the hash mismatches → the attestation **expires** (re-review + re-sign).
2. **Non-self (LH-Q-018).** The producer may not attest its own output; an `llm`-produced artifact must be signed by a *human* identity distinct from it.
3. **Signed as a human (LH-Q-018).** Authenticity is a **GPG/SSH-signed git commit** (`git commit -S`) by the recorded identity — something a local agent cannot read and reuse. A plaintext key in the working tree is **rejected** as forgeable.

A signature means *a human is accountable for exactly this content* — **not** that the content is correct. The cage is the safety; the signature is the liability anchor; the trace is the blame chain.

### CLI

| command | does |
|---|---|
| `casl init <dir>` | scaffold the canonical layout |
| `casl project <dir>` | the ledger view: requirement → artifact → kind/grade/trace |
| `casl deps <dir>` | check the dependency burden ledger (pinned + owned) |
| `casl trace <file>` | every line → requirement + author + `human`\|`llm`; flags untraced lines |
| `casl blame <file> <line>` | who is accountable for a line, and how it was produced |
| `casl gate <dir>` | the **Tier-0 obligation gate**: manifest + deps + trace + attestation, deny-by-default |
| `casl seam <dir>` | typed seam: which artifact realizes which choreography site (`implements`, LH-F-012 full) |
| `casl flow <dir>` | grade **per site** along the seam edges, with re-base candidates / applied (CEP-0070) |
| `casl observe <run>` | review the captured prompt→response of each oracle call (LH-G-005) |

`casl gate` is the single opener, and it refuses until every obligation holds — including the two acts only a human can perform: committing the owned bodies (so each line traces to a requirement) and `git commit -S` on the attestations (the signature). That refusal is the design, not a defect: *agents may veto, never vouch.*

---

## 11. When a File Is Rejected

On every `FAIL`, `casl check` names the requirement and a concrete diagnosis. The most common rejections and how to fix them:

- **"not projectable / not mergeable"** — a role cannot tell, after a choice, which branch was taken. Fix: inform every still-acting role in *every* branch, by message, about the outcome.
- **"capability containment"** — an action uses a `uses werkzeug` that the sender did not declare. Fix: add the matching `agent … caps { … }` declaration.
- **"approval dominance"** — an effectful action (`irreversible` or `mode ≠ read`) does not lie behind an `approval`/`consent` gate. Fix: move it into a `consent` branch of a `choice approval`.
- **"concurrency not certifiable (incomplete)"** — the endpoints are more concurrent than the global semantics captures. Fix: make ordering dependencies explicit, or avoid concurrency across recursions.
- **`async-rejected`** — see [§6](#6-async-buffered-sessions): increase the buffer bound `k`, or restructure the protocol so no reorder deadlocks arise (disjoint receivers), or leave it synchronous (remove the marker).
- **`WARN` (SHOULD)** — not an error, but a hint: e.g. a loop without `measure`, `ttl` too small, missing `on_crash`. Fix it when the guarantee is needed.

---

## 12. Further Reading

| Document | Content |
|---|---|
| `README.md` | project overview (formal core, engine, safety model, traceability) |
| `CASL.md` | L0/L1: coarse specification + requirements spec (requirements `LH-*`) |
| `docs/requirements.md` | L2: realization per requirement (`PH-*`) |
| `docs/semantics-l3.md` | formal rules: grammar, projection, reduction, metatheorems |
| `docs/analyses/async.md` | literature + design decision on the async enhancement |
| `docs/principles.md` | first principles P0–P9 |
| `docs/mechanization.md` | F\*/Rust workflow (verified core) |

The best way to write protocols is to copy a nearby example and iterate with `casl check` — the diagnostics will guide you.
