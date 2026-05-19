"""Materialkatalog: Import aus ``Materialliste.csv`` + Such-Helper.

Der Chef pflegt die Liste manuell in der CSV (im Repo-Root ``Materialliste.csv``).
Beim Backend-Startup wird ein idempotenter Import ausgeführt:

  * existierende Artikel (Match per ``artikelnummer``) werden geupdated
    (Beschreibungen + Preise können sich ändern),
  * fehlende Artikel werden auf ``active=False`` gesetzt (Soft-Delete, damit
    bereits angelegte Materialmeldungen ihre Referenz behalten),
  * neue Artikel werden angelegt.

Die CSV ist Semikolon-separiert mit UTF-8-BOM und folgendem Schema:
``;Artikelnummer;Menge;Beschreibung 1;Beschreibung 2;Listenpreis;Nettowert;``

(Die erste Spalte ist ein Typ-Marker „ART" und wird übersprungen.
Die Spalte ``Menge`` ist eine Default-Mengeneinheit aus dem Office-Stamm —
wird nicht im Katalog gespeichert, der Monteur gibt seine eigene Menge ein.)
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.orm_models import MaterialCatalogItem

logger = logging.getLogger(__name__)

# Die CSVs liegen im Repo-Root und werden via docker-compose nach /app/
# gemountet. Wir suchen alle Material*.csv-Dateien und leiten die
# ``kategorie`` aus dem Dateinamen ab.
_CSV_DIRS = (
    Path("/app"),
    Path(__file__).resolve().parents[3],  # Repo-Root im lokalen Dev
)

# Dateiname → Kategorie. Lowercase-Substring-Match, damit Tippfehler-tolerant.
_CATEGORY_PATTERNS = (
    ("brandschutz", "brandschutz"),
    ("isolierung", "isolierung"),
    # Fallback: alles andere mit „Material" im Namen ist die Standard-Liste.
    # Wird in ``_kategorie_from_filename`` als Default benutzt.
)


def _kategorie_from_filename(name: str) -> str:
    lower = name.lower()
    for needle, kat in _CATEGORY_PATTERNS:
        if needle in lower:
            return kat
    return "standard"


@dataclass
class CatalogRow:
    artikelnummer: str
    beschreibung_1: str
    beschreibung_2: str | None
    listenpreis_eur: float | None
    nettowert_eur: float | None
    kategorie: str = "standard"


def _find_csvs() -> list[Path]:
    """Liefert alle Material*.csv aus den Such-Verzeichnissen. Dedupliziert
    nach Dateinamen — wenn dieselbe CSV im /app/ Mount und im lokalen Repo
    auftaucht, gewinnt /app/."""
    seen: dict[str, Path] = {}
    for directory in _CSV_DIRS:
        if not directory.is_dir():
            continue
        for pattern in ("Material*.csv", "material*.csv"):
            for path in directory.glob(pattern):
                if path.is_file() and path.name not in seen:
                    seen[path.name] = path
    return list(seen.values())


def _parse_de_number(raw: str | None) -> float | None:
    """„51 €", „3,47 €", „1.234,56 €" → float. ``None`` wenn leer/unparsable."""
    if raw is None:
        return None
    s = raw.strip().replace("€", "").replace("\xa0", " ").strip()
    if not s:
        return None
    # Deutsche Notation: Tausender-Punkt, Dezimal-Komma → englisch
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _make_sort_key(b1: str, b2: str | None) -> str:
    # Einfache, locale-unabhängige Sortierung: lowercased + zusammengefügt.
    # Reicht für unsere ~170 Artikel; falls später echte Unicode-Sortierung
    # (Umlaute korrekt zwischen u und ü) gebraucht wird, hier auf
    # ``unicodedata.normalize`` umstellen.
    return f"{(b1 or '').strip().lower()} {(b2 or '').strip().lower()}".strip()


