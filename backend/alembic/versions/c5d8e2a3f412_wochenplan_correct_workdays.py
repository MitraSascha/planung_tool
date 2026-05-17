"""Wochenplan: korrekte Arbeitstage Mo–Fr in einer Tabelle, Standard-Arbeitszeiten.

Die vorherige Version trennte fälschlich nach „Wochenbeginn Mo–Mi" und
„Wochenende Do–Fr". Wochenende ist Sa+So. Plus: feste Arbeitszeit-Spalte
mit Mitra-Standard (Mo–Do 07:00–16:00 / 1 h Pause = 8 h; Fr 07:00–13:00
ohne Pause = 6 h; 38-h-Woche). Soll-Stunden im Soll/Ist-Vergleich sind
entsprechend vorbelegt.

Revision ID: c5d8e2a3f412
Revises: b9c3e6f8d211
Create Date: 2026-05-17 02:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d8e2a3f412"
down_revision: Union[str, None] = "b9c3e6f8d211"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WOCHENPLAN_HTML = r"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wochenplan Monteur – {{ project.name }}</title>
<style>{{ base_css | safe }}</style>
</head><body>
{{ brand_bar | safe }}
<div class="page-wrap">

<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Wochenplan Monteur</h1>
  <p class="hero-sub">{{ project.address or '—' }} · Auftraggeber {{ project.responsible or '—' }} · Projekt {{ project.slug }}</p>
</section>

<div class="note info">
  <strong>Arbeitszeit:</strong> Montag bis Donnerstag <strong>07:00 – 16:00 Uhr</strong> mit 1 Stunde flexibler Pause (= 8 h netto) ·
  Freitag <strong>07:00 – 13:00 Uhr</strong> ohne Pause (= 6 h netto) ·
  Wochenende: Sa + So frei · <strong>Wochensumme 38 h</strong>
</div>

<section class="card">
  <h2>1 · Wocheninfo</h2>
  <div class="field-row">
    <div><label>KW (Pflicht)</label><input type="week" required></div>
    <div><label>Monteur (Name)</label><input type="text" placeholder="{{ project.foreman or 'Name eintragen' }}" required></div>
    <div><label>Bauabschnitt diese Woche</label>
      <select required><option value="">— wählen —</option>
        {% for s in sections %}<option>Abschnitt {{ s.number }} – {{ s.name }}</option>{% endfor %}
      </select>
    </div>
    <div><label>Rückfragen an (Name / Telefon)</label><input type="text" placeholder="Bauleitung: {{ project.construction_manager or 'Name' }}"></div>
  </div>

  <details style="margin-top:14px;">
    <summary style="cursor:pointer;color:var(--brand-primary);font-weight:600;">Bauabschnitt-Ziele (Kurzreferenz)</summary>
    <div class="table-wrap" style="margin-top:10px;"><table>
      <thead><tr><th style="width:60px;">Nr.</th><th>Name</th><th>Ziel</th><th style="width:140px;">Geplante Stunden</th></tr></thead>
      <tbody>{% for s in sections %}<tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td>{{ s.name }}</td><td>{{ s.goal or '—' }}</td><td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% endif %}</td></tr>{% endfor %}</tbody>
    </table></div>
  </details>
</section>

<section class="card">
  <h2>2 · Tagesplanung Mo – Fr</h2>
  <div class="note info">Jede Zeile bietet Platz für bis zu 4 Aufgaben, Materialbedarf und Bemerkungen. Direkt in die Zellen tippen.</div>
  <div class="table-wrap"><table>
    <thead><tr>
      <th style="width:70px;">Tag</th>
      <th style="width:120px;">Arbeitszeit</th>
      <th>Aufgabe 1</th><th>Aufgabe 2</th><th>Aufgabe 3</th><th>Aufgabe 4</th>
      <th>Material­bedarf</th><th>Bemerkungen</th>
    </tr></thead>
    <tbody>
      <tr><td><strong>Mo</strong></td><td><small>07:00 – 16:00<br>1 h Pause · 8 h</small></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Di</strong></td><td><small>07:00 – 16:00<br>1 h Pause · 8 h</small></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Mi</strong></td><td><small>07:00 – 16:00<br>1 h Pause · 8 h</small></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Do</strong></td><td><small>07:00 – 16:00<br>1 h Pause · 8 h</small></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Fr</strong></td><td><small>07:00 – 13:00<br>keine Pause · 6 h</small></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
    </tbody>
  </table></div>
</section>

<section class="card">
  <h2>3 · Wochenabschluss</h2>
  <h3>Gesamtmaterial der KW</h3>
  <textarea placeholder="Alle Bestellungen/Abrufe der KW zusammengefasst"></textarea>
  <h3>Rückmeldung an Obermonteur</h3>
  <textarea placeholder="Offene Punkte / Rückmeldung an {{ project.foreman or 'Obermonteur' }}"></textarea>
  <h3>Soll-/Ist-Vergleich</h3>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:80px;">Tag</th><th style="width:110px;">Soll-Std.</th><th>Ist-Std.</th><th>Differenz / Grund</th></tr></thead>
    <tbody>
      <tr><td><strong>Mo</strong></td><td>8,0 h</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Di</strong></td><td>8,0 h</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Mi</strong></td><td>8,0 h</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Do</strong></td><td>8,0 h</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr><td><strong>Fr</strong></td><td>6,0 h</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
      <tr class="budget-total"><td><strong>Σ</strong></td><td><strong>38,0 h</strong></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>
    </tbody>
  </table></div>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Wochenziele nicht tageweise vorgeplant – mit Bauleitung {{ project.construction_manager or '—' }} abstimmen.</li>
    <li>Personaleinteilung nicht spezifiziert – Formular gilt für eingetragenen Monteur.</li>
    <li>Abweichende Arbeitszeiten (Überstunden, Feiertage) im Soll-Ist-Vergleich vermerken.</li>
  </ul>
</div>

{{ page_footer | safe }}
</div></body></html>
"""


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE document_templates SET html_template = :html, version = version + 1 "
            "WHERE slug = 'wochenplan'"
        ).bindparams(html=WOCHENPLAN_HTML)
    )


def downgrade() -> None:
    op.execute("UPDATE document_templates SET version = version - 1 WHERE slug = 'wochenplan'")
