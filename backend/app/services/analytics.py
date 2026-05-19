"""Analytics-Aggregation für das Projekt-Dashboard.

Liest die Kern-Tabellen (daily_reports, blockers, material_issues,
team_status, weekly_reports, material_items, risk_issues, offers) und
verdichtet sie zu KPIs / Zeitreihen / Listen, die das Frontend ohne
weitere Logik direkt rendern kann.

Pro-Projekt-Sichten und projektübergreifende Sichten in einem Modul, weil
sie auf den gleichen ORM-Tabellen aufbauen.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.orm_models import (
    Blocker,
    DailyReport,
    DailyReportAttendee,
    MaterialIssue,
    MaterialItem,
    Offer,
    Project,
    RiskIssue,
    TeamStatusEntry,
    User,
    WeeklyReport,
)


# ───────────────────────────────────────────────────────────────────────
# Output dataclasses (-> Pydantic models in app/models/analytics.py)
# ───────────────────────────────────────────────────────────────────────


@dataclass
class StatusBreakdown:
    green: int = 0
    yellow: int = 0
    red: int = 0
    total: int = 0


@dataclass
class TimeSeriesPoint:
    date: date
    value: float
    label: str | None = None


@dataclass
class TopItem:
    label: str
    count: int
    severity: str | None = None


@dataclass
class HoursPerUser:
    user_id: int
    display_name: str
    soll_hours: float
    ist_hours: float
    days: int


@dataclass
class HoursPerSection:
    section_number: int | None
    section_name: str | None
    ist_hours: float
    user_count: int
    report_count: int
    planned_hours: float | None = None
    # Diff = ist - planned; positiv = überzogen, negativ = noch Puffer
    delta_hours: float | None = None
    # Fortschritt in Prozent (kann > 100 sein bei Überschreitung). None wenn
    # planned_hours fehlt oder 0 — dann ist „Fortschritt" undefiniert.
    percent_done: float | None = None
    # Status: 'under' (< 80%), 'on_track' (80–100%), 'over' (> 100%),
    # 'unknown' (kein Soll hinterlegt)
    status: str = "unknown"


@dataclass
class ProjectAnalytics:
    """Pro-Projekt KPI-Set."""
    project_slug: str
    project_name: str
    # Letzte N Wochen
    period_start: date
    period_end: date
    # Status (alle Tagesberichte in der Periode)
    daily_status: StatusBreakdown = field(default_factory=StatusBreakdown)
    weekly_status: StatusBreakdown = field(default_factory=StatusBreakdown)
    # Probleme
    blockers_open: int = 0
    blockers_total: int = 0
    blockers_by_severity: dict[str, int] = field(default_factory=dict)
    material_open: int = 0
    material_total: int = 0
    risks_open: int = 0
    risks_total: int = 0
    # Material-Status (Inventory)
    materials_by_status: dict[str, int] = field(default_factory=dict)
    # Stunden
    hours_total_soll: float = 0.0
    hours_total_ist: float = 0.0
    # Geplante Gesamtstunden aus den Bauabschnitten (Projekt-Soll). Bezieht
    # sich auf den GESAMTPLAN, nicht auf die Periode — die Range-Bars
    # rechnen Ist (Periode) gegen dieses Plan-Soll.
    hours_total_planned: float = 0.0
    hours_total_delta: float = 0.0
    hours_total_percent: float | None = None
    hours_total_status: str = "unknown"
    hours_by_user: list[HoursPerUser] = field(default_factory=list)
    hours_by_section: list[HoursPerSection] = field(default_factory=list)
    # Zeitreihen
    daily_status_series: list[TimeSeriesPoint] = field(default_factory=list)
    blockers_opened_per_day: list[TimeSeriesPoint] = field(default_factory=list)
    # Kosten (aus Offers)
    offer_total_net: float | None = None
    offer_count: int = 0
    # Top-Probleme der letzten 14 Tage
    top_blockers: list[TopItem] = field(default_factory=list)
    top_material_issues: list[TopItem] = field(default_factory=list)


@dataclass
class PortfolioAnalytics:
    """Cross-project KPIs für Projekt-/Bauleitung-Dashboard."""
    generated_at: datetime
    project_count: int
    active_project_count: int
    projects_at_risk: list[dict[str, Any]] = field(default_factory=list)
    total_hours_ist_last_7d: float = 0.0
    total_hours_soll_last_7d: float = 0.0
    open_blockers_total: int = 0
    open_material_total: int = 0
    open_risks_total: int = 0
    total_offer_value_net: float = 0.0


# ───────────────────────────────────────────────────────────────────────
# Stunden-Helper: Tagesbericht + Anwesenheit → (user, day) Matrix
# ───────────────────────────────────────────────────────────────────────


def _attendance_hours_per_user_day(
    db: Session,
    *,
    project_id: int | None,
    period_start: date,
    period_end: date | None = None,
) -> list[dict[str, Any]]:
    """Aggregiert Stunden aus DailyReport + Attendees zu einer Liste von
    `{user_id, day, ist_hours, status, section_number, display_name}`-
    Einträgen — ein Eintrag pro (Anwesender, Tag, Bericht).

    Logik (an template_renderer.py auto_matrix angelehnt):
      * Wer einen Tagesbericht erstellt UND in eigenen Attendees ist (oder
        keine Attendees gesetzt), zählt für sich selbst.
      * Jeder gelistete Anwesende bekommt die ``ist_hours`` des Berichts
        gutgeschrieben — die App-Konvention ist „ein Monteur dokumentiert
        die Arbeitszeit für das anwesende Team".
      * Manuelle ``TeamStatusEntry``-Rows überschreiben den Auto-Wert
        pro (user, day) — Bauleitung-Korrektur gewinnt.

    Keine Multiplikation, keine Doppelzählung: Wenn ein User an einem Tag
    in zwei Berichten als Attendee auftaucht (z.B. zwei Abschnitte),
    werden die Stunden ADDIERT — er hat tatsächlich an beiden Stellen
    gearbeitet. Manuelle Override ersetzt den gesamten Tagessaldo.
    """
    end = period_end or date.today()

    daily_query = (
        db.query(DailyReport)
        .filter(
            DailyReport.report_date >= period_start,
            DailyReport.report_date <= end,
        )
    )
    if project_id is not None:
        daily_query = daily_query.filter(DailyReport.project_id == project_id)
    reports = daily_query.all()
    report_ids = [r.id for r in reports]

    # Attendees + User-Namen in einem Rutsch.
    attendees_by_report: dict[int, list[tuple[int, str]]] = defaultdict(list)
    if report_ids:
        att_rows = (
            db.query(DailyReportAttendee, User)
            .join(User, DailyReportAttendee.user_id == User.id)
            .filter(DailyReportAttendee.daily_report_id.in_(report_ids))
            .all()
        )
        for att, usr in att_rows:
            attendees_by_report[att.daily_report_id].append(
                (att.user_id, usr.display_name or usr.username)
            )

    # Owner-Name pro Bericht für den Fallback (kein Attendee gepflegt).
    owner_user = {r.id: r.user for r in reports}

    entries: list[dict[str, Any]] = []
    for r in reports:
        present = attendees_by_report.get(r.id, [])
        if not present:
            # Fallback: nur der Owner — sonst gehen seine Stunden verloren.
            usr = owner_user[r.id]
            if usr is not None:
                present = [(r.user_id, usr.display_name or usr.username)]
        for uid, name in present:
            entries.append({
                "user_id": uid,
                "display_name": name,
                "day": r.report_date,
                "ist_hours": float(r.ist_hours or 0),
                "status": r.status,
                "section_number": r.section_number,
                "source": "report",
                "report_id": r.id,
            })

    # Manuelle TeamStatusEntries — überschreiben den Auto-Wert pro (user, day).
    manual_query = (
        db.query(TeamStatusEntry, User)
        .join(User, TeamStatusEntry.user_id == User.id)
        .filter(
            TeamStatusEntry.day >= period_start,
            TeamStatusEntry.day <= end,
        )
    )
    if project_id is not None:
        manual_query = manual_query.filter(TeamStatusEntry.project_id == project_id)
    manual_rows = manual_query.all()
    manual_keys = {(t.user_id, t.day) for t, _ in manual_rows}

    # Auto-Einträge für (user, day) mit manueller Override raus.
    entries = [e for e in entries if (e["user_id"], e["day"]) not in manual_keys]
    for t, usr in manual_rows:
        entries.append({
            "user_id": t.user_id,
            "display_name": usr.display_name or usr.username,
            "day": t.day,
            "ist_hours": float(t.ist_hours or 0),
            "status": t.status,
            "section_number": None,
            "soll_hours": float(t.soll_hours or 0),
            "source": "manual",
            "report_id": None,
        })

    return entries


# ───────────────────────────────────────────────────────────────────────
# Project-level
# ───────────────────────────────────────────────────────────────────────


def project_analytics(
    db: Session,
    project: Project,
    *,
    weeks_back: int = 4,
) -> ProjectAnalytics:
    """Aggregiere KPIs für ein einzelnes Projekt über die letzten N Wochen."""
    today = date.today()
    period_start = today - timedelta(weeks=weeks_back)

    out = ProjectAnalytics(
        project_slug=project.slug,
        project_name=project.name,
        period_start=period_start,
        period_end=today,
    )

    # ── Daily Reports ──
    daily = (
        db.query(DailyReport)
        .filter(
            DailyReport.project_id == project.id,
            DailyReport.report_date >= period_start,
            DailyReport.report_date <= today,
        )
        .order_by(DailyReport.report_date)
        .all()
    )
    daily_counter = Counter(r.status for r in daily)
    out.daily_status = StatusBreakdown(
        green=daily_counter.get("green", 0),
        yellow=daily_counter.get("yellow", 0),
        red=daily_counter.get("red", 0),
        total=len(daily),
    )
    # Zeitreihe: pro Tag durchschnittlicher Status-Code (1=green, 2=yellow, 3=red)
    _status_code = {"green": 1, "yellow": 2, "red": 3}
    daily_by_day: dict[date, list[int]] = defaultdict(list)
    for r in daily:
        daily_by_day[r.report_date].append(_status_code.get(r.status, 0) or 0)
    out.daily_status_series = [
        TimeSeriesPoint(
            date=d,
            value=round(sum(vals) / len(vals), 2) if vals else 0,
            label=_status_code_label(round(sum(vals) / len(vals))) if vals else None,
        )
        for d, vals in sorted(daily_by_day.items())
    ]

    # ── Weekly Reports ──
    weekly = (
        db.query(WeeklyReport)
        .filter(
            WeeklyReport.project_id == project.id,
            WeeklyReport.week_start >= period_start,
        )
        .all()
    )
    weekly_counter = Counter(w.status for w in weekly)
    out.weekly_status = StatusBreakdown(
        green=weekly_counter.get("green", 0),
        yellow=weekly_counter.get("yellow", 0),
        red=weekly_counter.get("red", 0),
        total=len(weekly),
    )

    # ── Blocker ──
    blockers = (
        db.query(Blocker)
        .filter(Blocker.project_id == project.id)
        .all()
    )
    out.blockers_total = len(blockers)
    out.blockers_open = sum(1 for b in blockers if b.status == "open")
    out.blockers_by_severity = dict(
        Counter(b.severity for b in blockers if b.status == "open")
    )
    # Zeitreihe: pro Tag neu eröffnete Blocker (letzte 14 Tage)
    cutoff_14d = today - timedelta(days=14)
    blockers_per_day: dict[date, int] = defaultdict(int)
    for b in blockers:
        if b.created_at and b.created_at.date() >= cutoff_14d:
            blockers_per_day[b.created_at.date()] += 1
    out.blockers_opened_per_day = [
        TimeSeriesPoint(date=d, value=cnt)
        for d, cnt in sorted(blockers_per_day.items())
    ]
    # Top-3 Blocker (häufigste Wörter im description) — sehr einfach gehalten
    out.top_blockers = _top_descriptions(
        [b.description for b in blockers if b.status == "open"], limit=5
    )

    # ── Material-Issues ──
    material = (
        db.query(MaterialIssue)
        .filter(MaterialIssue.project_id == project.id)
        .all()
    )
    out.material_total = len(material)
    out.material_open = sum(1 for m in material if m.status == "open")
    out.top_material_issues = _top_descriptions(
        [m.description for m in material if m.status == "open"], limit=5
    )

    # ── Material-Items (Inventory) ──
    items = (
        db.query(MaterialItem.status, func.count(MaterialItem.id))
        .filter(MaterialItem.project_id == project.id)
        .group_by(MaterialItem.status)
        .all()
    )
    out.materials_by_status = {row[0]: row[1] for row in items}

    # ── Risks ──
    risks = (
        db.query(RiskIssue)
        .filter(RiskIssue.project_id == project.id)
        .all()
    )
    out.risks_total = len(risks)
    out.risks_open = sum(1 for r in risks if r.status == "offen")

    # ── Stunden ──
    # Quelle: Tagesberichte + Attendees, mit manuellem TeamStatusEntry-Override.
    # So tauchen Monteur-Stunden sofort nach dem Abschicken eines Tagesberichts
    # in der Analyse auf — vorher nur aus separat eingepflegten TeamStatus.
    hour_entries = _attendance_hours_per_user_day(
        db, project_id=project.id, period_start=period_start, period_end=today,
    )
    by_user: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"soll": 0.0, "ist": 0.0, "days": set(), "name": ""}
    )
    by_section: dict[int | None, dict[str, Any]] = defaultdict(
        lambda: {"ist": 0.0, "users": set(), "reports": set()}
    )
    section_name_lookup = {s.number: s.name for s in project.sections}
    section_planned_lookup: dict[int, float | None] = {
        s.number: (float(s.planned_hours) if s.planned_hours is not None else None)
        for s in project.sections
    }
    # Auch Abschnitte OHNE bisherige Ist-Buchungen sollen in der Bar erscheinen
    # (sonst sieht der PL nur „verbuchte" Abschnitte und übersieht die noch
    # nicht angefassten). Initialisiere alle Sektionen aus dem Projekt-Plan.
    for s in project.sections:
        _ = by_section[s.number]  # legt leeren Bucket an
    for e in hour_entries:
        bucket = by_user[e["user_id"]]
        bucket["soll"] += float(e.get("soll_hours") or 0)
        bucket["ist"] += float(e["ist_hours"] or 0)
        bucket["days"].add(e["day"])
        if not bucket["name"]:
            bucket["name"] = e["display_name"]

        sec_bucket = by_section[e.get("section_number")]
        sec_bucket["ist"] += float(e["ist_hours"] or 0)
        sec_bucket["users"].add(e["user_id"])
        if e.get("report_id") is not None:
            sec_bucket["reports"].add(e["report_id"])

    out.hours_by_user = sorted(
        [
            HoursPerUser(
                user_id=uid,
                display_name=b["name"] or f"User {uid}",
                soll_hours=round(b["soll"], 1),
                ist_hours=round(b["ist"], 1),
                days=len(b["days"]),
            )
            for uid, b in by_user.items()
        ],
        key=lambda h: -h.ist_hours,
    )

    def _hours_status(planned: float | None, ist: float) -> tuple[float | None, float | None, str]:
        """Liefert (percent, delta, status). status: under | on_track | over | unknown."""
        if planned is None or planned <= 0:
            return None, None, "unknown"
        percent = round(ist / planned * 100.0, 1)
        delta = round(ist - planned, 1)
        if percent > 100:
            status = "over"
        elif percent >= 80:
            status = "on_track"
        else:
            status = "under"
        return percent, delta, status

    section_rows: list[HoursPerSection] = []
    for sec, b in by_section.items():
        planned = section_planned_lookup.get(sec) if sec is not None else None
        ist = round(b["ist"], 1)
        percent, delta, status = _hours_status(planned, ist)
        section_rows.append(
            HoursPerSection(
                section_number=sec,
                section_name=section_name_lookup.get(sec) if sec is not None else None,
                ist_hours=ist,
                user_count=len(b["users"]),
                report_count=len(b["reports"]),
                planned_hours=planned,
                delta_hours=delta,
                percent_done=percent,
                status=status,
            )
        )
    out.hours_by_section = sorted(
        section_rows,
        key=lambda h: (h.section_number is None, h.section_number or 0),
    )

    out.hours_total_soll = round(sum(h.soll_hours for h in out.hours_by_user), 1)
    out.hours_total_ist = round(sum(h.ist_hours for h in out.hours_by_user), 1)
    # Plan-Soll aus den Sektionen (NICHT aus TeamStatus). Das ist der eigentliche
    # Projektplan, gegen den die Range-Bar im Frontend rechnet.
    out.hours_total_planned = round(
        sum(float(s.planned_hours or 0) for s in project.sections), 1
    )
    total_percent, total_delta, total_status = _hours_status(
        out.hours_total_planned or None, out.hours_total_ist
    )
    out.hours_total_percent = total_percent
    out.hours_total_delta = total_delta if total_delta is not None else 0.0
    out.hours_total_status = total_status

    # ── Offers (aus heute eingebauter Domäne) ──
    offers = (
        db.query(Offer)
        .filter(Offer.project_id == project.id)
        .all()
    )
    out.offer_count = len(offers)
    if offers:
        total = sum((o.total_net_eur or 0) for o in offers)
        out.offer_total_net = round(total, 2) if total else None

    return out


def _status_code_label(code: float) -> str:
    if code <= 1.4:
        return "green"
    if code <= 2.4:
        return "yellow"
    return "red"


def _top_descriptions(items: list[str | None], *, limit: int = 5) -> list[TopItem]:
    """Sehr einfache Top-N nach Wortpräsenz. Reine Heuristik für Demo —
    für sauberes Clustering bräuchten wir Embeddings."""
    counter: Counter[str] = Counter()
    for item in items:
        if not item:
            continue
        # Erste 60 Zeichen als label, falls einzigartig
        key = item.strip()[:60]
        if key:
            counter[key] += 1
    return [
        TopItem(label=label, count=cnt)
        for label, cnt in counter.most_common(limit)
    ]


# ───────────────────────────────────────────────────────────────────────
# Portfolio-level
# ───────────────────────────────────────────────────────────────────────


def portfolio_analytics(db: Session) -> PortfolioAnalytics:
    """Cross-Projekt-Sicht — für Bauleitung/Projektleitung-Dashboard."""
    today = date.today()
    last_7d = today - timedelta(days=7)

    projects = db.query(Project).all()
    out = PortfolioAnalytics(
        generated_at=datetime.now(timezone.utc),
        project_count=len(projects),
        active_project_count=sum(
            1 for p in projects if p.status in {"in_progress", "ready", "published"}
        ),
    )

    # Offene Probleme aggregiert
    out.open_blockers_total = (
        db.query(func.count(Blocker.id)).filter(Blocker.status == "open").scalar() or 0
    )
    out.open_material_total = (
        db.query(func.count(MaterialIssue.id))
        .filter(MaterialIssue.status == "open")
        .scalar()
        or 0
    )
    out.open_risks_total = (
        db.query(func.count(RiskIssue.id)).filter(RiskIssue.status == "offen").scalar() or 0
    )

    # Stunden letzte 7 Tage — gleiche Quelle wie pro-Projekt-Analytics:
    # Tagesbericht + Attendees, manueller TeamStatus überschreibt.
    hour_entries = _attendance_hours_per_user_day(
        db, project_id=None, period_start=last_7d, period_end=today,
    )
    out.total_hours_ist_last_7d = round(
        sum(float(e["ist_hours"] or 0) for e in hour_entries), 1
    )
    out.total_hours_soll_last_7d = round(
        sum(float(e.get("soll_hours") or 0) for e in hour_entries), 1
    )

    # Offer-Volumen aller Projekte
    out.total_offer_value_net = round(
        db.query(func.coalesce(func.sum(Offer.total_net_eur), 0)).scalar() or 0.0, 2
    )

    # Projekte at risk: irgendein roter Tagesbericht in letzten 7 Tagen ODER
    # mind. ein offener high/critical-Blocker
    at_risk: list[dict[str, Any]] = []
    for p in projects:
        recent_red = (
            db.query(DailyReport)
            .filter(
                DailyReport.project_id == p.id,
                DailyReport.status == "red",
                DailyReport.report_date >= last_7d,
            )
            .count()
        )
        critical_blockers = (
            db.query(Blocker)
            .filter(
                Blocker.project_id == p.id,
                Blocker.status == "open",
                Blocker.severity.in_(["high", "critical"]),
            )
            .count()
        )
        if recent_red or critical_blockers:
            at_risk.append({
                "slug": p.slug,
                "name": p.name,
                "recent_red_reports": recent_red,
                "critical_blockers": critical_blockers,
            })
    out.projects_at_risk = at_risk

    return out
