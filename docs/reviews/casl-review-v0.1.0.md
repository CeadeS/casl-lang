# Review — CASL Coarse Specification & Requirements Document v0.1.0

**Document reviewed:** CASL — Coarse Specification & Requirements Document, `v0.1.0` (draft), 2026-06-15
**Review date:** 2026-06-15
**Review scope:** standards conformance (ISO/IEC/IEEE 29148, DIN 69901-5, VDI/VDE 3694, BCP 14), internal consistency & traceability, requirement quality, technical soundness, source verification
**Finding scheme:** `R-<sev><n>` — C = critical, H = high, M = medium, N = low

---

## 1. Overall impression

For a first version the document is unusually mature and internally coherent. The refinement ladder (L0→L1→L2→L3), the stable ID scheme, the idea of encoding the **verification method simultaneously as a provability level** (B/S/M/T), and the docs-as-code discipline (Git + SemVer + requirement ID) are sound and conceived in conformance with the standards. The technical foundation (Session Types / MPST, projection, refinement contracts via SMT, monitoring with blame at the oracle boundary) is genuinely well-founded and the cited literature largely exists as stated.

The findings below therefore concern **no** fundamental construction errors, but rather (a) one factual misattribution of a source, (b) several places where the document does not yet meet its **own** rules (mandatory attributes, traceability), and (c) refinements of requirement atomicity and terminology. Most are closable in a v0.1.1 patch.

---

## 2. Strengths (deliberately retained)

- **Provability-driven verification matrix** (§4.4): B/S/M/T directly on the requirement attribute is elegant and makes testability derivable from the structure (LH-Q-006) — this is the strongest design feature.
- **Oracle principle** (LH-G-002): the clean separation "prove the deterministic hull / monitor the LLM as a nondeterministic oracle" is carried consistently through the whole document.
- **Standards framework**: 29148 attributes, BCP-14 levels, DIN-69901-5 role separation of requirements/specification document, SemVer baselines — correctly referenced (see §4 source verification).
- **Honest open-item tracking** (§8 TBD/TBR) with cross-refs out of the requirements (e.g. LH-Q-008 → TBR-002).

---

## 3. Findings

### Critical

**R-C1 — Misattribution of source [5] in §9** · affects `LH-Q-002`, `LH-F-005`, capability model
The informative reference "**L-CAC** / Formal Security Framework for MCP-Based AI Agents — arXiv 2604.05969 (capability set `(tool, params, scope, ttl, σ)`)" is misattributed. The arXiv ID **exists** and is correctly dated (April 2026), but the paper is titled *"A Formal Security Framework for MCP-Based AI Agents"* (Acharya & Gupta). In it:
- the framework is called **MCPShield**, not "L-CAC" (the name "L-CAC" does not appear in the paper);
- the formal model is the tuple **`M = (A, S, T, R, C, ℓ)`** plus an LTS; the cited capability tuple **`(tool, params, scope, ttl, σ)` does not appear there**.
*Why critical:* in a document with normative ambition, an invented/misattributed source is a credibility risk and undermines its own traceability requirement (LH-P-004).
*Fix:* either (a) correct the reference to the real paper (name MCPShield, model `M=(A,S,T,R,C,ℓ)`) **and** cite the true source of the tuple `(tool, params, scope, ttl, σ)` — or, if this tuple is CASL's **own** capability model, explicitly mark it as an original design instead of attributing it to a third-party source.

### High

**R-H1 — Source codes `T1`–`T5` are defined nowhere** · affects all requirements in §6
Every requirement carries `Source: T1…T5`, but the document contains **no legend** for what T1–T5 are (presumably the five upstream theses). The mandatory attribute "Source" (§4.3) is thereby effectively unresolvable and the required **bidirectional** traceability (LH-P-002) upward is broken — the document violates its own requirement here.
*Fix:* add a table `T1 = …, T2 = …` in §3 or §4.5 and ideally include an upstream column in the RTM.

**R-H2 — §6 lacks the mandatory attributes prescribed in §4.3** · affects all requirements, `LH-P-001`
§4.3 requires per requirement *at least* ID, title, level, text, **rationale**, source, verification, **status**, **introduced-in-version**. The entries in §6 carry only ID/title/level/source/verif/text — **rationale, status and introduced-in-version are missing throughout**. The document thereby violates LH-P-001 against itself.
*Fix:* either set the uniform fields globally (status = draft, introduced-in = 0.1.0) and add only the **rationale** per requirement (at least one sentence "why this requirement"), or reduce §4.3 explicitly to the attribute set actually maintained.

