# Issue — Wave 4: Strategische Doku-Set-Entscheidung

**Status:** offen, **wartet auf strategische Entscheidung des Inhabers**
**Quelle:** Web-Recherche 2026-05-16 (BAuA, ZVSHK, BGB §640)
**Abhängigkeit:** unabhängig — kann jederzeit umgesetzt werden, ändert aber die Architektur des Generators.

---

## Hintergrund

Der Generator erzeugt aktuell (nach Wave 2) **24 HTML-Dokumente** pro Standardprojekt, verteilt auf 5 Rollen-Ordner plus die KfW-Fachunternehmererklärung. Die externe Web-Recherche kam zu einer pointierten Empfehlung:

> **Ship a Bautagebuch + ergänzende GBU + Abnahmeprotokoll trio first, in exactly the ZVSHK/BAuA layout, with one big „Tag abschließen"-Button. That's 80% of the daily value; the other 17 doc types can come later.**

Die Hypothese: für die SHK-Kleinfirma ist das volle 24-Dokumente-Set ein **Premature Optimization** mit hohem LLM-Kosten-Aufwand und niedrigem Wirkungsgrad. Ein fokussiertes 3-5-Dokumente-Kernset würde:

- LLM-Kosten weiter senken (24 → 5 Worker-Tasks = ~80% weniger Output-Tokens).
- Die einzelnen Dokumente **deutlich** besser machen (mehr Prompt-Budget + Few-Shot-Fokus pro Doku).
- Akzeptanz beim Monteur erhöhen (weniger Überforderung).
- Die deutsche Bau-Konvention exakt spiegeln (gerichtsfest).

---

## Strategische Frage an den Inhaber

**Sollen wir das Doku-Set kürzen oder beibehalten?**

| Variante | Doku-Anzahl pro Standard-Projekt | Pro | Contra |
|---|---|---|---|
| **A — Status Quo** | 24 (nach Wave 2) | Vollständige Abdeckung, alle Rollen bedient | Höhere LLM-Kosten, mehr Lärm in der UI |
| **B — Kern + Bedarf** | ~8 (3 Pflicht + 5 wichtigste) | Fokus, niedrigere Kosten, klare Wertproposition | Verlust der „Vollständigkeitsillusion" |
| **C — Minimal-Kern** | ~3 (nur Bautagebuch + GBU + Abnahme) | Maximaler Fokus, deutsche Konvention exakt | Manche Rollen (Obermonteur, Allgemein) bekommen nichts |

---

## Empfohlenes Minimal-Kernset (für Variante B oder C)

### 1. Bautagebuch (Pflicht — § 4 HOAI / BGB-Standard)

**Datei:** `03_Bauleitung/BAULEITUNG_Bautagebuch.html` (neue Datei, ersetzt/ergänzt `BAULEITUNG_Detaillierter_Ablaufplan.html`).

**Inhalt nach Konvention:**
- Datum, Wetter
- Personal anwesend (Liste)
- Ausgeführte Arbeiten (Freitext mit data-field-id)
- Behinderungen / Verzögerungen
- Materiallieferungen (Tabelle)
- Foto-Galerie (aus photos.json)
- Unterschriftsfeld (Bauleitung)

**Layout:** A4, Firmen-Briefkopf links, Bauvorhaben rechts, Datumzeile, Unterschrift unten rechts.

### 2. Ergänzende Gefährdungsbeurteilung (BAuA / BGHM-Konvention)

**Datei:** `03_Bauleitung/BAULEITUNG_Gefaehrdungsbeurteilung.html` (bereits vorhanden, **Layout an BAuA/BGHM angleichen**).

**Quellen:**
- BAuA Handlungshilfe: <https://www.baua.de/SharedDocs/Handlungshilfen/DE/Gefaehrdungsbeurteilung/BG-ETEM-Muehlthaler/App-Ergaenzende-Gefaehrdungsbeurteilung>
- BGHM Check Bau/Montage: <https://www.baua.de/SharedDocs/Handlungshilfen/DE/Gefaehrdungsbeurteilung/BGHM-Hoffbauer/Check-fuer-sicherheit-und-gesundheitsschutz-fuer-bau-und-montagearbeiten>
- ZVSHK Onlineportal: <https://www.zvshk.de/onlineshop/shk-onlinelizenzen/onlineportal-shk-arbeitssicherheit>

**Struktur:** Basis-GBU (büro-vorbereitet pro Tätigkeit) + ergänzender Baustellen-Teil mit lokalen Bedingungen.

