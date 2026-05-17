# Implementierungsplan V2 — Erweiterungen HEZ Tool

Fortsetzung von `IMPLEMENTIERUNGSPLAN.md` (Phasen 1–9 erledigt). Dieser Plan
deckt die Erweiterung des Tools nach der Tiefenrecherche (2026-05-15).

## Leitplanken

Das HEZ Tool ist ein **Doku-Generator fuer die Baustellenplanung**. Es spart
das manuelle Erstellen der projektbezogenen Doku-Dateien pro Baustelle.

Explizit NICHT im Scope:

```text
Zeiterfassung der Monteure       -> CRM
Wartungsvertraege / Service      -> CRM
Grosshandels-Bestellungen        -> CRM / Grosshandels-Webshop
Chat zwischen Rollen             -> CRM / WhatsApp
Foto-Analyse auf Geraeten        -> ausserhalb Scope
```

Eingaben in das Tool:

```text
1. Strukturierte Projektdaten aus dem Formular (input.json)
2. Strangberechnungs-Daten aus dem externen Heizungs-Auslegungstool
3. Technische Unterlagen (PDF, CSV, XLSX) im docs/
4. Optional: Sprachnotizen (werden transkribiert und in den Generator-Prompt
   eingespeist, NICHT als End-Output gespeichert)
```

Outputs des Tools:

```text
1. Rollenbasierte HTML/MD-Dokumentation (00_Start ... 05_Allgemein)
2. Pflicht-Dokumente als PDF (IBN, hydraulischer Abgleich, KfW-FUE,
   Uebergabeprotokoll, SiGe)
3. Veroeffentlichung pro Projekt-Subdomain
```

---

## Phase 10: Pflicht-Dokumente als Generator-Output

Ziel: Die rechtlich notwendigen Dokumente werden vom Generator mitproduziert,
nicht mehr manuell in Word gepflegt.

### 10.1 Strangberechnungs-Datenmodell in der DB

Aufwand: M. Voraussetzung fuer 10.2 und 10.3.

```text
Project
  heating_design (1:1)
    system_type           # Heizkoerper / FBH / Mischsystem
    supply_temp_c         # Vorlauftemperatur Auslegung
    return_temp_c         # Ruecklauftemperatur Auslegung
    delta_t_k             # Spreizung
    pump_head_pa          # Foerderhoehe Pumpe
    total_volume_flow_lph # Gesamt-Volumenstrom

  heating_circuits (1:N)
    name                  # Strang / Etage / Wohnung
    room                  # Raum
    radiator_type         # Heizkoerper-Typ / Heizkreis FBH
    heat_load_w           # Norm-Heizlast
    volume_flow_lph       # Volumenstrom
    valve_type            # Ventilfabrikat
    valve_preset          # Voreinstellwert (kv / Stellung)
    pipe_length_m         # Rohrlaenge
    notes
```

Aufgaben:

```text
1. ORM-Modelle in backend/app/db/orm_models.py
2. Alembic-Migration "heating design schema"
3. Pydantic-DTOs in backend/app/models/heating.py
4. CRUD-Endpoints im neuen backend/app/api/heating.py
5. Frontend-Component features/heating-design/ (read-only Tabelle zunaechst)
```

### 10.2 Hydraulischer-Abgleich-Output (VdZ-Form)

Aufwand: M. Abhaengig von 10.1.

```text
Output-Datei: 03_Bauleitung/BAULEITUNG_Hydraulischer_Abgleich.html
              (und gleichnamiges .md, gleichnamiges .pdf via 10.7)

Pflicht-Inhalt nach VdZ Verfahren B:
- Anlagenkenndaten (System, Volumenstrom, Spreizung)
- Heizkreis-Tabelle mit Voreinstellwerten je Ventil
- Pumpenkennlinie / Foerderhoehe / Differenzdruck
- Datum, Monteur, Unterschriften-Feld
- VdZ-Kompatibilitaetsvermerk
```

Aufgaben:

```text
1. Neuer GenerationTask in generator_runner.py
2. Prompt-Template, das heating_design + heating_circuits aus input.json
   liest und das VdZ-Layout erzeugt
3. Output-Validator pruefen lassen ob Datei existiert
4. Im Frontend Output-Viewer fuer das Dokument
```

