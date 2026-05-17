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

from jinja2 import Environment, StrictUndefined, select_autoescape
from sqlalchemy.orm import Session, selectinload

from app.db.orm_models import (
    Blocker,
    DocumentTemplate,
    HeatingDesign,
    MaterialIssue,
    MaterialItem,
    Project,
    ProjectMember,
    ProjectSection,
    ProjectUpload,
    RiskIssue,
    SectionSchedule,
    TeamStatusEntry,
    User,
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

/* ───── Tables ────────────────────────────────────────────────────── */
.table-wrap { overflow-x: auto; border-radius: var(--radius); box-shadow: var(--card-shadow); background: #fff; margin-top: 10px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
thead th {
  background: var(--brand-primary); color: #fff; font-weight: 600;
  text-align: left; padding: 11px 14px; font-size: 13px;
  text-transform: uppercase; letter-spacing: 0.4px;
}
tbody td { padding: 11px 14px; border-top: 1px solid var(--card-border); vertical-align: top; color: var(--text-dark); }
tbody tr:nth-child(even) td { background: #fafbfc; }
tbody tr:hover td { background: #f3f6fa; }

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
  font-family: inherit; font-size: 14px;
  padding: 9px 12px; border: 1px solid var(--card-border); border-radius: var(--radius-sm);
  width: 100%; background: #fff; color: var(--text-dark); transition: border-color 0.12s, box-shadow 0.12s;
}
input:focus, select:focus, textarea:focus { outline: none; border-color: var(--brand-accent); box-shadow: 0 0 0 3px rgba(239, 128, 78, 0.18); }
textarea { min-height: 84px; resize: vertical; }
input[type="checkbox"] { width: 18px; height: 18px; accent-color: var(--brand-accent); margin-right: 8px; vertical-align: middle; }
label { font-size: 13.5px; color: var(--brand-primary); font-weight: 500; display: block; margin-bottom: 4px; }
.field-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin: 12px 0; }

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
  thead th { background: #1c3244 !important; color: #fff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  .doc-badge.formular, .kpi-card { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  h1, h2, h3 { page-break-after: avoid; }
  a { color: var(--brand-primary); border: none; }
}

/* ───── Mobile ────────────────────────────────────────────────────── */
@media (max-width: 720px) {
  body { font-size: 15px; }
  .page-wrap { padding: 0 12px 40px; }
  .brand-bar { padding: 18px 0; margin-bottom: 18px; }
  .brand-bar .brand-inner { gap: 12px; }
  .brand-logo .brand-mark { width: 40px; height: 40px; font-size: 17px; }
  .brand-meta { text-align: left; }
  .hero { padding: 20px 18px; }
  .hero h1 { font-size: 21px; }
  .hero-row { flex-direction: column; }
  .card, .abschnitt-card { padding: 16px 16px; }
  h2 { font-size: 17px; margin-top: 22px; }
  table { font-size: 13.5px; }
  thead th, tbody td { padding: 9px 10px; }
  .signature-row { grid-template-columns: 1fr; }
  .kpi-row { grid-template-columns: repeat(2, 1fr); }
  .role-grid { grid-template-columns: 1fr; }
}
@media (max-width: 420px) {
  .kpi-row { grid-template-columns: 1fr; }
}
"""


# Branded top-bar — rendered with project meta and injected into the context
# as ``brand_bar`` so all templates can use ``{{ brand_bar | safe }}`` instead
# of duplicating the markup.
BRAND_BAR_TEMPLATE = """
<div class="brand-bar">
  <div class="brand-inner">
    <div class="brand-logo">
      <!-- TODO: Logo-Asset einsetzen. Solange Datei nicht da:
           <img src="/api/templates/_assets/logo.png" alt="Mitra Sanitär" style="height:48px;">
      -->
      <div class="brand-mark">M</div>
      <div class="brand-text">
        <div class="brand-name">MITRA SANITÄR GmbH</div>
        <div class="brand-tag">Moderne Sanitär- und Heizungstechnik</div>
      </div>
    </div>
    <div class="brand-meta">
      <!-- Firmen-Anschrift / Kontakt — sobald Daten geliefert, hier einsetzen:
           <div><strong>Mitra Sanitär GmbH</strong></div>
           <div>Musterstraße 12 · 12345 Berlin</div>
           <div>Tel. +49 (0)30 ... · info&#64;mitra-sanitaer.de</div>
      -->
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
    <strong>Mitra Sanitär GmbH</strong> ·
    <!-- TODO: Adresse + Kontakt + Steuer-Nr. nach Liefer-Logo eintragen -->
    Tradition trifft Innovation
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


def _inject_token_script(html: str) -> str:
    if "</body>" not in html:
        return html
    return html.replace("</body>", _TOKEN_PROPAGATION_SCRIPT + _INLINE_FORM_SCRIPT + "</body>", 1)


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


_env.filters["de_date"] = _fmt_de_date
_env.filters["hours"] = _fmt_hours
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

    material_items = [
        {
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
        }
        for m in (
            db.query(MaterialItem)
            .filter(MaterialItem.project_id == project.id)
            .order_by(MaterialItem.section_number, MaterialItem.kind, MaterialItem.name)
            .all()
        )
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
    return {
        "entries": offer_list,
        "count": len(offer_list),
        "total_net_eur": sum((o["total_net_eur"] or 0.0) for o in offer_list) or None,
        "total_position_count": sum(o["position_count"] for o in offer_list),
        "suppliers": sorted({o["supplier_name"] for o in offer_list if o["supplier_name"]}),
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
