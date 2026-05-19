"""Nachkalkulations-API: ad-hoc-Käufe aus dem Artikelstamm = Nachträge.

Endpoints:
  - ``GET /api/projects/{slug}/nachkalkulation`` → JSON-Aggregation.
  - ``GET /api/projects/{slug}/nachkalkulation.csv`` → CSV-Export
    (UTF-8 BOM + ``;`` separator + deutsches Zahlenformat, fertig für
    Excel und das Office-Team).

Beide nur für PL/BL/Admin/Obermonteur — Monteur soll Nachkalkulation
nicht sehen (Kalkulation ist Lead-Verantwortung).
"""
from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.orm_models import Project, User
from app.models.nachkalkulation import (
    NachkalkulationItemRead,
    NachkalkulationResultRead,
    NachkalkulationSectionRead,
)
from app.services.auth import (
    SITE_LEAD_ROLES,
    get_current_user,
    require_project_role,
)
from app.services.nachkalkulation import (
    NachkalkulationResult,
    nachkalkulation_for_project,
)

router = APIRouter()


def _to_read(res: NachkalkulationResult) -> NachkalkulationResultRead:
    return NachkalkulationResultRead(
        project_slug=res.project_slug,
        project_name=res.project_name,
        items_total=res.items_total,
        sections_total=res.sections_total,
        grand_total=res.grand_total,
        items_verbaut=res.items_verbaut,
        sections=[
            NachkalkulationSectionRead(
                section_number=s.section_number,
                section_name=s.section_name,
                subtotal=s.subtotal,
                item_count=s.item_count,
                items=[NachkalkulationItemRead(**i.__dict__) for i in s.items],
            )
            for s in res.sections
        ],
    )


@router.get(
    "/{slug}/nachkalkulation",
    response_model=NachkalkulationResultRead,
)
def get_nachkalkulation(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NachkalkulationResultRead:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    return _to_read(nachkalkulation_for_project(db, project))


def _de_num(value: float | None, digits: int = 2) -> str:
    """Deutsches Zahlenformat: ``1234,56`` (Komma als Dezimaltrennzeichen,
    kein Tausenderpunkt für Excel-Roundtrip)."""
    if value is None:
        return ""
    return f"{value:.{digits}f}".replace(".", ",")


@router.get("/{slug}/nachkalkulation.csv")
def get_nachkalkulation_csv(
    slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    project = db.query(Project).filter(Project.slug == slug).one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    require_project_role(db, current_user, project, SITE_LEAD_ROLES)
    res = nachkalkulation_for_project(db, project)

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow([
        "Abschnitt-Nr",
        "Abschnitt-Name",
        "Artikel-Nr",
        "Bezeichnung",
        "Einheit",
        "Menge",
        "Listenpreis EUR",
        "Summe EUR",
        "Notiz",
    ])
    for sec in res.sections:
        for it in sec.items:
            writer.writerow([
                "" if sec.section_number is None else str(sec.section_number),
                sec.section_name or "",
                it.artikelnummer or "",
                it.name,
                it.unit or "",
                _de_num(it.ist_qty, digits=3),
                _de_num(it.preis_eur, digits=2),
                _de_num(it.position_sum, digits=2),
                (it.note or "").replace("\n", " ").replace("\r", " "),
            ])
        writer.writerow([
            "",
            f"Zwischensumme Abschnitt {sec.section_number if sec.section_number is not None else '(ohne)'}",
            "", "", "", "", "",
            _de_num(sec.subtotal, digits=2),
            "",
        ])
    writer.writerow(["", "GESAMT NETTO", "", "", "", "", "", _de_num(res.grand_total, digits=2), ""])

    body = "﻿" + buf.getvalue()  # UTF-8 BOM für Excel
    filename = f"nachkalkulation_{project.slug}.csv"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
