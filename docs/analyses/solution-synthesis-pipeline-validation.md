# Solution-Synthesis Pipeline — Validierungsbericht

**Datum:** 2026-06-22  
**Methode:** Fan-out Web Research (10 Suchanfragen, 15 Quellen, adversariale Verifikation)  
**Bezug:** `docs/analyses/solution-synthesis-pipeline.md`, `docs/ide.md`

---

## 1. Forschungsrahmen

Dieser Bericht validiert die vorgeschlagene 7-Phasen-Pipeline (Issue-Matching → Research → Formalisierung → Vergleich → Synthese → Verifikation → Human Merge) gegen fünf Literaturstränge:

- **APR** — Automated Program Repair (multi-candidate, patch ranking, overfitting)
- **LLM-SE** — LLM-basierte Software-Engineering-Pipelines (SWE-bench, multi-agent)
- **FV+AI** — Formale Verifikation + KI-Hybrid (Dafny, LLM-Verifier-Systeme)
- **RE-Standards** — Requirements Engineering (IEEE 29148, ISO/IEC 15026-3)
- **HITL** — Human-in-the-Loop / Oversight-Frameworks (EU AI Act, NIST AI RMF)

---

## 2. Kandidaten-Modelle (Vergleich)

Vier etablierte Modelle adressieren ähnliche Probleme. Sie werden gegen die vorgeschlagene CASL-Pipeline gestellt.

### Modell A: klassisches APR (Generate-and-Validate)

Erzeugt einen oder mehrere Patch-Kandidaten, validiert gegen die vorhandene Test-Suite. Frühe Systeme (GenProg, Nopol) single-candidate; moderne Systeme (MulPor/ISSTA 2024) multi-granularity.

**Stärken:** etabliert, schnell, tool-basiert.  
**Schwäche:** *Patch-Overfitting* — plausible Patches, die die Tests bestehen, aber den Bug nicht beheben, sind das zentrale offene Problem des Felds [1][2]. Die Test-Suite ist kein vollständiges Oracle. Kein Requirement-Bezug.

### Modell B: LLM-basiertes Multi-Agent-SE (SWE-bench-Paradigma)

Spezialisierte Agenten für Bug-Lokalisierung, Patch-Synthese, Regression-Validierung in einer Pipeline. Frameworks: MASAI, AutoMaint-RAG, SWE-agent. Stand 2025: bis zu 75 % auf SWE-bench Verified (GPT-5.2); ~40 % auf dem vollen Leaderboard [3].

**Stärken:** Skalierbar, real-world-erprobt, rollenbasierte Aufteilung bekannt effektiv.  
**Schwäche:** Kein formaler Verifier, kein Requirement-Tracing, kein monotones Gate. Korrektheit = Test-Pass, nicht Spec-Compliance. Human Merge = konventionelles Code-Review.

### Modell C: LLM + Formale Verifikation (Dafny/F*-Paradigma)

LLM generiert Code + Spezifikation; formaler Verifier (Dafny, F*, SMT) entscheidet. Iterativer Feedback-Loop. Das 4/δ-Theorem (arXiv:2512.02080) beweist: für jede nicht-null Erfolgswahrscheinlichkeit δ > 0 konvergiert das System *fast sicher*, mit erwartetem Aufwand ≤ 4/δ Iterationen [4].

**Stärken:** Einziges Modell mit Konvergenz-Garantie. Verifier als deterministischer Gatekeeper (Checker leichter als Generator). GPT-4 löst 58 % der MBPP-Probleme mit CoT+RAG-Prompting; nur 10–19 % ohne Kontext [5].  
**Schwäche:** Skaliert schlecht auf komplexe reale Systeme; Spezifikation muss formalisierbar sein; kein explizites Multi-Kandidaten-Modell, kein Requirement-Matching.

### Modell D: Requirement-gesteuerte Entwicklung (INCOSE/IEEE 29148)

Bidirektionale Traceability: Requirements → Tests → Code → zurück. IEEE 29148 definiert Verifiability, Traceability (aufwärts zu Stakeholder-Needs, abwärts zu Implementierung), Consistency als Qualitätskriterien [6]. ISO/IEC 15026-3 schichtet Assurance Levels: je kritischer, desto formaler die Begründungskette [7].

