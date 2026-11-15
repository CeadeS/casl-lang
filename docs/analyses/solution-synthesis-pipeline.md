# Solution-Synthesis Pipeline — Konzeptbericht

**Datum:** 2026-06-22  
**Status:** Konzept / zur Entscheidung  
**Bezug:** `docs/ide.md`, `docs/vision.md`, `casl_synth.py`

---

## 1. Das vorgeschlagene Modell

Das Gespräch hat eine Pipeline-Architektur skizziert, die Issue-Lösung in klar getrennte, auditierbare Phasen zerlegt:

```
Issue + Requirements
    │
    ▼
[1] Match-Gate
    Issue ↔ Requirement(s) verifiziert verknüpft
    │  nein → blocked
    │  ja   →
    ▼
[2] Researcher
    Lösungsraum aufspannen: Codebase, Literatur, Patterns, Precedents
    Abbruchkriterium: aus Requirements abgeleitet, nicht aus LLM-Confidence
    │
    ▼
[3] Formalizer
    Kandidaten ins selbe Schema überführen
    (vergleichbar, auditierbar, diff-fähig)
    │
    ▼
[4] Comparator
    Tradeoffs gegen Requirements gewichten
    Ergebnis: Ranking + Begründung, traceable
    │
    ▼
[5] Synthesizer
    Finale Lösung aus Kandidaten ableiten
    ⚠ gefährlichster Schritt (s. §3)
    │
    ▼
[6] Verifier  ← einzige trusted Komponente
    Compliance gegen alle gematchten Requirements
    Traceability vollständig?
    │  nein → zurück zu [5] oder eskalieren
    │  ja   →
    ▼
[Human merge]
    Kein Review im alten Sinne —
    Mensch prüft Scope-Zustimmung, nicht Korrektheit
```

---

## 2. Verhältnis zur bestehenden CASL-Architektur

### Was bereits existiert

Der aktuelle `casl_synth`-Loop ist **single-threaded**: ein Kandidat wird generiert, durch `casl check` (Tier 0) geprüft, bei Fehler repariert. Phasen [1]–[4] der vorgeschlagenen Pipeline existieren **nicht**; der Loop beginnt direkt bei [5] (Synthesizer) ohne Recherchevorläufer.

| Vorgeschlagene Phase | Entsprechung in CASL heute |
|---|---|
| [1] Match-Gate | Teilweise: Traceability-Invariant (jedes Artefakt hängt an ≥1 Requirement), aber kein formales Issue↔Req-Matching |
| [2] Researcher | Nicht vorhanden |
| [3] Formalizer | Nicht vorhanden |
| [4] Comparator | Nicht vorhanden |
| [5] Synthesizer | `casl_synth.py` (repair loop, single-candidate) |
| [6] Verifier | `casl_check.py` + `kernel.py` (Tier 0); Tier 1–3 des monotonen Gates |
| Human merge | Tier 3 (approval dominance, `LH-Q-011`) |

### Was neu wäre

Die vorgeschlagene Pipeline fügt einen **Explore-then-Converge**-Schritt vor der Synthese ein. Das ist konzeptuell der größte Unterschied zum bestehenden System: statt eines einzelnen Kandidaten mit Repair-Schleife werden mehrere Kandidaten explizit verglichen, bevor eine finale Lösung synthetisiert wird.

---

## 3. Die kritischen Punkte

### 3.1 Match-Gate: drei Schwierigkeitsgrade

**Trivial (lösbar):** Issue enthält explizite Requirement-ID. Mechanisch prüfbar, kein Interpretationsproblem. Kann als Precondition in Tier 0 erzwungen werden.

**Schwer (LLM-abhängig):** Issue beschreibt ein Problem in Prosa, Requirement beschreibt erwünschtes Verhalten — ein System muss semantisch matchen. Das Match selbst ist dann LLM-generiert und damit unverified. Ein falsch-positiver Match ist gefährlicher als gar kein Matching, weil er wie Korrektheit aussieht.

**Ungelöst (offen):** Ein Issue kann mehrere Requirements berühren, manche implizit durch Seiteneffekte. Unvollständiges Matching → partiell korrekte Lösung, die den Verifier passiert aber Invarianten anderswo bricht.

**Konsequenz:** Das Match-Gate muss selbst auditierbar sein. Minimalforderung: der Match-Schritt gibt eine explizite Begründung aus (welches Requirement, warum), die im Trace landet. Ideallösung: Requirement-IDs werden im Issue-Template erzwungen (strukturiert statt semantisch).

### 3.2 Abbruchkriterium des Researchers

Ein LLM-Researcher kann nicht wissen, wann er fertig ist — er kann immer "noch einen relevanten Aspekt" finden. Das Abbruchkriterium muss deshalb **extern** kommen, d.h. aus den Requirements: "Researcher terminiert, wenn alle relevanten Requirement-Dimensionen mindestens einen Kandidaten haben" oder nach einem festen Budget (Token/Zeit/Queries). Ohne explizites Kriterium degeneriert der Researcher zu einer unbegrenzten Suche.

### 3.3 Der Synthesizer ist der gefährlichste Schritt

