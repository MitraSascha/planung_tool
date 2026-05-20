# Tagesbericht: „Fehlendes Material" als Dropdown statt Freitext

**Status:** BLOCKED — User liefert noch die Auswahlliste
**Erstellt:** 2026-05-19
**Bereich:** Daily-Report-Form / Material

## Anforderung

Aktuell ist „Fehlendes Material" im Tagesbericht ein Freitext-Feld. Soll umgebaut werden zu einem **Dropdown** mit einer **vom User kuratierten Liste** ausgewählter Artikel.

## Konsequenz für bisherige Artikelstamm-Arbeit (2026-05-18)

Die bereits implementierte **Artikelstamm-Live-Suche** (DATANORM-DB, >2 Mio Artikel) wird damit **NICHT** der Pfad für „fehlendes Material" sein. Der Artikelstamm-Code (`services/artikelstamm.py`, `api/articles.py`, `MaterialPickerComponent` Artikelstamm-Tab) ist nicht obsolet — er bleibt für „ad-hoc Material aus dem Großhandel verbaut → Nachkalkulation" sinnvoll. Aber für den **Use-Case „Monteur meldet was er als nächstes braucht"** wird stattdessen die kuratierte Liste verwendet.

**Why:** User will Kontrolle über die Auswahl behalten — DATANORM-Live-Suche ist für diesen Use-Case zu unstrukturiert / zu viele Artikel.

## Implementierungs-Skizze (vorzubereiten)

- Neue Tabelle `material_picklist_entries` (oder Reuse einer bestehenden Struktur?) — vom Admin/Lead pflegbar.
- Dropdown im Daily-Report-Form: „Fehlendes Material" → `<select>` mit Auto-Complete (analog MaterialPicker, aber Quelle ist die kuratierte Liste).
- Optional: Mehrfach-Auswahl (Monteur meldet mehrere fehlende Posten an einem Tag).

## Entscheidung 2026-05-19 (final, vom Chef): zwei strikt getrennte Felder

**Keine KI-Extraktion aus der Arbeitstagerfassung in das Material-Feld.**
Die beiden Felder bleiben fachlich getrennt:

1. **Arbeitstagerfassung** (`raw_work_log`) — Monteur erzählt Erledigt/Offen,
   KI splittet. Material-Fehlmeldungen werden vom LLM-Prompt **explizit
   ausgeschlossen** (siehe ``_SYSTEM_PROMPT`` in
   ``backend/app/services/arbeitstagerfassung.py``, WICHTIG-Block).
2. **Materialerfassung** (`material_missing`) — separates Feld, Monteur trägt
   fehlendes Material selbst ein. Wenn die kuratierte Artikel-Liste da ist,
   wird daraus ein Dropdown (siehe ursprüngliche Skizze unten).

**Why:** Chef will klare Trennung; vermeidet falsch zugeordnete LLM-Treffer
und gibt dem Monteur die Hoheit darüber was als „Material fehlt" gilt.
**How to apply:** Beim Bauen des Material-Dropdowns NICHT zusätzlich die
LLM-Extraktion aktivieren. Roh-Text bleibt nur Quelle für Erledigt/Offen.

## Offene Punkte (warten auf User)

- **Liste der Artikel** für das Dropdown (User stellt zusammen).
- Soll die Liste pro Projekt oder global gepflegt werden?
- Sollen Mengen + Einheiten mit erfasst werden (nicht nur „brauche Artikel X")?
