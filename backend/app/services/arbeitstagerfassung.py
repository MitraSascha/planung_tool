"""Arbeitstagerfassung: ein Roh-Text → strukturierter Erledigt/Offen-Split.

Der Monteur tippt oder spricht in **einem** Feld einen freien Tagesabschluss
("Heute Strang 3 fertig gemacht, morgen noch Strang 4. Material 3 Bögen
DN50 fehlen noch."). Dieser Service ruft ein kleines LLM (gpt-4o-mini),
das in **einem** Call:

  1. ggf. nach Deutsch übersetzt (wenn der Monteur in seiner Muttersprache
     gesprochen hat — Voice-Pipeline detected die Sprache, Service bekommt
     sie als Hint),
  2. den Text in „Erledigte Arbeiten" und „Offene Aufgaben" splittet,
  3. saubere Stichpunkte (`- ` Bullet-Lines) formatiert.

Output landet in ``daily_reports.completed_work`` / ``daily_reports.open_work``.
Roh-Text bleibt in ``daily_reports.raw_work_log`` — damit Re-Edits den
Original-Input wieder splitten können.

Bei LLM-Fehler oder fehlendem ``OPENAI_API_KEY`` wird der Roh-Text einfach
unverändert nach ``completed`` geschoben (``pending`` bleibt leer) — der
Bericht ist dann nicht KI-strukturiert, aber nicht verloren.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from app.core.settings import settings

logger = logging.getLogger(__name__)

# Klein genug für Sekunden-Latenz, gut genug für strukturierte Outputs in
# Deutsch und in den typischen Baustellen-Sprachen.
LLM_MODEL = "gpt-4o-mini"


@dataclass
class ArbeitstagSplit:
    completed: str
    pending: str
    detected_language: str | None
    translated: bool


_SYSTEM_PROMPT = """Du bist ein Assistent für SHK-Handwerker (Sanitär, Heizung, Klima) auf Baustellen.

Eingabe: freier Tagesabschluss-Text (Tippeingabe oder Voice-Transkript), kann mehrsprachig sein (Türkisch, Russisch, Polnisch, Kurdisch, Arabisch, Deutsch, …).

Aufgabe:
1. Falls die Eingabe NICHT auf Deutsch ist → übersetze sie nach Deutsch und behalte Fachbegriffe (Vorlauf/Rücklauf, Druckprüfung, Strang, Heizkreis, Inbetriebnahme, Anschluss, Spülung, Dämmung) korrekt im Deutschen bei.
2. Erkenne im Text zwei Gruppen:
   - **Erledigte Arbeiten** (was wurde heute gemacht / fertig?)
   - **Offene Aufgaben** (was bleibt morgen / ist noch nicht fertig / muss noch?)
3. Formatiere beide Gruppen als saubere deutsche Stichpunkte, jede Zeile beginnt mit "- " und endet ohne Punkt.
4. Wenn eine Gruppe leer wäre (z.B. der Monteur hat nur Erledigtes oder nur Offenes erwähnt), gib einen leeren String "" zurück — KEIN Platzhalter wie „nichts".

Antworte AUSSCHLIESSLICH mit gültigem JSON in diesem Schema:
{
  "completed": "- ...\\n- ...",
  "pending": "- ...\\n- ...",
  "detected_language": "de" | "tr" | "ru" | "pl" | "ku" | "ar" | ... ,
  "translated": true | false
}
"""


def _fallback_split(raw_text: str, hint_language: str | None) -> ArbeitstagSplit:
    """Wenn LLM nicht verfügbar/fehlerhaft: Roh-Text als completed übernehmen,
    pending leer. Der Bericht ist damit nicht verloren — der Monteur sieht
    den Inhalt im Erledigt-Feld und kann manuell trennen.
    """
    return ArbeitstagSplit(
        completed=raw_text.strip(),
        pending="",
        detected_language=hint_language,
        translated=False,
    )


def split_arbeitstagerfassung(
    raw_text: str,
    source_language: str | None = None,
) -> ArbeitstagSplit:
    """Hauptfunktion: Roh-Text → strukturierter Split.

    Args:
        raw_text: Eingabe vom Monteur (Voice oder Text), mind. ein paar Worte.
        source_language: Optionaler Hint (ISO 639-1) — z.B. wenn die
            Voice-Pipeline schon „tr" erkannt hat. Der LLM nutzt das als
            Bestätigung, macht aber im Zweifel eigene Erkennung.

    Returns:
        :class:`ArbeitstagSplit`. Bei Fehlern Fallback (Roh-Text als completed).
    """
    text = (raw_text or "").strip()
    if not text:
        return ArbeitstagSplit(
            completed="", pending="", detected_language=source_language, translated=False
        )

    api_key = settings.openai_api_key
    if not api_key:
        logger.warning("Arbeitstagerfassung-Split übersprungen: OPENAI_API_KEY fehlt")
        return _fallback_split(text, source_language)

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        logger.warning("openai-Package fehlt — Fallback-Split")
        return _fallback_split(text, source_language)

    client = OpenAI(api_key=api_key)
    user_msg_parts = [f"Tagesabschluss-Text:\n{text}"]
    if source_language:
        user_msg_parts.append(f"\nErkannte Quellsprache: {source_language}")
    user_msg = "\n".join(user_msg_parts)

    try:
        completion = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            timeout=20.0,
        )
        raw_json = (completion.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM-Call für Arbeitstagerfassung fehlgeschlagen: %s", exc)
        return _fallback_split(text, source_language)

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        logger.warning("LLM-Antwort war kein JSON: %s — Antwort: %r", exc, raw_json[:200])
        return _fallback_split(text, source_language)

    completed = str(data.get("completed") or "").strip()
    pending = str(data.get("pending") or "").strip()
    detected = data.get("detected_language") or source_language
    if detected is not None:
        detected = str(detected).strip().lower() or None
    translated = bool(data.get("translated"))

    # Wenn der LLM beide Felder leer macht, lieber den Roh-Text bewahren als
    # einen sinnlos leeren Bericht abzuschicken.
    if not completed and not pending:
        return _fallback_split(text, source_language)

    return ArbeitstagSplit(
        completed=completed,
        pending=pending,
        detected_language=detected,
        translated=translated,
    )
