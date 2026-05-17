"""Seed the remaining document templates.

Twelve templates derived from the existing storage/projects/hez-640/* HTMLs.
All use {{ base_css | safe }} from the renderer and pull from the existing
ORM models (Project, ProjectSection, ProjectMember, ProjectUpload,
HeatingDesign). Six documents are intentionally left out — the ones the
user has open structural questions about (Teamstatus, Abschnittsplanung,
Blocker, Hydraulischer Abgleich, Material&Werkzeug, Risiken&Mängel).

Revision ID: e2f5b8a1c907
Revises: d1e9a7b3c604
Create Date: 2026-05-16 22:25:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e2f5b8a1c907"
down_revision: Union[str, None] = "d1e9a7b3c604"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# 1. Start: index
# ---------------------------------------------------------------------------
START_INDEX = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ project.name }} – Projekt-Start</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>start_index</code></div>
<h1>{{ project.name }}</h1>
<p>Projekt-Nr.: <strong>{{ project.slug }}</strong> · {{ today | de_date }}</p>

<div class="kpi-row">
  <div class="kpi-card"><span class="kpi-value">{{ totals.section_count }}</span><span class="kpi-label">Abschnitte</span></div>
  <div class="kpi-card"><span class="kpi-value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }}{% else %}—{% endif %}</span><span class="kpi-label">Geplante Stunden</span></div>
  <div class="kpi-card"><span class="kpi-value">{% if project.duration_weeks %}~{{ project.duration_weeks }}{% else %}—{% endif %}</span><span class="kpi-label">Wochen</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ open_points | length }}</span><span class="kpi-label">Offene Punkte</span></div>
</div>

<section><h2>Bauabschnitte</h2>
{% if sections %}<table><thead><tr><th>Nr.</th><th>Bezeichnung</th><th>Std.</th><th>Verantwortlich</th></tr></thead><tbody>
{% for s in sections %}<tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td>{{ s.name }}</td>
<td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
<td>{{ s.responsible or '—' }}</td></tr>{% endfor %}
</tbody></table>{% else %}<p class="offener-punkt">Keine Abschnitte angelegt.</p>{% endif %}</section>

<section><h2>Schnellzugriff Dokumente</h2>
<ul class="nav-list">
{% set current_cat = namespace(name=None) %}
{% for t in template_index %}
{% if t.category != current_cat.name %}<li><span class="nav-category">{{ t.category }}</span></li>{% set current_cat.name = t.category %}{% endif %}
<li><a href="/api/templates/{{ t.slug }}/render/{{ project.slug }}">{{ t.title }}</a></li>
{% endfor %}
</ul></section>

{% if open_points %}<section><h2>Offene Punkte</h2><div class="offene-punkte-box"><ul>
{% for p in open_points %}<li>{{ p }}</li>{% endfor %}
</ul></div></section>{% endif %}
</body></html>
"""

# ---------------------------------------------------------------------------
# 2. Projekt-Navigation: auto-generierte Dokumentenliste
# ---------------------------------------------------------------------------
PROJEKT_NAVIGATION = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dokumenten-Navigation – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>projekt_navigation</code></div>
<h1>Dokumenten-Navigation</h1>
<p>Projekt: <strong>{{ project.name }}</strong> ({{ project.slug }}) · {{ template_index | length }} Vorlagen verfügbar</p>

<table>
<thead><tr><th>Bereich</th><th>Dokument</th><th>Slug</th><th>Aktion</th></tr></thead>
<tbody>
{% for t in template_index %}
<tr><td>{{ t.category }}</td><td>{{ t.title }}</td><td><code>{{ t.slug }}</code></td>
<td><a href="/api/templates/{{ t.slug }}/render/{{ project.slug }}">Öffnen</a> ·
<a href="/api/templates/{{ t.slug }}/preview">Leer-Vorschau</a></td></tr>
{% endfor %}
</tbody></table>

