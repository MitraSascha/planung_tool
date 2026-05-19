"""Render project documents from DB-stored Jinja2 templates + domain data.

This is the replacement for the legacy "Codex generates a new HTML per run"
flow. Templates live in ``document_templates`` and read project data from
the ORM models that already exist (``Project``, ``ProjectSection``,
``HeatingDesign``, ``Blocker``, …) so any change in the domain layer is
visible in every document immediately — no per-document state drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from html import escape as _html_escape

from jinja2 import Environment, StrictUndefined, select_autoescape
from markupsafe import Markup
from sqlalchemy.orm import Session, selectinload

from app.db.orm_models import (
    Blocker,
    DailyReport,
    DailyReportAttendee,
    DocumentTemplate,
    HeatingDesign,
    MaterialIssue,
    MaterialItem,
    MaterialUsage,
    Project,
    ProjectMember,
    ProjectPhoto,
    ProjectSection,
    ProjectUpload,
    RiskIssue,
    SectionSchedule,
    TeamStatusEntry,
    User,
)
from app.services.milestones import (
    list_milestones_for_render as _list_milestones_render,
)


# Shared CSS injected into every template via {{ base_css | safe }}. Mitra
# Sanitär brand: marine blue #1c3244 (primary) + copper orange #ef804e
# (accent), Inter font family, mobile-first. Lives in one place so all
# templates stay visually consistent.
BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

:root {
  --brand-primary: #1c3244;
  --brand-primary-dark: #11202d;
  --brand-primary-soft: #2a4a64;
  --brand-accent: #ef804e;
  --brand-accent-soft: #fce5d8;
  --text-dark: #1c2532;
  --text-muted: #5b6b7c;
  --text-faint: #94a3b3;
  --page-bg: #d9e1ea;
  --card-bg: #ffffff;
  --card-border: #e3e8ef;
  --card-shadow: 0 2px 6px rgba(28, 50, 68, 0.06), 0 1px 2px rgba(28, 50, 68, 0.04);
  --card-shadow-lg: 0 6px 16px rgba(28, 50, 68, 0.08);
  --radius-sm: 6px;
  --radius: 10px;
  --radius-lg: 14px;
  --status-green-bg: #e3f5e8; --status-green-fg: #1d6b35;
  --status-yellow-bg: #fff3cd; --status-yellow-fg: #8a6500;
  --status-red-bg: #fbe1e1; --status-red-fg: #9b2129;
  --status-blue-bg: #e1ecf7; --status-blue-fg: #1c3244;
  --status-grey-bg: #eef1f5; --status-grey-fg: #5b6b7c;
}

* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 15px; line-height: 1.55; color: var(--text-dark);
  background: var(--page-bg);
  -webkit-font-smoothing: antialiased;
}

.page-wrap { max-width: 1080px; margin: 0 auto; padding: 0 18px 60px; }

/* ───── Brand-Header ───────────────────────────────────────────────── */
.brand-bar {
  background: linear-gradient(135deg, var(--brand-primary) 0%, var(--brand-primary-soft) 100%);
  color: #fff;
  padding: 22px 0;
  margin-bottom: 28px;
  box-shadow: 0 2px 8px rgba(28, 50, 68, 0.18);
}
.brand-bar .brand-inner {
  max-width: 1080px; margin: 0 auto; padding: 0 18px;
  display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap;
}
.brand-logo { display: flex; align-items: center; gap: 14px; }
.brand-logo .brand-mark {
  width: 46px; height: 46px; border-radius: 12px;
  background: var(--brand-accent);
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 20px; color: #fff;
  box-shadow: 0 2px 6px rgba(0,0,0,0.15);
}
.brand-logo .brand-text { line-height: 1.15; }
.brand-logo .brand-name { font-size: 18px; font-weight: 700; letter-spacing: 0.4px; }
.brand-logo .brand-tag { font-size: 12px; font-weight: 400; color: rgba(255,255,255,0.78); }
.brand-meta { font-size: 12.5px; color: rgba(255,255,255,0.85); text-align: right; }
.brand-meta strong { color: #fff; }

/* ───── Hero (Projekt-Kopfblock) ──────────────────────────────────── */
.hero {
  background: var(--card-bg);
  border-radius: var(--radius-lg);
  box-shadow: var(--card-shadow-lg);
  padding: 26px 28px;
  margin-bottom: 24px;
  border-left: 5px solid var(--brand-accent);
}
.hero-row { display: flex; justify-content: space-between; gap: 28px; flex-wrap: wrap; align-items: flex-start; }
.hero h1 { margin: 0 0 6px; font-size: 26px; font-weight: 700; color: var(--brand-primary); letter-spacing: -0.3px; }
.hero .hero-sub { color: var(--text-muted); font-size: 14.5px; margin: 0; }
.hero-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin-top: 18px; }
.hero-grid .item { font-size: 13px; }
.hero-grid .item .label { display: block; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.6px; font-size: 11px; font-weight: 600; }
.hero-grid .item .value { display: block; color: var(--text-dark); font-weight: 500; margin-top: 2px; }
.hero-grid .item .value.offen { color: #b14040; font-style: italic; font-weight: 400; }

/* ───── Doc-Type-Badge ────────────────────────────────────────────── */
.doc-badge {
  display: inline-block; padding: 5px 12px; border-radius: 999px;
  font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.6px;
  margin-bottom: 14px;
}
.doc-badge.info { background: var(--status-blue-bg); color: var(--status-blue-fg); }
.doc-badge.formular { background: var(--brand-accent); color: #fff; }

/* ───── Typography ────────────────────────────────────────────────── */
h1 { font-size: 24px; font-weight: 700; color: var(--brand-primary); margin: 0 0 6px; }
h2 { font-size: 19px; font-weight: 700; color: var(--brand-primary); margin: 30px 0 12px;
     padding-bottom: 6px; border-bottom: 2px solid var(--brand-accent); display: inline-block; }
h3 { font-size: 15.5px; font-weight: 600; color: var(--brand-primary); margin: 18px 0 8px; }
p { margin: 8px 0; }
a { color: var(--brand-primary); text-decoration: none; border-bottom: 1px solid rgba(28,50,68,0.2); }
a:hover { color: var(--brand-accent); border-bottom-color: var(--brand-accent); }
code { background: #eef1f5; padding: 2px 6px; border-radius: 4px; font-size: 12.5px; color: var(--brand-primary); font-family: 'JetBrains Mono', monospace; }
ul, ol { padding-left: 22px; }
li { margin-bottom: 4px; }

/* ───── Card / Section ────────────────────────────────────────────── */
.card {
  background: var(--card-bg);
  border-radius: var(--radius);
  box-shadow: var(--card-shadow);
  padding: 22px 24px;
  margin-bottom: 18px;
  border: 1px solid var(--card-border);
}
section { display: block; }
section.card h2 { margin-top: 0; }

/* ───── Tables ────────────────────────────────────────────────────── *
 * Desktop (>= 768px): Klassische Tabelle mit Sticky-Header.
 * Mobile (< 768px):   .data-cards Variante = jede Zeile zur Card mit
 *                     data-label="…" Labels. Standard-Tabellen bleiben
 *                     scrollbar im .table-wrap.
 * ─────────────────────────────────────────────────────────────────── */
.table-wrap {
  overflow-x: auto; -webkit-overflow-scrolling: touch;
  border-radius: var(--radius); box-shadow: var(--card-shadow);
  background: #fff; margin-top: 10px;
}
/* Auto-Wrap: jede freistehende <table> in einer Sektion bekommt
   default-overflow, falls der Autor das table-wrap vergisst. */
section > table, .card > table, .abschnitt-card > table {
  display: block; overflow-x: auto; -webkit-overflow-scrolling: touch;
}
table { border-collapse: collapse; width: 100%; font-size: 14px; }
thead th {
  background: var(--brand-primary); color: #fff; font-weight: 600;
  text-align: left; padding: 11px 14px; font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.4px;
  position: sticky; top: 0; z-index: 1;
}
tbody td { padding: 11px 14px; border-top: 1px solid var(--card-border); vertical-align: top; color: var(--text-dark); }
tbody tr:nth-child(even) td { background: #fafbfc; }
tbody tr:hover td { background: #f3f6fa; }

/* ───── Mobile: optionale Card-Variante für Datentabellen ─────────── *
 * <table class="data-cards"> mit <td data-label="…">value</td>
 * ─────────────────────────────────────────────────────────────────── */
@media (max-width: 767px) {
  .data-cards, .data-cards thead, .data-cards tbody, .data-cards tr, .data-cards td { display: block; width: 100%; }
  .data-cards thead { position: absolute; left: -9999px; width: 1px; height: 1px; overflow: hidden; }
  .data-cards tr {
    background: #fff; border: 1px solid var(--card-border); border-radius: var(--radius);
    margin-bottom: 10px; padding: 6px 0; box-shadow: var(--card-shadow);
  }
  .data-cards tr:nth-child(even) td, .data-cards tr:hover td { background: transparent; }
  .data-cards td {
    padding: 6px 14px; border: none; text-align: right;
    display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  }
  .data-cards td::before {
    content: attr(data-label);
    flex-shrink: 0; font-size: 11px; font-weight: 700;
    letter-spacing: 0.4px; text-transform: uppercase; color: var(--text-muted);
    text-align: left;
  }
  .data-cards td:first-child {
    background: #f6f8fb; padding: 10px 14px;
    border-radius: var(--radius) var(--radius) 0 0;
    margin: -6px 0 6px;
    font-weight: 700; color: var(--brand-primary); font-size: 15px;
    flex-direction: column; align-items: stretch; text-align: left;
  }
  .data-cards td:first-child::before { color: var(--brand-accent); margin-bottom: 2px; }
}

.kv-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.kv-table th, .kv-table td { padding: 10px 14px; border-bottom: 1px solid var(--card-border); text-align: left; vertical-align: top; }
.kv-table th { background: #f6f8fb; font-weight: 600; color: var(--brand-primary); width: 36%; }
.kv-table tr:last-child th, .kv-table tr:last-child td { border-bottom: none; }

.budget-total td { background: var(--brand-accent-soft) !important; font-weight: 700; color: var(--brand-primary); }

/* ───── KPI-Cards ─────────────────────────────────────────────────── */
.kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin: 16px 0; }
.kpi-card {
  background: linear-gradient(135deg, #fff 0%, #f6f8fb 100%);
  border: 1px solid var(--card-border); border-radius: var(--radius);
  padding: 16px 18px; text-align: left;
  box-shadow: var(--card-shadow);
  border-top: 3px solid var(--brand-accent);
}
.kpi-card .kpi-value { display: block; font-size: 26px; font-weight: 700; color: var(--brand-primary); line-height: 1.1; }
.kpi-card .kpi-label { display: block; font-size: 12.5px; color: var(--text-muted); margin-top: 4px; font-weight: 500; }

/* ───── Abschnitts-Badge ──────────────────────────────────────────── */
.abschnitt-num {
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--brand-primary); color: #fff;
  border-radius: 999px; min-width: 28px; height: 28px; padding: 0 8px;
  font-weight: 700; font-size: 13px;
}
.abschnitt-card {
  background: #fff; border-radius: var(--radius); padding: 22px 24px;
  box-shadow: var(--card-shadow); border: 1px solid var(--card-border);
  margin-bottom: 16px; border-left: 4px solid var(--brand-accent);
}
.abschnitt-card .abschnitt-head { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.abschnitt-card .abschnitt-head h3 { margin: 0; font-size: 17px; }
.abschnitt-card .abschnitt-meta { color: var(--text-muted); font-size: 13px; margin: 0 0 12px; }

/* ───── Status / Ampel-Badges ─────────────────────────────────────── */
.status-badge {
  display: inline-block; padding: 3px 11px; border-radius: 999px;
  font-size: 11.5px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.4px;
  white-space: nowrap;
}
.status-green  { background: var(--status-green-bg);  color: var(--status-green-fg); }
.status-yellow { background: var(--status-yellow-bg); color: var(--status-yellow-fg); }
.status-red    { background: var(--status-red-bg);    color: var(--status-red-fg); }
.status-blue   { background: var(--status-blue-bg);   color: var(--status-blue-fg); }
.status-grey   { background: var(--status-grey-bg);   color: var(--status-grey-fg); }
.risiko-hoch   { background: var(--status-red-bg);    color: var(--status-red-fg);   padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.risiko-mittel { background: var(--status-yellow-bg); color: var(--status-yellow-fg); padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.risiko-gering { background: var(--status-green-bg);  color: var(--status-green-fg);  padding: 3px 10px; border-radius: 6px; font-size: 12px; font-weight: 700; }

/* ───── Note-Boxes ────────────────────────────────────────────────── */
.note { border-radius: var(--radius); padding: 14px 18px; margin: 14px 0; font-size: 14px; border-left: 4px solid; }
.note.info  { background: #eaf2fb; border-color: var(--brand-primary); color: var(--brand-primary); }
.note.warn  { background: #fff3e0; border-color: var(--brand-accent); color: #7a3815; }
.note.offen { background: #fbe9da; border-color: var(--brand-accent); }
.note.offen .note-title { font-weight: 700; color: var(--brand-accent); display: block; margin-bottom: 6px; }
.note.offen ul { margin: 4px 0 0; padding-left: 22px; }
.offener-punkt { color: #b14040; font-style: italic; }

/* ───── Rolle-Cards (Start-Seite) ─────────────────────────────────── */
.role-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-top: 12px; }
.role-card {
  background: #fff; border-radius: var(--radius); padding: 20px 22px;
  box-shadow: var(--card-shadow); border: 1px solid var(--card-border);
  transition: transform 0.12s ease, box-shadow 0.12s ease;
  text-decoration: none; color: var(--text-dark); display: block; border-bottom: 4px solid var(--brand-accent);
}
.role-card:hover { transform: translateY(-2px); box-shadow: var(--card-shadow-lg); border-bottom-color: var(--brand-primary); }
.role-card .role-tag { font-size: 11px; color: var(--brand-accent); font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase; }
.role-card .role-title { font-size: 17px; font-weight: 700; color: var(--brand-primary); margin: 4px 0 8px; }
.role-card .role-desc { font-size: 13.5px; color: var(--text-muted); }

/* ───── Nav-Liste (Dokumenten-Index) ──────────────────────────────── */
.nav-list { list-style: none; padding: 0; margin: 8px 0 0; }
.nav-list .nav-category { display: block; font-size: 12px; font-weight: 700; color: var(--brand-accent); text-transform: uppercase; letter-spacing: 0.5px; margin: 18px 0 6px; }
.nav-list li.nav-item { margin: 4px 0; }
.nav-list li.nav-item a { display: inline-block; padding: 4px 0; font-size: 14px; border: none; }

/* ───── Gantt ─────────────────────────────────────────────────────── */
.gantt-grid { font-size: 12px; }
.gantt-grid th, .gantt-grid td { padding: 4px 6px; text-align: center; border: 1px solid var(--card-border); }
.gantt-grid .gantt-label { text-align: left; font-weight: 600; }
.gantt-grid .gantt-bar { background: var(--brand-primary); color: #fff; font-size: 11px; font-weight: 600; }
.gantt-grid .gantt-bar-2 { background: #2e6b3a; color: #fff; font-weight: 600; }
.gantt-grid .gantt-bar-3 { background: var(--brand-accent); color: #fff; font-weight: 600; }
.gantt-grid .gantt-bar-4 { background: #6f42c1; color: #fff; font-weight: 600; }
.gantt-grid .gantt-half { background: repeating-linear-gradient(45deg, var(--brand-primary), var(--brand-primary) 4px, #5a7a96 4px, #5a7a96 8px); color: #fff; }
.gantt-grid .gantt-off { background: #f6f8fb; }
.gantt-grid .gantt-now { outline: 2px solid var(--brand-accent); }
.gantt-grid .month-band { background: var(--brand-primary); color: #fff; font-weight: 700; }

/* ───── Unterschriften-Block ──────────────────────────────────────── */
.signature-row { display: grid; grid-template-columns: 1fr 1fr; gap: 28px; margin-top: 32px; }
.signature-box { background: #fff; border: 1px solid var(--card-border); border-radius: var(--radius); padding: 50px 18px 14px; font-size: 12.5px; color: var(--text-muted); position: relative; }
.signature-box::before { content: ''; position: absolute; top: 36px; left: 18px; right: 18px; border-top: 1px dashed var(--text-faint); }
.signature-box strong { display: block; color: var(--brand-primary); font-size: 13.5px; }

/* ───── Inputs / Form ─────────────────────────────────────────────── */
input[type="text"], input[type="date"], input[type="time"], input[type="week"], input[type="number"], select, textarea {
  font-family: inherit; font-size: 16px;            /* 16px verhindert iOS-Zoom */
  min-height: 48px;                                  /* Mobile Touch-Target */
  padding: 11px 14px;
  border: 1.5px solid var(--card-border); border-radius: var(--radius);
  width: 100%; background: #fff; color: var(--text-dark);
  transition: border-color 0.12s, box-shadow 0.12s;
  appearance: none;
}
input:hover:not(:disabled):not(:focus), select:hover:not(:disabled):not(:focus), textarea:hover:not(:disabled):not(:focus) { border-color: #b7c4cf; }
input:focus, select:focus, textarea:focus { outline: none; border-color: var(--brand-accent); box-shadow: 0 0 0 3px rgba(239, 128, 78, 0.30); }
input:disabled, select:disabled, textarea:disabled { background: #f6f7f9; color: var(--text-muted); cursor: not-allowed; }
textarea { min-height: 96px; resize: vertical; line-height: 1.5; }
input[type="checkbox"], input[type="radio"] {
  width: 20px; height: 20px; min-height: 0; padding: 0;
  accent-color: var(--brand-accent); cursor: pointer; vertical-align: middle;
}
label { font-size: 13.5px; color: var(--brand-primary); font-weight: 600; display: block; margin-bottom: 6px; }
select {
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8' fill='none'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%235b6b7c' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 14px center;
  padding-right: 38px;
}
.field-row { display: grid; grid-template-columns: 1fr; gap: 14px; margin: 12px 0; }
@media (min-width: 640px) { .field-row { grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); } }

/* ───── Buttons — einheitliches System, kein Inline-Style ──────────── */
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  min-height: 48px; padding: 0 18px;
  font-family: inherit; font-size: 14px; font-weight: 600; line-height: 1;
  border: 1.5px solid transparent; border-radius: var(--radius);
  background: transparent; color: var(--text-dark);
  cursor: pointer; text-decoration: none;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
  white-space: nowrap; user-select: none;
}
.btn:focus-visible { outline: none; box-shadow: 0 0 0 3px rgba(239, 128, 78, 0.35); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn--primary { background: var(--brand-primary); color: #fff; border-color: var(--brand-primary); }
.btn--primary:hover:not(:disabled) { background: var(--brand-primary-dark); border-color: var(--brand-primary-dark); }
.btn--accent  { background: var(--brand-accent);  color: #fff; border-color: var(--brand-accent); }
.btn--accent:hover:not(:disabled)  { filter: brightness(0.92); }
.btn--secondary { background: #fff; color: var(--text-dark); border-color: var(--card-border); }
.btn--secondary:hover:not(:disabled) { background: #f6f7f9; border-color: #b7c4cf; }
.btn--ghost   { background: transparent; color: var(--text-dark); }
.btn--ghost:hover:not(:disabled) { background: #f0f3f6; }
.btn--danger  { background: var(--status-red-fg); color: #fff; border-color: var(--status-red-fg); }
.btn--danger-ghost { background: transparent; color: var(--status-red-fg); }
.btn--danger-ghost:hover:not(:disabled) { background: var(--status-red-bg); }
.btn--icon    { min-width: 48px; padding: 0; }
.btn--sm      { min-height: 36px; padding: 0 12px; font-size: 13px; }
.btn--sm.btn--icon { min-width: 36px; }
.btn-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.btn-row--right { justify-content: flex-end; }

/* ───── Briefkopf-Box (Auftragnehmer-Platzhalter) ─────────────────── */
.briefkopf-box { border: 1px dashed var(--text-faint); border-radius: var(--radius); padding: 14px 16px; font-size: 13px; color: var(--text-muted); min-height: 78px; background: #fafbfc; }
.briefkopf-box strong { color: var(--brand-primary); display: block; font-size: 13.5px; margin-bottom: 4px; }

/* ───── Page-Footer ───────────────────────────────────────────────── */
.page-footer { margin-top: 36px; padding: 18px 0 4px; border-top: 1px solid var(--card-border); font-size: 12px; color: var(--text-muted); display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.page-footer .brand-mini { color: var(--brand-primary); font-weight: 600; }

/* ───── Print ─────────────────────────────────────────────────────── */
@media print {
  body { background: #fff; font-size: 11pt; color: #000; }
  .brand-bar { background: var(--brand-primary) !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .page-wrap { padding: 0; }
  .card, .hero, .abschnitt-card { box-shadow: none; border: 1px solid #ccc; page-break-inside: avoid; }
  thead th { background: #1c3244 !important; color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact;
             position: static !important; /* sticky-header bricht beim Drucken */ }
  table { page-break-inside: auto; }
  tr { page-break-inside: avoid; page-break-after: auto; }
  thead { display: table-header-group; }                  /* Header auf jeder Seite wiederholen */
  tfoot { display: table-footer-group; }
  .doc-badge.formular, .kpi-card { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  h1, h2, h3 { page-break-after: avoid; }
  a { color: var(--brand-primary); border: none; }
  .btn { display: none; }                                  /* Buttons nicht drucken */
  .data-cards { /* Card-Variante zurück auf normale Tabelle für Druck */
    display: table !important;
    thead { display: table-header-group !important; position: static !important; left: auto; width: auto; height: auto; }
    tr { display: table-row !important; }
    td { display: table-cell !important; text-align: left !important; }
    td::before { display: none !important; }
  }
}

/* ───── Mobile ────────────────────────────────────────────────────── */
@media (max-width: 720px) {
  body { font-size: 15px; }
  .page-wrap { padding: 0 12px 40px; }
  .brand-bar { padding: 16px 0; margin-bottom: 18px; }
  .brand-bar .brand-inner { gap: 12px; }
  .brand-logo .brand-mark { width: 40px; height: 40px; font-size: 17px; }
  .brand-meta { text-align: left; }
  .hero { padding: 18px 16px; }
  .hero h1 { font-size: 21px; }
  .hero-row { flex-direction: column; }
  .card, .abschnitt-card { padding: 16px 14px; }
  h2 { font-size: 17px; margin-top: 22px; }
  table:not(.data-cards) { font-size: 13.5px; }
  table:not(.data-cards) thead th, table:not(.data-cards) tbody td { padding: 9px 10px; }
  .signature-row { grid-template-columns: 1fr; }
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .role-grid { grid-template-columns: 1fr; }
}
@media (max-width: 420px) {
  .kpi-row { grid-template-columns: 1fr; }
  .hero-grid { grid-template-columns: 1fr 1fr; }
}
"""