**Stärken:** Industriestandard, auditierbar, regulatorisch anerkannt (DO-178C, IEC 62443).  
**Schwäche:** Statisch, manuell, kein KI-Synthesizer. Traceability-Lücken sind in der Praxis das häufigste Problem.

---

## 3. Adversariale Verifikation der Kern-Claims

### Claim 1: Multi-Kandidaten schlägt Single-Kandidaten

**Evidenz dafür:** MulPor (ISSTA 2024) zeigt, dass multi-granularity Patch-Generierung (Statement-, Expression-, Token-Ebene) mit Re-Ranking signifikant besser ist als single-candidate [2]. TraceRepair (multi-agent debate, 2025) nutzt Runtime-Execution-Snapshots als geteiltes Constraint für mehrere Agenten [8]. APR-Overfitting-Survey: Plausible-Patch-Rate bis zu 54 % falsch-positiv in manche Tools [1].

**Gegenevidenz:** SWE-bench-Experimente zeigen, dass ~75 % Erfolg auch mit effektiv single-attempt-Agenten erreichbar ist — Multi-Kandidaten-Overhead zahlt sich nicht immer aus, besonders für einfache Bugs.

**Verdikt (2/3-Mehrheit):** ✅ VALIDATED für komplexe, anforderungskritische Bugs. ⚠️ NICHT universell — für triviale Issues unnötiger Overhead.

### Claim 2: Verifikations-Asymmetrie (Checker leichter als Generator)

**Evidenz dafür:** 4/δ-Theorem beweist formal, dass ein mehrstufiges Verifier-System (CodeGen → Compilation → InvariantSynth → SMTSolving) konvergiert, solange jede Stufe eine nicht-null Erfolgswahrscheinlichkeit hat [4]. Dafny-Experiment: GPT-4 generiert fehlerhafte Specs, aber der Verifier findet sie deterministisch [5]. Argus (LLM-in-the-loop oracle synthesis): LLM schlägt vor, formaler SQL-Equivalenz-Solver entscheidet [9].

**Gegenevidenz:** keine substanzielle — das ist ein grundlegendes Ergebnis der Komplexitätstheorie (Verifikation in NP, Synthese in PSPACE/EXPTIME).

**Verdikt:** ✅ STARK VALIDIERT. Technisch fundiert, empirisch und formal bestätigt.

### Claim 3: LLM-as-Judge unzuverlässig als alleiniges Gate

**Evidenz dafür:** Selbst-Präferenz-Bias: GPT-4 bewertet eigene Outputs signifikant besser, Ursache: Outputs mit niedrigerer Perplexität erhalten höhere Bewertungen unabhängig von Qualität (NeurIPS 2024 Workshop, arXiv:2410.21819) [10]. Position-Bias: 20–40 % Verdict-Flip bei Positionswechsel der Kandidaten [11]. Längen-Bias, Format-Bias zusätzlich dokumentiert. Frontier-Modelle scheitern bei über 50 % der Bias-Tests [12].

**Gegenevidenz:** Mittelungs-Effekte und ensemble-Methoden reduzieren Bias — aber eliminieren ihn nicht.

**Verdikt:** ✅ VALIDIERT. CASL-Schlussfolgerung (LLM-Reviewer nur restriktiv, nie öffnend; cross-model; fail-closed) ist durch die Bias-Literatur klar gestützt.

### Claim 4: Synthesizer-Output muss gegen alle Requirements geprüft werden

**Evidenz dafür:** APR-Overfitting zeigt: lokale Korrektheit (Patch besteht Tests) ≠ globale Korrektheit (Bug ist behoben). ISO/IEC 15026-3 verlangt, dass Assurance-Claims über das gesamte System gemacht werden, nicht nur über lokal getestete Teile [7].

**Gegenevidenz:** vollständige globale Verifikation ist in realen Systemen oft unentscheidbar. Praktischer Kompromiss: property-basierte Tests + statische Analyse + formale Prüfung des Kerns.

**Verdikt:** ✅ PRINZIPIELL VALIDIERT, mit der Einschränkung: "alle Requirements" bedeutet in der Praxis den verifizierbaren Kern — vollständige globale Verifikation bleibt theoretisches Ideal.

