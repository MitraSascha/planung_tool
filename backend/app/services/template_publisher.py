"""Render all DB-stored templates for a project and write them as static
HTML files under ``storage/projects/<slug>/``.

This is the bridge between the new template-based render path and the
legacy file-based public output: the frontend keeps reading from
``storage/projects/<slug>/<category>/<filename>.html`` while the source of
truth lives in the database. After every generator run (or on demand via
the render-templates endpoint) the deterministic templates overwrite the
legacy KI-generated HTMLs — same path, much smaller variance.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.settings import settings
from app.services import template_renderer


# Slug -> on-disk filename within its category folder. Keeps the legacy file
# names so the frontend (nginx /preview, generated docs, navigation links)
# keeps working without changes.
SLUG_TO_FILENAME: dict[str, str] = {
    # 00_Start
    "start_index":              "index.html",
    "projekt_navigation":       "Projekt_Navigation.html",
    # 01_Monteur
    "ablaufplan_abschnitte":    "MONTEUR_Ablaufplan_Abschnitte.html",
    "wochenplan":               "MONTEUR_Wochenplan.html",
    "baustellenhinweise":       "MONTEUR_Baustellenhinweise.html",
    "tagescheckliste":          "MONTEUR_Tagescheckliste.html",
    # 02_Obermonteur
    "checklisten":              "OBERMONTEUR_Checklisten.html",
    "teamstatus":               "OBERMONTEUR_Teamstatus.html",
    "abschnittsplanung":        "OBERMONTEUR_Abschnittsplanung.html",
    # 03_Bauleitung
    "detaillierter_ablaufplan": "BAULEITUNG_Detaillierter_Ablaufplan.html",
    "gefaehrdungsbeurteilung":  "BAULEITUNG_Gefaehrdungsbeurteilung.html",
    "blocker_offene_punkte":    "BAULEITUNG_Blocker_und_Offene_Punkte.html",
    "material_werkzeug":        "BAULEITUNG_Material_und_Werkzeug.html",
    "risiken_maengel":          "BAULEITUNG_Risiken_und_Maengel.html",
    "hydraulischer_abgleich":   "BAULEITUNG_Hydraulischer_Abgleich.html",
    # 04_Projektleitung
    "projektuebersicht":              "PROJEKTLEITUNG_Projektuebersicht.html",
    "statusuebersicht":               "PROJEKTLEITUNG_Statusuebersicht.html",
    "meilensteinplan":                "PROJEKTLEITUNG_Meilensteinplan.html",
    "gantt_uebersicht":               "PROJEKTLEITUNG_Gantt_Uebersicht.html",
    "inbetriebnahmeprotokoll":        "PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html",
    "kfw_fachunternehmererklaerung":  "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html",
    # 05_Allgemein
    "kontakte":                 "ALLGEMEIN_Kontakte.html",
    "uebergabeprotokoll":       "ALLGEMEIN_Uebergabeprotokoll.html",
    "dokumentenindex":          "ALLGEMEIN_Dokumentenindex.html",
    "projektunterlagen":        "ALLGEMEIN_Projektunterlagen.html",
}


@dataclass(frozen=True)
class PublishedTemplate:
    slug: str
    category: str
    relative_path: str
    bytes_written: int


def publish_templates_to_storage(db: Session, project_slug: str) -> list[PublishedTemplate]:
    """Render every template registered in the DB and write it to its slot
    under ``storage/projects/<project_slug>/<category>/<filename>``.

    Raises ProjectNotFoundError if the project does not exist.
    """
    templates = template_renderer.list_templates(db)
    if not templates:
        return []

    project_root: Path = settings.projects_path / project_slug
    written: list[PublishedTemplate] = []

    for tpl in templates:
        filename = SLUG_TO_FILENAME.get(tpl.slug)
        if filename is None:
            # Unknown slug — write under <slug>.html so nothing is silently
            # dropped. Future templates can be added to the mapping at
            # leisure.
            filename = f"{tpl.slug}.html"

        target_dir = project_root / tpl.category
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename

        result = template_renderer.render(db, tpl.slug, project_slug)
        target.write_text(result.html, encoding="utf-8")

        written.append(
            PublishedTemplate(
                slug=tpl.slug,
                category=tpl.category,
                relative_path=f"{tpl.category}/{filename}",
                bytes_written=len(result.html.encode("utf-8")),
            )
        )

    return written
