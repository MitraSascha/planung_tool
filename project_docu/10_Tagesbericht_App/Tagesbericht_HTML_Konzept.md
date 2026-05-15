# Konzept: Mobile Monteur-HTML-App fuer Tagesberichte

## Ziel

Die mobile HTML-App soll Monteuren bei einer SHK-Heizungsmodernisierung in einem bewohnten Mehrfamilienhaus eine einfache Tagesdokumentation auf dem Handy ermoeglichen. Die Datei funktioniert offline, benoetigt keine Anmeldung und erzeugt am Tagesende automatisch einen Tagesbericht, der per E-Mail an das Buero gesendet werden kann.

## Einsatzsituation

- Baustelle: Heizungsmodernisierung im bewohnten Mehrfamilienhaus
- Nutzer: Monteure, Teamleiter, Bauleitung
- Bediengeraet: Smartphone oder Tablet
- Nutzung: taeglich vor Ort, auch ohne stabile Internetverbindung
- Ausgabe: strukturierter Tagesbericht per E-Mail

## Struktur der HTML-Seite

1. Kopfbereich
   - Titel der App
   - kurzer Hinweis "offline nutzbar"
   - Tagesstatus als sichtbare Ampel

2. Projektdaten
   - fest hinterlegtes Projekt: Mareschstrasse 1, Berlin Neukoelln
   - Abschnittsauswahl
   - Tagesdatum
   - Monteur oder Team

3. Aufgabenliste
   - baustellentaugliche Aufgaben passend zum ausgewaehlten Abschnitt
   - Checkboxen zum Abhaken
   - Erledigt-Anzeige als Fortschritt

4. Rueckmeldungen
   - Material fehlt
   - Probleme / Behinderungen
   - ausgefuehrte Arbeiten
   - offene Arbeiten

5. Foto-Hinweise
   - Hinweisfelder zu notwendigen Fotos
   - Checkboxen fuer Fotodokumentation

6. Tagesstatus
   - Gruen: Tagesziel erreicht, keine Blocker
   - Gelb: Teilziel erreicht, Rueckfrage oder Nacharbeit offen
   - Rot: Arbeit blockiert, Entscheidung oder Material notwendig

7. Zusammenfassung und Versand
   - automatische Zusammenfassung als Textvorschau
   - Button "Tagesbericht per E-Mail senden"
   - Button "Formular zuruecksetzen"

## Sinnvolle Felder

| Feld | Typ | Zweck |
| --- | --- | --- |
| Projekt | festes Textfeld | Zuordnung zur Baustelle Mareschstrasse 1 |
| Abschnitt | Auswahlfeld | Zuordnung zum Bauabschnitt |
| Tagesdatum | Datum | Berichtsdatum |
| Monteur / Team | Texteingabe | Verantwortliche Personen |
| Aufgaben | Checkboxliste | Tagesfortschritt dokumentieren |
| Material fehlt | Textfeld | Fehlende Teile, Mengen, Dimensionen |
| Probleme / Behinderungen | Textfeld | Zugang, Bestand, Absperrung, Bewohner, Planabweichung |
| Ausgefuehrte Arbeiten | Textfeld | Freitext fuer Tagesleistung |
| Offene Arbeiten | Textfeld | Restarbeiten und naechste Schritte |
| Foto-Hinweise | Checkboxliste | Nachweise fuer Demontage, Rohmontage, Druckprobe, Brandschutz |
| Tagesstatus | Gruen/Gelb/Rot | Schnelle Bewertung fuer Bauleitung und Buero |

## Beispiel-Tagesbericht

Betreff:

```text
Tagesbericht SHK - Mareschstrasse 1 - Abschnitt 2 - 14.05.2026
```

Mailtext:

```text
Tagesbericht SHK-Heizungsmodernisierung

Projekt: Mareschstrasse 1, Berlin Neukoelln
Abschnitt: Abschnitt 2 - Straenge
Datum: 14.05.2026
Monteur / Team: Team Strang 1
Status: Gelb - Rueckfrage oder Nacharbeit offen

Erledigte Aufgaben:
- Baustelle eingerichtet / Schutzmassnahmen geprueft
- Alte Heizkoerper und Anschlussleitungen demontiert
- Neue Steigleitung vorbereitet

Material fehlt:
Pressfittings 22 mm, 8 Stueck. Rohrschellen M8, ca. 20 Stueck.

Probleme / Behinderungen:
Wohnung 2. OG links war nicht zugaenglich. Bestand im Schacht weicht vom Plan ab.

Ausgefuehrte Arbeiten:
Demontage im EG und 1. OG abgeschlossen. Rohre im Strang A zugeschnitten und teilweise gepresst.

Offene Arbeiten:
Zugang 2. OG links klaeren. Brandschutzdurchfuehrung im Schacht durch Bauleitung pruefen lassen.

Foto-Hinweise:
- Bestand vor Demontage dokumentiert
- Rohmontage / Leitungsfuehrung fotografiert
- Problemstelle fotografiert
```

