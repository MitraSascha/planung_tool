"""Seed the Projektübersicht document template.

First entry in the new ``document_templates`` table — converts the previously
generated ``PROJEKTLEITUNG_Projektuebersicht.html`` into a Jinja2 template
with slots for project, sections, totals and a dynamic open-points list.
This replaces the old "Codex generates a fresh HTML per run" flow for this
document.

Revision ID: c8a4d1e7b502
Revises: b7e2f9c4a1d0
Create Date: 2026-05-16 21:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c8a4d1e7b502"
down_revision: Union[str, None] = "b7e2f9c4a1d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TEMPLATE_HTML = r"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Projektübersicht – {{ project.name }}</title>
  <style>
    body { font-family: "DejaVu Sans", Arial, sans-serif; font-size: 16px; line-height: 1.4; color: #1a1a1a; background: #fff; max-width: 920px; margin: 0 auto; padding: 20px; }
    h1 { font-size: 24px; margin: 0 0 6px; }
    h2 { font-size: 19px; margin: 32px 0 10px; border-bottom: 2px solid #1a1a1a; padding-bottom: 4px; }
    p { margin: 6px 0; }
    .header-row { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin-bottom: 24px; }
    .briefkopf { border: 1px solid #aaa; border-radius: 4px; padding: 12px 16px; min-width: 200px; min-height: 80px; font-size: 14px; color: #555; flex: 1; }
    .bauvorhaben-adresse { text-align: right; font-size: 14px; line-height: 1.8; flex-shrink: 0; }
    .stammdaten-table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    .stammdaten-table th, .stammdaten-table td { border: 1px solid #1a1a1a; padding: 9px 13px; text-align: left; vertical-align: top; }
    .stammdaten-table th { background: #f0f0f0; font-weight: 700; width: 34%; }
    table { border-collapse: collapse; width: 100%; margin-top: 10px; }
    th, td { border: 1px solid #1a1a1a; padding: 9px 12px; text-align: left; vertical-align: top; }
    thead th { background: #1a1a1a; color: #fff; font-weight: 700; }
    tbody tr:nth-child(even) { background: #f7f7f7; }
    .abschnitt-num { display: inline-flex; align-items: center; justify-content: center; background: #1769aa; color: #fff; border-radius: 50%; width: 28px; height: 28px; font-weight: 700; font-size: 14px; flex-shrink: 0; }
    .budget-total { background: #dce8f8 !important; font-weight: 700; }
    .offener-punkt { color: #b14040; font-style: italic; }
    .budget-note { font-size: 13px; color: #555; margin-top: 8px; }
    .offene-punkte-box { border: 2px solid #e67c00; border-radius: 8px; padding: 16px 20px; background: #fff8f0; margin-top: 12px; }
    .offene-punkte-box ul { margin: 10px 0 0; padding-left: 22px; }
    .offene-punkte-box li { margin-bottom: 8px; }
    .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; margin-top: 12px; }
    .kpi-card { border: 1px solid #1769aa; border-radius: 8px; padding: 14px 20px; flex: 1; min-width: 140px; text-align: center; }
    .kpi-card .kpi-value { font-size: 26px; font-weight: 700; color: #1769aa; display: block; }
    .kpi-card .kpi-label { font-size: 13px; color: #555; }
    .template-banner { background: #1769aa; color: #fff; padding: 6px 12px; border-radius: 4px; display: inline-block; font-size: 12px; margin-bottom: 12px; }
    @media print { body { font-size: 11pt; max-width: none; padding: 0; } .template-banner { display: none !important; } }
    @media (max-width: 600px) { body { font-size: 17px; padding: 12px; } .header-row { flex-direction: column; } .bauvorhaben-adresse { text-align: left; } table { display: block; overflow-x: auto; } h1 { font-size: 20px; } h2 { font-size: 17px; } .kpi-row { flex-direction: column; } .kpi-card { min-width: auto; } }
  </style>
</head>
<body>

  <div class="template-banner">Live-Vorschau aus Template <code>projektuebersicht</code></div>

  <div class="header-row">
    <div class="briefkopf">
      <strong>Auftragnehmer</strong><br>
      &nbsp;
    </div>
    <div class="bauvorhaben-adresse">
      <strong>Bauvorhaben</strong><br>
      {% if project.address is missing %}<span class="offener-punkt">Adresse fehlt</span>{% else %}{{ project.address }}{% endif %}<br>
      <br>
      Datum:&nbsp;&nbsp;&nbsp;{{ today | de_date }}<br>
      Projekt-Nr.:&nbsp;{{ project.slug }}
    </div>
  </div>

  <h1>Projektübersicht – {{ project.name }}</h1>
  {% if project.responsible %}<p>Projektverantwortlich: <strong>{{ project.responsible }}</strong></p>{% endif %}

  <div class="kpi-row">
    <div class="kpi-card">
      <span class="kpi-value">{{ totals.section_count }}</span>
      <span class="kpi-label">Bauabschnitte</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }}{% else %}—{% endif %}</span>
      <span class="kpi-label">Geplante Stunden gesamt</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-value">{% if project.duration_weeks %}~{{ project.duration_weeks }} Wo.{% else %}—{% endif %}</span>
      <span class="kpi-label">Projektdauer</span>
    </div>
    <div class="kpi-card">
      <span class="kpi-value">{{ open_points | length }}</span>
      <span class="kpi-label">Offene Punkte</span>
    </div>
  </div>

  <section>
    <h2>Stammdaten</h2>
    <table class="stammdaten-table">
      <tbody>
        <tr><th>Projekt-Nummer</th><td>{{ project.slug }}</td></tr>
        <tr><th>Projekttyp</th><td>{{ project.project_type or '—' }}</td></tr>
        <tr><th>Bauvorhaben / Adresse</th><td>{% if project.address is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.address }}{% endif %}</td></tr>
        <tr><th>Projektverantwortlicher</th><td>{% if project.responsible is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.responsible }}{% endif %}</td></tr>
        <tr><th>Bauleitung</th><td>{% if project.construction_manager is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.construction_manager }}{% endif %}</td></tr>
        <tr><th>Obermonteur</th><td>{% if project.foreman is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.foreman }}{% endif %}</td></tr>
        <tr><th>Geplanter Baubeginn</th><td>{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
        <tr><th>Geplantes Bauende</th><td>{% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
        <tr><th>Projektdauer</th><td>{% if project.duration_weeks %}ca. {{ project.duration_weeks }} Wochen{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
        <tr><th>Geplante Stunden gesamt</th><td>{% if totals.planned_hours %}<strong>{{ totals.planned_hours | hours }}</strong>{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
      </tbody>
    </table>
  </section>

  <section>
    <h2>Bauabschnitte</h2>
    {% if sections %}
    <table>
      <thead>
        <tr>
          <th style="width:46px;">Nr.</th>
          <th style="width:140px;">Bezeichnung</th>
          <th>Leistungsziel</th>
          <th style="width:110px;">Geplante Std.</th>
          <th style="width:160px;">Verantwortlich</th>
          <th style="width:160px;">Eingesetztes Personal</th>
        </tr>
      </thead>
      <tbody>
        {% for section in sections %}
        <tr>
          <td><span class="abschnitt-num">{{ section.number }}</span></td>
          <td>{{ section.name }}</td>
          <td>{{ section.goal or '—' }}</td>
          <td>{% if section.planned_hours %}{{ section.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
          <td>{{ section.responsible or '—' }}</td>
          <td>{{ section.staff_joined or '—' }}</td>
        </tr>
        {% endfor %}
        {% if totals.planned_hours %}
        <tr class="budget-total">
          <td colspan="3"><strong>Gesamt</strong></td>
          <td><strong>{{ totals.planned_hours | hours }}</strong></td>
          <td colspan="2"></td>
        </tr>
        {% endif %}
      </tbody>
    </table>
    {% else %}
    <p class="offener-punkt">Noch keine Bauabschnitte angelegt.</p>
    {% endif %}
  </section>

  <section>
    <h2>Terminrahmen</h2>
    {% if sections %}
    <table>
      <thead>
        <tr>
          <th>Nr.</th>
          <th>Bezeichnung</th>
          <th>Geplanter Start</th>
          <th>Geplantes Ende</th>
        </tr>
      </thead>
      <tbody>
        {% for section in sections %}
        <tr>
          <td><span class="abschnitt-num">{{ section.number }}</span></td>
          <td>{{ section.name }}</td>
          <td class="offener-punkt">Termin-Feinplanung folgt</td>
          <td class="offener-punkt">Termin-Feinplanung folgt</td>
        </tr>
        {% endfor %}
        <tr class="budget-total">
          <td colspan="2"><strong>Projekt gesamt</strong></td>
          <td><strong>{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}—{% endif %}</strong></td>
          <td><strong>{% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}—{% endif %}</strong></td>
        </tr>
      </tbody>
    </table>
    <p class="budget-note">Hinweis: Termin-Feinplanung je Abschnitt wird in der Abschnittsplanung gepflegt und in diesem Dokument automatisch übernommen, sobald die Domäne migriert ist.</p>
    {% endif %}
  </section>

  <section>
    <h2>Offene Punkte</h2>
    {% if open_points %}
    <div class="offene-punkte-box">
      <strong>Folgende Angaben fehlen und sind noch zu ergänzen:</strong>
      <ul>
        {% for point in open_points %}
        <li>{{ point }}</li>
        {% endfor %}
      </ul>
    </div>
    {% else %}
    <p>Keine offenen Punkte – alle Pflichtangaben liegen vor.</p>
    {% endif %}
  </section>

</body>
</html>
"""


def upgrade() -> None:
    document_templates = sa.table(
        "document_templates",
        sa.column("slug", sa.String),
        sa.column("category", sa.String),
        sa.column("title", sa.String),
        sa.column("description", sa.Text),
        sa.column("html_template", sa.Text),
        sa.column("data_schema", sa.Text),
        sa.column("version", sa.Integer),
    )
    op.bulk_insert(
        document_templates,
        [
            {
                "slug": "projektuebersicht",
                "category": "04_Projektleitung",
                "title": "Projektübersicht",
                "description": (
                    "Stammdaten, Bauabschnitte, Terminrahmen und automatisch "
                    "ermittelte offene Punkte. Liest aus Project + "
                    "ProjectSection; ersetzt PROJEKTLEITUNG_Projektuebersicht.html."
                ),
                "html_template": TEMPLATE_HTML,
                "data_schema": None,
                "version": 1,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM document_templates WHERE slug = 'projektuebersicht'"
    )