### 10.3 Inbetriebnahmeprotokoll (IBN)

Aufwand: M.

```text
Output-Datei: 04_Projektleitung/PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html

Pflicht-Inhalt:
- Anlagenkenndaten (Hersteller, Typ, Seriennummer, Baujahr)
- Sicherheitspruefung-Checkliste (Dichtheit, Abgas, Druck, Sicherheitsventil)
- Eingestellte Werte (Vorlauf, Ruecklauf, Druck, Pumpenstufe)
- Einweisung-Kunde-Bestaetigung
- Unterschriften-Feld Kunde + Monteur (Signature-Pad in 10.8)
- Datum, Ort
```

### 10.4 KfW-Fachunternehmererklaerung

Aufwand: M. Hohe Sichtbarkeit zum Endkunden — Verkaufsargument.

```text
Output-Datei: 04_Projektleitung/PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html

Pflicht-Inhalt (gemaess KfW-Vordruck 152/430):
- Antragsteller (Kunde, kommt aus Projekt-Stammdaten)
- Massnahmen-Beschreibung (Heizungs-Typ neu, Leistung, Effizienz)
- Bestaetigung Mindestanforderungen
- Bestaetigung hydraulischer Abgleich erfolgt (verweist auf 10.2)
- Fachunternehmer-Stempel-Bereich
- Datum, Unterschrift
```

### 10.5 Uebergabe-/Abnahmeprotokoll nach BGB §640

Aufwand: S.

```text
Output-Datei: 05_Allgemein/ALLGEMEIN_Uebergabeprotokoll.html

Pflicht-Inhalt:
- Leistungsbeschreibung (was wurde gemacht)
- Maengelliste / Restleistungen / Vorbehalte
- Datum der Abnahme (Beginn Gewaehrleistung!)
- Unterschriften Kunde + Bauleitung
```

### 10.6 Gefaehrdungsbeurteilung / SiGe-Plan

Aufwand: S. KI-generiert auf Basis Projekt-Typ + Bestand.

```text
Output-Datei: 03_Bauleitung/BAULEITUNG_Gefaehrdungsbeurteilung.html

Inhalt (KI-getrieben auf Basis Projekt-Stammdaten):
- Erkannte Risiken (Gas, Heissarbeit, Asbest-Verdacht, Absturzgefahr)
- Schutzmassnahmen je Risiko
- Unterweisung-Bestaetigungs-Feld
```

### 10.7 PDF-Export-Service

Aufwand: M. Voraussetzung fuer 10.1–10.6 in finaler Form.

```text
HTML -> PDF mit korrektem Layout. Optionen:
- WeasyPrint   (Python-nativ, gute CSS-Unterstuetzung) -> empfohlen
- Playwright   (browser-rendered, schwerer Container, perfekte Treffer)
- wkhtmltopdf  (deprecated, nicht empfohlen)

Aufgaben:
1. Service backend/app/services/pdf_export.py
2. Endpoint GET /api/projects/{slug}/outputs/file/{path}.pdf
   -> generiert PDF on-the-fly aus .html
3. PDF-spezifische CSS-Klassen in den Generator-Prompts
   (page-break-after, @page-Regeln, Druckraender)
```

### 10.8 Signature-Pad im Frontend

Aufwand: S.

```text
- Component shared/components/signature-pad/
  (Canvas-basiert oder Library wie signature_pad@4)
- Speichert die Unterschrift als PNG-DataURL in projektbezogener Tabelle
- Im IBN-/Uebergabe-Protokoll wird die Unterschrift bei PDF-Export
  eingebettet
```

---

## Phase 11: Multi-Source-Eingangs-Pipeline fuer Strangberechnungs-Daten

Ziel: Das Tool akzeptiert Strangberechnungs-Daten aus mehreren Quellen
(intern Viega Viptool Master und extern Architekten/Planer) und normalisiert
sie in das interne heating_design-Schema. Der Generator arbeitet immer mit
dem internen Schema, nicht mit den Rohformaten.

### 11.1 Adapter-Architektur

Aufwand: S. Pflichtbasis fuer 11.2–11.6.