**R-H3 — "Provability triad" names three, lists four** · §4.4
The heading says *triad*, but the section defines **four** methods (B, S, M, T).
*Fix:* rename to "provability **tetrad**" or, neutrally, "verification/provability levels".

### Medium

**R-M1 — Several requirements are not singular (29148 "singular")** · `LH-F-002`, `LH-Q-001`, `LH-Q-003`, `LH-F-004`, `LH-F-007`
29148 requires *one* verifiable statement per requirement. Several bundle separately verifiable properties:
- `LH-F-002` mixes a normative requirement ("the type MUST be a session type") with two **definitions** ("data types classify…", "interfaces are protocols") → move definitions to §3, isolate the requirement.
- `LH-Q-001` bundles protocol conformance + deadlock freedom + session fidelity — three different theorems/proofs.
- `LH-Q-003` bundles promise discharge (exactly once) + fulfillment of every interface obligation.
- `LH-F-004` / `LH-F-007` analogously.
*Fix:* split into sub-IDs (e.g. `LH-Q-001a/b/c`) so each property gets exactly one verification line in the RTM.

**R-M2 — RTM covers only 6 of ~24 requirements** · §7
The matrix lists `LH-F-002, LH-Q-002…006`. All other B-/T-/M-verifiable requirements (incl. all `LH-G`, `LH-F-001/003/004/006/007`, `LH-Q-001/007/008`, all `LH-P`/`LH-C`) are missing. Acceptable for a *template* in v0.1.0 — but LH-P-002 makes the RTM the central artifact.
*Fix:* mark §7 explicitly as an "incomplete template", add an **upstream column (T source)**, and in the roadmap (Appendix A) fix full coverage as a v0.2.0 acceptance criterion.

**R-M3 — BCP-14 legend without negative forms** · §4.1 vs. `LH-Q-002`
§4.1 defines only MUST/SHOULD/MAY. `LH-Q-002` however uses the prohibition form ("No agent **MAY** … call"). RFC 2119/8174 also covers MUST NOT/SHOULD NOT.
*Fix:* add "MUST NOT" and "SHOULD NOT" in §4.1.

**R-M4 — 29148 quality list in §4.3 is imprecise** · §4.3
The stated goals "unambiguous, singular, complete, feasible, verifiable, **traceable**" mix five genuine 29148 characteristics for individual requirements with "traceable", which in 29148:2018 is **not** among the nine individual-requirement characteristics; at the same time *necessary, appropriate, correct, conforming* are missing.
*Fix:* either mark as "incl." or align to the nine 29148 characteristics (traceability belongs to the set/management level, cf. LH-P).

### Low

**R-N1 — Separate MSC ≠ MPST cleanly** · §9, §5
Source [Provable Coordination, 2604.17612] is based on **Message Sequence Charts**, not Multiparty Session Types. Both know "projection" but are different formalisms. The document should make clear that it draws on **two related but distinct** projection traditions (MPST/Scribble *and* MSC). (Plus point: the MSC paper is mechanized in **Lean 4** — relevant for the host-language decision TBD-004.)

**R-N2 — Crash and refusal are different error classes** · `LH-F-007`
Placing "crash" (process stops → structurally typeable, **B**, cf. Generalised MPST w/ Crash-Stop) and "refusal" (oracle refuses → runtime event, **M**) under a single SHOULD requirement with verif `B/M` conflates the provability levels.
*Fix:* separate into `LH-F-007a` (crash tolerance, B) and `LH-F-007b` (refusal handling, M).

**R-N3 — Maturity of λPrompt overstated** · §9
Source [λ-Prompt, 2508.12475] exists but is an extended abstract; the author himself describes λPrompt as "not yet a full calculus".
*Fix:* soften from "dependently typed calculus" to "proposed / in-development type-driven prompt calculus".

**R-N4 — Make promise linearity precise** · §3, `LH-Q-003`
"Future, linear resource (discharged exactly once)" should distinguish between **write-once** (resolution) and **read-once** (consumption) — a future is typically *written* once but possibly *read* multiple times. Strict read-once is a design decision that should be made explicit (L2).

