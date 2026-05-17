"""Rebuild all 13 document templates with Mitra branding and rich content.

Replaces the minimal skeleton versions with Mitra-branded layouts (marine
blue + copper orange, Inter font, hero/card system, KPI rows, status
badges, signature blocks) and re-introduces the rich content the original
codex-generated HTMLs had: stammdaten, hinweise, risk matrix, scope lists,
work-logic explanations, signature blocks, etc.

DB-driven slots stay dynamic; standing static content (industry-standard
hazards, BGB §640 wording, work-logic explanations) is hard-coded because
it doesn't change per project. Six templates the user has open content
questions about (Teamstatus, Abschnittsplanung, Blocker, Hydraulik,
Material, Risiken) remain out of scope.

Revision ID: f3a8c2e6d109
Revises: e2f5b8a1c907
Create Date: 2026-05-16 23:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8c2e6d109"
down_revision: Union[str, None] = "e2f5b8a1c907"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_HEAD = r"""<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{TITLE}</title>
<style>{{ base_css | safe }}</style>
</head><body>
{{ brand_bar | safe }}
<div class="page-wrap">"""

_FOOT = r"""
{{ page_footer | safe }}
</div></body></html>"""


def _wrap(title_expr: str, body: str) -> str:
    return _HEAD.replace("{TITLE}", title_expr) + body + _FOOT


# ---------------------------------------------------------------------------
# 1. start_index — Projekt-Startseite mit Rollen-Cards + Schnellzugriff
# ---------------------------------------------------------------------------
START_INDEX = _wrap(
    "{{ project.name }} – Projektstart",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <div class="hero-row">
    <div>
      <h1>{{ project.name }}</h1>
      <p class="hero-sub">Heizungsmodernisierung · Projektstart und Dokumenten-Navigation</p>
    </div>
    <div>
      <span class="status-badge status-blue">Projekt {{ project.slug }}</span>
    </div>
  </div>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauvorhaben</span>
      <span class="value {% if project.address is missing %}offen{% endif %}">{{ project.address or 'Adresse fehlt' }}</span></div>
    <div class="item"><span class="label">Auftraggeber</span>
      <span class="value {% if project.responsible is missing %}offen{% endif %}">{{ project.responsible or 'Offen' }}</span></div>
    <div class="item"><span class="label">Geplanter Zeitraum</span>
      <span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}offen{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}offen{% endif %}</span></div>
    <div class="item"><span class="label">Stand</span>
      <span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<div class="kpi-row">
  <div class="kpi-card"><span class="kpi-value">{{ totals.section_count }}</span><span class="kpi-label">Bauabschnitte</span></div>
  <div class="kpi-card"><span class="kpi-value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }}{% else %}—{% endif %}</span><span class="kpi-label">Geplante Stunden</span></div>
  <div class="kpi-card"><span class="kpi-value">{% if project.duration_weeks %}~{{ project.duration_weeks }}{% else %}—{% endif %}</span><span class="kpi-label">Wochen Laufzeit</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ open_points | length }}</span><span class="kpi-label">Offene Punkte</span></div>
</div>

<section class="card">
  <h2>Rolle wählen</h2>
  <p class="hero-sub" style="margin-top:6px;">Direktzugriff auf die Dokumente Ihrer Rolle.</p>
  <div class="role-grid">
    <a class="role-card" href="/api/templates/wochenplan/render/{{ project.slug }}"><span class="role-tag">01 · Monteur</span><div class="role-title">Wochenplan &amp; Tagescheck</div><div class="role-desc">Tages-/Wochenplanung, Materialbedarf, Soll/Ist-Vergleich.</div></a>
    <a class="role-card" href="/api/templates/checklisten/render/{{ project.slug }}"><span class="role-tag">02 · Obermonteur</span><div class="role-title">Checklisten je Abschnitt</div><div class="role-desc">Prüfungen vor Beginn, während Ausführung und zum Abschluss.</div></a>
    <a class="role-card" href="/api/templates/detaillierter_ablaufplan/render/{{ project.slug }}"><span class="role-tag">03 · Bauleitung</span><div class="role-title">Detaillierter Ablaufplan</div><div class="role-desc">Gantt, Gewerke, Meilensteine und Materialliste je Abschnitt.</div></a>
    <a class="role-card" href="/api/templates/projektuebersicht/render/{{ project.slug }}"><span class="role-tag">04 · Projektleitung</span><div class="role-title">Projektübersicht</div><div class="role-desc">Stammdaten, Bauabschnitte, Terminrahmen, Budget.</div></a>
    <a class="role-card" href="/api/templates/kontakte/render/{{ project.slug }}"><span class="role-tag">05 · Allgemein</span><div class="role-title">Kontakte &amp; Übergaben</div><div class="role-desc">Projektbeteiligte, Kontaktdaten, Übergabeprotokoll.</div></a>
  </div>
</section>

<section class="card">
  <h2>Bauabschnitte im Projekt</h2>
  {% if sections %}
  <div class="table-wrap"><table>
    <thead><tr><th style="width:60px;">Nr.</th><th>Bezeichnung</th><th>Ziel</th><th style="width:140px;">Geplante Stunden</th></tr></thead>
    <tbody>
      {% for s in sections %}
      <tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td><strong>{{ s.name }}</strong></td><td>{{ s.goal or '—' }}</td>
      <td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
      {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="offener-punkt">Noch keine Bauabschnitte angelegt.</p>{% endif %}
</section>

<section class="card">
  <h2>Schnellzugriff Dokumente</h2>
  <ul class="nav-list">
  {% set current_cat = namespace(name=None) %}
  {% for t in template_index %}
    {% if t.category != current_cat.name %}
    <li class="nav-category">{{ t.category }}</li>
    {% set current_cat.name = t.category %}
    {% endif %}
    <li class="nav-item">→ <a href="/api/templates/{{ t.slug }}/render/{{ project.slug }}">{{ t.title }}</a></li>
  {% endfor %}
  </ul>
</section>

{% if open_points %}
<div class="note offen">
  <span class="note-title">Offene Punkte ({{ open_points | length }})</span>
  <ul>{% for p in open_points %}<li>{{ p }}</li>{% endfor %}</ul>
</div>
{% endif %}
""",
)