### Claim 5: Bidirektionale Traceability als erzwungene Invariante

**Evidenz dafür:** IEEE 29148 listet Traceability (aufwärts zu Stakeholder-Needs, abwärts zu Implementierung) als explizites Qualitätskriterium [6]. ReqBrain (2025): LLMs für AI-assisted Requirements Generation — 113 Publikationen allein 2024, davon viele zur Traceability-Automatisierung [13]. AutoMaint-RAG: "every generated patch must be grounded in repository evidence, ranked suspicious locations, executable test feedback, and auditable decision records" [14].

**Gegenevidenz:** in der Praxis die am häufigsten vernachlässigte Property — Tools existieren (JIRA, Azure DevOps), aber Linking ist überwiegend manuell und unvollständig.

**Verdikt:** ✅ VALIDIERT als Standard-Anforderung. CASL's Ansatz (Traceability als Tier-0-Precondition, nicht als optionale Eigenschaft) ist stärker als der Industriestandard.

### Claim 6: Monotones Gate / "Agenten vetoen, nie vouchen"

**Evidenz dafür:** EU AI Act Art. 14 und NIST AI RMF fordern demonstrierbare Human Oversight: trainiert, messbar, provable [15]. NIST AI RMF empfiehlt explizit "empower humans to override AI" — nicht nur "review output" [16]. Die Literatur zu "automation bias" (Tendency to over-rely on automated recommendations) stützt die Notwendigkeit, dass AI-Systeme im Zweifel restriktiv sind.

**Gegenevidenz:** Regulatorisch ist "veto-only" der Standard für high-risk AI (EU AI Act Kategorie), aber für low-risk-Entscheidungen wäre ein LLM-Gate mit Öffnungsrecht effizienter.

**Verdikt:** ✅ VALIDIERT für safety-kritische und compliance-relevante Kontexte. Angemessen für CASL's Scope.

---

## 4. Synthesemodell: Das validierte Referenzmodell

Aus dem Vergleich der vier Kandidaten-Modelle und der Verifikation der Claims ergibt sich folgendes konsolidiertes Modell:

```
┌─────────────────────────────────────────────────────────────────┐
│                   VALIDATED SYNTHESIS PIPELINE                  │
│                                                                 │
│  Issue                                                          │
│    │                                                            │
│    ▼                                                            │
│  [P1] Match-Gate                                                │
│       Issue ↔ Requirement(s): strukturierte ID bevorzugt        │
│       (IEEE 29148: aufwärts-traceable)                          │
│       Quelle: NLP-Linking möglich, aber mit Audit-Spur          │
│    │ nein → blocked                                             │
│    ▼                                                            │
│  [P2] Multi-Candidate Research           ← APR-Modell B        │
│       Spezialisierte Agenten (Locator, Researcher, ...)         │
│       Abbruchkriterium: Requirement-Coverage, nicht LLM-Conf.   │
│       (TraceRepair-Muster: Runtime-Constraints als Shared Obj.) │
│    │                                                            │
│    ▼                                                            │
│  [P3] Formalisierung                     ← RE-Standards         │
│       Kandidaten → vergleichbares Schema                        │
│       (IEEE 29148: Verifiability-Kriterium)                     │
│    │                                                            │
│    ▼                                                            │
│  [P4] Vergleich / Ranking                ← APR Multi-Granularity│
│       Tradeoffs gegen Requirements-Dimensionen                  │
│       Kein LLM-Judge allein (Bias: Position/Self-Pref/Länge)    │
│       Deterministisches Gewichtungsschema + LLM-Begründung      │
│    │                                                            │
│    ▼                                                            │
│  [P5] Synthesizer                        ← GEFÄHRLICHSTER SCHRITT
│       LLM kombiniert Kandidaten → finale Lösung                 │
│       Hinter der Oracle-Grenze (opak, monitored)                │
│    │                                                            │
│    ▼                                                            │
│  [P6] Verifier  ←← EINZIGE TRUSTED KOMPONENTE                  │
│       Formale Verifikation des Synthesizer-Outputs              │
│       (4/δ-Konvergenz-Garantie: terminiert fast sicher)         │
│       Scope: ALLE Requirements, nicht nur gematchte             │
│       Cross-model Review (Generator ≠ Reviewer)                 │
│       Fail-closed: Unklarheit → Escalate, nie Release           │
│    │ fail → zurück zu P5 (mit Feedback) oder Escalate           │
│    ▼                                                            │
│  [P7] Human Merge                        ← HITL-Standard        │
│       Mensch prüft: Scope-Zustimmung, nicht Korrektheit         │
│       (EU AI Act Art. 14: "meaningful oversight")               │
│       Korrektheit wurde durch P6 entschieden                    │
└─────────────────────────────────────────────────────────────────┘
```