**R-N5 — "Baseline: yes" vs. release "open"** · document control
A configuration baseline (ISO 10007) usually implies a release; but the release table is "open".
*Fix:* clarify whether v0.1.0 is a genuine CM baseline or only an internal draft snapshot.

**R-N6 — Small items** · various
(a) §5 and Appendix A use "1./1./1." instead of consecutive numbering (cosmetic, Markdown re-renders depending on the renderer). (b) Note: IEEE 828-2012 is now *inactive/reserved* and is titled "…in Systems and Software Engineering" (no longer just "Software CM Plans") — update at the next revision of the standards list. (c) LH-Q-004: name the targeted decidable SMT fragment (e.g. QF_LIA/EUF) in L2.

---

## 4. Source verification (§9 informative, §2 normative)

All arXiv IDs were checked against arxiv.org. Finding: **all IDs exist**; only the *attribution* at [5] is wrong.

| No | Citation (short) | ID | Verdict | Note |
|---|---|---|---|---|
| — | Agent-Oriented Programming, Shoham 1993 | — | **correct** | Artif. Intelligence 60(1):51–92, DOI 10.1016/0004-3702(93)90034-9 |
| — | Scribble (MPST language) | — | **correct** | Established practical MPST language (Yoshida et al.) |
| 1 | Provable Coordination … via MSC | 2604.17612 | **correct** | Bollig/Függer/Nowak, Apr 2026; projection, "ZipperGen", v2 in Lean 4. Note R-N1: MSC, not MPST |
| 2 | λ-Prompt / Type-Driven Prompt Prog. | 2508.12475 | **correct, caveat** | A. Paul, 2025; extended abstract, λPrompt "not yet a full calculus" → R-N3 |
| 3 | Monitorability of Session Types | 2105.06291 | **correct** | Run-time verification, soundness/completeness, Scala toolkit |
| 4 | Generalised MPST w/ Crash-Stop | 2207.02015 | **correct** | Barwell/Scalas/Yoshida/Zhou; extended CONCUR-2022 version |
| 5 | "L-CAC" / MCP Security Framework | 2604.05969 | **MISATTRIBUTED** | Real paper = *A Formal Security Framework for MCP-Based AI Agents* (Acharya & Gupta); framework **MCPShield**, model `M=(A,S,T,R,C,ℓ)`; "L-CAC" and `(tool,params,scope,ttl,σ)` **not** in the paper → R-C1 |
| 6 | Prompt Flow Integrity | 2503.15547 | **correct** | PFI: agent isolation, privilege-escalation guardrails |

**Standards (§2)** — all confirmed: **29148:2018** (StRS/SyRS/SRS; nine individual-requirement characteristics *necessary, appropriate, unambiguous, complete, singular, feasible, verifiable, correct, conforming* + set characteristics), **DIN 69901-5:2009** (definitions of requirements/specification document correct), **VDI/VDE 3694** (requirements/specification document for automation systems), **BCP 14 = RFC 2119 + RFC 8174**, **ISO 10007 / IEEE 828** (CM pairing appropriate; nuance see R-N6b), **SemVer 2.0.0** (semver.org). Cf. R-M4 on the rendering of the 29148 characteristics in §4.3.

---

## 5. Recommended patch for v0.1.1 (prioritized)

1. **[R-C1]** Correct source [5] or declare the capability tuple as an original design.
2. **[R-H1]** Add legend `T1`–`T5` (+ upstream column in RTM).
3. **[R-H2]** Add rationale per requirement; set status/version globally — or align §4.3.
4. **[R-H3]** "Triad" → "tetrad".
5. **[R-M3]** Negative forms MUST NOT/SHOULD NOT in §4.1.
6. **[R-M4]** Align the 29148 quality list in §4.3 or mark it "incl.".
7. **[R-M1/R-N2]** Split non-singular requirements into sub-IDs.
8. **[R-M2]** Mark §7 as an incomplete template; full coverage as a v0.2.0 criterion.
9. **[R-N1/N3/N4/N5/N6]** Refinements (MSC≠MPST, λPrompt maturity, promise semantics, baseline status, small items).

> Note: findings R-H1, R-H2 and R-M2 concern places where the document does not yet meet its **own** process requirements (LH-P-001/-002) — closing these first raises the credibility of the standards framework the most.

*End of review — CASL v0.1.0.*
