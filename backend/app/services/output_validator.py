from pathlib import Path


class OutputValidationError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


SMALL_PROJECT_REQUIRED_FOLDERS = (
    "01_Projektuebersicht",
    "06_Detaillierter_Ablaufplan",
    "08_Monteur_Tagescheckliste",
    "10_Tagesbericht_App",
    "11_Meilensteinplan",
    "14_Gantt_Uebersicht",
)


def validate_project_output(output_path: Path, expected_section_count: int, project_type: str = "standard") -> None:
    errors: list[str] = []

    if not output_path.exists():
        raise OutputValidationError([f"Output directory does not exist: {output_path}"])

    index_file = output_path / "99_HTML_Uebersicht" / "index.html"
    if not index_file.exists():
        errors.append(f"Missing required file: {index_file.relative_to(output_path)}")

    if project_type == "small":
        for folder in SMALL_PROJECT_REQUIRED_FOLDERS:
            folder_path = output_path / folder
            if not folder_path.exists():
                errors.append(f"Missing required folder: {folder}")
                continue
            if not any(folder_path.glob("*.html")):
                errors.append(f"Missing HTML file in: {folder}")
        if errors:
            raise OutputValidationError(errors)
        return

    overview_path = output_path / "01_Projektuebersicht"
    overview_html_exists = any(overview_path.glob("*.html")) if overview_path.exists() else False
    overview_md_exists = any(overview_path.glob("*.md")) if overview_path.exists() else False

    if not overview_path.exists():
        errors.append("Missing required folder: 01_Projektuebersicht")
    elif not overview_html_exists:
        errors.append("Missing HTML file in: 01_Projektuebersicht")
    elif not overview_md_exists:
        errors.append("Missing Markdown file in: 01_Projektuebersicht")

    for section_number in range(1, expected_section_count + 1):
        folder_number = section_number + 1
        section_path = output_path / f"{folder_number:02d}_Abschnitt_{section_number}"

        if not section_path.exists():
            errors.append(f"Missing section folder: {section_path.relative_to(output_path)}")
            continue

        if not any(section_path.glob("*.html")):
            errors.append(f"Missing HTML file in: {section_path.relative_to(output_path)}")

        if not any(section_path.glob("*.md")):
            errors.append(f"Missing Markdown file in: {section_path.relative_to(output_path)}")

    if errors:
        raise OutputValidationError(errors)