def parse_csv(csv_text: str, kategorie: str = "standard") -> list[CatalogRow]:
    """Robustes Parsing — BOM, leere Zeilen, fehlende Spalten tolerant.

    Schema (1-indexed):
      1 = Typ-Marker (ART)
      2 = Artikelnummer
      3 = Menge (ignoriert)
      4 = Beschreibung 1
      5 = Beschreibung 2
      6 = Listenpreis
      7 = Nettowert
    """
    # BOM entfernen falls drin
    csv_text = csv_text.lstrip("﻿")
    reader = csv.reader(io.StringIO(csv_text), delimiter=";")
    rows: list[CatalogRow] = []
    for line in reader:
        if not line or len(line) < 5:
            continue
        marker = (line[0] or "").strip().lower()
        if marker != "art":
            # Header-Zeile oder leere Trennzeile — überspringen
            continue
        artnr = (line[1] or "").strip()
        if not artnr:
            continue
        b1 = (line[3] or "").strip()
        if not b1:
            # Ohne Beschreibung 1 ist der Artikel nicht sinnvoll auswählbar
            continue
        b2 = (line[4] or "").strip() or None
        lp = _parse_de_number(line[5] if len(line) > 5 else None)
        nw = _parse_de_number(line[6] if len(line) > 6 else None)
        rows.append(CatalogRow(
            artikelnummer=artnr[:32],
            beschreibung_1=b1[:255],
            beschreibung_2=(b2 or "")[:255] or None,
            listenpreis_eur=lp,
            nettowert_eur=nw,
            kategorie=kategorie,
        ))
    return rows


def import_from_csv(
    db: Session, csv_paths: list[Path] | None = None
) -> dict[str, int]:
    """Idempotenter Import aus allen Material*.csv-Dateien.

    Strategie:
      1. Alle CSVs sammeln (oder die explizit übergebenen).
      2. Jede CSV parsen, Kategorie aus dem Dateinamen ableiten.
      3. Existierende Artikel matchen per artikelnummer:
         - vorhanden: update (Beschreibung, Preis, **Kategorie**), active=True
         - nicht vorhanden: insert
      4. Artikel, die in **keiner** CSV mehr vorkommen, auf active=False.
      5. Einzige Transaktion — bei Fehler nichts persistieren.

    Bei fehlenden CSVs passiert nichts (kein Crash). Konflikt-Sonderfall:
    derselbe Artikelnummer in zwei CSVs → die letzte gewinnt
    (Reihenfolge: alphabetisch nach Dateiname).
    """
    targets = csv_paths if csv_paths is not None else _find_csvs()
    if not targets:
        logger.info("Materialkatalog: keine Material*.csv gefunden — übersprungen")
        return {"imported": 0, "updated": 0, "deactivated": 0, "skipped": 0}

    all_parsed: list[CatalogRow] = []
    for path in sorted(targets, key=lambda p: p.name.lower()):
        try:
            csv_text = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            logger.warning("Materialkatalog: konnte %s nicht lesen: %s", path, exc)
            continue
        kat = _kategorie_from_filename(path.name)
        rows = parse_csv(csv_text, kategorie=kat)
        logger.info(
            "Materialkatalog: %s → %d Zeilen (kategorie=%s)", path.name, len(rows), kat
        )
        all_parsed.extend(rows)

    if not all_parsed:
        logger.warning("Materialkatalog: 0 verwertbare Zeilen aus %d CSVs", len(targets))
        return {"imported": 0, "updated": 0, "deactivated": 0, "skipped": 0}

    # Dedup per Artikelnummer — letzter Eintrag gewinnt (passt zur Sortierung).
    by_artnr: dict[str, CatalogRow] = {}
    for row in all_parsed:
        by_artnr[row.artikelnummer] = row

    existing = {
        row.artikelnummer: row
        for row in db.query(MaterialCatalogItem).all()
    }
    parsed_artnrs = set(by_artnr.keys())

    imported = 0
    updated = 0
    for row in by_artnr.values():
        item = existing.get(row.artikelnummer)
        if item is None:
            db.add(
                MaterialCatalogItem(
                    artikelnummer=row.artikelnummer,
                    beschreibung_1=row.beschreibung_1,
                    beschreibung_2=row.beschreibung_2,
                    listenpreis_eur=row.listenpreis_eur,
                    nettowert_eur=row.nettowert_eur,
                    kategorie=row.kategorie,
                    sort_key=_make_sort_key(row.beschreibung_1, row.beschreibung_2),
                    active=True,
                )
            )
            imported += 1
        else:
            changed = False
            if item.beschreibung_1 != row.beschreibung_1:
                item.beschreibung_1 = row.beschreibung_1
                changed = True
            if item.beschreibung_2 != row.beschreibung_2:
                item.beschreibung_2 = row.beschreibung_2
                changed = True
            if item.listenpreis_eur != row.listenpreis_eur:
                item.listenpreis_eur = row.listenpreis_eur
                changed = True
            if item.nettowert_eur != row.nettowert_eur:
                item.nettowert_eur = row.nettowert_eur
                changed = True
            if item.kategorie != row.kategorie:
                item.kategorie = row.kategorie
                changed = True
            new_sort = _make_sort_key(row.beschreibung_1, row.beschreibung_2)
            if item.sort_key != new_sort:
                item.sort_key = new_sort
                changed = True
            if not item.active:
                item.active = True
                changed = True
            if changed:
                updated += 1

    # Soft-Delete für Artikel, die aus allen CSVs verschwunden sind.
    deactivated = 0
    for artnr, item in existing.items():
        if artnr not in parsed_artnrs and item.active:
            item.active = False
            deactivated += 1

    db.commit()
    logger.info(
        "Materialkatalog importiert: +%d neu, ~%d aktualisiert, ⌀%d deaktiviert (Quellen: %d CSV)",
        imported, updated, deactivated, len(targets),
    )
    return {
        "imported": imported,
        "updated": updated,
        "deactivated": deactivated,
        "skipped": 0,
    }