## Mailto-Uebergabe

Die HTML-Datei erzeugt aus allen Eingaben automatisch einen Berichtstext. Beim Klick auf "Tagesbericht per E-Mail senden" wird ein `mailto:`-Link erzeugt:

```text
mailto:buero@example.de?subject=Tagesbericht%20SHK...&body=Tagesbericht%20...
```

Vorteile:

- funktioniert ohne Server
- funktioniert offline bis zum Oeffnen der Mail-App
- nutzt die vorhandene Mail-App des Handys
- keine Anmeldung und keine zentrale Benutzerverwaltung notwendig

Grenzen:

- sehr lange Berichte koennen je nach Mail-App gekuerzt werden
- Fotos werden nicht automatisch angehaengt
- der Versand ist erst erfolgt, wenn der Monteur die E-Mail in der Mail-App absendet

Praxisempfehlung:

- Fotos separat in der Mail-App anhaengen
- feste Empfaengeradresse im HTML vorbelegen
- Betreff immer mit Projekt, Abschnitt und Datum erzeugen

## Spaetere Anbindung an Datenbank, Dateiablage oder interne API

### Variante 1: Interne API

Die statische HTML-Datei kann spaeter statt `mailto:` einen `fetch()`-Aufruf an eine interne HEZ-API senden. Das Backend kann die Daten dann weiterverarbeiten:

- E-Mail an Buero senden
- Eintrag in der Projektdatenbank speichern
- PDF-Tagesbericht erzeugen
- Benachrichtigung an Bauleitung senden
- Materialmangel automatisch als Aufgabe anlegen

Beispiel-Datenstruktur:

```json
{
  "projekt": "Mareschstrasse 1, Berlin Neukoelln",
  "abschnitt": "Abschnitt 2 - Straenge",
  "datum": "2026-05-14",
  "team": "Team Strang 1",
  "status": "Gelb",
  "aufgaben": ["Demontage abgeschlossen", "Rohmontage vorbereitet"],
  "materialFehlt": "Pressfittings 22 mm",
  "probleme": "Wohnung 2. OG links nicht zugaenglich",
  "ausgefuehrteArbeiten": "Demontage EG und 1. OG abgeschlossen",
  "offeneArbeiten": "Zugang 2. OG links klaeren",
  "fotoHinweise": ["Bestand", "Rohmontage", "Problemstelle"]
}
```

### Variante 2: Datenbank

Das Backend kann jeden Tagesbericht als eigenen Datensatz speichern. Sinnvolle Spalten:

- Zeitstempel
- Projekt
- Abschnitt
- Datum
- Team
- Status
- erledigte Aufgaben
- Material fehlt
- Probleme
- ausgefuehrte Arbeiten
- offene Arbeiten
- Foto-Hinweise

### Variante 3: Datenbank

Bei mehreren Baustellen kann eine kleine Datenbank sinnvoll sein. Tabellen:

- Projekte
- Abschnitte
- Tagesberichte
- Aufgaben
- Materialmangel
- Probleme / Behinderungen
- Fotos / Fotolinks

### Variante 4: Fotodokumentation

Fotos sollten nicht direkt in der HTML-Datei gespeichert werden. Besser:

- Monteur fotografiert mit Handy
- Mail-App: Fotos manuell anhaengen
- spaeter: Upload-Link zu interner API, Nextcloud, Google Drive oder SharePoint
- Tagesbericht speichert nur Foto-Hinweise und optional Dateinamen

## Bedienkonzept fuer Monteure

- grosse Felder und Buttons fuer Handschuh-/Baustellenbedienung
- keine Pflicht zur Anmeldung
- klare Reihenfolge von oben nach unten
- Standardaufgaben wechseln automatisch passend zum Abschnitt
- Freitextfelder fuer alles, was nicht in die Checkliste passt
- Ampelstatus zwingt zu schneller Bewertung des Tages
- Berichtsvorschau zeigt vor dem Versand, was ans Buero geht

## Datenschutz und Organisation

- Keine personenbezogenen Bewohnerdaten in Freitext schreiben.
- Wohnungsbezug nur sachlich dokumentieren, zum Beispiel "2. OG links nicht zugaenglich".
- Fotos mit Bewohnerbezug vermeiden oder vor Versand pruefen.
- Die Empfaengeradresse sollte eine zentrale Projekt- oder Buero-Adresse sein.

## Geaenderte Dateien

- `Tagesbericht_HTML_Konzept.md`
- `Mobile_Monteur_HTML_Code.html`