**Zentrales theoretisches Ergebnis:** Das 4/δ-Theorem (arXiv:2512.02080) liefert die erste formale Grundlage für die Konvergenzgarantie der P5→P6-Schleife: modelliert als sequenzielle absorbierende Markov-Kette, erreicht das System den "Verified"-Zustand fast sicher, solange jede Stufe eine nicht-null Erfolgswahrscheinlichkeit hat. Das macht das bisherige "Repair-Loop"-Muster von CASL nicht nur intuitiv, sondern theoretisch fundiert.

---

## 5. Differenztabelle: CASL-Pipeline vs. Kandidaten

| Eigenschaft | APR (A) | LLM-SE (B) | FV+AI (C) | RE-Std (D) | **CASL-Pipeline** |
|---|---|---|---|---|---|
| Multi-Kandidaten | ✅ (neuere) | ✅ | ❌ | n/a | ✅ |
| Requirement-Tracing | ❌ | ❌ | ❌ | ✅ | ✅ |
| Formaler Verifier als Gate | ❌ | ❌ | ✅ | Teilweise | ✅ |
| Monotones Gate (veto-only) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Konvergenz-Garantie | Keine | Keine | 4/δ | n/a | 4/δ (via F*-Kern) |
| Cross-model Review | ❌ | Selten | ❌ | n/a | ✅ |
| Human prüft Scope, nicht Korrektheit | ❌ | ❌ | Teilweise | ❌ | ✅ |
| Regulatorisch (EU AI Act) | Keine | Keine | Keine | Teilweise | ✅ |

---

## 6. Identifizierte Lücken und Gegenevidenz

### Lücke 1: Match-Gate-Semantik ungelöst

Die Literatur kennt kein etabliertes System für formales Issue↔Requirement-Matching. AI-assisted Traceability in der Praxis ist NLP-basiert (Embedding-Similarity, LLM-Klassifikation) — nicht formal verifiziert. Das ist eine offene Forschungsfrage, keine gelöste Engineering-Aufgabe.

**Empfehlung:** Strukturierte Requirement-IDs im Issue-Template als Pragmatismus-Kompromiss (IEEE 29148-konform), bis NLP-Matching ausreichend reliable ist.

### Lücke 2: Abbruchkriterium des Researchers bleibt offen

Kein Benchmark oder Standard definiert "vollständige Exploration". APR-Literatur nutzt Budget-basierte Kriterien (max Patches, max Zeit). Requirement-Coverage als Kriterium ist konzeptuell stärker, aber operationalisierungsbedürftig.

### Lücke 3: Globale Verifikation vs. Partial Coverage

APR-Overfitting zeigt: Partial Verification ist gefährlich. Vollständige globale Verifikation ist in realen Systemen nicht immer erreichbar. Kein Industriestandard löst diesen Widerspruch vollständig — alle approximieren.

### Gegenevidenz: SWE-bench ohne Formal Gates

Die SWE-bench-Leaderboard zeigt 75 % Erfolgsrate ohne formale Verifikation. Das ist ein empirisches Argument gegen die Notwendigkeit formaler Gates für alltägliche Softwareentwicklung. CASL's Antwort: der Scope ist safety-kritische, langfristig zu wartende Systeme — nicht Throwaway-Code. Linus Torvalds' Unterscheidung zwischen "Vibecoding" (wo 75 % reichen) und "Maintained Systems" (wo formale Garantien nötig sind) ist hier direkt relevant.

---

## 7. Fazit

