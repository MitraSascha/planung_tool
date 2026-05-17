"""Refactor Projektübersicht-Template to use shared base_css.

Replaces the inline 80-line <style> block with {{ base_css | safe }}.
Bumps version to 2.

Revision ID: d1e9a7b3c604
Revises: c8a4d1e7b502
Create Date: 2026-05-16 22:05:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e9a7b3c604"
down_revision: Union[str, None] = "c8a4d1e7b502"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TEMPLATE_HTML_V2 = r"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Projektübersicht – {{ project.name }}</title>
  <style>{{ base_css | safe }}</style>
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
          <th>Start (abgeleitet)</th>
          <th>Ende (abgeleitet)</th>
          <th>Dauer</th>
        </tr>
      </thead>
      <tbody>
        {% for section in sections %}
        <tr>
          <td><span class="abschnitt-num">{{ section.number }}</span></td>
          <td>{{ section.name }}</td>
          <td>{% if section.derived_start %}{{ section.derived_start | de_date }}{% else %}<span class="offener-punkt">—</span>{% endif %}</td>
          <td>{% if section.derived_end %}{{ section.derived_end | de_date }}{% else %}<span class="offener-punkt">—</span>{% endif %}</td>
          <td>{% if section.duration_days %}~{{ section.duration_days }} Tage{% else %}—{% endif %}</td>
        </tr>
        {% endfor %}
        <tr class="budget-total">
          <td colspan="2"><strong>Projekt gesamt</strong></td>
          <td><strong>{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}—{% endif %}</strong></td>
          <td><strong>{% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}—{% endif %}</strong></td>
          <td><strong>{% if project.duration_weeks %}~{{ project.duration_weeks }} Wo.{% else %}—{% endif %}</strong></td>
        </tr>
      </tbody>
    </table>
    <p class="budget-note">Hinweis: Termine je Abschnitt sind aus Projektrahmen und Stundenanteil abgeleitet. Die Feinplanung wird künftig in der Abschnittsplanung gepflegt und in alle abhängigen Dokumente übernommen.</p>
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
    op.execute(
        sa.text(
            """
            UPDATE document_templates
            SET html_template = :html, version = 2
            WHERE slug = 'projektuebersicht'
            """
        ).bindparams(html=TEMPLATE_HTML_V2)
    )


def downgrade() -> None:
    # Roll back to v1 inline-CSS template — not reproduced here; consult
    # migration c8a4d1e7b502 if a real downgrade is ever needed.
    op.execute(
        "UPDATE document_templates SET version = 1 WHERE slug = 'projektuebersicht'"
    )