```text
Strategy-Pattern in backend/app/services/heating_importers/:

  base.py
    class HeatingImporter(Protocol):
        source_name: str                            # "viptool_xlsx" etc.
        def can_handle(file_bytes, hint) -> bool
        def parse(file_bytes, mapping) -> HeatingDesignImport

  viptool_xlsx.py        # 11.2
  generic_table.py       # 11.3 (Excel/CSV mit Spalten-Mapping)
  viptool_ifc.py         # 11.4
  manual.py              # 11.5 (kein Import, direkt-Schreibung im Frontend)

Internes Schema (heating_design / heating_circuits aus 10.1) bekommt
ein Provenance-Feld:
  source       str   # adapter-Name
  source_file  str   # Original-Dateiname
  imported_at  datetime
  imported_by  user_id
```

Endpoint:

```text
POST /api/projects/{slug}/heating-design/import
  multipart: file + adapter_hint (optional) + mapping (optional, JSON)
  -> wenn adapter_hint fehlt: erster passender Adapter laut can_handle
  -> Antwort: Vorschau der parsed Daten + Erkenntnisse (Spaltenzuordnung)
  -> Confirmation-Schritt (zweiter Endpoint) schreibt in DB

POST /api/projects/{slug}/heating-design/import/confirm
  Body: parsed Daten aus dem Vorschau-Schritt (vom Nutzer ggf. korrigiert)
  -> persistiert in heating_design / heating_circuits
```

### 11.2 Viptool-Master-Adapter (intern)

Aufwand: M. Erste Implementation, abhaengig von 11.1.

```text
- Voraussetzung: Beispieldatei aus echtem Viptool-Workflow
- Bevorzugtes Format: Excel-Tabellenausgabe aus Master
- Fallback: PDF-Tabellenextraktion mit pdfplumber
- Mapping ist fest verdrahtet auf die Master-Spalten (kein UI-Mapping noetig)
```

### 11.3 Generic-Table-Adapter (extern)

Aufwand: M. Der Schluessel fuer Daten von externen Architekten/Planern.

```text
- Akzeptiert Excel (.xlsx, .xls) und CSV
- Erkennt automatisch Header-Zeile (Heuristik)
- Frontend-Dialog "Spalten zuordnen":
  - Liste der vermuteten Pflicht-Spalten (Strang, Raum, Heizflaeche,
    Volumenstrom, Voreinstellwert, kv, Heizlast, Rohrlaenge, Ventil-Typ)
  - Vorschlag auf Basis Header-Aehnlichkeit (Fuzzy-Match)
  - Nutzer kann manuell korrigieren
- Mapping-Persistenz: Pro "Quelle" (Architekt-Name oder Datei-Pattern)
  wird das Mapping in der DB gespeichert.
  Tabelle external_source_mappings: name, column_map (JSON), created_by, ...
  -> beim naechsten Upload derselben Quelle wird das Mapping automatisch
     vorgeschlagen
```

### 11.4 IFC-Adapter (optional, bei BIM-Workflow)

Aufwand: L. Nur wenn IFC-Quellen tatsaechlich vorkommen.

```text
- Library: ifcopenshell
- Mappt IfcDistributionFlowElement-Hierarchien auf heating_circuits
- Master kann IFC exportieren; auch externe BIM-Architekten liefern oft IFC
- Wichtig fuer Plan-Viewer (Phase 12 hat das nicht, IFC waere natuerlicher
  Schritt zu 3D-Ansicht)
- Erst angehen wenn 11.2 und 11.3 produktiv laufen
```

### 11.5 Manuelle Eingabe als Edit-Component

Aufwand: M. Immer-verfuegbarer Fallback.

```text
- Frontend-Component features/heating-design-editor/
- Editierbare Tabelle (Heizkreise) mit Inline-Validierung
- Add/Remove/Sort-Zeilen
- Korrigiert Import-Ergebnisse oder dient als reine Eingabe-Maske
  (kleine Projekte ohne Berechnungstool)
- Provenance "manual" wird gesetzt
```

### 11.6 Generator-Prompts und Provenance im Output

Aufwand: S. Abhaengig von 10.1–10.2 und 11.x.