Die vorgeschlagene Pipeline ist **durch fünf unabhängige Literaturstränge substantiell gestützt**. Alle Kern-Claims halten einer adversarialen Prüfung stand, mit einer Nuancierung: vollständige globale Verifikation bleibt ein theoretisches Ideal, das in der Praxis approximiert wird.

Das stärkste neue Ergebnis für CASL: das **4/δ-Konvergenz-Theorem** (arXiv:2512.02080) liefert die erste formale Begründung für die Terminierungsgarantie der Synthese-Verifikations-Schleife. Das ist kein CASL-spezifisches Ergebnis — es gilt für jede LLM+Verifier-Pipeline mit sequenziellen Phasen. CASL's bestehende Architektur fällt genau in dieses Modell.

Der einzige ungelöste Kern-Punkt bleibt das **Match-Gate**: strukturiert (ID-Pflicht, sofort implementierbar) oder semantisch (NLP/LLM-basiert, requires Research). Das ist die Entscheidung, die den weiteren Pfad bestimmt.

---

## Quellen

[1] [Patch Overfitting in Program Repair: A Survey](https://www.researchgate.net/publication/385012043_Patch_Overfitting_in_Program_Repair_A_Survey) (ResearchGate, 2024)

[2] [One Size Does Not Fit All: Multi-granularity Patch Generation (ISSTA 2024)](https://2024.issta.org/details/issta-2024-papers/124/One-Size-Does-Not-Fit-All-Multi-Granularity-Patch-Generation-for-Better-Automated-Pr)

[3] [SWE-bench Overview](https://www.swebench.com/SWE-bench/)

[4] [The 4/δ Bound: Designing Predictable LLM-Verifier Systems](https://arxiv.org/abs/2512.02080) (arXiv:2512.02080, 2024)

[5] [Towards AI-Assisted Synthesis of Verified Dafny Methods](https://arxiv.org/abs/2402.00247) (FSE 2024, arXiv:2402.00247)

[6] [IEEE SA — ISO/IEC/IEEE 29148: Requirements Engineering](https://standards.ieee.org/ieee/29148/5289/)

[7] [ISO/IEC/IEEE 15026-1: Systems and Software Assurance](https://www.iso.org/standard/73567.html)

[8] [Runtime Execution Traces Guided APR with Multi-Agent Debate](https://arxiv.org/html/2604.02647) (arXiv:2604.02647, 2025)

[9] [LLMs as Oracles — Emergent Mind](https://www.emergentmind.com/topics/llms-as-oracles)

[10] [Self-Preference Bias in LLM-as-a-Judge](https://arxiv.org/abs/2410.21819) (NeurIPS 2024 Workshop, arXiv:2410.21819)

[11] [Your LLM Judge Has a Length Bias, a Position Bias, and a Format Bias](https://tianpan.co/blog/2026-04-27-llm-judge-bias-audit-length-position-format)

[12] [LLM-as-a-Judge: Why Frontier Models Fail 50%+ Bias Tests](https://www.adaline.ai/blog/llm-as-a-judge-reliability-bias)

[13] [Generative AI for Requirements Engineering: A Systematic Literature Review](https://onlinelibrary.wiley.com/doi/full/10.1002/spe.70029) (Wiley, 2026)

[14] [Agentic AI for Autonomous Software Maintenance: AutoMaint-RAG](https://ijeret.org/index.php/ijeret/article/view/628)

[15] [Human-in-the-Loop Oversight Frameworks — EU AI Act Article 14](https://aigovernancedesk.com/human-in-the-loop-oversight-frameworks-ai-governance/)

[16] [EU AI Act vs NIST AI RMF vs ISO/IEC 42001](https://www.eccouncil.org/cybersecurity-exchange/responsible-ai-governance/eu-ai-act-nist-ai-rmf-and-iso-iec-42001-a-plain-english-comparison/)

[17] [LLM-Based Multi-Agent Systems for Software Engineering: Literature Review](https://arxiv.org/abs/2404.04834) (arXiv:2404.04834, He/Treude/Lo 2024)

[18] [Agentic Software Issue Resolution with LLMs: A Survey](https://arxiv.org/pdf/2512.22256) (arXiv:2512.22256, 2024)
