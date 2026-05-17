from pathlib import Path


class OutputValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


STANDARD_REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "00_Start": ("index.html", "Projekt_Navigation.html"),
    "01_Monteur": (
        "MONTEUR_Tagescheckliste.html",
        "MONTEUR_Wochenplan.html",
        "MONTEUR_Ablaufplan_Abschnitte.html",
        "MONTEUR_Baustellenhinweise.html",
    ),
    "02_Obermonteur": (
        "OBERMONTEUR_Teamstatus.html",
        "OBERMONTEUR_Abschnittsplanung.html",
        "OBERMONTEUR_Checklisten.html",
    ),
    "03_Bauleitung": (
        "BAULEITUNG_Detaillierter_Ablaufplan.html",
        "BAULEITUNG_Material_und_Werkzeug.html",
        "BAULEITUNG_Risiken_und_Maengel.html",
        "BAULEITUNG_Blocker_und_Offene_Punkte.html",
        # Pflicht-Dokumente (IMPLEMENTIERUNGSPLAN_V2 10.2 + 10.6)
        "BAULEITUNG_Hydraulischer_Abgleich.html",
        "BAULEITUNG_Gefaehrdungsbeurteilung.html",
    ),
    "04_Projektleitung": (
        "PROJEKTLEITUNG_Projektuebersicht.html",
        "PROJEKTLEITUNG_Meilensteinplan.html",
        "PROJEKTLEITUNG_Gantt_Uebersicht.html",
        "PROJEKTLEITUNG_Statusuebersicht.html",
        # Pflicht-Dokument (IMPLEMENTIERUNGSPLAN_V2 10.3)
        "PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html",
        # Pflicht-Dokument (IMPLEMENTIERUNGSPLAN_V2 10.4) — KfW-FUE BEG-EM
        "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html",
    ),
    "05_Allgemein": (
        "ALLGEMEIN_Projektunterlagen.html",
        "ALLGEMEIN_Kontakte.html",
        "ALLGEMEIN_Dokumentenindex.html",
        # Pflicht-Dokument (IMPLEMENTIERUNGSPLAN_V2 10.5)
        "ALLGEMEIN_Uebergabeprotokoll.html",
    ),
}


SMALL_REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "00_Start": ("index.html", "Projekt_Navigation.html"),
    "01_Monteur": (
        "MONTEUR_Tagescheckliste.html",
        "MONTEUR_Ablaufplan_Abschnitte.html",
        "MONTEUR_Baustellenhinweise.html",
    ),
    "04_Projektleitung": (
        "PROJEKTLEITUNG_Projektuebersicht.html",
        "PROJEKTLEITUNG_Meilensteinplan.html",
        "PROJEKTLEITUNG_Gantt_Uebersicht.html",
        # Pflicht-Dokument: IBN auch bei Kleinprojekten zwingend.
        "PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html",
        # Pflicht-Dokument: KfW-FUE auch bei Kleinprojekten zwingend
        # (Etagenheizung & Co. werden oft ueber KfW gefoerdert).
        "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html",
    ),
    "05_Allgemein": (
        "ALLGEMEIN_Projektunterlagen.html",
        "ALLGEMEIN_Kontakte.html",
        # Pflicht-Dokument: Uebergabeprotokoll auch bei Kleinprojekten zwingend.
        "ALLGEMEIN_Uebergabeprotokoll.html",
    ),
}


def _required_for(project_type: str) -> dict[str, tuple[str, ...]]:
    return SMALL_REQUIRED_FILES if project_type == "small" else STANDARD_REQUIRED_FILES


def validate_project_output(
    output_path: Path,
    expected_section_count: int,
    project_type: str = "standard",
) -> None:
    errors: list[str] = []

    if not output_path.exists():
        raise OutputValidationError([f"Output directory does not exist: {output_path}"])

    required = _required_for(project_type)

    for folder, files in required.items():
        folder_path = output_path / folder
        if not folder_path.exists():
            errors.append(f"Missing required folder: {folder}")
            continue

        for filename in files:
            html_path = folder_path / filename
            if not html_path.exists():
                errors.append(f"Missing required file: {folder}/{filename}")
                continue

    if errors:
        raise OutputValidationError(errors)