# Branded top-bar — rendered with project meta and injected into the context
# as ``brand_bar`` so all templates can use ``{{ brand_bar | safe }}`` instead
# of duplicating the markup.
BRAND_BAR_TEMPLATE = """
<div class="brand-bar">
  <div class="brand-inner">
    <div class="brand-logo">
      <div class="brand-mark">M</div>
      <div class="brand-text">
        <div class="brand-name">MITRA SANITÄR GmbH</div>
        <div class="brand-tag">Moderne Sanitär- und Heizungstechnik</div>
      </div>
    </div>
    <div class="brand-meta">
      <div><strong>Projekt-Nr.</strong> {{ project.slug }}</div>
      <div>Stand: {{ today | de_date }}</div>
    </div>
  </div>
</div>
"""

# Page footer — small print line at the very bottom of every document.
PAGE_FOOTER_TEMPLATE = """
<div class="page-footer">
  <div>
    <strong>Mitra Sanitär GmbH</strong> · Tradition trifft Innovation
  </div>
  <div>Projekt {{ project.slug }} · Erstellt {{ today | de_date }}</div>
</div>
"""


def _render_string(template_str: str, ctx: dict) -> str:
    return _env.from_string(template_str).render(**ctx)


# Auto-injected before </body> on every render so that clicking from one
# template to the next carries the ?token=... query forward — saves the user
# from re-pasting JWTs while browsing the document set. Skipped if the URL
# has no ?token at all (i.e. when called via a future auth-cookie route).
_TOKEN_PROPAGATION_SCRIPT = """<script>
(function(){
  var t = new URLSearchParams(window.location.search).get('token');
  if (!t) return;
  // Token an alle internen API-Links anhängen (templates, outputs, sonstiges)
  var SELECTORS = [
    'a[href^="/api/templates/"]',
    'a[href^="/api/projects/"]',
    'a[href$=".html"]',
  ];
  SELECTORS.forEach(function(sel){
    document.querySelectorAll(sel).forEach(function(a){
      var h = a.getAttribute('href');
      if (!h || h.indexOf('http') === 0 || h.indexOf('token=') >= 0) return;
      a.setAttribute('href', h + (h.indexOf('?')<0?'?':'&') + 'token=' + encodeURIComponent(t));
    });
  });
})();
</script>"""


