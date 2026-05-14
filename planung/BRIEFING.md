# Briefing: HEZ Projektgenerator

## Ausgangslage

Aktuell existiert mit `project_docu/` ein manuell erzeugtes Referenzprojekt fuer eine SHK-Heizungsmodernisierung. Dieses Projekt enthaelt Markdown- und HTML-Dokumente fuer Projektuebersicht, Bauabschnitte, Ablaufplaene, Checklisten, Monteurplaene, Materiallisten, Risiken, Gantt-Uebersicht und Tagesbericht-App.

Diese bestehende Struktur soll als Schema fuer ein neues webbasiertes Tool dienen.

## Ziel

Das Tool soll fuer jedes neue SHK-Projekt automatisch eine vollstaendige Projektdokumentation erzeugen.

Ein Projekt bekommt einen eindeutigen Slug, zum Beispiel:

```text
hez-640
```

Daraus entsteht spaeter automatisch eine Subdomain:

```text
hez-640.hez.tech-artist.de
```

Unter dieser Subdomain soll die erzeugte HTML-Dokumentation erreichbar sein.

## Grundprinzip

Die KI soll nicht frei kreativ arbeiten, sondern ein festes Schema projektspezifisch befuellen.

```text
Referenzschema aus project_docu/
+ strukturierte Projektdaten
+ technische Unterlagen aus docs/
+ Formularwerte
+ fachliche Generator-Anweisung
= neue .md- und .html-Projektdokumentation
```

## Eingaben

### 1. Technische Projektdaten

Technische Rohdaten werden pro Projekt hochgeladen oder uebergeben, zum Beispiel:

```text
docs/
  Heizlastdaten
  CSV-Dateien
  Plaene
  technische Listen
  weitere Unterlagen
```

### 2. Fachliche Generator-Anweisung

`Information.md` beschreibt, welche Dokumente erzeugt werden sollen und welche fachliche Tiefe erwartet wird.

Wichtig: `Information.md` darf keine feste Anzahl von Bauabschnitten erzwingen. Die Anzahl der Bauabschnitte kommt aus den strukturierten Projektdaten.

### 3. Formular-Input

Das Tool stellt ein Formular bereit, in dem projektspezifische Werte gepflegt werden.

Beispiele:

```text
Projektname
Projekt-Slug
Adresse
Projektverantwortlicher
Bauleitung
Obermonteur
Startdatum
Zieltermin
geplante Stunden
Bauabschnitte
verantwortliche Personen je Abschnitt
eingesetzte Mitarbeiter
Besonderheiten
offene Punkte
```

### 4. Flexible Bauabschnitte

Bauabschnitte muessen dynamisch sein, weil nicht jede Baustelle gleich gross ist.

Beispiele:

```text
Abschnitt 1: Kellerleitung
Abschnitt 2: Straenge
Abschnitt 3: Heizzentrale
Abschnitt 4: Wohnungen
```

Oder bei einem anderen Projekt:

```text
Abschnitt 1: Demontage
Abschnitt 2: Montage
Abschnitt 3: Inbetriebnahme
```

Die Generator-Logik darf niemals fest auf 3 oder 4 Abschnitte programmiert werden.

## Erwarteter Output

Pro Projekt sollen wieder Markdown- und HTML-Dateien nach dem bekannten Schema erzeugt werden.

Beispielstruktur:

```text
01_Projektuebersicht/
02_Abschnitt_1/
03_Abschnitt_2/
04_Abschnitt_3/
...
06_Detaillierter_Ablaufplan/
07_Checklisten/
08_Monteur_Tagescheckliste/
09_Monteur_Wochenplan/
10_Tagesbericht_App/
11_Meilensteinplan/
12_Material_und_Werkzeug/
13_Risiko_und_Maengel/
14_Gantt_Uebersicht/
99_HTML_Uebersicht/
```

Die Abschnittsordner werden anhand der eingegebenen Bauabschnitte dynamisch erzeugt.

## KI-Integration

Die KI wird ueber Codex CLI eingebunden.

Wichtig:

```text
codex exec -p hez-generator
```

`-p` ist das Codex-Profil aus `config.toml`, nicht der eigentliche Prompt.

Der Prompt wird vom Backend dynamisch erzeugt und per stdin an Codex uebergeben.

## Betrieb

Das gesamte System soll spaeter in Docker laufen.

Geplante Services:

```text
backend    FastAPI, Generatorlogik, Codex CLI
frontend   Angular 21+ Admin-Oberflaeche
postgres   SQL-Datenbank
nginx      Reverse Proxy und Subdomain-Routing
storage    Workspaces, Uploads, veroeffentlichte Projekte
```

## Datenhaltung

Alles, was erzeugt wird, muss dauerhaft gespeichert bleiben.

Gespeichert werden sollen mindestens:

```text
Projektstammdaten
Formularwerte
Bauabschnitte
hochgeladene Unterlagen
generierte Markdown-Dateien
generierte HTML-Dateien
Generatorlauf-Status
Fehlerausgaben
Zeitpunkte
veroeffentlichte Version
```

Auswertungen kommen spaeter. Trotzdem muessen die Daten von Anfang an sauber strukturiert gespeichert werden.

## Nicht im ersten Schritt

Folgende Themen werden bewusst spaeter behandelt:

```text
Statistiken
Projekt-Auswertung
Performance-Auswertung
Nutzertracking
komplexe Rechteverwaltung
mehrere Kundenbereiche
```