<p class="budget-note">Diese Liste pflegt sich selbst — sobald ein neues Template in der Datenbank angelegt wird, erscheint es hier ohne weiteres Zutun.</p>
</body></html>
"""

# ---------------------------------------------------------------------------
# 3. Allgemein: Kontakte
# ---------------------------------------------------------------------------
KONTAKTE = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kontakte – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>kontakte</code></div>
<h1>Kontakte</h1>
<p>Projekt: <strong>{{ project.name }}</strong> · Stand: {{ today | de_date }}</p>

<section><h2>Schlüsselrollen</h2>
<table class="stammdaten-table"><tbody>
<tr><th>Projektverantwortlich</th><td>{% if project.responsible is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.responsible }}{% endif %}</td></tr>
<tr><th>Bauleitung</th><td>{% if project.construction_manager is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.construction_manager }}{% endif %}</td></tr>
<tr><th>Obermonteur</th><td>{% if project.foreman is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.foreman }}{% endif %}</td></tr>
</tbody></table></section>

<section><h2>Projekt-Mitglieder</h2>
{% if members %}
<table><thead><tr><th>Rolle im Projekt</th><th>Name</th><th>Benutzer</th><th>Globale Rolle</th></tr></thead>
<tbody>
{% for m in members %}<tr><td>{{ m.role }}</td><td>{{ m.display_name }}</td><td><code>{{ m.username }}</code></td><td>{{ m.global_role }}</td></tr>{% endfor %}
</tbody></table>
{% else %}
<p class="offener-punkt">Noch keine Projekt-Mitglieder angelegt. Mitglieder werden über die Projekt-Verwaltung zugewiesen.</p>
{% endif %}</section>
</body></html>
"""

# ---------------------------------------------------------------------------
# 4. Projektleitung: Statusübersicht
# ---------------------------------------------------------------------------
STATUSUEBERSICHT = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Statusübersicht – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>statusuebersicht</code></div>
<h1>Statusübersicht</h1>
<p>{{ project.name }} · Projekt-Status: <span class="status-badge status-grey">{{ project.status }}</span> · {{ today | de_date }}</p>

<section><h2>Abschnitts-Status</h2>
{% if sections %}
<table><thead><tr><th>Nr.</th><th>Bezeichnung</th><th>Geplante Std.</th><th>Verantwortlich</th><th>Blocker</th><th>Material offen</th></tr></thead>
<tbody>
{% for s in sections %}
{% set blocker_count = blockers | selectattr('section_number', 'equalto', s.number) | list | length %}
{% set material_count = material_issues | selectattr('section_number', 'equalto', s.number) | list | length %}
<tr><td><span class="abschnitt-num">{{ s.number }}</span></td>
<td>{{ s.name }}</td>
<td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}—{% endif %}</td>
<td>{{ s.responsible or '—' }}</td>
<td>{% if blocker_count %}<span class="status-badge status-red">{{ blocker_count }}</span>{% else %}<span class="status-badge status-green">0</span>{% endif %}</td>
<td>{% if material_count %}<span class="status-badge status-yellow">{{ material_count }}</span>{% else %}<span class="status-badge status-green">0</span>{% endif %}</td>
</tr>
{% endfor %}
</tbody></table>
{% else %}<p class="offener-punkt">Keine Abschnitte angelegt.</p>{% endif %}</section>

<section><h2>Aktive Blocker</h2>
{% if blockers %}
<table><thead><tr><th>Abschnitt</th><th>Beschreibung</th><th>Schwere</th></tr></thead><tbody>
{% for b in blockers %}<tr><td>{{ b.section_number or '—' }}</td><td>{{ b.description }}</td><td>{{ b.severity }}</td></tr>{% endfor %}
</tbody></table>
{% else %}<p>Keine aktiven Blocker.</p>{% endif %}</section>

