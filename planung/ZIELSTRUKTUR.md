# Zielstruktur: HEZ Projektbetrieb und Generator-Output

## Grundsatz

Das System besteht aus zwei klar getrennten Ebenen:

```text
1. Generator-Output
   Statische, projektspezifische Unterlagen, die aus input.json, Uploads und Referenzschema erzeugt werden.

2. Baustellenbetrieb
   Dynamische App-Funktionen fuer Tagesberichte, Wochenberichte, Materialmeldungen,
   Blocker, Fotos, Pruefung und Verlauf.
```

Der Generator soll keine isolierten Mail-Formulare erzeugen. Ausfuellbare Berichte werden in der App gespeichert. E-Mail ist nur eine optionale Zusatzaktion.

```text
Richtig:
Formular ausfuellen -> in Datenbank speichern -> im Projekt sichtbar -> optional per Mail senden

Nicht mehr Ziel:
Formular ausfuellen -> nur per Mail senden
```

## Nutzerfluss

### Projektvorbereitung

```text
Admin/Projektleitung
-> Projekt anlegen
-> Projektdaten und Bauabschnitte pflegen
-> technische Unterlagen hochladen
-> Generator starten
-> Output pruefen und veroeffentlichen
-> Benutzer anlegen und Projektrollen zuweisen
```

### Baustelle

```text
Monteur Milo
-> Projektlink oeffnen
-> einloggen
-> landet in seiner rollenbasierten Projektansicht
-> Tagesbericht ausfuellen
-> Fotos/Material/Blocker melden
-> eigene Checklisten und Wochenplan ansehen
```

### Steuerung

```text
Bauleitung/Obermonteur/Projektleitung
-> Projektlink oeffnen
-> Berichte und offene Punkte pruefen
-> Wochenstatus erfassen
-> Material- und Blockerlisten bearbeiten
-> Projektunterlagen und erzeugte Dokumentation einsehen
```

## Rollen

### Admin

Systemrolle fuer Einrichtung und Verwaltung.

```text
Darf:
- Benutzer anlegen
- globale Rollen setzen
- Projekte sehen
- Projektrollen zuweisen
- Generator starten
- Output veroeffentlichen
- alle Berichte sehen
- Datenschutz-/Reidentify-Funktionen nutzen
```

### Projektleitung

Projektweite Steuerungsrolle.

```text
Darf:
- eigene Projekte steuern
- Projektrollen verwalten, falls freigegeben
- Generator starten
- Output pruefen
- alle Projektberichte sehen
- Risiken, Meilensteine, Gantt und Auswertungen sehen
```

### Bauleitung

Operative Steuerung der Baustelle.

```text
Darf:
- Tagesberichte pruefen
- Wochenberichte erstellen
- offene Punkte bearbeiten
- Material- und Blockerstatus pflegen
- relevante Projektunterlagen sehen
```

### Obermonteur

Teamfuehrung vor Ort.

```text
Darf:
- Tagesberichte erfassen
- Wochenbericht vorbereiten oder erfassen
- Materialbedarf melden
- Blocker melden
- Abschnittsstatus sehen
- Monteurunterlagen und Bauleitungsunterlagen sehen
```

### Monteur

Ausfuehrende Rolle vor Ort.

```text
Darf:
- Tagesbericht erfassen
- Fotos hochladen
- Material fehlt melden
- Blocker melden
- eigene Checklisten und Ablaufplaene sehen
```

### Viewer

Leserolle.

```text
Darf:
- freigegebene Projektunterlagen sehen
- keine Berichte erfassen
- keine Rollen oder Projektstruktur aendern
```

## Rollenbasierte Projekt-Startseite

Jeder Projektlink fuehrt zuerst auf eine App-Startseite, nicht auf eine unstrukturierte Dateiliste.

```text
<slug>.hez.tech-artist.de
```

Die Startseite zeigt je nach Rolle unterschiedliche Hauptbereiche.

### Monteur-Startseite

```text
Heute
- Tagesbericht ausfuellen
- Fotos hochladen
- Material fehlt melden
- Problem / Blocker melden

Meine Unterlagen
- Tagescheckliste
- Wochenplan
- Ablaufplan fuer meinen Abschnitt
- Sicherheits- und Baustellenhinweise

Verlauf
- meine letzten Tagesberichte
- meine offenen Meldungen
```

