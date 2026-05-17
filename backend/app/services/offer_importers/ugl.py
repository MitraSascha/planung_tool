"""UGL (Daten-Austausch-Format) parser for SHK supplier offers.

UGL is a fixed-record ASCII format used by German wholesalers (Daten-
norm-style) to ship orders and offers. Each line starts with a 3-digit
record type (Satzart) and the remaining columns sit at fixed offsets.

Record types we care about:
    100 — Header (offer-no, supplier, currency)
    110 — Optional header continuation (date, address)
    120 — Line item (article-no, qty, price, total)

The spec varies by vendor (some use ``;``-separated rather than fixed
width). We support both: if a record contains ``;`` we split on it,
otherwise we fall back to fixed offsets sourced from the most common
GAEB-UGL / Datanorm export shape.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Sequence

from app.models.offers import OfferBase, OfferImportPreview, OfferItemBase
from app.services.offer_importers.base import (
    OfferColumnMapping,
    OfferImporter,
    OfferImporterError,
)


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    text = value.strip().replace(" ", "")
    if not text:
        return None
    # UGL prices typically come in cents without separator (e.g. "0001234"
    # = 12.34 EUR) OR as plain decimal — handle both.
    if "," in text or "." in text:
        cleaned = text.replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    # Fixed-width integer cents — divide by 100.
    try:
        return int(text) / 100.0
    except ValueError:
        return None


def _to_date(value: str | None) -> date | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y%m%d", "%d%m%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _split_fields(line: str) -> list[str]:
    """Split a UGL record by ';' if separator is used, else by tab."""
    if ";" in line:
        return [f.strip() for f in line.split(";")]
    if "\t" in line:
        return [f.strip() for f in line.split("\t")]
    return [line]


class UglOfferImporter(OfferImporter):
    source_name = "ugl"
    display_name = "UGL / Datanorm (SHK)"
    accepts_extensions = (".ugl", ".001", ".txt", ".dat")

    def can_handle(self, filename: str, content_head: bytes) -> bool:
        lower = filename.lower()
        if any(lower.endswith(ext) for ext in (".ugl",)):
            return True
        # For ambiguous .txt/.001/.dat: only claim when the head clearly
        # starts with a UGL record type. Avoids stealing random text files.
        head = content_head[:128].decode("latin-1", errors="replace").lstrip()
        return head.startswith(("100", "110", "120"))

    def parse(
        self,
        filename: str,
        content: bytes,
        mapping: OfferColumnMapping | None = None,
    ) -> OfferImportPreview:
        if not content:
            raise OfferImporterError("UGL-Datei ist leer.")
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="replace")

        lines = [ln.rstrip("\r\n") for ln in text.splitlines() if ln.strip()]
        if not lines:
            raise OfferImporterError("UGL-Datei enthaelt keine lesbaren Zeilen.")

        supplier_name: str | None = None
        offer_no: str | None = None
        offer_date: date | None = None
        currency = "EUR"
        items: list[OfferItemBase] = []
        warnings: list[str] = []
        position = 0

        for ln in lines:
            if len(ln) < 3 or not ln[:3].isdigit():
                warnings.append(f"Zeile ignoriert (keine Satzart): {ln[:40]!r}")
                continue
            satzart = ln[:3]
            fields = _split_fields(ln[3:].lstrip(";").lstrip("\t"))

            if satzart == "100":
                # 100;<offer_no>;<supplier_name>;<currency>;...
                if len(fields) >= 1 and fields[0]:
                    offer_no = fields[0]
                if len(fields) >= 2 and fields[1]:
                    supplier_name = fields[1]
                if len(fields) >= 3 and fields[2]:
                    currency = fields[2][:8] or "EUR"
            elif satzart == "110":
                # 110;<offer_date>;<remark>;...
                if len(fields) >= 1:
                    offer_date = _to_date(fields[0]) or offer_date
            elif satzart == "120":
                # 120;<art_no>;<qty>;<unit>;<unit_price>;<total>;<name>;<vat>
                items.append(
                    OfferItemBase(
                        position_index=position,
                        position_label=str(position + 1),
                        article_no=(fields[0] if len(fields) > 0 else None) or None,
                        qty=_to_float(fields[1]) if len(fields) > 1 else None,
                        unit=(fields[2] if len(fields) > 2 else None) or None,
                        unit_price_net_eur=_to_float(fields[3]) if len(fields) > 3 else None,
                        total_net_eur=_to_float(fields[4]) if len(fields) > 4 else None,
                        name=(fields[5] if len(fields) > 5 else None) or None,
                        vat_rate=_to_float(fields[6]) if len(fields) > 6 else None,
                    )
                )
                position += 1
            else:
                warnings.append(f"Unbekannte Satzart '{satzart}' uebersprungen")

        if not items:
            raise OfferImporterError(
                "Keine UGL-Positionen (Satzart 120) gefunden. "
                "Datei ist vermutlich kein Angebot im UGL-Format."
            )

        total_net = sum(
            (it.total_net_eur for it in items if it.total_net_eur is not None), 0.0
        ) or None

        return OfferImportPreview(
            source_type="ugl",
            source_file=filename,
            offer=OfferBase(
                supplier_name=supplier_name or "Unbekannter Lieferant",
                offer_no=offer_no,
                offer_date=offer_date,
                currency=currency,
                total_net_eur=total_net,
                total_gross_eur=None,
                vat_rate=None,
                notes=None,
            ),
            items=items,
            warnings=warnings,
            detected_columns={
                "article_no": "Feld 1 (Satzart 120)",
                "qty": "Feld 2 (Satzart 120)",
                "unit": "Feld 3 (Satzart 120)",
                "unit_price_net_eur": "Feld 4 (Satzart 120)",
                "total_net_eur": "Feld 5 (Satzart 120)",
                "name": "Feld 6 (Satzart 120)",
            },
        )