<section><h2>Offene Material-Themen</h2>
{% if material_issues %}
<table><thead><tr><th>Abschnitt</th><th>Beschreibung</th><th>Priorität</th></tr></thead><tbody>
{% for m in material_issues %}<tr><td>{{ m.section_number or '—' }}</td><td>{{ m.description }}</td><td>{{ m.priority }}</td></tr>{% endfor %}
</tbody></table>
{% else %}<p>Keine offenen Material-Themen.</p>{% endif %}</section>
</body></html>
"""

# ---------------------------------------------------------------------------
# 5. Projektleitung: Meilensteinplan
# ---------------------------------------------------------------------------
MEILENSTEINPLAN = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meilensteinplan – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>meilensteinplan</code></div>
<h1>Meilensteinplan</h1>
<p>{{ project.name }} · Projekt-Nr. {{ project.slug }}</p>

<table><thead><tr><th>Nr.</th><th>Meilenstein</th><th>Termin (abgeleitet)</th><th>Verantwortlich</th><th>Status</th></tr></thead>
<tbody>
<tr><td>M00</td><td>Projektstart</td>
<td>{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td>
<td>{{ project.responsible or '—' }}</td><td><span class="status-badge status-grey">geplant</span></td></tr>

{% for s in sections %}
<tr><td>M{{ '%02d' % loop.index }}</td>
<td>Abschluss Abschnitt {{ s.number }} – {{ s.name }}</td>
<td>{% if s.derived_end %}{{ s.derived_end | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td>
<td>{{ s.responsible or '—' }}</td>
<td><span class="status-badge status-grey">geplant</span></td></tr>
{% endfor %}

<tr class="budget-total"><td>M{{ '%02d' % (sections | length + 1) }}</td>
<td><strong>Projektabschluss / Übergabe</strong></td>
<td>{% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td>
<td>{{ project.responsible or '—' }}</td>
<td><span class="status-badge status-grey">geplant</span></td></tr>
</tbody></table>

<p class="budget-note">Termine pro Abschnitt sind aus Projektrahmen und Stundenanteil abgeleitet. Sobald die Abschnittsplanung gepflegt wird, ersetzen die echten Termine die Schätzung — automatisch in allen Dokumenten.</p>
</body></html>
"""

# ---------------------------------------------------------------------------
# 6. Projektleitung: Gantt-Übersicht
# ---------------------------------------------------------------------------
GANTT_UEBERSICHT = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gantt-Übersicht – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>gantt_uebersicht</code></div>
<h1>Gantt-Übersicht</h1>
<p>{{ project.name }} · {% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %} · {% if project.duration_weeks %}~{{ project.duration_weeks }} Wochen{% endif %}</p>

{% if sections and project.planned_start and project.planned_end %}
<table class="gantt-grid"><thead><tr>
<th style="width:36px;">Nr.</th><th style="width:160px;">Bezeichnung</th>
<th>Start</th><th>Ende</th><th>Dauer</th><th>Std.</th>
</tr></thead><tbody>
{% for s in sections %}
<tr>
<td><span class="abschnitt-num">{{ s.number }}</span></td>
<td>{{ s.name }}</td>
<td>{{ s.derived_start | de_date }}</td>
<td>{{ s.derived_end | de_date }}</td>
<td>~{{ s.duration_days }} Tage</td>
<td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}—{% endif %}</td>
</tr>
{% endfor %}
</tbody></table>

<section><h2>Balkenansicht (abschnittweise)</h2>
<table><thead><tr><th style="width:160px;">Abschnitt</th>
{% for s in sections %}<th style="text-align:center;">Abschnitt {{ s.number }}</th>{% endfor %}
</tr></thead><tbody>
{% for s in sections %}<tr>
<td>{{ s.name }}</td>
{% for o in sections %}
{% if o.number == s.number %}<td class="gantt-bar">~{{ s.duration_days }}d</td>{% else %}<td class="gantt-off">&nbsp;</td>{% endif %}
{% endfor %}
</tr>{% endfor %}
</tbody></table>
</section>

{% else %}
<p class="offener-punkt">Projektrahmen oder Abschnitte fehlen — Gantt kann nicht aufgebaut werden.</p>
{% endif %}
</body></html>
"""

# ---------------------------------------------------------------------------
# 7. Monteur: Wochenplan
# ---------------------------------------------------------------------------
WOCHENPLAN = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wochenplan – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>wochenplan</code></div>
<h1>Wochenplan</h1>
<p>{{ project.name }} · Stand: {{ today | de_date }}</p>

<table><thead><tr><th>Abschnitt</th><th>Personal</th><th>Mo</th><th>Di</th><th>Mi</th><th>Do</th><th>Fr</th></tr></thead>
<tbody>
{% for s in sections %}
<tr>
<td><strong>{{ s.number }} – {{ s.name }}</strong><br><span style="font-size:12px;color:#555;">{% if s.planned_hours %}{{ s.planned_hours | hours }}{% endif %}</span></td>
<td style="font-size:13px;">{{ s.staff_joined or '—' }}</td>
<td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td>
</tr>
{% endfor %}
</tbody></table>

<p class="budget-note">Mo–Fr-Zellen werden in der zukünftigen Wochenplanungs-Maske editierbar — der Wochenplan zeigt dann die geplanten Stunden je Tag.</p>
</body></html>
"""