# ---------------------------------------------------------------------------
# 2. projekt_navigation — Dokumenten-Index, gruppiert nach Kategorie
# ---------------------------------------------------------------------------
PROJEKT_NAVIGATION = _wrap(
    "Projekt-Navigation – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Projekt-Navigation</h1>
  <p class="hero-sub">Vollständige Liste aller Dokumente, gruppiert nach Rollenordner.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projekt</span><span class="value">{{ project.name }}</span></div>
    <div class="item"><span class="label">Bauvorhaben</span><span class="value">{{ project.address or '—' }}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
    <div class="item"><span class="label">Dokumente</span><span class="value">{{ template_index | length }} verfügbar</span></div>
  </div>
</section>

<div class="kpi-row">
  <div class="kpi-card"><span class="kpi-value">{{ template_index | length }}</span><span class="kpi-label">Dokumente gesamt</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ template_index | selectattr('category', 'in', ['00_Start', '04_Projektleitung', '05_Allgemein']) | list | length }}</span><span class="kpi-label">Informationsseiten</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ template_index | selectattr('category', 'in', ['01_Monteur', '02_Obermonteur', '03_Bauleitung']) | list | length }}</span><span class="kpi-label">Baustellen-Dokumente</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ template_index | map(attribute='category') | unique | list | length }}</span><span class="kpi-label">Bereiche</span></div>
</div>

{% set current_cat = namespace(name=None) %}
{% for t in template_index %}
  {% if t.category != current_cat.name %}
    {% if current_cat.name is not none %}</tbody></table></div></section>{% endif %}
    <section class="card">
      <h2>{{ t.category }}</h2>
      <div class="table-wrap"><table><thead><tr><th>Dokument</th><th>Slug</th><th style="width:220px;">Aktion</th></tr></thead><tbody>
    {% set current_cat.name = t.category %}
  {% endif %}
  <tr><td><strong>{{ t.title }}</strong></td>
    <td><code>{{ t.slug }}</code></td>
    <td><a href="/api/templates/{{ t.slug }}/render/{{ project.slug }}">Öffnen</a> · <a href="/api/templates/{{ t.slug }}/preview">Leer-Vorschau</a></td>
  </tr>
{% endfor %}
{% if current_cat.name is not none %}</tbody></table></div></section>{% endif %}

<div class="note info">
  <strong>Selbstaktualisierend:</strong> Diese Liste pflegt sich von selbst. Sobald ein neues Template in der Datenbank angelegt wird, erscheint es hier automatisch.
</div>
""",
)


# ---------------------------------------------------------------------------
# 3. ablaufplan_abschnitte (Monteur) — pro Abschnitt eine Timeline-Card
# ---------------------------------------------------------------------------
ABLAUFPLAN_ABSCHNITTE = _wrap(
    "Monteur-Ablaufplan – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Monteur-Ablaufplan je Bauabschnitt</h1>
  <p class="hero-sub">{{ project.name }} · {{ project.address or 'Adresse offen' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Gesamtzeitraum</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Bauleitung</span><span class="value {% if project.construction_manager is missing %}offen{% endif %}">{{ project.construction_manager or 'Offen' }}</span></div>
    <div class="item"><span class="label">Obermonteur / vor Ort</span><span class="value {% if project.foreman is missing %}offen{% endif %}">{{ project.foreman or 'Offen' }}</span></div>
    <div class="item"><span class="label">Abschnittsreihenfolge</span><span class="value">{% for s in sections %}{{ s.number }} {{ s.name }}{% if not loop.last %}, {% endif %}{% endfor %}</span></div>
  </div>
</section>

<div class="note info">Dieser Plan zeigt die vorgesehene Reihenfolge und die Hauptarbeiten je Abschnitt. Exakte Tagestermine werden in der Abschnittsplanung gepflegt und automatisch übernommen.</div>

<h2>Ablauf nach Bauabschnitt</h2>
{% for s in sections %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3></div>
  <p class="abschnitt-meta">{{ s.goal or '—' }}</p>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:32%;">Wer</th><th>Was</th><th style="width:22%;">Wann</th><th style="width:110px;">Umfang</th></tr></thead>
    <tbody>
      <tr>
        <td><strong>Verantwortlich:</strong> {{ s.responsible or '—' }}<br><strong>Mitarbeit:</strong> {{ s.staff_joined or '—' }}</td>
        <td>{{ s.goal or 'Hauptleistung gemäß Leistungsverzeichnis' }}</td>
        <td>{% if s.derived_start %}{{ s.derived_start | de_date }} – {{ s.derived_end | de_date }}{% else %}<span class="offener-punkt">Termin offen</span>{% endif %}</td>
        <td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
      </tr>
    </tbody>
  </table></div>
</div>
{% endfor %}

<div class="note info">
  <strong>Arbeitslogik für die Baustelle:</strong>
  <ul>
    <li>Keller-Hauptleitungen zuerst – sie versorgen alle späteren Abschnitte.</li>
    <li>Erst nach Abschluss eines Strangs an die zugehörigen Wohnungen gehen.</li>
    <li>Heizkörper-Montage nur, wenn der Strang anschlussbereit und gespült ist.</li>
    <li>Fernwärmestation als Abschluss – schließt die Anlage hydraulisch.</li>
  </ul>
</div>

{% if open_points %}
<div class="note offen">
  <span class="note-title">Offene Punkte ({{ open_points | length }})</span>
  <ul>{% for p in open_points %}<li>{{ p }}</li>{% endfor %}</ul>
</div>
{% endif %}
""",
)