def search(
    db: Session,
    query: str | None = None,
    kategorie: str | None = None,
    limit: int = 200,
) -> list[MaterialCatalogItem]:
    """Such-Helper für den API-Endpoint.

    Filter:
      * aktive Artikel
      * optional ``kategorie`` (standard | brandschutz | isolierung)
      * **Token-Match** (alle Tokens müssen irgendwo in Beschreibung_1,
        Beschreibung_2 oder Artikelnummer vorkommen — UND-Verknüpfung).
        Damit findet „bogen 22" auch „Temponox Bogen 90 Grad, 22mm".

    Sortierung: ``sort_key`` (alphabetisch nach Beschreibung).
    """
    q = (query or "").strip()
    stmt = db.query(MaterialCatalogItem).filter(MaterialCatalogItem.active.is_(True))
    if kategorie:
        kat = kategorie.strip().lower()
        if kat:
            stmt = stmt.filter(MaterialCatalogItem.kategorie == kat)
    if q:
        # Tokenize: jeder Whitespace-separierte Begriff muss irgendwo matchen.
        tokens = [t for t in q.split() if t]
        for tok in tokens:
            pattern = f"%{tok}%"
            stmt = stmt.filter(
                (MaterialCatalogItem.beschreibung_1.ilike(pattern))
                | (MaterialCatalogItem.beschreibung_2.ilike(pattern))
                | (MaterialCatalogItem.artikelnummer.ilike(pattern))
            )
    stmt = stmt.order_by(MaterialCatalogItem.sort_key.asc())
    return stmt.limit(max(1, min(limit, 1000))).all()


def available_categories(db: Session) -> list[str]:
    """Distinct-Liste der Kategorien für die Filter-Chips im Frontend."""
    rows = (
        db.query(MaterialCatalogItem.kategorie)
        .filter(MaterialCatalogItem.active.is_(True))
        .filter(MaterialCatalogItem.kategorie.is_not(None))
        .distinct()
        .order_by(MaterialCatalogItem.kategorie.asc())
        .all()
    )
    return [r[0] for r in rows if r[0]]