# ---------------------------------------------------------------------------
# 8. Monteur: Ablaufplan Abschnitte
# ---------------------------------------------------------------------------
ABLAUFPLAN_ABSCHNITTE = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ablaufplan Abschnitte – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>ablaufplan_abschnitte</code></div>
<h1>Ablaufplan Abschnitte</h1>
<p>{{ project.name }}</p>

{% if sections %}
{% for s in sections %}
<section><h2>Abschnitt {{ s.number }} – {{ s.name }}</h2>
<table class="stammdaten-table"><tbody>
<tr><th>Leistungsziel</th><td>{{ s.goal or '—' }}</td></tr>
<tr><th>Geplante Stunden</th><td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
<tr><th>Verantwortlich</th><td>{{ s.responsible or '—' }}</td></tr>
<tr><th>Eingesetztes Personal</th><td>{{ s.staff_joined or '—' }}</td></tr>
<tr><th>Start (abgeleitet)</th><td>{% if s.derived_start %}{{ s.derived_start | de_date }}{% endif %}</td></tr>
<tr><th>Ende (abgeleitet)</th><td>{% if s.derived_end %}{{ s.derived_end | de_date }}{% endif %}</td></tr>
</tbody></table></section>
{% endfor %}
{% else %}
<p class="offener-punkt">Keine Abschnitte angelegt.</p>
{% endif %}
</body></html>
"""

# ---------------------------------------------------------------------------
# 9. Bauleitung: Detaillierter Ablaufplan
# ---------------------------------------------------------------------------
DETAILLIERTER_ABLAUFPLAN = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Detaillierter Ablaufplan – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>detaillierter_ablaufplan</code></div>
<h1>Detaillierter Ablaufplan</h1>
<p>{{ project.name }} · {% if project.planned_start %}Start {{ project.planned_start | de_date }}{% endif %} · {% if project.planned_end %}Ende {{ project.planned_end | de_date }}{% endif %}</p>

{% if sections %}
<table><thead><tr><th>Nr.</th><th>Bezeichnung</th><th>Leistungsziel</th><th>Std.</th><th>Start</th><th>Ende</th><th>Dauer</th></tr></thead>
<tbody>
{% for s in sections %}<tr>
<td><span class="abschnitt-num">{{ s.number }}</span></td>
<td>{{ s.name }}</td>
<td style="font-size:13px;">{{ s.goal or '—' }}</td>
<td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
<td>{% if s.derived_start %}{{ s.derived_start | de_date }}{% else %}—{% endif %}</td>
<td>{% if s.derived_end %}{{ s.derived_end | de_date }}{% else %}—{% endif %}</td>
<td>{% if s.duration_days %}~{{ s.duration_days }} Tage{% else %}—{% endif %}</td>
</tr>{% endfor %}
</tbody></table>
{% else %}
<p class="offener-punkt">Keine Abschnitte angelegt.</p>
{% endif %}

<p class="budget-note">Detail-Termine je Arbeitstag werden nach Migration der Termin-Domäne automatisch ergänzt — die hier abgeleiteten Werte basieren auf Stundenanteil am Gesamtprojekt.</p>
</body></html>
"""

# ---------------------------------------------------------------------------
# 10. Obermonteur: Checklisten
# ---------------------------------------------------------------------------
CHECKLISTEN = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Checklisten – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>checklisten</code></div>
<h1>Checklisten je Abschnitt</h1>
<p>{{ project.name }} · {{ today | de_date }}</p>

