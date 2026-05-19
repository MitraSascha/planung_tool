"""Read-only-Zugriff auf die externe Artikelstamm-DB (DATANORM, >2 Mio Artikel).

Wird vom Material-Picker des Tagesbericht-Wizards verwendet, damit Monteure
auch Material verbuchen können, das nicht im Projekt-Material-Stamm steht
(typisch: ad-hoc Großhandel-Einkauf vor Ort).

Die DB läuft in einem eigenen Docker-Netzwerk (`artikelstamm_net`); die
Verbindungs-URL kommt über `ARTIKELSTAMM_DB_URL`. Wenn nicht konfiguriert,
liefern die Funktionen leere Ergebnisse — kein harter Fehler, damit das
Tool auch ohne Artikelstamm-Anbindung läuft.

Suche nutzt PostgreSQL ILIKE über kurztext1, kurztext2, artikelnummer,
hersteller, hersteller_artikelnummer, ean. Robust und ohne externe
Abhängigkeit (Ollama für Vektor-Suche). Vektor-Suche kann später als
zweiter Pfad ergänzt werden, sobald sichergestellt ist, dass Ollama
erreichbar ist.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.core.settings import settings

logger = logging.getLogger(__name__)


def _connect() -> psycopg.Connection | None:
    url = settings.artikelstamm_db_url
    if not url:
        return None
    try:
        return psycopg.connect(url, connect_timeout=3)
    except Exception as exc:  # pragma: no cover — connectivity check at runtime
        logger.warning("Artikelstamm-DB nicht erreichbar: %s", exc)
        return None


def is_available() -> bool:
    """True wenn die DB konfiguriert + erreichbar ist."""
    conn = _connect()
    if conn is None:
        return False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            return cur.fetchone() is not None
    finally:
        conn.close()


def search_articles(query: str, limit: int = 30) -> list[dict[str, Any]]:
    """ILIKE-Suche über die wichtigsten Text-Spalten. Liefert eine Liste
    von Artikel-Dicts; leere Liste wenn DB nicht erreichbar oder Query
    leer ist.

    Sortierung: Treffer im kurztext1 vor Treffer in anderen Spalten,
    danach alphabetisch nach artikelnummer.
    """
    q = (query or "").strip()
    if not q or len(q) < 2:
        return []
    limit = max(1, min(int(limit or 30), 100))
    conn = _connect()
    if conn is None:
        return []
    try:
        pattern = f"%{q}%"
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    a.artikelnummer,
                    a.kurztext1,
                    a.kurztext2,
                    a.warengruppe,
                    a.mengeneinheit,
                    a.preis_eur,
                    h.hersteller,
                    h.hersteller_artikelnummer,
                    h.ean,
                    -- Score: 3 wenn artikelnummer/EAN exakt, 2 wenn kurztext1 trifft,
                    -- 1 sonst. Sortierung priorisiert relevante Treffer.
                    (CASE
                        WHEN a.artikelnummer ILIKE %(exact)s OR h.ean = %(q)s THEN 3
                        WHEN a.kurztext1 ILIKE %(pat)s THEN 2
                        ELSE 1
                     END) AS rank_score
                FROM artikel a
                LEFT JOIN artikel_hersteller h USING (artikelnummer)
                WHERE a.aktiv = true
                  AND (
                       a.artikelnummer ILIKE %(pat)s
                    OR a.kurztext1 ILIKE %(pat)s
                    OR a.kurztext2 ILIKE %(pat)s
                    OR h.hersteller ILIKE %(pat)s
                    OR h.hersteller_artikelnummer ILIKE %(pat)s
                    OR h.ean = %(q)s
                  )
                ORDER BY rank_score DESC, a.artikelnummer
                LIMIT %(lim)s
                """,
                {"pat": pattern, "exact": q, "q": q, "lim": limit},
            )
            rows = cur.fetchall()
        # numerischer Preis aus NUMERIC → float
        for r in rows:
            if r.get("preis_eur") is not None:
                r["preis_eur"] = float(r["preis_eur"])
        return rows
    except Exception as exc:
        logger.warning("Artikelstamm-Suche fehlgeschlagen: %s", exc)
        return []
    finally:
        conn.close()


def get_article(artikelnummer: str) -> dict[str, Any] | None:
    """Einzelner Artikel mit allen Stammdaten — wird beim „aus Artikelstamm
    anlegen"-Flow gerufen, um die Daten ohne erneute Suche zu holen."""
    if not artikelnummer:
        return None
    conn = _connect()
    if conn is None:
        return None
    try:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    a.artikelnummer,
                    a.kurztext1,
                    a.kurztext2,
                    a.warengruppe,
                    a.mengeneinheit,
                    a.preis_eur,
                    h.hersteller,
                    h.hersteller_artikelnummer,
                    h.ean,
                    al.langtext
                FROM artikel a
                LEFT JOIN artikel_hersteller h USING (artikelnummer)
                LEFT JOIN artikel_langtext al USING (artikelnummer)
                WHERE a.artikelnummer = %s
                LIMIT 1
                """,
                (artikelnummer,),
            )
            row = cur.fetchone()
        if row and row.get("preis_eur") is not None:
            row["preis_eur"] = float(row["preis_eur"])
        return row
    except Exception as exc:
        logger.warning("Artikel-Lookup fehlgeschlagen für %s: %s", artikelnummer, exc)
        return None
    finally:
        conn.close()
