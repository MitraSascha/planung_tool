import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.core.settings import settings
from app.db.orm_models import HeatingDesign, Offer, ProjectPhoto, VoiceNote
from app.models.project import ProjectCreate, ProjectWorkspace
from app.services.output_validator import validate_project_output


def write_heating_design_json(slug: str, design: HeatingDesign | None) -> Path | None:
    """Schreibt die Strangberechnungs-Daten als heating_design.json neben
    input.json in den Projekt-Workspace, damit Generator-Tasks (Hydraulischer
    Abgleich u.a.) sie konsumieren koennen.

    Bei design=None wird eine ggf. vorhandene Datei entfernt — der Generator
    weist die Daten dann als "Offene Punkte" aus.
    """
    workspace_path = settings.workspaces_path / slug
    target = workspace_path / "heating_design.json"

    if design is None:
        if target.exists():
            target.unlink()
        return None

    payload = {
        "system_type": design.system_type,
        "supply_temp_c": design.supply_temp_c,
        "return_temp_c": design.return_temp_c,
        "delta_t_k": design.delta_t_k,
        "pump_head_pa": design.pump_head_pa,
        "total_volume_flow_lph": design.total_volume_flow_lph,
        "pump_model": design.pump_model,
        "notes": design.notes,
        "source": design.source,
        "source_file": design.source_file,
        "imported_at": design.imported_at.isoformat() if design.imported_at else None,
        "circuits": [
            {
                "position": circuit.position,
                "strand": circuit.strand,
                "room": circuit.room,
                "floor": circuit.floor,
                "radiator_type": circuit.radiator_type,
                "area_sqm": circuit.area_sqm,
                "heat_load_w": circuit.heat_load_w,
                "volume_flow_lph": circuit.volume_flow_lph,
                "pressure_drop_pa": circuit.pressure_drop_pa,
                "pipe_length_m": circuit.pipe_length_m,
                "valve_type": circuit.valve_type,
                "valve_preset": circuit.valve_preset,
                "kv_value": circuit.kv_value,
                "notes": circuit.notes,
            }
            for circuit in sorted(design.circuits, key=lambda c: c.position)
        ],
    }

    workspace_path.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_offers_json(slug: str, offers: Iterable[Offer]) -> Path | None:
    """Schreibt die Angebote eines Projekts als ``offers.json`` in den
    Workspace, damit Generator-Templates (Material- und Werkzeug-Listen,
    Stücklisten, Kosten-Auswertungen) sie konsumieren koennen.

    Wenn keine Angebote vorhanden sind, wird die Datei ggf. entfernt und
    ``None`` zurueckgegeben — Generator-Templates ignorieren die fehlende
    Datei dann sauber.
    """
    workspace_path = settings.workspaces_path / slug
    target = workspace_path / "offers.json"

    offers_list = list(offers)
    if not offers_list:
        if target.exists():
            target.unlink()
        return None

    payload = {
        "offers": [
            {
                "id": offer.id,
                "supplier_name": offer.supplier_name,
                "offer_no": offer.offer_no,
                "offer_date": offer.offer_date.isoformat() if offer.offer_date else None,
                "currency": offer.currency,
                "total_net_eur": offer.total_net_eur,
                "total_gross_eur": offer.total_gross_eur,
                "vat_rate": offer.vat_rate,
                "source_type": offer.source_type,
                "source_file": offer.source_file,
                "notes": offer.notes,
                "items": [
                    {
                        "position_label": item.position_label,
                        "article_no": item.article_no,
                        "name": item.name,
                        "description": item.description,
                        "qty": item.qty,
                        "unit": item.unit,
                        "unit_price_net_eur": item.unit_price_net_eur,
                        "total_net_eur": item.total_net_eur,
                        "vat_rate": item.vat_rate,
                    }
                    for item in sorted(offer.items, key=lambda i: i.position_index)
                ],
                "item_count": len(offer.items),
            }
            for offer in offers_list
        ],
        "summary": {
            "offer_count": len(offers_list),
            "total_net_eur": sum(o.total_net_eur or 0 for o in offers_list) or None,
            "suppliers": sorted({o.supplier_name for o in offers_list}),
        },
    }

    workspace_path.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def write_voice_notes_to_workspace(
    slug: str,
    notes: Iterable[VoiceNote],
) -> Path | None:
    """Schreibt die transkribierten Sprachnotizen als ``voice_notes.json``
    neben ``input.json`` in den Workspace, damit Generator-Tasks sie als
    zusaetzlichen Kontext lesen koennen.

    Nur Notizen mit ``transcription_status="ok"`` und nicht-leerem
    ``transcript`` werden eingeschlossen. Wenn keine Notiz die Kriterien
    erfuellt, wird eine ggf. vorhandene Datei entfernt und ``None``
    zurueckgegeben — der Generator-Prompt erwaehnt die Datei dann gar nicht.
    """
    workspace_path = settings.workspaces_path / slug
    target = workspace_path / "voice_notes.json"

    payload: list[dict] = []
    for note in notes:
        if note.transcription_status != "ok":
            continue
        if not note.transcript or not note.transcript.strip():
            continue
        payload.append(
            {
                "id": note.id,
                "intent": note.intent,
                "transcript": note.transcript.strip(),
                "transcript_language": note.transcript_language,
                "transcript_provider": note.transcript_provider,
                "created_at": (
                    note.created_at.isoformat() if note.created_at else None
                ),
                "username": note.user.username if note.user else None,
            }
        )

    if not payload:
        if target.exists():
            target.unlink()
        return None

    workspace_path.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return target


