"""Seed the six remaining document templates with full content + Inline-Edit forms.

Covers the templates the user previously had open questions about:
- teamstatus (Obermonteur) — dynamic list per person × day
- abschnittsplanung (Obermonteur) — termin editor, propagates to all plans
- blocker_offene_punkte (Bauleitung) — dynamic blocker list
- hydraulischer_abgleich (Bauleitung) — heating design view + import-link
- material_werkzeug (Bauleitung) — dynamic material/tool inventory
- risiken_maengel (Bauleitung) — dynamic risks/defects list

All use the brand-bar, base_css and inline-form-submit script from the
renderer. All hard-coded sample rows are gone — lists grow via Add-forms.

Revision ID: b9c3e6f8d211
Revises: a4b8d2f5e310
Create Date: 2026-05-17 01:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b9c3e6f8d211"
down_revision: Union[str, None] = "a4b8d2f5e310"
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


# ───────────────────────────────────────────────────────────────────────────
# 1. teamstatus (Obermonteur) — Liste je Person × Tag, dynamisch erweiterbar
# ───────────────────────────────────────────────────────────────────────────
TEAMSTATUS = _wrap(
    "Teamstatus – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Teamstatus Obermonteur</h1>
  <p class="hero-sub">{{ project.name }} · Pro Person und Tag eine Zeile. Status nur als Grün, Gelb oder Rot.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Obermonteur</span><span class="value">{{ project.foreman or '—' }}</span></div>
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Einträge gesamt</span><span class="value">{{ team_status | length }}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<div class="note info">
  <strong>Ampeldefinition:</strong>
  <span class="status-badge status-green">Grün</span> = im Plan ·
  <span class="status-badge status-yellow">Gelb</span> = Achtung ·
  <span class="status-badge status-red">Rot</span> = Blockade
</div>

<section class="card">
  <h2>Erfasste Einträge</h2>
  {% if team_status %}
  <div class="table-wrap"><table>
    <thead><tr><th>Person</th><th>Datum</th><th>Status</th><th>Soll-Std.</th><th>Ist-Std.</th><th>Bemerkung</th><th style="width:80px;"></th></tr></thead>
    <tbody>
      {% for e in team_status %}
      <tr>
        <td><strong>{{ e.display_name }}</strong></td>
        <td>{{ e.day | de_date }}</td>
        <td><span class="status-badge status-{{ e.status }}">{{ e.status }}</span></td>
        <td>{% if e.soll_hours is not none %}{{ '%.1f' % e.soll_hours }} h{% else %}—{% endif %}</td>
        <td>{% if e.ist_hours is not none %}{{ '%.1f' % e.ist_hours }} h{% else %}—{% endif %}</td>
        <td>{{ e.note or '—' }}</td>
        <td><button data-api-delete="/api/projects/{{ project.slug }}/team-status/{{ e.id }}" style="background:transparent;border:1px solid var(--card-border);border-radius:6px;padding:4px 8px;cursor:pointer;font-size:12px;">×</button></td>
      </tr>
      {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="hero-sub">Noch keine Einträge. Über das Formular unten beliebig viele hinzufügen.</p>{% endif %}
</section>

<section class="card">
  <h2>Neuer Eintrag</h2>
  {% if members %}
  <form data-api-post="/api/projects/{{ project.slug }}/team-status">
    <div class="field-row">
      <div><label>Person *</label>
        <select name="user_id" required>
          <option value="">— wählen —</option>
          {% for m in members %}<option value="{{ m.user_id }}">{{ m.display_name }} ({{ m.role }})</option>{% endfor %}
        </select></div>
      <div><label>Datum *</label><input type="date" name="day" required></div>
      <div><label>Status *</label>
        <select name="status" required>
          <option value="green">Grün — im Plan</option>
          <option value="yellow">Gelb — Achtung</option>
          <option value="red">Rot — Blockade</option>
        </select></div>
      <div><label>Soll-Std.</label><input type="number" step="0.5" name="soll_hours" placeholder="z. B. 8"></div>
      <div><label>Ist-Std.</label><input type="number" step="0.5" name="ist_hours" placeholder="z. B. 7,5"></div>
    </div>
    <div class="field-row"><div style="grid-column: span 2;"><label>Bemerkung</label><textarea name="note" placeholder="Kurze Notiz zum Status"></textarea></div></div>
    <button type="submit" style="background:var(--brand-accent);color:#fff;border:none;border-radius:8px;padding:10px 18px;font-weight:600;cursor:pointer;font-family:inherit;">Eintrag speichern</button>
  </form>
  {% else %}
  <div class="note offen"><span class="note-title">Keine Projekt-Mitglieder zugewiesen</span><p>Über die Projekt-Verwaltung Mitglieder zuweisen, dann erscheinen sie hier als Auswahl.</p></div>
  {% endif %}
</section>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 2. abschnittsplanung (Obermonteur) — Termine pro Abschnitt, propagiert
# ───────────────────────────────────────────────────────────────────────────
ABSCHNITTSPLANUNG = _wrap(
    "Abschnittsplanung – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Abschnittsplanung – Zeitplanung &amp; Reihenfolge</h1>
  <p class="hero-sub">Termine pro Abschnitt eintragen. Sie werden automatisch in Gantt, Wochenplan, Meilensteinplan und Detail-Ablaufplan übernommen.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projektrahmen</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Abschnitte</span><span class="value">{{ totals.section_count }}</span></div>
    <div class="item"><span class="label">Geplante Stunden gesamt</span><span class="value">{% if totals.planned_hours %}{{ totals.planned_hours | hours }}{% else %}—{% endif %}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<div class="note info">
  <strong>So funktioniert's:</strong> Pro Abschnitt einen Start- und Endtermin eintragen und „Speichern" drücken. Solange kein konkreter Termin gepflegt ist, wird das Datum aus dem Stundenanteil <em>abgeleitet</em> (siehe Spalte "Abgeleitet"). Sobald Du speicherst, wird der echte Termin überall sichtbar.
</div>

{% if sections %}
{% for s in sections %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3>
  {% if s.schedule_pinned %}<span class="status-badge status-green">Termin gepflegt</span>{% else %}<span class="status-badge status-grey">abgeleitet</span>{% endif %}
  </div>
  <p class="abschnitt-meta"><strong>Ziel:</strong> {{ s.goal or '—' }} · <strong>Geplante Std.:</strong> {% if s.planned_hours %}{{ s.planned_hours | hours }}{% endif %} · <strong>Verantwortlich:</strong> {{ s.responsible or '—' }}</p>

  <form data-api-put="/api/projects/{{ project.slug }}/section-schedules">
    <input type="hidden" name="section_id" value="{{ s.id }}">
    <div class="field-row">
      <div><label>Start *</label><input type="date" name="start_date" value="{% if s.derived_start %}{{ s.derived_start.isoformat() }}{% endif %}" required></div>
      <div><label>Ende *</label><input type="date" name="end_date" value="{% if s.derived_end %}{{ s.derived_end.isoformat() }}{% endif %}" required></div>
      <div><label>Notiz</label><input type="text" name="notes" placeholder="Optional: Bedingungen, Übergaben"></div>
    </div>
    <button type="submit" style="background:var(--brand-accent);color:#fff;border:none;border-radius:8px;padding:8px 16px;font-weight:600;cursor:pointer;font-family:inherit;font-size:13px;">Termin speichern</button>
  </form>

  {% if not s.schedule_pinned %}
  <p class="hero-sub" style="margin-top:10px;font-size:13px;">Abgeleitet aus Stundenanteil ({% if s.duration_days %}{{ s.duration_days }} Tage{% endif %}). Speichern um zu fixieren.</p>
  {% endif %}
</div>
{% endfor %}
{% else %}
<div class="note offen"><span class="note-title">Keine Abschnitte angelegt</span></div>
{% endif %}
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 3. blocker_offene_punkte (Bauleitung) — Liste + Add-Form
# ───────────────────────────────────────────────────────────────────────────
BLOCKER_OFFENE_PUNKTE = _wrap(
    "Blocker &amp; offene Punkte – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Blocker &amp; offene Punkte</h1>
  <p class="hero-sub">{{ project.name }} · alle Blockaden und offenen Entscheidungen in einer Liste, beliebig viele pro Abschnitt.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Offen</span><span class="value">{{ all_blockers | selectattr('status', 'equalto', 'open') | list | length }}</span></div>
    <div class="item"><span class="label">In Arbeit</span><span class="value">{{ all_blockers | selectattr('status', 'equalto', 'in_progress') | list | length }}</span></div>
    <div class="item"><span class="label">Erledigt</span><span class="value">{{ all_blockers | selectattr('status', 'equalto', 'resolved') | list | length }}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<section class="card">
  <h2>Alle Blocker</h2>
  {% if all_blockers %}
  <div class="table-wrap"><table>
    <thead><tr><th>Abschnitt</th><th>Beschreibung</th><th>Schwere</th><th>Status</th><th>Erfasst</th><th style="width:60px;"></th></tr></thead>
    <tbody>
      {% for b in all_blockers %}
      <tr>
        <td>{% if b.section_number %}<span class="abschnitt-num">{{ b.section_number }}</span>{% else %}<span class="hero-sub">—</span>{% endif %}</td>
        <td>{{ b.description }}</td>
        <td>
          {% if b.severity == 'high' %}<span class="risiko-hoch">Hoch</span>
          {% elif b.severity == 'medium' %}<span class="risiko-mittel">Mittel</span>
          {% else %}<span class="risiko-gering">Gering</span>{% endif %}
        </td>
        <td>
          {% if b.status == 'open' %}<span class="status-badge status-red">Offen</span>
          {% elif b.status == 'in_progress' %}<span class="status-badge status-yellow">In Arbeit</span>
          {% else %}<span class="status-badge status-green">Erledigt</span>{% endif %}
        </td>
        <td><small>{{ b.created_at | de_date }}</small></td>
        <td><button data-api-delete="/api/projects/{{ project.slug }}/blockers/{{ b.id }}" style="background:transparent;border:1px solid var(--card-border);border-radius:6px;padding:4px 8px;cursor:pointer;font-size:12px;">×</button></td>
      </tr>
      {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p>Aktuell keine Blocker erfasst.</p>{% endif %}
</section>

<section class="card">
  <h2>Neuer Blocker</h2>
  <form data-api-post="/api/projects/{{ project.slug }}/blockers">
    <div class="field-row">
      <div><label>Bauabschnitt</label>
        <select name="section_number">
          <option value="">— ohne Zuordnung —</option>
          {% for s in sections %}<option value="{{ s.number }}">{{ s.number }} – {{ s.name }}</option>{% endfor %}
        </select></div>
      <div><label>Schwere *</label>
        <select name="severity" required>
          <option value="high">Hoch — Eskalation</option>
          <option value="medium" selected>Mittel — beobachten</option>
          <option value="low">Gering — Hinweis</option>
        </select></div>
      <div><label>Status *</label>
        <select name="status" required>
          <option value="open" selected>Offen</option>
          <option value="in_progress">In Arbeit</option>
          <option value="resolved">Erledigt</option>
        </select></div>
    </div>
    <label>Beschreibung *</label><textarea name="description" required placeholder="Worum geht es? Was wird benötigt, um den Blocker aufzulösen?"></textarea>
    <button type="submit" style="background:var(--brand-accent);color:#fff;border:none;border-radius:8px;padding:10px 18px;font-weight:600;cursor:pointer;font-family:inherit;margin-top:10px;">Blocker speichern</button>
  </form>
</section>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 4. hydraulischer_abgleich (Bauleitung) — Anzeige aus HeatingDesign + Upload-Link
# ───────────────────────────────────────────────────────────────────────────
HYDRAULISCHER_ABGLEICH = _wrap(
    "Hydraulischer Abgleich – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Hydraulischer Abgleich nach Verfahren B</h1>
  <p class="hero-sub">{{ project.name }} · {{ project.address or 'Adresse offen' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Datum</span><span class="value">{{ today | de_date }}</span></div>
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Anlage</span><span class="value">{{ heating.system_type or '—' }}</span></div>
    <div class="item"><span class="label">Heizkreise erfasst</span><span class="value">{{ heating.circuits | length }}</span></div>
  </div>
</section>

{% if heating.circuits | length == 0 %}
<div class="note offen">
  <span class="note-title">Heizkreis-Daten fehlen — bitte importieren</span>
  <p>Excel/CSV-Datei mit den Auslegungsdaten hochladen. Unterstützte Formate: <code>.xlsx</code>, <code>.xls</code>, <code>.csv</code>. Das Backend erkennt das Format automatisch (siehe <code>/api/heating-importers</code>).</p>
</div>
{% endif %}

<section class="card">
  <h2>Datei hochladen &amp; importieren</h2>
  <p class="hero-sub">Laden Sie die Excel/CSV mit den Heizkreis-Daten hoch. Das System erkennt das Format automatisch und schlägt Spalten-Mappings vor. Aktuell verfügbare Importer:</p>
  <ul>
    <li><strong>generic_table</strong> — beliebige Tabelle (xlsx/xls/csv) mit Heizkörper-/Strang-Spalten</li>
    <li><strong>viptool_master</strong> — VipTool Master-Export</li>
  </ul>
  <p class="hero-sub">In der App: Projekt → Uploads → Datei wählen → Importer wird vorgeschlagen → Mapping bestätigen → Daten landen in <code>heating_designs</code> + <code>heating_circuits</code> und erscheinen sofort hier.</p>
  <p><a href="/api/heating-importers">Verfügbare Importer (JSON)</a></p>
</section>

<section class="card">
  <h2>Anlagenkenndaten</h2>
  <table class="kv-table">
    <tr><th>System-Typ</th><td>{{ heating.system_type or '—' }}</td></tr>
    <tr><th>Vorlauf</th><td>{% if heating.supply_temp_c %}{{ heating.supply_temp_c }} °C{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
    <tr><th>Rücklauf</th><td>{% if heating.return_temp_c %}{{ heating.return_temp_c }} °C{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
    <tr><th>Spreizung ΔT</th><td>{% if heating.delta_t_k %}{{ heating.delta_t_k }} K{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
    <tr><th>Volumenstrom gesamt</th><td>{% if heating.total_volume_flow_lph %}{{ heating.total_volume_flow_lph }} l/h{% else %}<span class="offener-punkt">offen</span>{% endif %}</td></tr>
    <tr><th>Pumpe</th><td>{{ heating.pump_model or 'offen' }}</td></tr>
  </table>
</section>

<section class="card">
  <h2>Heizkreis-Tabelle</h2>
  {% if heating.circuits %}
  <div class="table-wrap"><table>
    <thead><tr><th>Strang</th><th>Raum</th><th>Geschoss</th><th>Heizkörper</th><th>Heizlast (W)</th><th>Volumenstrom (l/h)</th><th>Ventil-Voreinst.</th></tr></thead>
    <tbody>
      {% for c in heating.circuits %}
      <tr>
        <td>{{ c.strand or '—' }}</td><td>{{ c.room or '—' }}</td><td>{{ c.floor or '—' }}</td>
        <td>{{ c.radiator_type or '—' }}</td>
        <td>{% if c.heat_load_w %}{{ c.heat_load_w }}{% else %}—{% endif %}</td>
        <td>{% if c.volume_flow_lph %}{{ c.volume_flow_lph }}{% else %}—{% endif %}</td>
        <td>{{ c.valve_preset or '—' }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table></div>
  {% else %}
  <p class="hero-sub">Keine Heizkreise erfasst. Über den Upload-Bereich oben Excel/CSV importieren.</p>
  {% endif %}
</section>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 5. material_werkzeug (Bauleitung) — dynamisches Inventar
# ───────────────────────────────────────────────────────────────────────────
MATERIAL_WERKZEUG = _wrap(
    "Material &amp; Werkzeug – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Material- und Werkzeugliste</h1>
  <p class="hero-sub">{{ project.name }} · dynamische Liste je Abschnitt, beliebig erweiterbar.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Einträge gesamt</span><span class="value">{{ material_items | length }}</span></div>
    <div class="item"><span class="label">Fehlt</span><span class="value">{{ material_items | selectattr('status', 'equalto', 'fehlt') | list | length }}</span></div>
    <div class="item"><span class="label">Bestellt</span><span class="value">{{ material_items | selectattr('status', 'equalto', 'bestellt') | list | length }}</span></div>
    <div class="item"><span class="label">Vorhanden</span><span class="value">{{ material_items | selectattr('status', 'equalto', 'vorhanden') | list | length }}</span></div>
  </div>
</section>

{% for s in sections %}
{% set items = material_items | selectattr('section_number', 'equalto', s.number) | list %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3></div>
  {% if items %}
  <div class="table-wrap"><table>
    <thead><tr><th>Art</th><th>Bezeichnung</th><th>Soll</th><th>Ist</th><th>Einheit</th><th>Lagerort</th><th>Status</th><th style="width:60px;"></th></tr></thead>
    <tbody>
    {% for it in items %}
    <tr>
      <td>{% if it.kind == 'werkzeug' %}<span class="status-badge status-blue">Werkzeug</span>{% else %}<span class="status-badge status-grey">Material</span>{% endif %}</td>
      <td><strong>{{ it.name }}</strong></td>
      <td>{% if it.soll_qty is not none %}{{ it.soll_qty }}{% else %}—{% endif %}</td>
      <td>{% if it.ist_qty is not none %}{{ it.ist_qty }}{% else %}—{% endif %}</td>
      <td>{{ it.unit or '—' }}</td>
      <td>{{ it.location or '—' }}</td>
      <td>
        {% if it.status == 'fehlt' %}<span class="status-badge status-red">Fehlt</span>
        {% elif it.status == 'bestellt' %}<span class="status-badge status-yellow">Bestellt</span>
        {% elif it.status == 'geliefert' %}<span class="status-badge status-blue">Geliefert</span>
        {% else %}<span class="status-badge status-green">Vorhanden</span>{% endif %}
      </td>
      <td><button data-api-delete="/api/projects/{{ project.slug }}/material-items/{{ it.id }}" style="background:transparent;border:1px solid var(--card-border);border-radius:6px;padding:4px 8px;cursor:pointer;font-size:12px;">×</button></td>
    </tr>
    {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="hero-sub">Noch keine Einträge für diesen Abschnitt.</p>{% endif %}
</div>
{% endfor %}

{# Einträge ohne Abschnittsbezug #}
{% set unassigned = material_items | rejectattr('section_number') | list %}
{% if unassigned %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><h3>Allgemein (ohne Abschnitt)</h3></div>
  <div class="table-wrap"><table>
    <thead><tr><th>Art</th><th>Bezeichnung</th><th>Soll</th><th>Ist</th><th>Einheit</th><th>Lagerort</th><th>Status</th><th></th></tr></thead>
    <tbody>{% for it in unassigned %}<tr>
      <td>{{ it.kind }}</td><td>{{ it.name }}</td><td>{{ it.soll_qty or '—' }}</td><td>{{ it.ist_qty or '—' }}</td><td>{{ it.unit or '—' }}</td><td>{{ it.location or '—' }}</td><td>{{ it.status }}</td>
      <td><button data-api-delete="/api/projects/{{ project.slug }}/material-items/{{ it.id }}" style="background:transparent;border:1px solid var(--card-border);border-radius:6px;padding:4px 8px;cursor:pointer;font-size:12px;">×</button></td>
    </tr>{% endfor %}</tbody>
  </table></div>
</div>
{% endif %}

<section class="card">
  <h2>Neuer Eintrag</h2>
  <form data-api-post="/api/projects/{{ project.slug }}/material-items">
    <div class="field-row">
      <div><label>Abschnitt</label>
        <select name="section_number">
          <option value="">— allgemein —</option>
          {% for s in sections %}<option value="{{ s.number }}">{{ s.number }} – {{ s.name }}</option>{% endfor %}
        </select></div>
      <div><label>Art *</label>
        <select name="kind" required>
          <option value="material" selected>Material</option>
          <option value="werkzeug">Werkzeug</option>
        </select></div>
      <div><label>Bezeichnung *</label><input type="text" name="name" required placeholder="z. B. Rohrschelle DN20"></div>
      <div><label>Soll-Menge</label><input type="number" step="0.1" name="soll_qty"></div>
      <div><label>Ist-Menge</label><input type="number" step="0.1" name="ist_qty"></div>
      <div><label>Einheit</label><input type="text" name="unit" placeholder="Stk, m, kg"></div>
      <div><label>Lagerort</label><input type="text" name="location" placeholder="z. B. Container Keller"></div>
      <div><label>Status *</label>
        <select name="status" required>
          <option value="vorhanden">Vorhanden</option>
          <option value="fehlt">Fehlt</option>
          <option value="bestellt">Bestellt</option>
          <option value="geliefert">Geliefert</option>
        </select></div>
    </div>
    <label>Notiz</label><textarea name="note" placeholder="Optional"></textarea>
    <button type="submit" style="background:var(--brand-accent);color:#fff;border:none;border-radius:8px;padding:10px 18px;font-weight:600;cursor:pointer;font-family:inherit;margin-top:10px;">Eintrag speichern</button>
  </form>
</section>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 6. risiken_maengel (Bauleitung) — dynamische Risiken/Mängel-Liste
# ───────────────────────────────────────────────────────────────────────────
RISIKEN_MAENGEL = _wrap(
    "Risiken &amp; Mängel – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Risiken- und Mängelliste</h1>
  <p class="hero-sub">{{ project.name }} · Risiken (vor Eintritt) und Mängel (nach Eintritt) je Abschnitt protokollieren.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Risiken</span><span class="value">{{ risk_issues | selectattr('kind', 'equalto', 'risiko') | list | length }}</span></div>
    <div class="item"><span class="label">Mängel</span><span class="value">{{ risk_issues | selectattr('kind', 'equalto', 'mangel') | list | length }}</span></div>
    <div class="item"><span class="label">Offen</span><span class="value">{{ risk_issues | selectattr('status', 'equalto', 'offen') | list | length }}</span></div>
    <div class="item"><span class="label">Erledigt</span><span class="value">{{ risk_issues | selectattr('status', 'equalto', 'erledigt') | list | length }}</span></div>
  </div>
</section>

<div class="note info"><strong>Sinn der Liste:</strong> Risiken werden präventiv protokolliert (was könnte schiefgehen, mit welcher Schwere). Mängel werden reaktiv festgehalten (was ist schiefgegangen, wer kümmert sich, bis wann). Dient als Nachweis Richtung Bauleitung, Auftraggeber und KfW.</div>

<section class="card">
  <h2>Alle Einträge</h2>
  {% if risk_issues %}
  <div class="table-wrap"><table>
    <thead><tr><th>Art</th><th>Abschnitt</th><th>Beschreibung</th><th>Schwere</th><th>Verantwortlich</th><th>Frist</th><th>Status</th><th style="width:60px;"></th></tr></thead>
    <tbody>
      {% for r in risk_issues %}
      <tr>
        <td>{% if r.kind == 'mangel' %}<span class="status-badge status-red">Mangel</span>{% else %}<span class="status-badge status-yellow">Risiko</span>{% endif %}</td>
        <td>{% if r.section_number %}<span class="abschnitt-num">{{ r.section_number }}</span>{% else %}—{% endif %}</td>
        <td>{{ r.description }}</td>
        <td>
          {% if r.severity == 'hoch' %}<span class="risiko-hoch">Hoch</span>
          {% elif r.severity == 'mittel' %}<span class="risiko-mittel">Mittel</span>
          {% else %}<span class="risiko-gering">Gering</span>{% endif %}
        </td>
        <td>{{ r.responsible or '—' }}</td>
        <td>{% if r.due_date %}{{ r.due_date | de_date }}{% else %}—{% endif %}</td>
        <td>
          {% if r.status == 'offen' %}<span class="status-badge status-red">Offen</span>
          {% elif r.status == 'in_arbeit' %}<span class="status-badge status-yellow">In Arbeit</span>
          {% else %}<span class="status-badge status-green">Erledigt</span>{% endif %}
        </td>
        <td><button data-api-delete="/api/projects/{{ project.slug }}/risk-issues/{{ r.id }}" style="background:transparent;border:1px solid var(--card-border);border-radius:6px;padding:4px 8px;cursor:pointer;font-size:12px;">×</button></td>
      </tr>
      {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="hero-sub">Keine Einträge. Über das Formular unten Risiken oder Mängel erfassen.</p>{% endif %}
</section>

<section class="card">
  <h2>Neuer Eintrag</h2>
  <form data-api-post="/api/projects/{{ project.slug }}/risk-issues">
    <div class="field-row">
      <div><label>Art *</label>
        <select name="kind" required>
          <option value="risiko" selected>Risiko (präventiv)</option>
          <option value="mangel">Mangel (reaktiv)</option>
        </select></div>
      <div><label>Abschnitt</label>
        <select name="section_number">
          <option value="">— ohne Zuordnung —</option>
          {% for s in sections %}<option value="{{ s.number }}">{{ s.number }} – {{ s.name }}</option>{% endfor %}
        </select></div>
      <div><label>Schwere *</label>
        <select name="severity" required>
          <option value="hoch">Hoch</option>
          <option value="mittel" selected>Mittel</option>
          <option value="gering">Gering</option>
        </select></div>
      <div><label>Status *</label>
        <select name="status" required>
          <option value="offen" selected>Offen</option>
          <option value="in_arbeit">In Arbeit</option>
          <option value="erledigt">Erledigt</option>
        </select></div>
      <div><label>Verantwortlich</label><input type="text" name="responsible" placeholder="Name"></div>
      <div><label>Frist</label><input type="date" name="due_date"></div>
    </div>
    <label>Beschreibung *</label><textarea name="description" required placeholder="Was ist das Risiko / der Mangel? Wo? Welche Folge?"></textarea>
    <button type="submit" style="background:var(--brand-accent);color:#fff;border:none;border-radius:8px;padding:10px 18px;font-weight:600;cursor:pointer;font-family:inherit;margin-top:10px;">Eintrag speichern</button>
  </form>
</section>
""",
)