Der Synthesizer kombiniert Teile verschiedener Kandidaten. Das Ergebnis kann:
- lokal alle Requirements aus [1]–[4] erfüllen, aber
- global inkonsistent sein (Seiteneffekte auf nicht-gematchte Requirements).

**Konsequenz:** Der Verifier muss die *synthetisierte* Lösung gegen **alle** Requirements des Projekts prüfen, nicht nur gegen die gematchten. Das erhöht den Scope des Verifiers erheblich, ist aber die einzige sichere Option.

### 3.4 Monotonieinvariante der Pipeline

In der bestehenden CASL-IDE gilt: jede Schicht kann die erlaubte Menge nur *verkleinern*. Für die vorgeschlagene Pipeline muss das explizit gesichert sein:
- Phasen [2]–[4] sind **opake Agenten hinter der Orakelgrenze** — sie schlagen vor, entscheiden nicht.
- Phase [6] (Verifier) ist die **einzige öffnende Instanz**, analog zu Tier 0 in der bestehenden Architektur.
- Der Human-Merge prüft Scope-Zustimmung, nicht Korrektheit — das setzt voraus, dass [6] tatsächlich alle Korrektheitsfragen abschließt.

---

## 4. Warum das Abstraktionsebene-Argument trägt

Linus Torvalds' Compiler-Analogie ist hier direkt relevant: Compiler ermöglichten einen 1000x-Sprung, weil sie die Abstraktionsebene verschoben — nicht weil sie Assembler schneller schrieben. Der Mensch hörte auf, in Registern zu denken.

Die vorgeschlagene Pipeline macht dasselbe für Issue-Lösung: der Mensch entscheidet beim Merge nicht mehr "ist die Lösung korrekt?" (das erledigt der Verifier), sondern "stimme ich dem Scope zu?" Das ist eine echte Abstraktionsverschiebung — aber nur wenn der Verifier tatsächlich vertrauenswürdig ist. Ohne einen formalen Verifier-Kern bleibt die Pipeline ein schnelleres Review, kein Abstraktionssprung.

Für CASL heißt das: die Pipeline ist nur so stark wie `casl_check` + der bewiesene Kern. Das ist gleichzeitig ihre Stärke (der Kern existiert bereits) und ihre Begrenzung (was der Kern nicht prüfen kann, bleibt ungesichert).

---

## 5. Einordnungsoptionen ins Projekt

### Option A: Erweiterung von `casl_synth`

Die bestehende Repair-Schleife in `casl_synth.py` wird um Phasen [2]–[4] erweitert. Der Synthesizer in Phase [5] ersetzt den heutigen single-candidate-Generator. Konservativster Ansatz, minimale neue Konzepte.

**Passt zu:** v0.15.x als schrittweise Erweiterung der IDE-Phasen aus `docs/ide.md`.  
**Risiko:** `casl_synth` wird komplex; der Multi-Kandidaten-Flow ist konzeptuell verschieden vom Repair-Loop.

### Option B: Neues CEP

Die Pipeline wird als eigenständiges Konzept formalisiert: CEP-`XXXX` "Multi-Candidate Solution Synthesis". Klare Trennung von der bestehenden Synth-Architektur; Phasen [1]–[6] werden als Requirements spezifiziert, bevor irgendetwas implementiert wird.

**Passt zu:** dem CEP-Requirement-System (Proposals/, audit-erzwungen).  
**Empfehlung:** wenn die Pipeline mehr als eine Implementierungsdetail ist und strukturelle Auswirkungen auf die Architektur hat.

### Option C: Erst in `docs/ide.md` einarbeiten

Phase [2]–[4] als "Phase 6" der IDE-Roadmap dokumentieren, kein CEP, keine Implementierung. Entscheidung über Umfang vertagt.

**Passt zu:** aktuellem Zustand: alle IDE-Phasen 1–5 sind delivered, kein offener PR wartet auf diesen Scope.

---

## 6. Empfehlung

Der kritischste offene Punkt ist das **Match-Gate** (§3.1). Bevor die Researcher/Formalizer/Comparator-Phasen sinnvoll sind, muss klar sein, wie Issue↔Requirement-Matching funktioniert — strukturiert (ID-Pflicht im Issue) oder semantisch (LLM-Match mit Audit-Spur).

**Vorgeschlagene Reihenfolge:**
1. Match-Gate-Semantik klären (strukturiert vs. semantisch, Abbruchkriterium für Researcher)
2. Wenn strukturiert: als Tier-0-Precondition implementierbar, kein CEP nötig
3. Wenn semantisch: CEP ist angebracht, weil ein LLM-Schritt vor dem Gate ein neues Vertrauensmodell einführt
4. Danach Phasen [2]–[4] als optionale Erweiterung des Synth-Loops

Der Human-Merge als "Scope-Zustimmung statt Korrektheitsprüfung" ist das langfristig interessanteste Ziel — und setzt voraus, dass [6] den Verifier-Kern wirklich vollständig nutzt.

---

*Dieser Bericht ist ein Konzeptdokument zur Entscheidungsfindung. Er impliziert keine Implementierungsverpflichtung.*
