from __future__ import annotations

from app.services.offer_importers.base import OfferImporter, OfferImporterError


_importers: dict[str, OfferImporter] = {}


def register_offer_importer(importer: OfferImporter) -> None:
    _importers[importer.source_name] = importer


def get_offer_importer(source_name: str) -> OfferImporter:
    if source_name not in _importers:
        raise OfferImporterError(f"Unknown offer importer: {source_name}")
    return _importers[source_name]


def available_offer_importers() -> list[dict[str, str]]:
    return [
        {
            "source_name": imp.source_name,
            "display_name": imp.display_name,
            "accepts_extensions": ",".join(imp.accepts_extensions),
        }
        for imp in _importers.values()
    ]


def detect_offer_importer(filename: str, head: bytes) -> OfferImporter | None:
    for imp in _importers.values():
        try:
            if imp.can_handle(filename, head):
                return imp
        except Exception:
            continue
    return None


def _bootstrap() -> None:
    from app.services.offer_importers.generic_table import GenericOfferTableImporter
    from app.services.offer_importers.ugl import UglOfferImporter

    # UGL first so its strict magic-byte check wins over the generic catch-all
    # for files that happen to share the .txt/.001 extension.
    register_offer_importer(UglOfferImporter())
    register_offer_importer(GenericOfferTableImporter())


_bootstrap()