SEEDS = [
    ("teamstatus",            "02_Obermonteur", "Teamstatus",                 "Dynamische Liste je Person × Tag (Grün/Gelb/Rot). Beliebig viele Personen, Add-Form, keine hartkodierten Zeilen."),
    ("abschnittsplanung",     "02_Obermonteur", "Abschnittsplanung",          "Termin-Editor je Abschnitt. Gespeicherte Termine propagieren automatisch in Gantt, Wochenplan, Meilensteinplan, Ablaufplan."),
    ("blocker_offene_punkte", "03_Bauleitung",  "Blocker & offene Punkte",    "Liste aller Blocker mit Schwere, Status, Abschnittsbezug. Beliebig viele pro Tag und Abschnitt erfassbar."),
    ("hydraulischer_abgleich","03_Bauleitung",  "Hydraulischer Abgleich",     "Anlagenkenndaten + Heizkreis-Tabelle aus HeatingDesign. Import-Endpoints für xlsx/xls/csv verfügbar."),
    ("material_werkzeug",     "03_Bauleitung",  "Material & Werkzeug",        "Dynamisches Material-/Werkzeug-Inventar je Abschnitt. Soll/Ist, Status (vorhanden/fehlt/bestellt/geliefert)."),
    ("risiken_maengel",       "03_Bauleitung",  "Risiken & Mängel",           "Risiken (präventiv) und Mängel (reaktiv) als dynamische Liste. Schwere, Verantwortlich, Frist, Status."),
]

TEMPLATES_HTML = {
    "teamstatus":             TEAMSTATUS,
    "abschnittsplanung":      ABSCHNITTSPLANUNG,
    "blocker_offene_punkte":  BLOCKER_OFFENE_PUNKTE,
    "hydraulischer_abgleich": HYDRAULISCHER_ABGLEICH,
    "material_werkzeug":      MATERIAL_WERKZEUG,
    "risiken_maengel":        RISIKEN_MAENGEL,
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
    rows = [
        {
            "slug": slug,
            "category": category,
            "title": title,
            "description": description,
            "html_template": TEMPLATES_HTML[slug],
            "data_schema": None,
            "version": 1,
        }
        for slug, category, title, description in SEEDS
    ]
    op.bulk_insert(document_templates, rows)


def downgrade() -> None:
    slugs = ", ".join(f"'{slug}'" for slug, *_ in SEEDS)
    op.execute(f"DELETE FROM document_templates WHERE slug IN ({slugs})")