# ---------------------------------------------------------------------------
# 4. wochenplan (Monteur) — Wocheninfo + Mo-Mi/Do-Fr Tabellen + Abschluss
# ---------------------------------------------------------------------------
WOCHENPLAN = _wrap(
    "Wochenplan Monteur – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Wochenplan Monteur</h1>
  <p class="hero-sub">{{ project.address or '—' }} · Auftraggeber {{ project.responsible or '—' }} · Projekt {{ project.slug }}</p>
</section>

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
  <h3>Wochenbeginn: Montag bis Mittwoch</h3>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:70px;">Tag</th><th>Aufgabe 1</th><th>Aufgabe 2</th><th>Aufgabe 3</th><th>Aufgabe 4</th><th>Material­bedarf</th><th>Bemerkungen</th></tr></thead>
    <tbody>
      {% for day in ['Mo', 'Di', 'Mi'] %}<tr><td><strong>{{ day }}</strong></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>{% endfor %}
    </tbody>
  </table></div>
  <h3>Wochenende: Donnerstag bis Freitag</h3>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:70px;">Tag</th><th>Aufgabe 1</th><th>Aufgabe 2</th><th>Aufgabe 3</th><th>Aufgabe 4</th><th>Material­bedarf</th><th>Bemerkungen</th></tr></thead>
    <tbody>
      {% for day in ['Do', 'Fr'] %}<tr><td><strong>{{ day }}</strong></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>{% endfor %}
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
    <thead><tr><th style="width:80px;">Tag</th><th>Soll-Std.</th><th>Ist-Std.</th><th>Differenz / Grund</th></tr></thead>
    <tbody>{% for day in ['Mo','Di','Mi','Do','Fr'] %}<tr><td><strong>{{ day }}</strong></td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>{% endfor %}</tbody>
  </table></div>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Wochenziele nicht tageweise vorgeplant – mit Bauleitung {{ project.construction_manager or '—' }} abstimmen.</li>
    <li>Personaleinteilung nicht spezifiziert – Formular gilt für eingetragenen Monteur.</li>
    <li>Soll-Stunden nicht hinterlegt – Standardarbeitszeit mit Bauleitung klären.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 5. checklisten (Obermonteur) — 4 Abschnitt-Cards × 3 Sub-Sections
# ---------------------------------------------------------------------------
CHECKLISTEN = _wrap(
    "Checklisten Obermonteur – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Fachliche Checklisten – Obermonteur</h1>
  <p class="hero-sub">{{ project.address or '—' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Obermonteur</span><span class="value">{{ project.foreman or '—' }}</span></div>
    <div class="item"><span class="label">Geplanter Start</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Geplantes Ende</span><span class="value">{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
  </div>
</section>

<div class="kpi-row">
  {% for s in sections %}<div class="kpi-card"><span class="kpi-value">{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}—{% endif %}</span><span class="kpi-label">Abschnitt {{ s.number }} – {{ s.name }}</span></div>{% endfor %}
</div>

<div class="note info">Jeder Bauabschnitt hat drei kurze Teilprüfungen: <strong>vor Beginn</strong>, <strong>während der Ausführung</strong> und zum <strong>Abschluss</strong>. Häkchen setzen, Pflichtfelder ausfüllen.</div>

{% for s in sections %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3></div>
  <p class="abschnitt-meta"><strong>Ziel:</strong> {{ s.goal or '—' }} · <strong>Verantwortlich:</strong> {{ s.responsible or '—' }}</p>

  <h3>1. Vor Beginn</h3>
  <p><label><input type="checkbox"> Material vollständig bereitgestellt</label></p>
  <p><label><input type="checkbox"> Vorgelagerte Gewerke abgestimmt / freigegeben</label></p>
  <p><label><input type="checkbox"> Dämmung / Zubehör vor Ort</label></p>
  <div class="field-row">
    <div><label>Prüftermin festlegen *</label><input type="date" required></div>
    <div><label>Zuständig vor Ort *</label><input type="text" value="{{ s.responsible or '' }}" required></div>
    <div><label>Offene Freigabe / Blockade</label><input type="text" placeholder="z. B. Asbest-Probenahme ausstehend"></div>
  </div>

  <h3>2. Ausführung prüfen</h3>
  <p><label><input type="checkbox"> Hydraulik-Montage sauber, dicht, druckfest</label></p>
  <p><label><input type="checkbox"> Elektro-Abstand / Schutzklasse geprüft</label></p>
  <p><label><input type="checkbox"> Dämmungs-Stoß sauber, GEG-konform</label></p>
  <p><label><input type="checkbox"> Prüfdruck vorbereitet (DVGW-W 400)</label></p>
  <div class="field-row">
    <div><label>Prüfdruck Sollwert</label><input type="text" placeholder="z. B. 6 bar / 30 min"></div>
    <div><label>Kurzhinweis aus der Kontrolle</label><input type="text"></div>
  </div>

  <h3>3. Abschluss</h3>
  <p><label><input type="checkbox"> Prüfdruck gehalten</label></p>
  <p><label><input type="checkbox"> Sichtkontrolle abgeschlossen</label></p>
  <div class="field-row">
    <div><label>Status Abschnitt *</label>
      <select required><option value="">— wählen —</option><option>Frei</option><option>Mit Restpunkten</option><option>Gesperrt</option></select>
    </div>
    <div style="grid-column: span 2;"><label>Restpunkte oder Nacharbeit</label><textarea placeholder="Was muss noch erledigt werden?"></textarea></div>
  </div>
</div>
{% endfor %}

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Konkrete Prüfdruck-Sollwerte je Dimension fehlen – mit Bauleitung abstimmen.</li>
    <li>Anschlusspläne Pumpen / Regelung sind in den Quelldaten nicht hinterlegt.</li>
    <li>Dämmstärken je Rohrdimension – GEG-Vorgabe konkretisieren.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 6. detaillierter_ablaufplan (Bauleitung) — Gantt + Eckdaten je BA
# ---------------------------------------------------------------------------
DETAILLIERTER_ABLAUFPLAN = _wrap(
    "Detaillierter Ablaufplan – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Detaillierter Ablaufplan</h1>
  <p class="hero-sub">{{ project.address or '—' }} · Auftraggeber {{ project.responsible or '—' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projektverantwortlich</span><span class="value">{{ project.responsible or '—' }}</span></div>
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Obermonteur</span><span class="value">{{ project.foreman or '—' }}</span></div>
    <div class="item"><span class="label">Geplante Stunden gesamt</span><span class="value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }} · {{ totals.section_count }} BA{% else %}—{% endif %}</span></div>
    <div class="item"><span class="label">Planstart</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Planende</span><span class="value">{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
  </div>
</section>

<section class="card">
  <h2>Terminübersicht – Balkenplan</h2>
  {% if sections and project.planned_start and project.planned_end %}
  <div class="table-wrap"><table class="gantt-grid">
    <thead>
      <tr><th class="gantt-label">Abschnitt</th>
      {% for s in sections %}<th>BA {{ s.number }}</th>{% endfor %}
      <th>Stunden</th><th>Zeitraum</th></tr>
    </thead>
    <tbody>
    {% for s in sections %}
    <tr>
      <td class="gantt-label"><span class="abschnitt-num">{{ s.number }}</span> {{ s.name }}</td>
      {% for o in sections %}
        {% if o.number == s.number %}<td class="gantt-bar gantt-bar-{{ s.number }}">~{{ s.duration_days }} d</td>
        {% else %}<td class="gantt-off">&nbsp;</td>{% endif %}
      {% endfor %}
      <td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}—{% endif %}</td>
      <td>{% if s.derived_start %}{{ s.derived_start | de_date }} – {{ s.derived_end | de_date }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table></div>
  <p class="hero-sub" style="margin-top:12px;">Lage und Dauer aus Projektrahmen und Stundenanteil abgeleitet. Detail-Termine werden nach Migration der Termin-Domäne automatisch ergänzt.</p>
  {% else %}
  <div class="note offen"><span class="note-title">Projektrahmen oder Abschnitte fehlen</span></div>
  {% endif %}
</section>

{% for s in sections %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3></div>
  <table class="kv-table">
    <tr><th>Ziel</th><td>{{ s.goal or '—' }}</td></tr>
    <tr><th>Geplante Stunden</th><td>{% if s.planned_hours %}<strong>{{ s.planned_hours | hours }}</strong>{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
    <tr><th>Geplanter Zeitraum</th><td>{% if s.derived_start %}{{ s.derived_start | de_date }} – {{ s.derived_end | de_date }} (~{{ s.duration_days }} Tage){% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
    <tr><th>Verantwortlich</th><td>{{ s.responsible or '—' }}</td></tr>
    <tr><th>Personal</th><td>{{ s.staff_joined or '—' }}</td></tr>
  </table>

  <h3>Gewerke &amp; Hauptleistungen</h3>
  <p class="hero-sub">Detail-Leistungsverzeichnis (Demontagen, Neuverlegungen, Druckprüfungen, Dämmung) wird aus dem Angebot abgeleitet, sobald die Angebote-Domäne im Backend gepflegt ist.</p>

  <h3>Meilensteine</h3>
  <ol>
    <li>Vorbereitung &amp; Materialbereitstellung</li>
    <li>Hauptarbeiten gemäß Leistungsziel ausgeführt</li>
    <li>Druckprüfung / Funktionsprüfung bestanden</li>
    <li>Dämmung &amp; Sichtkontrolle abgeschlossen</li>
    <li>Abnahme &amp; Übergabe an Folgeabschnitt</li>
  </ol>
</div>
{% endfor %}

<div class="note offen">
  <span class="note-title">Offene Punkte (Gesamtprojekt)</span>
  <ul>
    <li>Tagestermine je Abschnitt verbindlich machen (Abschnittsplanung).</li>
    <li>Baugenehmigung / Mieterinformation koordinieren.</li>
    <li>Material-Artikelnummern und Mengen aus den Angeboten in eine Material-Domäne überführen.</li>
    <li>Übergabemappe und Heizlast-Endfassung vorbereiten.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 7. gefaehrdungsbeurteilung (Bauleitung) — Risiken + Schutzmaßnahmen + Unterweisung
# ---------------------------------------------------------------------------
GEFAEHRDUNGSBEURTEILUNG = _wrap(
    "Gefährdungsbeurteilung – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Gefährdungsbeurteilung / SiGe-Plan</h1>
  <p class="hero-sub">SHK-Heizungsmodernisierung – {{ project.address or 'Adresse offen' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projektverantwortlich</span><span class="value">{{ project.responsible or '—' }}</span></div>
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Gültig für Projektlaufzeit</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<div class="note info"><strong>Rechtliche Grundlage:</strong> § 5 ArbSchG, § 3 BetrSichV, DGUV Regel 100-500, BGV A1, TRGS 519 (Asbest), DIN EN ISO 9606 (Schweißen), ZVSHK. Risiken der Stufe „Hoch" sind durch die Bauleitung freizugeben.</div>

<section class="card">
  <h2>1 · Erkannte Risiken</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Risiko</th><th style="width:140px;">Stufe</th><th>Auftreten in Bauabschnitt</th></tr></thead>
    <tbody>
      <tr><td><strong>Enge Räume / Keller</strong><br><small>Sauerstoffmangel, Fluchtweg, CO-Belastung</small></td><td><span class="risiko-hoch">Hoch</span></td><td>BA 1</td></tr>
      <tr><td><strong>Heißarbeiten</strong> (Löten, Pressen)<br><small>Brandgefahr, Verbrennung</small></td><td><span class="risiko-hoch">Hoch</span></td><td>BA 1 · 2 · 3 · 4</td></tr>
      <tr><td><strong>Asbest-Verdacht</strong><br><small>Bei Altbau vor 1993 zwingend Probenahme</small></td><td><span class="risiko-hoch">Hoch</span></td><td>BA 1 · 2 · 3</td></tr>
      <tr><td><strong>Absturzgefahr</strong> (Leitern, Gerüst)</td><td><span class="risiko-mittel">Mittel</span></td><td>BA 2 · 3</td></tr>
      <tr><td><strong>Elektrische Gefährdung</strong></td><td><span class="risiko-mittel">Mittel</span></td><td>BA 4</td></tr>
      <tr><td><strong>Staub &amp; Lärm</strong> (Kernbohrungen, Stemmen)</td><td><span class="risiko-mittel">Mittel</span></td><td>BA 1 · 2 · 3</td></tr>
      <tr><td><strong>Schwere Lasten</strong> (Heizkörper, Station)</td><td><span class="risiko-mittel">Mittel</span></td><td>BA 3 · 4</td></tr>
      <tr><td><strong>Verbrühungsgefahr</strong> (Heizwasser)</td><td><span class="risiko-mittel">Mittel</span></td><td>BA 1 · 4</td></tr>
      <tr><td><strong>Schnitt- / Verletzungsgefahr</strong></td><td><span class="risiko-gering">Gering</span></td><td>Alle Abschnitte</td></tr>
    </tbody>
  </table></div>
  <div class="note warn"><strong>Hinweis:</strong> Risiken mit „Hoch" sind branchenüblich für SHK. Bei Baujahr unbekannt ist eine Asbest-Probenahme vor Abbruch zwingend.</div>
</section>

<section class="card">
  <h2>2 · Schutzmaßnahmen</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Risiko</th><th>Schutzmaßnahme (PSA · Brandschutz · Lüftung · Organisation)</th><th style="width:160px;">Verantwortlich</th></tr></thead>
    <tbody>
      <tr><td>Enge Räume</td><td>10 min lüften, CO-Warngerät, Fluchtwege markieren, Zweimannregel, 30-min-Kommunikation, 200 lux Beleuchtung</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
      <tr><td>Heißarbeiten</td><td>Erlaubnisschein, Feuerlöscher ABC 6 kg &lt; 5 m, Lötmatte, Brandwache 60 min, Schutzbrille EN 169/407, 1 m Abstand</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
      <tr><td>Asbest</td><td>STOP-Regel, Labor vor Abbruch, Halbmaske P3 EN 143 + Anzug Typ 5/6, nass arbeiten, Entsorgung TRGS 519 / KrWG</td><td>{{ project.construction_manager or 'Bauleitung' }}</td></tr>
      <tr><td>Absturz</td><td>Leitern DGUV 208-016, Gurt + Anschlagpunkt ab 3 m, Gerüst ab 2 m, max. 150 kg, gegen Wegrutschen sichern</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
      <tr><td>Elektrisch</td><td>EFK, LOTO, Spannungsprüfer, schriftliche Dokumentation, Rückkopplung</td><td>{{ project.construction_manager or 'Bauleitung' }}</td></tr>
      <tr><td>Staub &amp; Lärm</td><td>FFP2-Maske, Kapselgehörschutz EN 352 ab 85 dB, Wasserring, H-Klasse Industriesauger, Mieter 24 h vorinformieren</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
      <tr><td>Schwere Lasten</td><td>max. 25 kg, Teamlift, Hubwagen, rückengerecht, Kran &gt; 100 kg</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
      <tr><td>Verbrühung</td><td>drucklos schalten, 0 bar öffnen, Handschuhe EN 407 Stufe 3, Warnschild, Erste-Hilfe-Kühlmaterial</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
      <tr><td>Schnitt</td><td>Handschuhe EN 388 Klasse 4, entgraten, täglich aufräumen, S3-Sicherheitsschuhe</td><td>{{ project.foreman or 'Obermonteur' }}</td></tr>
    </tbody>
  </table></div>
</section>

<section class="card">
  <h2>3 · Unterweisungsbestätigung der Mitarbeiter</h2>
  <p class="hero-sub">Alle eingesetzten Mitarbeiter bestätigen die Unterweisung. Handschriftlich oder digital.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Name</th><th style="width:160px;">Datum Unterweisung</th><th style="width:200px;">Unterschrift / Kürzel</th></tr></thead>
    <tbody>
      {% for n in range(6) %}<tr><td><input type="text" placeholder="Vor- und Nachname" required></td><td><input type="date" required></td><td><input type="text" placeholder="Kürzel / Unterschrift" required></td></tr>{% endfor %}
    </tbody>
  </table></div>
</section>

<section class="card">
  <h2>4 · Erstellung &amp; Freigabe</h2>
  <div class="field-row">
    <div><label>Datum Erstellung *</label><input type="date" required></div>
    <div><label>Verantwortliche Bauleitung *</label><input type="text" value="{{ project.construction_manager or '' }}" required></div>
  </div>
  <div class="signature-row">
    <div class="signature-box"><strong>Auftraggeber / Eigentümer</strong>Ort, Datum, Unterschrift</div>
    <div class="signature-box"><strong>Bauleitung / SHK-Unternehmen</strong>Ort, Datum, Unterschrift</div>
  </div>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Baujahr Bestandsanlage unbekannt – Schadstoffgutachten ausstehend.</li>
    <li>Elektrofachkraft für BA 4 noch festzulegen.</li>
    <li>Heißarbeitserlaubnisschein-Vordruck und CO-Warngeräte-Anzahl prüfen.</li>
    <li>Gerüstbedarf BA 2 abhängig von Stockwerksanzahl der Stränge.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 8. gantt_uebersicht (Projektleitung) — KW-Raster + Summary
# ---------------------------------------------------------------------------
GANTT_UEBERSICHT = _wrap(
    "Gantt-Übersicht – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Gantt-Übersicht</h1>
  <p class="hero-sub">{{ project.address or '—' }} · {{ project.responsible or '—' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projektstart</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Projektende</span><span class="value">{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Laufzeit</span><span class="value">{% if project.duration_weeks %}~{{ project.duration_weeks }} Wochen{% endif %}</span></div>
    <div class="item"><span class="label">Geplante Stunden</span><span class="value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }}{% endif %}</span></div>
    <div class="item"><span class="label">Bauabschnitte</span><span class="value">{{ totals.section_count }}</span></div>
    <div class="item"><span class="label">Projekttyp</span><span class="value">{{ project.project_type or '—' }}</span></div>
  </div>
</section>

<section class="card">
  <h2>Wochenraster – alle Bauabschnitte</h2>
  <div class="note info"><strong>Planungsstand:</strong> Wochenzuordnung ist aus Stundenanteil abgeleitet, exakte Termine werden in der Abschnittsplanung gepflegt.</div>
  {% if sections and project.planned_start and project.planned_end %}
  <div class="table-wrap"><table class="gantt-grid">
    <thead><tr><th class="gantt-label">Abschnitt</th>{% for s in sections %}<th>BA {{ s.number }}</th>{% endfor %}<th>Stunden</th></tr></thead>
    <tbody>
    {% for s in sections %}
    <tr>
      <td class="gantt-label"><span class="abschnitt-num">{{ s.number }}</span> {{ s.name }}<br><small>{{ s.derived_start | de_date }} – {{ s.derived_end | de_date }}</small></td>
      {% for o in sections %}{% if o.number == s.number %}<td class="gantt-bar gantt-bar-{{ s.number }}">~{{ s.duration_days }} d</td>{% else %}<td class="gantt-off">&nbsp;</td>{% endif %}{% endfor %}
      <td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="offener-punkt">Projektrahmen oder Abschnitte fehlen.</p>{% endif %}
</section>

<section class="card">
  <h2>Abschnitte – Kurzübersicht</h2>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:60px;">#</th><th>Abschnitt</th><th>Stunden</th><th>Zeitraum</th><th>Verantwortlich</th></tr></thead>
    <tbody>
    {% for s in sections %}
    <tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td><strong>{{ s.name }}</strong><br><small>{{ s.goal or '—' }}</small></td>
      <td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% endif %}</td>
      <td>{% if s.derived_start %}{{ s.derived_start | de_date }} – {{ s.derived_end | de_date }}{% endif %}</td>
      <td>{{ s.responsible or '—' }}</td></tr>
    {% endfor %}
    {% if totals.planned_hours %}<tr class="budget-total"><td colspan="2"><strong>Gesamt</strong></td><td><strong>{{ totals.planned_hours | hours }}</strong></td><td>{% if project.planned_start %}{{ project.planned_start | de_date }} – {{ project.planned_end | de_date }}{% endif %}</td><td></td></tr>{% endif %}
    </tbody>
  </table></div>
</section>

{% if open_points %}
<div class="note offen"><span class="note-title">Offene Punkte ({{ open_points | length }})</span><ul>{% for p in open_points %}<li>{{ p }}</li>{% endfor %}</ul></div>
{% endif %}
""",
)


# ---------------------------------------------------------------------------
# 9. meilensteinplan (PL) — Meilenstein-Tabelle mit Ist-Inputs
# ---------------------------------------------------------------------------
MEILENSTEINPLAN = _wrap(
    "Meilensteinplan – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Meilensteinplan</h1>
  <p class="hero-sub">{{ project.address or '—' }} · Projekt {{ project.slug }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Geplanter Start</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Geplantes Ende</span><span class="value">{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Planstand aktualisiert am *</span><input type="date" required></div>
    <div class="item"><span class="label">Bearbeitet von *</span><input type="text" required></div>
  </div>
</section>

<section class="card">
  <h2>Grundlage</h2>
  <p>Dieser Plan baut auf den im Projekt hinterlegten Bauabschnitten und dem Gesamt-Terminrahmen auf. Bei Abschnitten ohne hinterlegten Detailtermin gilt die abgeleitete Lage aus dem Stundenanteil.</p>
  <div class="kpi-row">
    {% for s in sections %}<div class="kpi-card"><span class="kpi-value">{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}—{% endif %}</span><span class="kpi-label">Abschnitt {{ s.number }} – {{ s.name }}</span></div>{% endfor %}
  </div>
</section>

<section class="card">
  <h2>Meilensteine</h2>
  <div class="note info">Soll-Termine ohne belastbare Abschnittsplanung sind als „offen" markiert. Ist-Termine und Status direkt ausfüllen.</div>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:54px;">Nr.</th><th>Meilenstein</th><th>Bezug / Ziel</th><th style="width:150px;">Verantwortlich</th><th style="width:140px;">Soll-Termin</th><th style="width:140px;">Ist-Termin</th><th style="width:140px;">Status</th></tr></thead>
    <tbody>
      <tr><td><strong>M01</strong></td><td>Projektstart erfolgt</td><td>Baustelle freigegeben und Arbeiten gestartet</td><td>{{ project.responsible or '—' }}</td>
        <td>{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
        <td><input type="date"></td>
        <td><select><option>Offen</option><option>In Arbeit</option><option>Erledigt</option><option>Verschoben</option></select></td></tr>
      {% for s in sections %}
      <tr><td><strong>M{{ '%02d' % (loop.index + 1) }}</strong></td><td>Abschnitt {{ s.number }} abgeschlossen</td>
        <td>{{ s.goal or s.name }}</td><td>{{ s.responsible or '—' }}</td>
        <td>{% if s.derived_end %}{{ s.derived_end | de_date }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
        <td><input type="date"></td>
        <td><select><option>Offen</option><option>In Arbeit</option><option>Erledigt</option><option>Verschoben</option></select></td></tr>
      {% endfor %}
      <tr class="budget-total"><td><strong>M{{ '%02d' % (sections | length + 2) }}</strong></td><td><strong>Gesamtfertigstellung</strong></td><td>Gesamtprojekt baulich abgeschlossen, Übergabe vorbereitet</td><td>{{ project.responsible or '—' }}</td>
        <td>{% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
        <td><input type="date"></td>
        <td><select><option>Offen</option><option>In Arbeit</option><option>Erledigt</option><option>Verschoben</option></select></td></tr>
    </tbody>
  </table></div>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Keine belastbaren Soll-Termine je Abschnitt – ergänzen, sobald die Abschnittsplanung steht.</li>
    <li>Abhängigkeiten zwischen Wohnungen und Fernwärmestation festhalten.</li>
    <li>Statusstand aus Tagesberichten / Sprachmemos einpflegen (geplante Domäne).</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 10. projektuebersicht (PL) — Stammdaten + Bauabschnitte + Termine + Budget
# ---------------------------------------------------------------------------
PROJEKTUEBERSICHT = _wrap(
    "Projektübersicht – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <div class="hero-row">
    <div>
      <h1>Projektübersicht</h1>
      <p class="hero-sub">{{ project.name }} · Auftraggeber {{ project.responsible or '—' }}</p>
    </div>
    <div class="briefkopf-box" style="min-width:240px;"><strong>Auftragnehmer</strong>Firmendaten ergänzen</div>
  </div>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauvorhaben</span><span class="value {% if project.address is missing %}offen{% endif %}">{{ project.address or 'Adresse fehlt' }}</span></div>
    <div class="item"><span class="label">Projekt-Nr.</span><span class="value">{{ project.slug }}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<div class="kpi-row">
  <div class="kpi-card"><span class="kpi-value">{{ totals.section_count }}</span><span class="kpi-label">Bauabschnitte</span></div>
  <div class="kpi-card"><span class="kpi-value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }}{% else %}—{% endif %}</span><span class="kpi-label">Geplante Stunden</span></div>
  <div class="kpi-card"><span class="kpi-value">{% if project.duration_weeks %}~{{ project.duration_weeks }}{% else %}—{% endif %}</span><span class="kpi-label">Wochen Laufzeit</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ uploads | length }}</span><span class="kpi-label">Vorliegende Unterlagen</span></div>
</div>

<section class="card">
  <h2>Stammdaten</h2>
  <table class="kv-table">
    <tr><th>Projekt-Nummer</th><td>{{ project.slug }}</td></tr>
    <tr><th>Projekttyp</th><td>{{ project.project_type or '—' }}</td></tr>
    <tr><th>Bauvorhaben / Adresse</th><td>{% if project.address is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.address }}{% endif %}</td></tr>
    <tr><th>Auftraggeber / Bauherr</th><td>{{ project.responsible or '—' }}</td></tr>
    <tr><th>Projektverantwortlicher</th><td>{% if project.responsible is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.responsible }}{% endif %}</td></tr>
    <tr><th>Bauleitung</th><td>{% if project.construction_manager is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.construction_manager }}{% endif %}</td></tr>
    <tr><th>Obermonteur</th><td>{% if project.foreman is missing %}<span class="offener-punkt">Offener Punkt</span>{% else %}{{ project.foreman }}{% endif %}</td></tr>
    <tr><th>Geplanter Baubeginn</th><td>{% if project.planned_start %}{{ project.planned_start | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
    <tr><th>Geplantes Bauende</th><td>{% if project.planned_end %}{{ project.planned_end | de_date }}{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
    <tr><th>Projektdauer</th><td>{% if project.duration_weeks %}ca. {{ project.duration_weeks }} Wochen{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
    <tr><th>Geplante Stunden gesamt</th><td>{% if totals.planned_hours %}<strong>{{ totals.planned_hours | hours }}</strong>{% else %}<span class="offener-punkt">Offener Punkt</span>{% endif %}</td></tr>
  </table>
</section>

<section class="card">
  <h2>Bauabschnitte</h2>
  {% if sections %}
  <div class="table-wrap"><table>
    <thead><tr><th style="width:48px;">Nr.</th><th>Bezeichnung</th><th>Leistungsziel</th><th style="width:110px;">Geplante Std.</th><th style="width:160px;">Verantwortlich</th><th style="width:200px;">Eingesetztes Personal</th></tr></thead>
    <tbody>
      {% for s in sections %}
      <tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td><strong>{{ s.name }}</strong></td><td>{{ s.goal or '—' }}</td>
        <td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
        <td>{{ s.responsible or '—' }}</td><td>{{ s.staff_joined or '—' }}</td></tr>
      {% endfor %}
      {% if totals.planned_hours %}<tr class="budget-total"><td colspan="3"><strong>Gesamt</strong></td><td><strong>{{ totals.planned_hours | hours }}</strong></td><td colspan="2"></td></tr>{% endif %}
    </tbody>
  </table></div>
  {% else %}<p class="offener-punkt">Noch keine Bauabschnitte angelegt.</p>{% endif %}
</section>

<section class="card">
  <h2>Terminrahmen</h2>
  {% if sections %}
  <div class="table-wrap"><table>
    <thead><tr><th style="width:48px;">Nr.</th><th>Bezeichnung</th><th>Geplanter Start</th><th>Geplantes Ende</th><th>Dauer</th></tr></thead>
    <tbody>
      {% for s in sections %}
      <tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td>{{ s.name }}</td>
        <td>{% if s.derived_start %}{{ s.derived_start | de_date }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
        <td>{% if s.derived_end %}{{ s.derived_end | de_date }}{% else %}<span class="offener-punkt">offen</span>{% endif %}</td>
        <td>{% if s.duration_days %}~{{ s.duration_days }} Tage{% else %}—{% endif %}</td></tr>
      {% endfor %}
      <tr class="budget-total"><td colspan="2"><strong>Projekt gesamt</strong></td>
        <td><strong>{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</strong></td>
        <td><strong>{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</strong></td>
        <td><strong>{% if project.duration_weeks %}~{{ project.duration_weeks }} Wo.{% endif %}</strong></td></tr>
    </tbody>
  </table></div>
  <p class="hero-sub">Termine je Abschnitt sind aus Projektrahmen und Stundenanteil abgeleitet. Die Feinplanung wird in der Abschnittsplanung gepflegt und automatisch übernommen.</p>
  {% endif %}
</section>

<section class="card">
  <h2>Vorliegende Projektunterlagen</h2>
  {% if uploads %}
  <div class="table-wrap"><table>
    <thead><tr><th>Dateiname</th><th style="width:180px;">Typ</th><th style="width:150px;">Hochgeladen</th></tr></thead>
    <tbody>{% for u in uploads %}<tr><td>{{ u.filename }}</td><td><code>{{ u.content_type or '—' }}</code></td><td>{{ u.created_at | de_date }}</td></tr>{% endfor %}</tbody>
  </table></div>
  {% else %}<p>Noch keine Projektunterlagen hochgeladen.</p>{% endif %}
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte ({{ open_points | length }})</span>
  <ul>
    {% for p in open_points %}<li>{{ p }}</li>{% endfor %}
    <li>Budgetsummen netto/brutto je Angebot – kommen aus der zukünftigen Angebote-Domäne.</li>
    <li>Firmendaten Auftragnehmer-Briefkopf eintragen.</li>
    <li>Zahlungsplan / Abschlagszahlungen aus dem Werkvertrag übernehmen.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 11. statusuebersicht (PL) — Ampeldefinition + Status-Tabelle mit Inputs
# ---------------------------------------------------------------------------
STATUSUEBERSICHT = _wrap(
    "Statusübersicht – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Statusübersicht je Bauabschnitt</h1>
  <p class="hero-sub">{{ project.address or '—' }} · Auftraggeber {{ project.responsible or '—' }} · Projekt {{ project.slug }}</p>
</section>

<section class="card">
  <h2>Projektbezug</h2>
  <table class="kv-table">
    <tr><th>Geplanter Start</th><td>{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</td>
        <th>Geplantes Ende</th><td>{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</td></tr>
    <tr><th>Bauleitung</th><td>{{ project.construction_manager or '—' }}</td>
        <th>Obermonteur</th><td>{{ project.foreman or '—' }}</td></tr>
  </table>
</section>

<section class="card">
  <h2>Freigabe dieser Übersicht</h2>
  <div class="field-row">
    <div><label>Stand-Datum *</label><input type="date" required></div>
    <div><label>Aktualisiert von *</label><input type="text" placeholder="Name eintragen" required></div>
  </div>
</section>

<section class="card">
  <h2>Ampeldefinition</h2>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:120px;">Status</th><th>Bedeutung für die Projektleitung</th></tr></thead>
    <tbody>
      <tr><td><span class="status-badge status-green">Grün</span></td><td>Abschnitt läuft planmäßig. Kein akuter Eingriff nötig.</td></tr>
      <tr><td><span class="status-badge status-yellow">Gelb</span></td><td>Termin-, Personal- oder Materialrisiko erkennbar. Beobachten und nachsteuern.</td></tr>
      <tr><td><span class="status-badge status-red">Rot</span></td><td>Akute Störung oder Terminabweichung. Entscheidung oder Eskalation nötig.</td></tr>
    </tbody>
  </table></div>
</section>

<section class="card">
  <h2>Status je Bauabschnitt</h2>
  <div class="note info">Die Ampel zeigt den aktuellen Abschnittsstatus. Begründungen kurz und entscheidungsreif formulieren.</div>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:48px;">#</th><th>Abschnitt</th><th>Ziel</th><th style="width:140px;">Verantw.</th><th style="width:90px;">Std.</th><th style="width:130px;">Status *</th><th>Kurzbegründung *</th></tr></thead>
    <tbody>
      {% for s in sections %}
      <tr><td><span class="abschnitt-num">{{ s.number }}</span></td><td><strong>{{ s.name }}</strong></td><td>{{ s.goal or '—' }}</td>
        <td>{{ s.responsible or '—' }}</td><td>{% if s.planned_hours %}{{ s.planned_hours | hours }}{% endif %}</td>
        <td><select required><option value="">— wählen —</option><option>Grün</option><option>Gelb</option><option>Rot</option></select></td>
        <td><textarea required placeholder="Abweichung, Grund oder nächster Schritt"></textarea></td></tr>
      {% endfor %}
    </tbody>
  </table></div>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Aktueller Ampelstatus je Abschnitt ist vor Nutzung einzutragen.</li>
    <li>Kurze Begründung bei Abweichung Pflicht.</li>
    <li>Name der freigebenden Person ergänzen (oben „Aktualisiert von").</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 12. kontakte (Allgemein) — Schlüsselrollen + Mitglieder-Tabelle
# ---------------------------------------------------------------------------
KONTAKTE = _wrap(
    "Kontakte – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Kontaktliste Projektbeteiligte</h1>
  <p class="hero-sub">Übersicht für Baustelle und Büro. Fehlende Telefon- und E-Mail-Daten sind als offen markiert.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauvorhaben</span><span class="value">{{ project.address or '—' }}</span></div>
    <div class="item"><span class="label">Auftraggeber</span><span class="value">{{ project.responsible or '—' }}</span></div>
    <div class="item"><span class="label">Geplanter Start</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Geplantes Ende</span><span class="value">{% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
  </div>
</section>

<section class="card">
  <h2>Schlüsselrollen</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>Rolle</th><th>Person / Organisation</th><th>Telefon</th><th>E-Mail</th><th>Hinweis</th></tr></thead>
    <tbody>
      <tr><td><strong>Bauherr / Auftraggeber</strong></td><td>{{ project.responsible or '—' }}</td><td><span class="offener-punkt">Offen</span></td><td><span class="offener-punkt">Offen</span></td><td>Kontaktdaten ergänzen.</td></tr>
      <tr><td><strong>Bauleitung</strong></td><td>{{ project.construction_manager or '—' }}</td><td><span class="offener-punkt">Offen</span></td><td><span class="offener-punkt">Offen</span></td><td>Steuert Baustelle.</td></tr>
      <tr><td><strong>Obermonteur / Vor Ort</strong></td><td>{{ project.foreman or '—' }}</td><td><span class="offener-punkt">Offen</span></td><td><span class="offener-punkt">Offen</span></td><td>Verantwortlich für mehrere Bauabschnitte.</td></tr>
    </tbody>
  </table></div>
</section>

<section class="card">
  <h2>Projekt-Mitglieder</h2>
  {% if members %}
  <div class="table-wrap"><table>
    <thead><tr><th>Rolle im Projekt</th><th>Name</th><th>Benutzer</th><th>Globale Rolle</th></tr></thead>
    <tbody>{% for m in members %}<tr><td>{{ m.role }}</td><td>{{ m.display_name }}</td><td><code>{{ m.username }}</code></td><td>{{ m.global_role }}</td></tr>{% endfor %}</tbody>
  </table></div>
  {% else %}<p>Noch keine Projekt-Mitglieder zugewiesen.</p>{% endif %}
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Keine Telefon-/E-Mail-Daten im Projektdatensatz hinterlegt.</li>
    <li>Weitere Beteiligte (Hausverwaltung, externer FW-Dienstleister) bei Bedarf ergänzen.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# 13. uebergabeprotokoll (Allgemein) — BGB §640 Abnahmeprotokoll
# ---------------------------------------------------------------------------
UEBERGABEPROTOKOLL = _wrap(
    "Übergabeprotokoll – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <div class="hero-row">
    <div>
      <h1>Übergabe- und Abnahmeprotokoll</h1>
      <p class="hero-sub">nach BGB § 640 · Projekt {{ project.slug }}</p>
    </div>
    <div class="briefkopf-box" style="min-width:240px;"><strong>Firmen-Briefkopf</strong>Platz für Firmenangaben, Logo, Kontaktdaten</div>
  </div>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauvorhaben</span><span class="value">{{ project.address or '—' }}</span></div>
    <div class="item"><span class="label">Auftraggeber</span><span class="value">{{ project.responsible or '—' }}</span></div>
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Geplanter Zeitraum</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
  </div>
</section>

<section class="card">
  <h2>Abnahmeangaben</h2>
  <div class="field-row">
    <div><label>Datum der Abnahme *</label><input type="date" required></div>
    <div><label>Abnahme erfolgt durch</label><input type="text" placeholder="{{ project.responsible or 'Auftraggeber' }}"></div>
  </div>
  <div class="note info"><strong>Rechtlicher Hinweis:</strong> Mit Unterschrift beginnt die Gewährleistungsfrist gemäß BGB § 634a.</div>
</section>

<section class="card">
  <h2>Leistungsbeschreibung</h2>
  <p>Die nachstehenden Punkte sind aus den im Projekt hinterlegten Bauabschnitten abgeleitet und beschreiben die zur Abnahme vorgelegten Leistungen je Abschnitt.</p>
  <ul>
    {% for s in sections %}<li><strong>Abschnitt {{ s.number }} – {{ s.name }}:</strong> {{ s.goal or '—' }}</li>{% endfor %}
  </ul>
</section>

<section class="card">
  <h2>Mängelliste und Restleistungen</h2>
  <h3>Festgestellte Punkte bei der Abnahme</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>Bereich / Abschnitt</th><th>Festgestellter Mangel oder Restleistung</th><th style="width:200px;">Frist / Verantwortlich</th></tr></thead>
    <tbody>{% for n in range(4) %}<tr><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>{% endfor %}</tbody>
  </table></div>
</section>

<section class="card">
  <h2>Vorbehalte</h2>
  <h3>Hinweise des Kunden oder der Bauleitung</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>Vorbehalt</th><th>Bezug / Begründung</th></tr></thead>
    <tbody>{% for n in range(3) %}<tr><td contenteditable="true">&nbsp;</td><td contenteditable="true">&nbsp;</td></tr>{% endfor %}</tbody>
  </table></div>
</section>

<section class="card">
  <h2>Unterschriften</h2>
  <p>Mit den Unterschriften wird der Inhalt dieses Protokolls bestätigt.</p>
  <div class="signature-row">
    <div class="signature-box"><strong>Kunde / Auftraggeber</strong>Ort, Datum, Unterschrift</div>
    <div class="signature-box"><strong>Bauleitung / SHK-Unternehmen</strong>Ort, Datum, Unterschrift</div>
  </div>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Tatsächlicher Fertigstellungsgrad je Abschnitt nicht separat dokumentiert – vor Abnahme prüfen.</li>
    <li>Foto-Dokumentation einbetten, sobald die Foto-Galerie-Domäne aktiv ist.</li>
    <li>Konkrete Termin-/Fristzusagen für Restleistungen sind festzulegen.</li>
  </ul>
</div>
""",
)


# ---------------------------------------------------------------------------
# Migration upgrade — UPDATE all 13 templates, bump version.
# ---------------------------------------------------------------------------
TEMPLATES = {
    "start_index":              START_INDEX,
    "projekt_navigation":       PROJEKT_NAVIGATION,
    "ablaufplan_abschnitte":    ABLAUFPLAN_ABSCHNITTE,
    "wochenplan":               WOCHENPLAN,
    "checklisten":              CHECKLISTEN,
    "detaillierter_ablaufplan": DETAILLIERTER_ABLAUFPLAN,
    "gefaehrdungsbeurteilung":  GEFAEHRDUNGSBEURTEILUNG,
    "gantt_uebersicht":         GANTT_UEBERSICHT,
    "meilensteinplan":          MEILENSTEINPLAN,
    "projektuebersicht":        PROJEKTUEBERSICHT,
    "statusuebersicht":         STATUSUEBERSICHT,
    "kontakte":                 KONTAKTE,
    "uebergabeprotokoll":       UEBERGABEPROTOKOLL,
}


def upgrade() -> None:
    for slug, html in TEMPLATES.items():
        op.execute(
            sa.text(
                "UPDATE document_templates SET html_template = :html, version = version + 1 "
                "WHERE slug = :slug"
            ).bindparams(html=html, slug=slug)
        )


def downgrade() -> None:
    # Revert is not practical (would require keeping all previous versions);
    # rolling forward is the supported path.
    op.execute(
        "UPDATE document_templates SET version = version - 1 WHERE slug IN "
        "('start_index','projekt_navigation','ablaufplan_abschnitte','wochenplan',"
        "'checklisten','detaillierter_ablaufplan','gefaehrdungsbeurteilung',"
        "'gantt_uebersicht','meilensteinplan','projektuebersicht','statusuebersicht',"
        "'kontakte','uebergabeprotokoll')"
    )