```text
- Im _BASE_RULES des generator_runner: Hinweis, dass heating_design.json
  im Workspace liegt (analog input.json)
- Pro Pflicht-Dokument-Task wird der relevante Schnitt aus heating_design
  in den Prompt eingebettet
- Im generierten Output (z.B. Hydraulischer Abgleich) wird die Datenquelle
  ausgewiesen:
    "Datenherkunft: Viptool Master, importiert 2026-03-12 von M. Mueller"
    bzw.
    "Datenherkunft: externe Strangberechnung Architekturbuero XY,
     Datei strangberechnung_hez640.xlsx, importiert ..."
  Das ist fachlich wichtig fuer Streit-/Pruef-Faelle.
```

---

## Phase 12: Foto-Doku

Ziel: Fotos sind Beweismittel im Streitfall und ergaenzen die generierten
Dokumente um visuelle Belege.

### 12.1 Foto-Upload mit Metadaten

Aufwand: M.

```text
- ORM ProjectPhoto: project_id, section_number, taken_at, geo_lat, geo_lng,
                    monteur_user_id, file_path, sha256, caption,
                    linked_to (daily_report_id | blocker_id | ...)
- EXIF-Parser im Backend (Pillow) extrahiert GPS + Zeit aus dem Foto
- Endpoint POST /api/projects/{slug}/photos
- Hash-Speicherung gegen Manipulationsverdacht
```

### 12.2 Foto-Annotation im Frontend

Aufwand: M.

```text
- Canvas-Overlay zum Zeichnen von Pfeilen/Text auf das Foto
- Annotation wird als separate Overlay-PNG gespeichert + im Server
  per Pillow zusammengerendert (Original bleibt unveraendert)
```

### 12.3 Fotos in den Generator-Output einbetten

Aufwand: S. Abhaengig von 12.1.

```text
- Generator-Prompt erhaelt eine Liste der vorhandenen Fotos pro Bauabschnitt
  inkl. Caption + URL
- HTML-Output bindet die Fotos per relativem Pfad ein
  (Bilder werden im output-Bundle mitkopiert)
- PDF-Export 10.7 nimmt die Fotos mit
```

### 12.4 Tagesbericht-Foto-Galerie

Aufwand: S.

```text
- Im DailyReport-Form: Foto-Anhaenge erlauben
- Liste zeigt Thumbnails
```

---

## Phase 13: Sprachnotizen als Input-Kanal

Ziel: Monteur diktiert auf der Baustelle. Transkription wird in den
Generator-Prompt eingespeist und produziert daraus strukturierte HTML-Dokumente.

### 13.1 Audio-Upload + Transkription

Aufwand: M.

```text
- Frontend: Audio-Aufnahme im Browser (MediaRecorder API)
- Endpoint POST /api/projects/{slug}/voice-notes
- Transkription:
  - Option A: OpenAI Whisper API (qualitativ am besten, kostet)
  - Option B: faster-whisper lokal im Container (kein API-Call,
              GPU-faehig, CPU funktioniert mit Verzoegerung)
  -> Empfehlung: Option B, faster-whisper-large-v3 im Container,
                 weil Daten ohnehin tokenisiert werden sollten
- ORM VoiceNote: project_id, user_id, audio_path, transcript,
                 intent (daily_report | ibn | uebergabe | freitext)
```

### 13.2 Sprachnotiz als Generator-Input

Aufwand: S. Abhaengig von 13.1.

```text
- Im Generate-Request akzeptiert das Backend optional eine
  voice_note_id-Liste
- Die Transkripte werden vor dem Generator-Lauf in input.json
  unter "voice_notes": [...] aufgenommen
- Generator-Prompt: "Beruecksichtige die folgenden Sprachnotizen
  des Monteurs als zusaetzlichen Kontext bei der Generierung..."
- Erlaubt Use-Case wie: "diktiere die IBN-Werte und das Tool fuellt
  das IBN-Protokoll"
```

### 13.3 Intent-Routing

Aufwand: S.

```text
- Beim Hochladen waehlt der Nutzer das Intent (welches Dokument soll
  daraus entstehen)
- Optional: KI klassifiziert den Intent automatisch ("dieser Text
  klingt nach Inbetriebnahmeprotokoll-Eintrag")
```

---

## Phase 14: Mobile + Rollen-UX

Ziel: Die Erfassungs- und Anzeige-Schicht laeuft auf der Baustelle ohne
Internet und ohne Tablet-Neustart.

### 14.1 Rollenbasierte Landing-Page

Aufwand: M. Steht bereits in ZIELSTRUKTUR.md, noch nicht gebaut.

