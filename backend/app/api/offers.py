"""REST API for project offers (Angebote).

Provides CRUD, import preview/confirm for xlsx/csv/UGL, and a PDF upload
that stores the file as attachment and records user-typed headline data.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.core.settings import settings
from app.db.database import get_db
from app.db.orm_models import Offer, OfferItem, Project, User
from app.models.offers import (
    OfferImportPreview,
    OfferItemRead,
    OfferRead,
    OfferSummary,
    OfferWrite,
)
from app.services.auth import (
    PROJECT_READ_ROLES,
    SITE_LEAD_ROLES,
    get_current_user,
    require_project_role,
)
from app.services.offer_importers import (
    OfferColumnMapping,
    OfferImporterError,
    available_offer_importers,
    detect_offer_importer,
    get_offer_importer,
)
from app.services.offer_to_material import sync_offer_to_material
from app.services.radiator_matching import apply_radiator_offers


router = APIRouter()


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _project_or_404(db: Session, slug: str) -> Project:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _offer_or_404(db: Session, project: Project, offer_id: int) -> Offer:
    offer = (
        db.query(Offer)
        .options(selectinload(Offer.items), selectinload(Offer.imported_by))
        .filter(Offer.id == offer_id, Offer.project_id == project.id)
        .one_or_none()
    )
    if offer is None:
        raise HTTPException(status_code=404, detail="Offer not found")
    return offer


def _offer_to_read(project: Project, offer: Offer) -> OfferRead:
    return OfferRead(
        id=offer.id,
        project_slug=project.slug,
        supplier_name=offer.supplier_name,
        offer_no=offer.offer_no,
        offer_date=offer.offer_date,
        currency=offer.currency,
        total_net_eur=offer.total_net_eur,
        total_gross_eur=offer.total_gross_eur,
        vat_rate=offer.vat_rate,
        notes=offer.notes,
        source_type=offer.source_type,  # type: ignore[arg-type]
        source_file=offer.source_file,
        attached_file_path=offer.attached_file_path,
        imported_at=offer.created_at,
        imported_by_user_id=offer.imported_by_user_id,
        imported_by_username=offer.imported_by.username if offer.imported_by else None,
        updated_at=offer.updated_at,
        items=[
            OfferItemRead(
                id=item.id,
                position_index=item.position_index,
                position_label=item.position_label,
                article_no=item.article_no,
                name=item.name,
                description=item.description,
                qty=item.qty,
                unit=item.unit,
                unit_price_net_eur=item.unit_price_net_eur,
                total_net_eur=item.total_net_eur,
                vat_rate=item.vat_rate,
                notes=item.notes,
            )
            for item in offer.items
        ],
    )


def _offer_to_summary(project: Project, offer: Offer, item_count: int) -> OfferSummary:
    return OfferSummary(
        id=offer.id,
        project_slug=project.slug,
        supplier_name=offer.supplier_name,
        offer_no=offer.offer_no,
        offer_date=offer.offer_date,
        currency=offer.currency,
        total_net_eur=offer.total_net_eur,
        total_gross_eur=offer.total_gross_eur,
        source_type=offer.source_type,  # type: ignore[arg-type]
        source_file=offer.source_file,
        attached_file_path=offer.attached_file_path,
        imported_at=offer.created_at,
        item_count=item_count,
    )


def _offers_dir(project: Project) -> Path:
    path = settings.workspaces_path / project.slug / "offers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _apply_write_to_offer(
    offer: Offer, payload: OfferWrite, current_user_id: int
) -> None:
    offer.supplier_name = payload.supplier_name
    offer.offer_no = payload.offer_no
    offer.offer_date = payload.offer_date
    offer.currency = payload.currency or "EUR"
    offer.total_net_eur = payload.total_net_eur
    offer.total_gross_eur = payload.total_gross_eur
    offer.vat_rate = payload.vat_rate
    offer.notes = payload.notes
    offer.source_type = payload.source_type
    offer.source_file = payload.source_file
    offer.attached_file_path = payload.attached_file_path
    if offer.imported_by_user_id is None:
        offer.imported_by_user_id = current_user_id


def _replace_items(offer: Offer, items: list) -> None:
    offer.items.clear()
    for index, item in enumerate(items):
        offer.items.append(
            OfferItem(
                position_index=item.position_index or index,
                position_label=item.position_label,
                article_no=item.article_no,
                name=item.name,
                description=item.description,
                qty=item.qty,
                unit=item.unit,
                unit_price_net_eur=item.unit_price_net_eur,
                total_net_eur=item.total_net_eur,
                vat_rate=item.vat_rate,
                notes=item.notes,
            )
        )


# ----------------------------------------------------------------------
# Catalog
# ----------------------------------------------------------------------


@router.get("/offer-importers")
def list_offer_importers(
    current_user: User = Depends(get_current_user),
) -> list[dict[str, str]]:
    return available_offer_importers()


# ----------------------------------------------------------------------
# List / Read / Delete
# ----------------------------------------------------------------------


@router.get("/projects/{slug}/offers", response_model=list[OfferSummary])
def list_offers(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OfferSummary]:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)

    rows = (
        db.query(Offer, db.query(OfferItem.id).filter(OfferItem.offer_id == Offer.id).count())
        .filter(Offer.project_id == project.id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    # Simpler: fetch offers + items via selectinload, then count locally.
    offers = (
        db.query(Offer)
        .options(selectinload(Offer.items))
        .filter(Offer.project_id == project.id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    return [_offer_to_summary(project, o, len(o.items)) for o in offers]


@router.get("/projects/{slug}/offers/{offer_id}", response_model=OfferRead)
def get_offer(
    slug: str,
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    offer = _offer_or_404(db, project, offer_id)
    return _offer_to_read(project, offer)


@router.delete("/projects/{slug}/offers/{offer_id}", status_code=204)
def delete_offer(
    slug: str,
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    offer = _offer_or_404(db, project, offer_id)
    # Delete attached file (best-effort).
    if offer.attached_file_path:
        path = Path(offer.attached_file_path)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
    db.delete(offer)
    db.commit()


# ----------------------------------------------------------------------
# Manual create / update
# ----------------------------------------------------------------------


@router.post("/projects/{slug}/offers", response_model=OfferRead)
def create_offer(
    slug: str,
    payload: OfferWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    offer = Offer(project_id=project.id, supplier_name=payload.supplier_name)
    _apply_write_to_offer(offer, payload, current_user.id)
    db.add(offer)
    db.flush()
    _replace_items(offer, payload.items)
    db.commit()
    db.refresh(offer)
    return _offer_to_read(project, offer)


@router.put("/projects/{slug}/offers/{offer_id}", response_model=OfferRead)
def update_offer(
    slug: str,
    offer_id: int,
    payload: OfferWrite,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferRead:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    offer = _offer_or_404(db, project, offer_id)
    _apply_write_to_offer(offer, payload, current_user.id)
    _replace_items(offer, payload.items)
    db.commit()
    db.refresh(offer)
    return _offer_to_read(project, offer)


# ----------------------------------------------------------------------
# Import flow: xlsx / csv / ugl
# ----------------------------------------------------------------------


@router.post(
    "/projects/{slug}/offers/import",
    response_model=OfferImportPreview,
)
async def import_offer_preview(
    slug: str,
    file: UploadFile = File(...),
    adapter_hint: str | None = Form(None),
    mapping_json: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferImportPreview:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty upload")

    if adapter_hint:
        importer = get_offer_importer(adapter_hint)
    else:
        importer = detect_offer_importer(file.filename or "", raw[:4096])
        if importer is None:
            raise HTTPException(
                status_code=400,
                detail="Kein passender Importer fuer diese Datei. "
                "Bitte adapter_hint setzen oder Datei als xlsx/csv/UGL exportieren.",
            )

    column_mapping: OfferColumnMapping | None = None
    if mapping_json:
        try:
            parsed = json.loads(mapping_json)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid mapping_json: {exc}") from exc
        column_mapping = OfferColumnMapping(
            item_columns=parsed.get("item_columns", {}),
            header_overrides=parsed.get("header_overrides", {}),
        )

    try:
        return importer.parse(file.filename or "", raw, column_mapping)
    except OfferImporterError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/projects/{slug}/offers/import/confirm",
    response_model=OfferRead,
)
def import_offer_confirm(
    slug: str,
    preview: OfferImportPreview,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferRead:
    """Persist a (possibly user-edited) preview as a new offer."""
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    offer = Offer(
        project_id=project.id,
        supplier_name=preview.offer.supplier_name,
        offer_no=preview.offer.offer_no,
        offer_date=preview.offer.offer_date,
        currency=preview.offer.currency or "EUR",
        total_net_eur=preview.offer.total_net_eur,
        total_gross_eur=preview.offer.total_gross_eur,
        vat_rate=preview.offer.vat_rate,
        notes=preview.offer.notes,
        source_type=preview.source_type,
        source_file=preview.source_file,
        imported_by_user_id=current_user.id,
    )
    db.add(offer)
    db.flush()
    _replace_items(offer, preview.items)
    db.commit()
    db.refresh(offer)
    # Angebots-Positionen als Material-Stamm spiegeln (Soll-Liste).
    sync_offer_to_material(db, offer.id)
    db.commit()
    # Heizkörper-Positionen automatisch auf Heizkreise mappen (Best-effort).
    apply_radiator_offers(db, project.id)
    return _offer_to_read(project, offer)


# ----------------------------------------------------------------------
# PDF upload + manual headline data
# ----------------------------------------------------------------------


@router.post("/projects/{slug}/offers/pdf", response_model=OfferRead)
async def upload_pdf_offer(
    slug: str,
    file: UploadFile = File(...),
    supplier_name: str = Form(...),
    offer_no: str | None = Form(None),
    offer_date: str | None = Form(None),
    total_net_eur: float | None = Form(None),
    total_gross_eur: float | None = Form(None),
    vat_rate: float | None = Form(None),
    notes: str | None = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OfferRead:
    """Upload a PDF offer + user-typed headline figures. No auto-parsing."""
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien akzeptiert.")
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Leere Datei.")

    # Store PDF under workspaces/<slug>/offers/<uuid>_<filename>
    target_dir = _offers_dir(project)
    safe_name = file.filename.replace("/", "_").replace("\\", "_")
    target_path = target_dir / f"{uuid.uuid4().hex}_{safe_name}"
    target_path.write_bytes(raw)

    parsed_date: date | None = None
    if offer_date:
        try:
            parsed_date = date.fromisoformat(offer_date)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Datum im Format YYYY-MM-DD erwartet: {exc}"
            ) from exc

    offer = Offer(
        project_id=project.id,
        supplier_name=supplier_name,
        offer_no=offer_no,
        offer_date=parsed_date,
        currency="EUR",
        total_net_eur=total_net_eur,
        total_gross_eur=total_gross_eur,
        vat_rate=vat_rate,
        notes=notes,
        source_type="pdf",
        source_file=file.filename,
        attached_file_path=str(target_path),
        imported_by_user_id=current_user.id,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return _offer_to_read(project, offer)


@router.get("/projects/{slug}/offers/{offer_id}/attachment")
def download_offer_attachment(
    slug: str,
    offer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    project = _project_or_404(db, slug)
    require_project_role(db, current_user, project, PROJECT_READ_ROLES)
    offer = _offer_or_404(db, project, offer_id)
    if not offer.attached_file_path:
        raise HTTPException(status_code=404, detail="Keine Datei angehaengt")
    path = Path(offer.attached_file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Datei nicht (mehr) vorhanden")
    return FileResponse(
        path=str(path),
        filename=offer.source_file or path.name,
        media_type="application/pdf"
        if (offer.source_file or "").lower().endswith(".pdf")
        else "application/octet-stream",
    )