_BACK_BUTTON_HTML = """
<style>
.sheet-back-bar {
  position: fixed; top: 0; left: 0; right: 0; z-index: 9998;
  display: flex; align-items: center; gap: 12px;
  padding: 10px 18px;
  background: rgba(28, 50, 68, 0.95);
  color: #fff;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  font-size: 14px; font-weight: 600;
  box-shadow: 0 2px 8px rgba(0,0,0,0.18);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.sheet-back-bar button, .sheet-back-bar a {
  display: inline-flex; align-items: center; gap: 6px;
  min-height: 36px; padding: 0 14px;
  background: rgba(255, 255, 255, 0.14);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.22);
  border-radius: 8px;
  font: inherit; cursor: pointer; text-decoration: none;
  transition: background 0.12s;
}
.sheet-back-bar button:hover, .sheet-back-bar a:hover {
  background: rgba(255, 255, 255, 0.24);
}
.sheet-back-bar .sheet-title {
  flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  opacity: 0.85; font-weight: 500; font-size: 13px;
}
body { padding-top: 56px !important; }
@media (max-width: 480px) {
  .sheet-back-bar { padding: 8px 12px; font-size: 13px; }
  .sheet-back-bar button, .sheet-back-bar a { padding: 0 10px; min-height: 32px; }
  .sheet-back-bar .sheet-title { display: none; }
  body { padding-top: 48px !important; }
}
@media print {
  .sheet-back-bar { display: none !important; }
  body { padding-top: 0 !important; }
}
</style>
<div class="sheet-back-bar" role="banner">
  <button type="button" onclick="(function(){
    var ref = document.referrer;
    var t = new URLSearchParams(window.location.search).get('token');
    var origin = window.location.origin;
    // Wenn die Referrer-URL aus unserer App kommt: history.back()
    if (ref && ref.indexOf(origin) === 0) { window.history.back(); return; }
    // Sonst: zurück zur Projekt-Detail-View (Slug aus URL extrahieren)
    var m = window.location.pathname.match(/\\/projects\\/([^/]+)/);
    if (m) { window.location.href = origin + '/projects/' + m[1] + (t ? '?token=' + encodeURIComponent(t) : ''); return; }
    window.location.href = origin + (t ? '/?token=' + encodeURIComponent(t) : '/');
  })();" aria-label="Zurück zur App">← Zurück</button>
  <span class="sheet-title" id="sheet-back-bar-title"></span>
  <button type="button" onclick="window.print()" title="Drucken" aria-label="Drucken">🖨</button>
</div>
<script>(function(){ var t = document.getElementById('sheet-back-bar-title'); if (t) t.textContent = document.title || ''; })();</script>
"""