```text
- Neue Component features/role-landing/
- Beim Login: Routing zu /projects/<slug>/ -> rollenabhaengig:
  - monteur       -> Tagesbericht / heute / meine Unterlagen
  - obermonteur   -> Team-Status / Erfassen / Plaene
  - bauleitung    -> Steuerung / Berichte / Material
  - projektleitung-> Ueberblick / Statusampel / Doku
- Pflegt nur die Hauptaktionen pro Rolle, Details bleiben in den
  existierenden Routes
```

### 14.2 PWA: Manifest + Service Worker

Aufwand: S.

```text
- @angular/service-worker
- manifest.webmanifest mit Icons, Theme
- Installierbar als "App" auf Tablet/Phone
```

### 14.3 Offline-Cache

Aufwand: M. Abhaengig von 14.2.

```text
- IndexedDB-Cache fuer Projekte, Bauabschnitte, eigene Tagesberichte
- Offline-Submit von Tagesberichten in eine lokale Queue
- Sync beim naechsten Empfang
- Konflikt-Strategie: server-wins, lokale Drafts bleiben sichtbar
```

### 14.4 Push-Benachrichtigungen

Aufwand: M. Abhaengig von 14.2.

```text
- Web Push API (VAPID-Keys)
- Subscription pro User
- Trigger: neuer Blocker, Generatorlauf abgeschlossen, Mangel zugewiesen
- Keine Chat-Push (out of scope)
```

### 14.5 Multi-Projekt-Querschnitt fuer Bauleitung

Aufwand: S.

```text
- Neue Route /overview/all
- Liste aller Projekte mit offenen Blockern, Status, naechsten Terminen
- Filter ueber Status, Rolle, Region
```

---

## Phase 15: KI-Mehrwert auf bestehenden Daten

Ziel: Was schon im Tool ist nochmal smarter machen — ohne neue Datenquellen.

### 15.1 Smart-Wochenbericht-Entwurf

Aufwand: S.

```text
- Bauleitung klickt "Wochenbericht generieren"
- Backend nimmt alle DailyReports der KW
- KI-Aufruf (analog Generator-Pipeline) -> Entwurf fuer
  summary, next_week_plan, manpower_notes, material_notes, risks
- Bauleitung sieht Entwurf, kann editieren, dann speichern
```

### 15.2 Anomalie-Hinweise

Aufwand: S.

```text
- Cron oder On-Demand-Check:
  - 3x rote Tagesberichte in Folge -> Notification an Projektleitung
  - Material gleicher Beschreibung 3x in 14 Tagen gemeldet
    -> Hinweis "Wiederkehrendes Material-Problem"
  - Blocker > 7 Tage offen -> Eskalation
- Reine Heuristik, kein ML
```

---

## Phase 16: Compliance & DSGVO-Workflow

### 16.1 Lösch- und Auskunfts-Workflow

Aufwand: M.

```text
- Admin-Aktion: "Kundendaten anonymisieren" pro Projekt
  -> Stammdaten gehasht/genullt, Doku-Outputs neu generiert ohne PII
  (Tokenizer-Pipeline kann das schon, jetzt UI-getrieben)
- Audit-Log: wer hat wann was geloescht
```

### 16.2 Aufbewahrungsfristen-Automatik

Aufwand: S.

```text
- Konfigurierbare TTL je Datentyp (Tagesberichte 6 J, Doku 10 J, Fotos 6 J)
- Cronjob loescht abgelaufene Daten oder verschiebt sie ins Archiv
```

### 16.3 Audit-Log

Aufwand: M.

```text
- Tabelle audit_events
- Middleware oder SQLAlchemy-Event-Listener fuer CRUD-Operationen
- Frontend-Sicht im Admin
```

---

## Phase 17: Optionale Zukunfts-Themen

```text
17.1 GAEB-Import (Leistungsverzeichnis fuer Gewerbe-Auftraege)
17.2 Multi-Mandant (wenn das Tool extern angeboten wird)
17.3 Schnittstelle zum CRM (Stunden-Sync, Kunden-Sync) -- Richtung definieren
17.4 E-Rechnungs-Schnittstelle (XRechnung/ZUGFeRD) -- nur wenn Rechnungslogik
     ins Tool kommt; aktuell uebernimmt das CRM
```

---

