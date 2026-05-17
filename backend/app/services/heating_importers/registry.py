from __future__ import annotations

from app.services.heating_importers.base import HeatingImporter, HeatingImporterError


_importers: dict[str, HeatingImporter] = {}


def register(importer: HeatingImporter) -> None:
    _importers[importer.source_name] = importer


def get_importer(source_name: str) -> HeatingImporter:
    if source_name not in _importers:
        raise HeatingImporterError(f"Unknown importer: {source_name}")
    return _importers[source_name]


def available_importers() -> list[dict[str, str]]:
    return [
        {
            "source_name": importer.source_name,
            "display_name": importer.display_name,
            "accepts_extensions": ",".join(importer.accepts_extensions),
        }
        for importer in _importers.values()
    ]


def detect_importer(filename: str, content_head: bytes) -> HeatingImporter | None:
    """Try every registered importer and return the first one that claims the file."""
    for importer in _importers.values():
        try:
            if importer.can_handle(filename, content_head):
                return importer
        except Exception:
            continue
    return None


# ----------------------------------------------------------------------
# Plug concrete importers in here. Imported at module load so registrations
# happen automatically when the registry is imported.
# ----------------------------------------------------------------------

def _bootstrap() -> None:
    from app.services.heating_importers.generic_table import GenericTableImporter
    from app.services.heating_importers.viptool_master import ViptoolMasterImporter

    register(ViptoolMasterImporter())
    register(GenericTableImporter())


_bootstrap()