### Obermonteur-Startseite

```text
Baustelle heute
- Tagesberichte Team
- offene Blocker
- fehlendes Material
- Status je Bauabschnitt

Erfassen
- eigener Tagesbericht
- Wochenstatus
- Materialmeldung
- Blocker

Unterlagen
- Monteurplaene
- Abschnittsplaene
- Checklisten
```

### Bauleitungs-Startseite

```text
Steuerung
- Tagesberichte pruefen
- Wochenbericht erfassen
- offene Punkte bearbeiten
- Materialstatus
- Blockerstatus

Projektunterlagen
- detaillierter Ablaufplan
- Risiken und Maengel
- Material und Werkzeug
- Gantt / Meilensteine
```

### Projektleitungs-Startseite

```text
Projektueberblick
- Statusampel
- Meilensteine
- Gantt
- Risiken
- offene Blocker
- fehlendes Material

Dokumentation
- Projektuebersicht
- veroeffentlichte Unterlagen
- Berichtsarchiv
- Generator-Ausgaben
```

## App-Bereiche

### 1. Uebersicht

Dashboard fuer Projektsituation.

```text
Zeigt:
- Projektstatus
- aktuelle Ampel
- Anzahl Tagesberichte
- offene Blocker
- offenes Material
- letzte Aktivitaeten
```

### 2. Baustelle

Hauptbereich fuer laufende Erfassung.

```text
Funktionen:
- Tagesbericht erfassen
- Fotos hochladen
- Material fehlt melden
- Blocker melden
- eigene Eintraege sehen
```

### 3. Berichte

Archiv und Pruefung.

```text
Funktionen:
- Tagesberichte je Projekt anzeigen
- Wochenberichte anzeigen
- nach Datum, Abschnitt, Nutzer, Status filtern
- Bericht als PDF/HTML oeffnen
- optional per Mail senden
```

### 4. Offene Punkte

Operative Aufgabenliste.

```text
Funktionen:
- Material offen
- Blocker offen
- Maengel offen
- Status setzen: offen, in Arbeit, erledigt
- Verantwortliche Person setzen
```

### 5. Unterlagen

Rollenbasierte Sicht auf generierte Dokumente.

```text
Funktionen:
- relevante Dokumente je Rolle anzeigen
- alle Dokumente fuer Leitung sichtbar
- Suche / Filter nach Rolle, Abschnitt, Kategorie
```

### 6. Administration

Verwaltung.

```text
Funktionen:
- Benutzer anlegen
- globale Rollen vergeben
- Projektmitglieder zuweisen
- Projektrollen setzen
```

## Generator-Output

Der Generator erzeugt kuenftig nicht mehr nur eine flache Sammlung von Dokumenten. Der Output wird rollen- und zweckorientiert strukturiert.

Jeder veroeffentlichte Generator-Output muss dauerhaft nachvollziehbar bleiben. Eine neue Veroeffentlichung ersetzt nur den aktuellen Live-Stand, loescht aber keine alten Generator-Ausgaben.

Speicherregel:

```text
storage/projects/<slug>/
  ... aktueller Live-Stand ...
  _versions/
    run-<generation_run_id>/
      ... vollstaendiger Output dieses Generatorlaufs ...
    20260515T104500Z/
      ... vollstaendiger Output einer manuellen Veroeffentlichung ...
```

Damit ist auch in mehreren Jahren nachvollziehbar, welche Dateien zu welchem Generatorlauf erzeugt und veroeffentlicht wurden. Die normale Benutzeroberflaeche zeigt standardmaessig nur den aktuellen Live-Stand; Versionen werden separat als Archiv sichtbar gemacht.

Zielstruktur:

```text
output/
  00_Start/
    index.html
    Projekt_Navigation.html

  01_Monteur/
    MONTEUR_Tagescheckliste.html
    MONTEUR_Wochenplan.html
    MONTEUR_Ablaufplan_Abschnitte.html
    MONTEUR_Baustellenhinweise.html

  02_Obermonteur/
    OBERMONTEUR_Teamstatus.html
    OBERMONTEUR_Abschnittsplanung.html
    OBERMONTEUR_Checklisten.html

  03_Bauleitung/
    BAULEITUNG_Detaillierter_Ablaufplan.html
    BAULEITUNG_Material_und_Werkzeug.html
    BAULEITUNG_Risiken_und_Maengel.html
    BAULEITUNG_Blocker_und_Offene_Punkte.html

  04_Projektleitung/
    PROJEKTLEITUNG_Projektuebersicht.html
    PROJEKTLEITUNG_Meilensteinplan.html
    PROJEKTLEITUNG_Gantt_Uebersicht.html
    PROJEKTLEITUNG_Statusuebersicht.html

  05_Allgemein/
    ALLGEMEIN_Projektunterlagen.html
    ALLGEMEIN_Kontakte.html
    ALLGEMEIN_Dokumentenindex.html
```

## Benennung

Dateien muessen sofort erkennen lassen, fuer wen sie gedacht sind.

Regel:

```text
<ROLLE>_<INHALT>.html
```

Beispiele:

```text
MONTEUR_Tagescheckliste.html
MONTEUR_Wochenplan.html
OBERMONTEUR_Teamstatus.html
BAULEITUNG_Material_und_Werkzeug.html
PROJEKTLEITUNG_Gantt_Uebersicht.html
```

## Ausfuellbare Dokumente

Ausfuellbare Dokumente sind App-Formulare, nicht statische Generator-Dateien.

### Tagesbericht

```text
Speicherort:
daily_reports

Felder:
- Projekt
- Datum
- Abschnitt
- Team
- erledigte Arbeiten
- offene Arbeiten
- Material fehlt
- Blocker
- Status gruen/gelb/rot
- Notizen
- Fotos

Aktionen:
- speichern
- spaeter bearbeiten, falls erlaubt
- optional per Mail senden
- als PDF/HTML exportieren
```

### Wochenbericht

```text
Speicherort:
weekly_reports

Felder:
- Kalenderwoche / Zeitraum
- Zusammenfassung
- Plan naechste Woche
- Personal
- Material
- Risiken
- Status gruen/gelb/rot

Aktionen:
- speichern
- optional per Mail senden
- als PDF/HTML exportieren
```

### Materialmeldung

```text
Speicherort:
material_issues

Felder:
- Abschnitt
- Beschreibung
- Prioritaet
- Status
- Verantwortlich
- Faelligkeit
```

### Blocker

```text
Speicherort:
blockers

Felder:
- Abschnitt
- Beschreibung
- Schweregrad
- Status
- Verantwortlich
- Faelligkeit
```

## Navigation

Die veroeffentlichte Projektseite soll nicht mit einer kompletten Dateiuebersicht starten.

Startseite:

```text
Projektname
Adresse
eigene Rolle
heutige Hauptaktionen
relevante Unterlagen
offene Punkte
letzte Berichte
```

Die vollstaendige Dokumentenliste bleibt verfuegbar, aber nur als Unterbereich.

## Konsequenz fuer den Generator

Der Generator muss kuenftig Folgendes erzeugen:

```text
1. Rollenbasierte Dokumente
2. klare Datei- und Ordnernamen
3. eine strukturierte Dokumentennavigation
4. keine Mail-only-Formulare
5. keine ausfuellbaren Berichte als isolierte statische HTML-Endpunkte
6. Hinweise, welche App-Formulare fuer laufende Erfassung genutzt werden sollen
```

Die App muss Folgendes uebernehmen:

```text
1. Login und rollenbasierte Projektstartseite
2. Tagesbericht speichern
3. Wochenbericht speichern
4. Material/Blocker speichern und bearbeiten
5. Berichtshistorie anzeigen
6. optionaler Mailversand
7. Export als PDF/HTML
```

## Naechste Umsetzungsschritte

Empfohlene Reihenfolge:

```text
1. App-Tab "Baustelle" bauen
2. Tagesbericht-Formular sichtbar machen und speichern
3. Berichtsliste je Projekt anzeigen
4. Material- und Blockerliste mit Status bauen
5. Rollenbasierte Projektstartseite einfuehren
6. Generator-Prompt auf neue Output-Struktur umstellen
7. Output-Validator an neue Ordnerstruktur anpassen
8. Alte Mail-only-Formulare aus dem Generator-Output entfernen
```