def copy_photos_to_workspace(
    slug: str,
    photos: Iterable[ProjectPhoto],
) -> Path | None:
    """Kopiert die vorhandenen Foto-Dateien in ``storage/workspaces/<slug>/photos/``
    und schreibt zusaetzlich eine ``photos.json`` mit den Metadaten (id,
    filename, caption, section_number, daily_report_id, taken_at, GPS,
    relativer Pfad).

    Der Generator (Codex/Claude) liest ``photos.json`` und bindet die Fotos
    pro Bauabschnitt als ``<img src="../photos/<filename>">`` in die HTML-Doku
    ein; beim Veroeffentlichen werden die Dateien ebenfalls in
    ``storage/projects/<slug>/photos/`` mitkopiert (vgl. ``publish_project``).

    Bei leerer Liste werden ein eventuell vorhandener ``photos/``-Ordner und
    die Manifest-Datei entfernt und ``None`` zurueckgegeben.
    """
    workspace_path = settings.workspaces_path / slug
    photos_dir = workspace_path / "photos"
    manifest_path = workspace_path / "photos.json"

    payload: list[dict] = []
    photo_list = list(photos)

    if not photo_list:
        if photos_dir.exists():
            shutil.rmtree(photos_dir)
        if manifest_path.exists():
            manifest_path.unlink()
        return None

    workspace_path.mkdir(parents=True, exist_ok=True)
    if photos_dir.exists():
        shutil.rmtree(photos_dir)
    photos_dir.mkdir(parents=True, exist_ok=True)

    for photo in photo_list:
        source_candidate = photo.annotated_path or photo.path
        if not source_candidate:
            continue
        source = Path(source_candidate)
        if not source.exists():
            continue

        # Zielname: <sha256-prefix>_<originalname> haelt sowohl Eindeutigkeit
        # als auch die Endung des Originals aufrecht — wichtig, damit der
        # Browser/PDF-Export den richtigen Mime-Type kennt.
        suffix = source.suffix or Path(photo.filename or "").suffix or ".jpg"
        target_name = f"{photo.sha256[:12]}{suffix}"
        target_path = photos_dir / target_name
        shutil.copy2(source, target_path)

        payload.append(
            {
                "id": photo.id,
                "filename": target_name,
                "original_filename": photo.filename,
                "relative_path": f"photos/{target_name}",
                "caption": photo.caption,
                "section_number": photo.section_number,
                "daily_report_id": photo.daily_report_id,
                "taken_at": photo.taken_at.isoformat() if photo.taken_at else None,
                "geo_lat": photo.geo_lat,
                "geo_lng": photo.geo_lng,
                "width": photo.width,
                "height": photo.height,
                "content_type": photo.content_type,
                "sha256": photo.sha256,
                "is_annotated": bool(photo.annotated_path),
            }
        )

    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return photos_dir


def create_project_workspace(project: ProjectCreate) -> ProjectWorkspace:
    workspace_path = settings.workspaces_path / project.slug
    output_path = workspace_path / "output"
    docs_path = workspace_path / "docs"

    workspace_path.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(parents=True, exist_ok=True)
    docs_path.mkdir(parents=True, exist_ok=True)

    input_path = workspace_path / "input.json"
    input_path.write_text(
        json.dumps(project.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return ProjectWorkspace(
        slug=project.slug,
        workspace_path=str(workspace_path),
        input_path=str(input_path),
        output_path=str(output_path),
        preview_url=f"https://{project.slug}.{settings.public_base_domain}",
    )


def _version_label() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clear_current_public_output(public_project: Path) -> None:
    if not public_project.exists():
        return

    for item in public_project.iterdir():
        if item.name == "_versions":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _copy_output_contents(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)

    for item in source.iterdir():
        target_item = target / item.name
        if item.is_dir():
            shutil.copytree(item, target_item)
        else:
            shutil.copy2(item, target_item)


def publish_project(
    slug: str,
    expected_section_count: int,
    project_type: str = "standard",
    version_label: str | None = None,
) -> Path:
    workspace_output = settings.workspaces_path / slug / "output"
    public_project = settings.projects_path / slug

    if not workspace_output.exists():
        raise FileNotFoundError(f"Workspace output does not exist: {workspace_output}")

    validate_project_output(workspace_output, expected_section_count, project_type)

    version_root = public_project / "_versions"
    version_path = version_root / (version_label or _version_label())

    if version_path.exists():
        version_path = version_root / f"{version_path.name}_{datetime.now(timezone.utc).strftime('%f')}"

    shutil.copytree(workspace_output, version_path)

    _clear_current_public_output(public_project)
    _copy_output_contents(workspace_output, public_project)

    # Zusaetzlich Fotos mitveroeffentlichen, damit die generierten HTML-Seiten
    # die relativen ``photos/...``-Pfade aufloesen koennen.
    workspace_photos = settings.workspaces_path / slug / "photos"
    if workspace_photos.exists() and any(workspace_photos.iterdir()):
        public_photos = public_project / "photos"
        if public_photos.exists():
            shutil.rmtree(public_photos)
        shutil.copytree(workspace_photos, public_photos)

    return public_project