## Priorisierung nach Hebel pro Aufwand

| Phase   | Was                                | Aufwand | Hebel    | Reihenfolge |
|---------|------------------------------------|---------|----------|-------------|
| 10.1    | Strangberechnungs-Datenmodell      | M       | hoch     | 1           |
| 10.7    | PDF-Export-Service                 | M       | hoch     | 2           |
| 10.2    | Hydraulischer Abgleich Output      | M       | hoch     | 3           |
| 10.3    | IBN-Protokoll                      | M       | hoch     | 4           |
| 10.5    | Uebergabeprotokoll                 | S       | hoch     | 5           |
| 10.4    | KfW-Fachunternehmererklaerung      | M       | hoch     | 6           |
| 10.8    | Signature-Pad                      | S       | mittel   | 7           |
| 10.6    | Gefaehrdungsbeurteilung            | S       | mittel   | 8           |
| 11.1    | Adapter-Architektur                | S       | hoch     | 9a          |
| 11.3    | Generic-Table-Adapter (extern)     | M       | hoch     | 9b          |
| 11.2    | Viptool-Master-Adapter (intern)    | M       | hoch     | 9c          |
| 11.5    | Manuelle Eingabe-Editor            | M       | hoch     | 9d          |
| 11.6    | Generator-Prompts + Provenance     | S       | hoch     | 9e          |
| 11.4    | IFC-Adapter                        | L       | mittel   | spaeter     |
| 14.1    | Rollenbasierte Landing-Page        | M       | hoch     | 10          |
| 12.1-3  | Foto-Doku (Upload, Annotation, Embed) | M+M+S | mittel   | 11          |
| 13.1-3  | Sprachnotizen-Pipeline             | M+S+S   | hoch     | 12          |
| 14.2-3  | PWA + Offline                      | S+M     | mittel   | 13          |
| 14.4    | Push                               | M       | mittel   | 14          |
| 15.1    | Smart-Wochenbericht                | S       | mittel   | 15          |
| 14.5    | Multi-Projekt-Querschnitt          | S       | mittel   | 16          |
| 15.2    | Anomalie-Hinweise                  | S       | niedrig  | 17          |
| 16.1-3  | DSGVO-Workflow                     | M+S+M   | mittel   | 18          |
| 17.x    | Zukunft                            | -       | -        | spaeter     |

Aufwand-Skala: S = bis 0,5 Tag, M = 0,5–2 Tage, L = > 2 Tage.

---

## Abhaengigkeiten

```text
10.1 (heating_design Schema)
  -> 10.2 (Hydraulischer Abgleich)
  -> 11.1-3 (Importer fuettert das Schema)

10.7 (PDF-Service)
  -> 10.2, 10.3, 10.4, 10.5, 10.6 (alle Pflicht-Doks brauchen PDF)

10.8 (Signature-Pad)
  -> 10.3, 10.5 (Doks mit Unterschrift)

12.1 (Foto-Upload)
  -> 12.2 (Annotation)
  -> 12.3 (Embedding in Output)
  -> 12.4 (Galerie im Tagesbericht)

13.1 (Whisper)
  -> 13.2 (Sprache als Generator-Input)
  -> 13.3 (Intent-Routing)

14.2 (PWA-Basis)
  -> 14.3 (Offline-Cache)
  -> 14.4 (Push)
```

---

## Empfohlene erste Iteration

Wenn ich entscheiden muesste, was zuerst kommt, dann der Block

```text
Phase 10.1 + 10.7 + 10.2 + 10.3 + 10.5
```

— also: Strangschema in der DB, PDF-Export, und die drei zentralen Pflicht-
Dokumente (Hydraulischer Abgleich, IBN, Uebergabe). Damit ersetzt das Tool
sofort die Word-Vorlagen fuer drei der haeufigsten manuellen Dokumente und
liefert messbaren Zeitgewinn.

Direkt danach: Phase 11 (Strangdaten-Importer), damit der Stranglauf nicht
mehr abgetippt wird. Das ist der eigentliche Schub bei dem "viel Zeit beim
Erstellen jeder Baustelle" Problem.

Sprachnotizen (Phase 13) und Foto-Doku (Phase 12) kommen danach — sie sind
"nice to have", aber ohne die Pflicht-Dokumente waere das die falsche
Reihenfolge.