{% if sections %}
{% for s in sections %}
<section><h2>Abschnitt {{ s.number }} – {{ s.name }}</h2>
<p style="font-size:13px;color:#555;">Verantwortlich: <strong>{{ s.responsible or '—' }}</strong> · Personal: {{ s.staff_joined or '—' }}</p>
<table><thead><tr><th style="width:40px;">✓</th><th>Prüfpunkt</th><th>Bemerkung</th></tr></thead><tbody>
<tr><td>☐</td><td>Arbeitsbereich abgesichert, Wege freigehalten</td><td>&nbsp;</td></tr>
<tr><td>☐</td><td>Werkzeug und Material vollständig vor Ort</td><td>&nbsp;</td></tr>
<tr><td>☐</td><td>PSA (Helm, Brille, Handschuhe) angelegt</td><td>&nbsp;</td></tr>
<tr><td>☐</td><td>Anlagenstillstand mit Bauleitung abgestimmt</td><td>&nbsp;</td></tr>
<tr><td>☐</td><td>Leistungsziel erreicht: {{ s.goal or '—' }}</td><td>&nbsp;</td></tr>
<tr><td>☐</td><td>Sauberer Arbeitsplatz hinterlassen</td><td>&nbsp;</td></tr>
</tbody></table></section>
{% endfor %}
{% else %}
<p class="offener-punkt">Keine Abschnitte angelegt — Checklisten werden je Abschnitt aufgebaut.</p>
{% endif %}
</body></html>
"""

# ---------------------------------------------------------------------------
# 11. Bauleitung: Gefährdungsbeurteilung
# ---------------------------------------------------------------------------
GEFAEHRDUNGSBEURTEILUNG = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gefährdungsbeurteilung – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>gefaehrdungsbeurteilung</code></div>
<h1>Gefährdungsbeurteilung</h1>
<p>{{ project.name }} · erstellt am {{ today | de_date }}</p>

<table><thead><tr><th>Gefährdung</th>
{% for s in sections %}<th>Abschnitt {{ s.number }}</th>{% endfor %}
</tr></thead>
<tbody>
{% set hazards = [
  ('Heißes Wasser / Verbrühung beim Öffnen von Leitungen', 'Anlage drucklos und ausgekühlt, Auffangwanne, PSA'),
  ('Absturz / Stolperstellen in engen Schächten', 'Beleuchtung, Markierung, Aufräumen nach Arbeitsende'),
  ('Lasten beim Tragen von Heizkörpern/Rohren', 'Hebehilfen, zu zweit tragen, Rückenschulung'),
  ('Asbest / Altbau-Substanz', 'Vorab-Prüfung, bei Verdacht sofort Bauleitung'),
  ('Brandgefahr bei Pressen/Löten', 'Brandwache, Feuerlöscher griffbereit, Schweißerlaubnis'),
] %}
{% for hazard, _ in hazards %}
<tr><td>{{ hazard }}</td>
{% for s in sections %}<td style="text-align:center;"><span class="status-badge status-yellow">prüfen</span></td>{% endfor %}
</tr>
{% endfor %}
</tbody></table>

<h2>Maßnahmen-Übersicht</h2>
<ul>
{% for hazard, mitigation in hazards %}<li><strong>{{ hazard }}:</strong> {{ mitigation }}</li>{% endfor %}
</ul>

<div class="signature-row">
<div class="signature-box">{{ project.construction_manager or 'Bauleitung' }} · Datum: ____________</div>
<div class="signature-box">{{ project.foreman or 'Obermonteur' }} · Datum: ____________</div>
</div>
</body></html>
"""

# ---------------------------------------------------------------------------
# 12. Allgemein: Übergabeprotokoll
# ---------------------------------------------------------------------------
UEBERGABEPROTOKOLL = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Übergabeprotokoll – {{ project.name }}</title><style>{{ base_css | safe }}</style></head><body>
<div class="template-banner">Live-Vorschau aus Template <code>uebergabeprotokoll</code></div>
<h1>Übergabeprotokoll</h1>
<p>{{ project.name }} · {{ today | de_date }}</p>