def _inject_back_bar_and_scripts(html: str) -> str:
    """Inject Back-Button (oben fixiert) + Token-Propagation + AJAX-Form-Handler.

    Reihenfolge im HTML:
      <body>[INSERTED: back-bar] ... [INSERTED before </body>: scripts] </body>
    """
    if "</body>" not in html:
        return html
    # Back-Bar nach <body> einsetzen
    body_open_idx = html.lower().find("<body")
    if body_open_idx >= 0:
        body_tag_end = html.find(">", body_open_idx) + 1
        html = html[:body_tag_end] + _BACK_BUTTON_HTML + html[body_tag_end:]
    return html.replace("</body>", _TOKEN_PROPAGATION_SCRIPT + _INLINE_FORM_SCRIPT + "</body>", 1)


def _inject_token_script(html: str) -> str:
    """Legacy-Alias — ruft die neue Funktion auf."""
    return _inject_back_bar_and_scripts(html)


# Generic AJAX form-submit handler — any <form data-api-post="…"> or
# <button data-api-delete="…"> is intercepted, sent as JSON with the
# Bearer token from the URL, and reloads the page on success. Keeps the
# templates free of inline JavaScript and works across all CRUD-driven
# documents (Blocker, Material, Risiken, Teamstatus, Abschnittsplanung).
_INLINE_FORM_SCRIPT = """<script>
(function(){
  var token = new URLSearchParams(window.location.search).get('token');
  if (!token) return;

  function flash(msg, ok) {
    var b = document.createElement('div');
    b.textContent = msg;
    b.style.cssText = 'position:fixed;top:20px;right:20px;padding:12px 18px;border-radius:8px;color:#fff;z-index:9999;font-family:Inter,sans-serif;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,0.2);background:' + (ok ? '#1d6b35' : '#9b2129');
    document.body.appendChild(b);
    setTimeout(function(){ b.remove(); }, 2400);
  }

  function collectForm(form) {
    var data = {};
    Array.prototype.forEach.call(form.querySelectorAll('input,select,textarea'), function(el){
      if (!el.name) return;
      var v = el.value;
      if (el.type === 'checkbox') v = el.checked;
      else if (el.type === 'number') v = v === '' ? null : parseFloat(v);
      else if (el.type === 'date' || el.type === 'time' || el.type === 'week') v = v || null;
      else if (v === '') v = null;
      data[el.name] = v;
    });
    return data;
  }

  document.addEventListener('submit', function(ev){
    var form = ev.target;
    var url = form.getAttribute('data-api-post') || form.getAttribute('data-api-put') || form.getAttribute('data-api-patch');
    if (!url) return;
    ev.preventDefault();
    var method = form.hasAttribute('data-api-put') ? 'PUT' : (form.hasAttribute('data-api-patch') ? 'PATCH' : 'POST');
    fetch(url, {
      method: method,
      headers: {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
      body: JSON.stringify(collectForm(form))
    }).then(function(r){
      if (r.ok) { flash('Gespeichert', true); setTimeout(function(){ window.location.reload(); }, 400); }
      else r.text().then(function(t){ flash('Fehler ' + r.status + ': ' + t.slice(0,140), false); });
    }).catch(function(e){ flash('Netzwerkfehler: ' + e.message, false); });
  }, true);

  document.addEventListener('click', function(ev){
    var btn = ev.target.closest('[data-api-delete]');
    if (!btn) return;
    ev.preventDefault();
    if (!confirm(btn.getAttribute('data-confirm') || 'Eintrag wirklich löschen?')) return;
    fetch(btn.getAttribute('data-api-delete'), {
      method: 'DELETE',
      headers: {'Authorization': 'Bearer ' + token}
    }).then(function(r){
      if (r.ok) { flash('Gelöscht', true); setTimeout(function(){ window.location.reload(); }, 400); }
      else r.text().then(function(t){ flash('Fehler ' + r.status + ': ' + t.slice(0,140), false); });
    }).catch(function(e){ flash('Netzwerkfehler: ' + e.message, false); });
  }, true);
})();
</script>"""