### 3. Abnahmeprotokoll (BGB § 640)

**Datei:** `05_Allgemein/ALLGEMEIN_Uebergabeprotokoll.html` (bereits vorhanden, **Layout an BGB-Standard angleichen**).

**Inhalt:**
- Leistungsbeschreibung
- Mängelliste
- Vorbehalte
- Datum
- Unterschriftsfelder (Auftraggeber + Auftragnehmer, je 200 px)
- „Seite X von Y" Footer

---

## Optional ergänzbare Dokumente (Variante B)

Wenn statt Minimal-Kernset ein etwas größeres Set:

- `MONTEUR_Tagescheckliste.html` (am häufigsten genutzt von Monteuren)
- `BAULEITUNG_Risiken_und_Maengel.html` (rechtlich relevant)
- `PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html` (Förder-Nachweis BEG-EM)
- `PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html` (technisch Pflicht)
- `00_Start/index.html` + `Projekt_Navigation.html` (Einstieg)

---

## Umsetzung (falls Variante B oder C gewählt wird)

### T4.1 — Doku-Plan kürzen

**Datei:** `backend/app/services/generator_runner.py`

- In `_standard_tasks()` Plan-Liste die nicht gewünschten Einträge auskommentieren oder per Feature-Flag steuerbar machen (`settings.minimal_doc_set: bool`).
- `_BULK_FILE_PURPOSES` ggf. um neue Einträge (Bautagebuch) erweitern.
- Output-Validator (`output_validator.py`) entsprechend anpassen — `STANDARD_REQUIRED_FILES` und `SMALL_REQUIRED_FILES` kürzen.
- Tests in `test_output_validator.py` und `test_generator_tasks.py` aktualisieren.

### T4.2 — Bautagebuch-Doku neu konzipieren

- Per-File-Purpose für `BAULEITUNG_Bautagebuch.html` in `_BULK_FILE_PURPOSES` einfügen.
- Explizit die BGB-/HOAI-Felder enumerieren (Datum, Wetter, Personal, Arbeiten, Behinderungen, Material, Foto, Unterschrift).
- Layout-Vorgaben (Briefkopf links, Bauvorhaben rechts) sind bereits in `<protocol_layout>` der `_BASE_RULES` definiert — greift automatisch.

### T4.3 — GBU- und Abnahme-Layout an BAuA/BGB angleichen

- Existing `_RISK_ASSESSMENT_PURPOSE` und `_HANDOVER_PROTOCOL_PURPOSE` erweitern um explizite Verweise auf BAuA-Struktur bzw. § 640 BGB.
- Optional: BAuA-Vorlagen-Snippets als Few-Shot im `<examples>`-Block ergänzen.

### T4.4 — Frontend: „Tag abschließen"-Hero-Button

- Auf Monteur-Landing einen großen primären Button „Tag abschließen" hinzufügen, der direkt zum Bautagebuch-Eintrag des heutigen Datums leitet (legt einen neuen Eintrag an, falls noch keiner existiert).
- Inhalt aus dem Tagesbericht-Wizard wird automatisch in den Bautagebuch-Eintrag übernommen.

---

## Entscheidungs-Voraussetzungen

Bevor Wave 4 sinnvoll umgesetzt werden kann, sollte geklärt sein:

1. **Wie oft werden welche Dokumente in der Praxis tatsächlich genutzt?**
   Dafür: 4 Wochen Telemetrie auf der App (Aufruf-Counter pro generierter Datei via View-URL).

2. **Welche Dokumente verlangt der typische Auftraggeber / Behörde / KfW konkret?**
   Inhaber-Wissen — sollte vor jeder Doku-Set-Entscheidung dokumentiert sein.

3. **Welche Dokumente werden im Streitfall gerichtsfest erwartet?**
   Bautagebuch + GBU + Abnahmeprotokoll sind hier unbestritten — der Rest ist „nice to have".

---

## Erfolgsmessung (wenn Variante B/C gewählt)

- Generator-Wallclock pro Standard-Projekt < 50% des heutigen Wertes.
- LLM-Output-Tokens pro Projekt-Run < 30% des heutigen Wertes (Cache-Wirkung + weniger Files).
- Doku-Liste auf der Rollen-Landing zeigt < 8 Einträge pro Rolle.
- Monteur-Akzeptanz steigt (Self-Reported Survey nach 4 Wochen).