<section><h2>Projektdaten</h2>
<table class="stammdaten-table"><tbody>
<tr><th>Projekt-Nr.</th><td>{{ project.slug }}</td></tr>
<tr><th>Auftraggeber</th><td>{{ project.responsible or '—' }}</td></tr>
<tr><th>Bauvorhaben</th><td>{% if project.address is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.address }}{% endif %}</td></tr>
<tr><th>Bauleitung</th><td>{{ project.construction_manager or '—' }}</td></tr>
<tr><th>Obermonteur</th><td>{{ project.foreman or '—' }}</td></tr>
<tr><th>Geplanter Zeitraum</th><td>{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</td></tr>
</tbody></table></section>

<section><h2>Übergebene Leistungen</h2>
<table><thead><tr><th style="width:40px;">✓</th><th>Abschnitt</th><th>Leistung</th><th>Bemerkung</th></tr></thead>
<tbody>
{% for s in sections %}<tr><td>☐</td><td><strong>{{ s.number }} – {{ s.name }}</strong></td><td>{{ s.goal or '—' }}</td><td>&nbsp;</td></tr>{% endfor %}
</tbody></table></section>

<section><h2>Anmerkungen / Mängel bei Übergabe</h2>
<div style="border:1px solid #1a1a1a; min-height:120px; padding:10px;">&nbsp;</div>
</section>

<div class="signature-row">
<div class="signature-box">Übergeber: {{ project.construction_manager or '____________' }}<br>Datum, Unterschrift</div>
<div class="signature-box">Übernehmer: ____________<br>Datum, Unterschrift</div>
</div>
</body></html>
"""


SEEDS = [
    ("start_index", "00_Start", "Projekt-Start (index)", "Landing-Seite mit Kennzahlen, Abschnitts-Tabelle und Direktlinks zu allen anderen Templates."),
    ("projekt_navigation", "00_Start", "Projekt-Navigation", "Auto-generierte Liste aller verfügbaren Dokument-Templates inkl. Render-/Preview-Links."),
    ("kontakte", "05_Allgemein", "Kontakte", "Schlüsselrollen aus dem Projekt + alle ProjectMember mit User-Daten."),
    ("statusuebersicht", "04_Projektleitung", "Statusübersicht", "Abschnitts-Status mit Blocker- und Material-Zähler aus den Domänen-Tabellen."),
    ("meilensteinplan", "04_Projektleitung", "Meilensteinplan", "Projektstart, Abschluss je Abschnitt, Projektabschluss — Termine aus Stundenanteil abgeleitet."),
    ("gantt_uebersicht", "04_Projektleitung", "Gantt-Übersicht", "Gantt-Tabelle und Balkenansicht; Lage und Dauer aus Stundenanteil berechnet."),
    ("wochenplan", "01_Monteur", "Wochenplan", "Mo–Fr-Raster je Abschnitt mit Personalzuordnung."),
    ("ablaufplan_abschnitte", "01_Monteur", "Ablaufplan Abschnitte", "Pro Abschnitt ein Detailblock mit Stunden, Verantwortlich, Personal, abgeleiteten Terminen."),
    ("detaillierter_ablaufplan", "03_Bauleitung", "Detaillierter Ablaufplan", "Tabellarischer Ablauf aller Abschnitte mit Stunden und abgeleiteten Terminen."),
    ("checklisten", "02_Obermonteur", "Checklisten", "Pro Abschnitt ein Prüf-Block mit Standard-Items (PSA, Sauberkeit, Leistungsziel)."),
    ("gefaehrdungsbeurteilung", "03_Bauleitung", "Gefährdungsbeurteilung", "Standard-Gefährdungs-Matrix je Abschnitt mit Maßnahmenliste und Unterschriftsfeldern."),
    ("uebergabeprotokoll", "05_Allgemein", "Übergabeprotokoll", "Projektdaten, Leistungs-Checkliste je Abschnitt, Mängel-Freitext, Unterschriften."),
]

TEMPLATES_HTML = {
    "start_index": START_INDEX,
    "projekt_navigation": PROJEKT_NAVIGATION,
    "kontakte": KONTAKTE,
    "statusuebersicht": STATUSUEBERSICHT,
    "meilensteinplan": MEILENSTEINPLAN,
    "gantt_uebersicht": GANTT_UEBERSICHT,
    "wochenplan": WOCHENPLAN,
    "ablaufplan_abschnitte": ABLAUFPLAN_ABSCHNITTE,
    "detaillierter_ablaufplan": DETAILLIERTER_ABLAUFPLAN,
    "checklisten": CHECKLISTEN,
    "gefaehrdungsbeurteilung": GEFAEHRDUNGSBEURTEILUNG,
    "uebergabeprotokoll": UEBERGABEPROTOKOLL,
}


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
    rows = []
    for slug, category, title, description in SEEDS:
        rows.append(
            {
                "slug": slug,
                "category": category,
                "title": title,
                "description": description,
                "html_template": TEMPLATES_HTML[slug],
                "data_schema": None,
                "version": 1,
            }
        )
    op.bulk_insert(document_templates, rows)


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for slug, *_ in SEEDS)
    op.execute(f"DELETE FROM document_templates WHERE slug IN ({slugs})")