class TemplateNotFoundError(LookupError):
    """Raised when a requested template slug does not exist in the DB."""


class ProjectNotFoundError(LookupError):
    """Raised when a requested project slug does not exist."""


_env = Environment(
    autoescape=select_autoescape(default_for_string=True, default=True),
    trim_blocks=True,
    lstrip_blocks=True,
    # Missing keys render as empty/marker; we surface "fehlt" in templates
    # explicitly rather than crashing on every typo.
    undefined=StrictUndefined,
)


def _fmt_de_date(value: date | datetime | str | None) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime("%d.%m.%Y")


def _fmt_hours(value: float | int | None) -> str:
    if value is None:
        return ""
    if value == int(value):
        return f"{int(value):,}".replace(",", ".") + " h"
    return f"{value:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".") + " h"


def _missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _fmt_bullets(value: str | None) -> Markup:
    """Wandelt Mehrzeilen-Text mit ``- ``-Bindestrichen in eine HTML-Liste.

    - Wenn mindestens eine Zeile mit ``- `` oder ``* `` beginnt: ``<ul><li>…</li></ul>``
    - Sonst: jede Zeile mit ``<br>`` getrennt
    - Leer/None → ``—``
    Auto-escape sicher: alle Werte werden zuerst escaped.
    """
    if value is None:
        return Markup("—")
    text = str(value).strip()
    if not text:
        return Markup("—")
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    bullet_lines = [ln for ln in lines if ln.lstrip().startswith(("-", "*", "•"))]
    if bullet_lines and len(bullet_lines) >= max(2, len(lines) // 2):
        items = []
        for ln in lines:
            stripped = ln.lstrip()
            if stripped.startswith(("-", "*", "•")):
                stripped = stripped[1:].lstrip()
            items.append(f"<li>{_html_escape(stripped)}</li>")
        return Markup("<ul class=\"goal-list\">" + "".join(items) + "</ul>")
    return Markup("<br>".join(_html_escape(ln) for ln in lines))


_env.filters["de_date"] = _fmt_de_date
_env.filters["hours"] = _fmt_hours
_env.filters["bullets"] = _fmt_bullets
_env.tests["missing"] = _missing


@dataclass(frozen=True)
class RenderResult:
    html: str
    open_points: list[str]
    template_slug: str
    template_version: int


def list_templates(db: Session) -> list[DocumentTemplate]:
    return (
        db.query(DocumentTemplate)
        .order_by(DocumentTemplate.category, DocumentTemplate.title)
        .all()
    )


def get_template(db: Session, slug: str) -> DocumentTemplate:
    template = db.query(DocumentTemplate).filter(DocumentTemplate.slug == slug).first()
    if template is None:
        raise TemplateNotFoundError(slug)
    return template


def _section_schedule(
    project: Project,
    sections_data: list[dict[str, Any]],
    overrides: dict[int, "SectionSchedule"] | None = None,
) -> list[dict[str, Any]]:
    """Derive start/end per section. If a SectionSchedule row exists for a
    section, its concrete dates take precedence — the rest are still derived
    from stundenanteil to keep the document complete."""
    overrides = overrides or {}

    def _maybe_override(section_id: int, derived_start, derived_end, duration_days):
        ov = overrides.get(section_id)
        if ov is None:
            return derived_start, derived_end, duration_days, False
        start = ov.start_date or derived_start
        end = ov.end_date or derived_end
        if start and end:
            duration_days = max(1, (end - start).days + 1)
        return start, end, duration_days, True

    if not (project.planned_start and project.planned_end and sections_data):
        result = []
        for s in sections_data:
            start, end, dur, has_override = _maybe_override(s.get("id"), None, None, None)
            result.append({**s, "derived_start": start, "derived_end": end, "duration_days": dur, "schedule_pinned": has_override})
        return result

    total_days = (project.planned_end - project.planned_start).days or 1
    total_hours = sum(float(s["planned_hours"] or 0) for s in sections_data)
    if total_hours <= 0:
        # Fall back to equal split.
        slice_days = max(1, total_days // len(sections_data))
        result = []
        cursor = project.planned_start
        for i, s in enumerate(sections_data):
            end = (
                project.planned_end
                if i == len(sections_data) - 1
                else cursor.fromordinal(cursor.toordinal() + slice_days - 1)
            )
            start, end, dur, has_override = _maybe_override(s.get("id"), cursor, end, slice_days)
            result.append(
                {**s, "derived_start": start, "derived_end": end, "duration_days": dur, "schedule_pinned": has_override}
            )
            cursor = cursor.fromordinal(end.toordinal() + 1)
        return result

    result = []
    cursor = project.planned_start
    for i, s in enumerate(sections_data):
        share = float(s["planned_hours"] or 0) / total_hours if total_hours else 1 / len(sections_data)
        span = max(1, round(total_days * share))
        if i == len(sections_data) - 1:
            end = project.planned_end
        else:
            end = cursor.fromordinal(cursor.toordinal() + span - 1)
        start, end, dur, has_override = _maybe_override(s.get("id"), cursor, end, span)
        result.append(
            {**s, "derived_start": start, "derived_end": end, "duration_days": dur, "schedule_pinned": has_override}
        )
        cursor = cursor.fromordinal(end.toordinal() + 1)
    return result


def _build_project_context(db: Session, project_slug: str) -> dict[str, Any]:
    from app.db.orm_models import Offer  # avoid top-level circular import risk

    project = (
        db.query(Project)
        .options(
            selectinload(Project.sections).selectinload(ProjectSection.staff_members),
            selectinload(Project.heating_design).selectinload(HeatingDesign.circuits),
            selectinload(Project.offers).selectinload(Offer.items),
        )
        .filter(Project.slug == project_slug)
        .first()
    )
    if project is None:
        raise ProjectNotFoundError(project_slug)

    sections = []
    total_hours = 0.0
    for section in project.sections:
        staff_names: list[str] = []
        for link in section.staff_members:
            user = link.user
            if user is not None:
                staff_names.append(user.display_name or user.username)
        if section.staff:
            for chunk in str(section.staff).split(","):
                chunk = chunk.strip()
                if chunk and chunk not in staff_names:
                    staff_names.append(chunk)
        if section.planned_hours:
            total_hours += float(section.planned_hours)
        sections.append(
            {
                "id": section.id,
                "number": section.number,
                "name": section.name,
                "goal": section.goal,
                "planned_hours": section.planned_hours,
                "responsible": section.responsible,
                "staff_names": staff_names,
                "staff_joined": ", ".join(staff_names) if staff_names else None,
            }
        )

    duration_weeks: int | None = None
    if project.planned_start and project.planned_end:
        delta = (project.planned_end - project.planned_start).days
        duration_weeks = max(1, round(delta / 7))

    blockers = (
        db.query(Blocker)
        .filter(Blocker.project_id == project.id, Blocker.status == "open")
        .order_by(Blocker.section_number, Blocker.created_at)
        .all()
    )
    material = (
        db.query(MaterialIssue)
        .filter(MaterialIssue.project_id == project.id, MaterialIssue.status == "open")
        .order_by(MaterialIssue.section_number, MaterialIssue.created_at)
        .all()
    )

    heating = project.heating_design

    members = (
        db.query(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project.id)
        .order_by(ProjectMember.project_role, User.display_name)
        .all()
    )
    member_rows = [
        {
            "user_id": u.id,
            "role": m.project_role,
            "username": u.username,
            "display_name": u.display_name,
            "global_role": u.global_role,
        }
        for m, u in members
    ]

    upload_rows = [
        {
            "filename": up.filename,
            "content_type": up.content_type,
            "created_at": up.created_at,
        }
        for up in (
            db.query(ProjectUpload)
            .filter(ProjectUpload.project_id == project.id)
            .order_by(ProjectUpload.created_at.desc())
            .all()
        )
    ]

    template_index = [
        {"slug": t.slug, "title": t.title, "category": t.category}
        for t in list_templates(db)
    ]

    # Section schedule overrides — these turn the derived dates into the real
    # pinned dates wherever the user has filled them in.
    schedule_rows = (
        db.query(SectionSchedule)
        .join(ProjectSection, SectionSchedule.section_id == ProjectSection.id)
        .filter(ProjectSection.project_id == project.id)
        .all()
    )
    schedule_overrides = {r.section_id: r for r in schedule_rows}
    sections_with_schedule = _section_schedule(project, sections, schedule_overrides)

    # New domain rows (extendable lists, no longer hard-coded in templates).
    team_status_rows = (
        db.query(TeamStatusEntry, User)
        .join(User, TeamStatusEntry.user_id == User.id)
        .filter(TeamStatusEntry.project_id == project.id)
        .order_by(TeamStatusEntry.day.desc(), User.display_name)
        .all()
    )
    team_status_list = [
        {
            "id": t.id,
            "user_id": t.user_id,
            "display_name": u.display_name,
            "day": t.day,
            "status": t.status,
            "soll_hours": t.soll_hours,
            "ist_hours": t.ist_hours,
            "note": t.note,
        }
        for t, u in team_status_rows
    ]

    # Automatischer Teamstatus aus Tagesberichten + Attendees.
    # Jeder Anwesende erbt für seinen Tag den Bericht-Status.
    # Mehrere Berichte pro User/Tag (z.B. unterschiedliche Sections):
    # Worst-Case-Status gewinnt (red > yellow > green).
    status_rank = {"red": 3, "yellow": 2, "green": 1}
    auto_matrix: dict[tuple[int, date], dict] = {}
    auto_rows = (
        db.query(DailyReport, DailyReportAttendee, User)
        .join(DailyReportAttendee, DailyReportAttendee.daily_report_id == DailyReport.id)
        .join(User, DailyReportAttendee.user_id == User.id)
        .filter(DailyReport.project_id == project.id)
        .all()
    )
    for rep, att, usr in auto_rows:
        key = (att.user_id, rep.report_date)
        prev = auto_matrix.get(key)
        if prev is None or status_rank.get(rep.status, 0) > status_rank.get(prev["status"], 0):
            auto_matrix[key] = {
                "user_id": att.user_id,
                "display_name": usr.display_name or usr.username,
                "day": rep.report_date,
                "status": rep.status,
                "report_id": rep.id,
                "section_number": rep.section_number,
                "ist_hours": rep.ist_hours,
                "note": None,
                "soll_hours": None,
                "manual": False,
            }

    # Manuelle TeamStatusEntries überschreiben den Auto-Status.
    for t in team_status_list:
        auto_matrix[(t["user_id"], t["day"])] = {
            "user_id": t["user_id"],
            "display_name": t["display_name"],
            "day": t["day"],
            "status": t["status"],
            "ist_hours": t["ist_hours"],
            "soll_hours": t["soll_hours"],
            "note": t["note"],
            "manual": True,
        }

    # Pivot in Matrix-Form: Liste User + Liste Tage + Lookup-Dict
    member_rows_for_team = (
        db.query(ProjectMember, User)
        .join(User, ProjectMember.user_id == User.id)
        .filter(ProjectMember.project_id == project.id)
        .order_by(User.display_name)
        .all()
    )
    team_users = [
        {"user_id": m.user_id, "display_name": u.display_name or u.username, "project_role": m.project_role}
        for m, u in member_rows_for_team
    ]
    team_days_set = {entry["day"] for entry in auto_matrix.values()}
    team_days = sorted(team_days_set, reverse=True)[:30]  # letzte 30 Tage mit Daten
    team_status_matrix = {
        f"{e['user_id']}|{e['day']}": e for e in auto_matrix.values()
    }

    material_items_raw = (
        db.query(MaterialItem)
        .filter(MaterialItem.project_id == project.id)
        .order_by(MaterialItem.section_number, MaterialItem.kind, MaterialItem.name)
        .all()
    )
    # Offer-Info pro item_id (für Bulk-Reassign-Filter im Sheet)
    from app.db.orm_models import Offer as _Offer, OfferItem as _OfferItem
    _offer_link_rows = (
        db.query(_OfferItem.id, _Offer.id, _Offer.supplier_name, _Offer.offer_no, _Offer.source_file)
        .join(_Offer, _Offer.id == _OfferItem.offer_id)
        .filter(_Offer.project_id == project.id)
        .all()
    )
    _offer_by_item: dict[int, dict] = {
        oi_id: {"offer_id": o_id, "supplier_name": s, "offer_no": no, "source_file": sf}
        for oi_id, o_id, s, no, sf in _offer_link_rows
    }
    material_items = []
    for m in material_items_raw:
        offer_info = _offer_by_item.get(m.offer_item_id) if m.offer_item_id else None
        material_items.append({
            "id": m.id,
            "section_number": m.section_number,
            "kind": m.kind,
            "name": m.name,
            "soll_qty": m.soll_qty,
            "ist_qty": m.ist_qty,
            "unit": m.unit,
            "location": m.location,
            "status": m.status,
            "note": m.note,
            "offer_item_id": m.offer_item_id,
            "offer_id": offer_info["offer_id"] if offer_info else None,
            "offer_supplier": offer_info["supplier_name"] if offer_info else None,
            "offer_no": offer_info["offer_no"] if offer_info else None,
            "offer_source_file": offer_info["source_file"] if offer_info else None,
            "percent_done": (
                round((m.ist_qty or 0) / m.soll_qty * 100.0, 1)
                if m.soll_qty
                else None
            ),
            "remaining": (m.soll_qty - (m.ist_qty or 0)) if m.soll_qty is not None else None,
        })

    # Verbrauchs-Aggregate für Material-Status
    total_soll = sum((m.soll_qty or 0.0) for m in material_items_raw)
    total_ist = sum((m.ist_qty or 0.0) for m in material_items_raw)
    items_completed = sum(
        1 for m in material_items_raw
        if m.soll_qty is not None and m.ist_qty is not None and m.ist_qty >= m.soll_qty
    )
    material_summary = {
        "total_soll": total_soll,
        "total_ist": total_ist,
        "percent_done": round(total_ist / total_soll * 100.0, 1) if total_soll else None,
        "items_completed": items_completed,
        "items_total": len(material_items_raw),
    }

    # Letzte 15 Verbrauchsbuchungen (für Historie im Material-Sheet)
    usage_rows = (
        db.query(MaterialUsage, MaterialItem, User)
        .outerjoin(MaterialItem, MaterialUsage.material_item_id == MaterialItem.id)
        .outerjoin(User, MaterialUsage.user_id == User.id)
        .filter(MaterialUsage.project_id == project.id)
        .order_by(MaterialUsage.used_at.desc(), MaterialUsage.id.desc())
        .limit(15)
        .all()
    )
    material_usages_recent = [
        {
            "id": u.id,
            "material_item_id": u.material_item_id,
            "material_name": (mi.name if mi else "(gelöscht)"),
            "qty_used": u.qty_used,
            "unit": u.unit,
            "used_at": u.used_at,
            "section_number": u.section_number,
            "username": (usr.display_name or usr.username) if usr else None,
            "notes": u.notes,
        }
        for u, mi, usr in usage_rows
    ]

    risk_issues = [
        {
            "id": r.id,
            "section_number": r.section_number,
            "kind": r.kind,
            "description": r.description,
            "severity": r.severity,
            "responsible": r.responsible,
            "status": r.status,
            "due_date": r.due_date,
        }
        for r in (
            db.query(RiskIssue)
            .filter(RiskIssue.project_id == project.id)
            .order_by(RiskIssue.section_number, RiskIssue.created_at)
            .all()
        )
    ]

    # Project-Photos für Foto-Galerien (z.B. Übergabeprotokoll).
    photo_rows = (
        db.query(ProjectPhoto)
        .filter(ProjectPhoto.project_id == project.id)
        .order_by(ProjectPhoto.section_number.nulls_last(), ProjectPhoto.created_at)
        .all()
    )
    photos = [
        {
            "id": p.id,
            "section_number": p.section_number,
            "caption": p.caption,
            "filename": p.filename,
            "view_url": f"/api/projects/{project.slug}/photos/{p.id}/view",
            "annotated_url": (
                f"/api/projects/{project.slug}/photos/{p.id}/annotated"
                if p.annotated_path else None
            ),
            "taken_at": p.taken_at,
            "created_at": p.created_at,
        }
        for p in photo_rows
    ]
    photos_by_section: dict[int | None, list[dict[str, Any]]] = {}
    for ph in photos:
        photos_by_section.setdefault(ph["section_number"], []).append(ph)

    # Full blockers (not just open ones) for the dedicated blocker template.
    all_blockers = [
        {
            "id": b.id,
            "section_number": b.section_number,
            "description": b.description,
            "severity": b.severity,
            "status": b.status,
            "created_at": b.created_at,
        }
        for b in (
            db.query(Blocker)
            .filter(Blocker.project_id == project.id)
            .order_by(Blocker.status, Blocker.section_number, Blocker.created_at.desc())
            .all()
        )
    ]

    return {
        "project": {
            "slug": project.slug,
            "name": project.name,
            "project_type": project.project_type,
            "address": project.address,
            "client_name": project.client_name,
            "responsible": project.responsible,
            "construction_manager": project.construction_manager,
            "foreman": project.foreman,
            "planned_start": project.planned_start,
            "planned_end": project.planned_end,
            "duration_weeks": duration_weeks,
            "status": project.status,
        },
        "sections": sections_with_schedule,
        "members": member_rows,
        "uploads": upload_rows,
        "template_index": template_index,
        "team_status": team_status_list,
        "material_items": material_items,
        "material_summary": material_summary,
        "material_usages_recent": material_usages_recent,
        "team_users": team_users,
        "team_days": team_days,
        "team_status_matrix": team_status_matrix,
        "milestones": _list_milestones_render(db, project.id),
        "photos": photos,
        "photos_by_section": photos_by_section,
        "risk_issues": risk_issues,
        "all_blockers": all_blockers,
        "base_css": BASE_CSS,
        "brand_bar": "__BRAND_BAR_PLACEHOLDER__",
        "page_footer": "__PAGE_FOOTER_PLACEHOLDER__",
        "totals": {
            "section_count": len(sections),
            "planned_hours": total_hours if total_hours else None,
        },
        "blockers": [
            {
                "section_number": b.section_number,
                "description": b.description,
                "severity": b.severity,
            }
            for b in blockers
        ],
        "material_issues": [
            {
                "section_number": m.section_number,
                "description": m.description,
                "priority": m.priority,
            }
            for m in material
        ],
        "heating": {
            "system_type": heating.system_type if heating else None,
            "supply_temp_c": heating.supply_temp_c if heating else None,
            "return_temp_c": heating.return_temp_c if heating else None,
            "delta_t_k": heating.delta_t_k if heating else None,
            "pump_model": heating.pump_model if heating else None,
            "total_volume_flow_lph": heating.total_volume_flow_lph if heating else None,
            "circuit_count": len(heating.circuits) if heating else 0,
            "total_heat_load_kw": (
                round(
                    sum(c.heat_load_w or 0.0 for c in heating.circuits) / 1000.0,
                    2,
                )
                if heating and heating.circuits
                else None
            ),
            "total_volume_flow_lph_sum": (
                round(sum(c.volume_flow_lph or 0.0 for c in heating.circuits), 0)
                if heating and heating.circuits
                else None
            ),
            "total_area_sqm": (
                round(sum(c.area_sqm or 0.0 for c in heating.circuits), 1)
                if heating and heating.circuits
                else None
            ),
            "circuits": [
                {
                    "strand": c.strand,
                    "room": c.room,
                    "floor": c.floor,
                    "radiator_type": c.radiator_type,
                    "area_sqm": c.area_sqm,
                    "heat_load_w": c.heat_load_w,
                    "heat_load_kw": round(c.heat_load_w / 1000.0, 2) if c.heat_load_w else None,
                    "volume_flow_lph": c.volume_flow_lph,
                    "valve_preset": c.valve_preset,
                    "w_per_sqm": (
                        round(c.heat_load_w / c.area_sqm, 0)
                        if c.heat_load_w and c.area_sqm
                        else None
                    ),
                }
                for c in (heating.circuits if heating else [])
            ],
        },
        "offers": _build_offers_context(project.offers if project else []),
        "today": date.today(),
    }


def _build_offers_context(offers: list) -> dict[str, Any]:
    """Pack offers into a Jinja-friendly dict with summary totals.

    Note: keys are chosen to avoid collisions with Python ``dict`` methods
    that Jinja2 resolves before key access — e.g. ``items`` would conflict
    with ``dict.items()`` and resolve to the bound method instead of our
    list. Use ``positions`` / ``entries`` instead.
    """
    offer_list = []
    for offer in offers:
        positions = sorted(offer.items, key=lambda i: i.position_index)
        offer_list.append({
            "id": offer.id,
            "supplier_name": offer.supplier_name,
            "offer_no": offer.offer_no,
            "offer_date": offer.offer_date,
            "currency": offer.currency or "EUR",
            "total_net_eur": offer.total_net_eur,
            "total_gross_eur": offer.total_gross_eur,
            "vat_rate": offer.vat_rate,
            "source_type": offer.source_type,
            "source_file": offer.source_file,
            "position_count": len(positions),
            "positions": [
                {
                    "position_label": it.position_label,
                    "article_no": it.article_no,
                    "name": it.name,
                    "description": it.description,
                    "qty": it.qty,
                    "unit": it.unit,
                    "unit_price_net_eur": it.unit_price_net_eur,
                    "total_net_eur": it.total_net_eur,
                    "vat_rate": it.vat_rate,
                }
                for it in positions
            ],
        })
    radiator_keywords = ("heizk", "badheizk", " hk ", "radiator")
    radiator_positions = []
    for o in offer_list:
        for p in o["positions"]:
            text = f" {(p.get('name') or '')} {(p.get('description') or '')} ".lower()
            if any(kw in text for kw in radiator_keywords):
                radiator_positions.append({
                    "supplier_name": o["supplier_name"],
                    "offer_no": o["offer_no"],
                    **p,
                })

    return {
        "entries": offer_list,
        "count": len(offer_list),
        "total_net_eur": sum((o["total_net_eur"] or 0.0) for o in offer_list) or None,
        "total_position_count": sum(o["position_count"] for o in offer_list),
        "suppliers": sorted({o["supplier_name"] for o in offer_list if o["supplier_name"]}),
        "radiator_positions": radiator_positions,
    }


def _collect_open_points(ctx: dict[str, Any]) -> list[str]:
    """Surface the typical 'KI hat Daten nicht gefunden'-fields as a list
    the user actually sees in the rendered document. This is the answer to
    'der user soll sich nicht darum kümmern müssen, ob die KI was vergessen
    hat'."""
    points: list[str] = []
    project = ctx["project"]
    if _missing(project.get("address")):
        points.append("Bauvorhaben-Adresse")
    if _missing(project.get("responsible")):
        points.append("Projektverantwortlicher")
    if _missing(project.get("construction_manager")):
        points.append("Bauleitung")
    if _missing(project.get("foreman")):
        points.append("Obermonteur")
    if project.get("planned_start") is None:
        points.append("Geplanter Baubeginn")
    if project.get("planned_end") is None:
        points.append("Geplantes Bauende")
    if not ctx["sections"]:
        points.append("Bauabschnitte (keine angelegt)")
    else:
        for section in ctx["sections"]:
            if section.get("planned_hours") in (None, 0):
                points.append(f"Geplante Stunden für Abschnitt {section['number']} {section['name']}")
    return points


def _finalise(html: str, ctx: dict) -> str:
    # Brand-bar and page-footer are rendered separately so their own Jinja
    # expressions ({{ project.slug }}, {{ today }}) resolve cleanly even if
    # the document template author forgets to pass context through.
    brand = _render_string(BRAND_BAR_TEMPLATE, ctx)
    footer = _render_string(PAGE_FOOTER_TEMPLATE, ctx)
    html = html.replace("__BRAND_BAR_PLACEHOLDER__", brand)
    html = html.replace("__PAGE_FOOTER_PLACEHOLDER__", footer)
    return _inject_token_script(html)


def render(db: Session, slug: str, project_slug: str) -> RenderResult:
    template_row = get_template(db, slug)
    ctx = _build_project_context(db, project_slug)
    ctx["open_points"] = _collect_open_points(ctx)
    jinja_template = _env.from_string(template_row.html_template)
    html = jinja_template.render(**ctx)
    return RenderResult(
        html=_finalise(html, ctx),
        open_points=ctx["open_points"],
        template_slug=template_row.slug,
        template_version=template_row.version,
    )


def render_preview(db: Session, slug: str) -> RenderResult:
    """Render the template with empty placeholder data — for admins to
    inspect the layout before any project data exists."""
    template_row = get_template(db, slug)
    ctx: dict[str, Any] = {
        "project": {
            "slug": "PREVIEW",
            "name": "Vorschau – noch keine Projektdaten",
            "project_type": "standard",
            "address": None,
            "client_name": None,
            "responsible": None,
            "construction_manager": None,
            "foreman": None,
            "planned_start": None,
            "planned_end": None,
            "duration_weeks": None,
            "status": "draft",
        },
        "sections": [],
        "members": [],
        "uploads": [],
        "template_index": [
            {"slug": t.slug, "title": t.title, "category": t.category}
            for t in list_templates(db)
        ],
        "team_status": [],
        "material_items": [],
        "photos": [],
        "photos_by_section": {},
        "risk_issues": [],
        "all_blockers": [],
        "base_css": BASE_CSS,
        "brand_bar": "__BRAND_BAR_PLACEHOLDER__",
        "page_footer": "__PAGE_FOOTER_PLACEHOLDER__",
        "totals": {"section_count": 0, "planned_hours": None},
        "blockers": [],
        "material_issues": [],
        "heating": {
            "system_type": None,
            "supply_temp_c": None,
            "return_temp_c": None,
            "delta_t_k": None,
            "pump_model": None,
            "total_volume_flow_lph": None,
            "circuit_count": 0,
            "total_heat_load_kw": None,
            "total_volume_flow_lph_sum": None,
            "total_area_sqm": None,
            "circuits": [],
        },
        "offers": {
            "entries": [],
            "count": 0,
            "total_net_eur": None,
            "total_position_count": 0,
            "suppliers": [],
        },
        "today": date.today(),
    }
    ctx["open_points"] = _collect_open_points(ctx)
    jinja_template = _env.from_string(template_row.html_template)
    html = jinja_template.render(**ctx)
    return RenderResult(
        html=_finalise(html, ctx),
        open_points=ctx["open_points"],
        template_slug=template_row.slug,
        template_version=template_row.version,
    )
