"""Seed the six remaining document templates so the Mitra template-set
covers all 25 docs the codex flow previously generated.

- baustellenhinweise (01_Monteur)
- tagescheckliste (01_Monteur) — backed by DailyReport domain
- inbetriebnahmeprotokoll (04_Projektleitung)
- kfw_fachunternehmererklaerung (04_Projektleitung)
- dokumentenindex (05_Allgemein)
- projektunterlagen (05_Allgemein) — backed by ProjectUpload

Revision ID: d4f7b1c9e520
Revises: c5d8e2a3f412
Create Date: 2026-05-17 03:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f7b1c9e520"
down_revision: Union[str, None] = "c5d8e2a3f412"
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
# 1. baustellenhinweise (01_Monteur)
# ───────────────────────────────────────────────────────────────────────────
BAUSTELLENHINWEISE = _wrap(
    "Baustellenhinweise – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Baustellenhinweise</h1>
  <p class="hero-sub">{{ project.name }} · {{ project.address or 'Adresse offen' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Obermonteur</span><span class="value">{{ project.foreman or '—' }}</span></div>
    <div class="item"><span class="label">Zeitraum</span><span class="value">{% if project.planned_start %}{{ project.planned_start | de_date }}{% endif %} – {% if project.planned_end %}{{ project.planned_end | de_date }}{% endif %}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<section class="card">
  <h2>Zugang &amp; Zufahrt</h2>
  <table class="kv-table">
    <tr><th>Anfahrt</th><td>{{ project.address or '—' }}</td></tr>
    <tr><th>Parkmöglichkeiten</th><td><span class="offener-punkt">vom Bauleiter zu ergänzen</span></td></tr>
    <tr><th>Schlüssel / Zutritt</th><td><span class="offener-punkt">vom Bauleiter zu ergänzen</span></td></tr>
    <tr><th>Sicherheits- / Hausordnung</th><td><span class="offener-punkt">vom Bauleiter zu ergänzen</span></td></tr>
  </table>
</section>

<section class="card">
  <h2>Personen vor Ort</h2>
  {% if members %}
  <div class="table-wrap"><table>
    <thead><tr><th>Rolle</th><th>Name</th><th>Benutzer</th></tr></thead>
    <tbody>{% for m in members %}<tr><td>{{ m.role }}</td><td><strong>{{ m.display_name }}</strong></td><td><code>{{ m.username }}</code></td></tr>{% endfor %}</tbody>
  </table></div>
  {% else %}<p class="hero-sub">Noch keine Projekt-Mitglieder zugewiesen. Pflege in der Projekt-Verwaltung.</p>{% endif %}
  <div class="note info" style="margin-top:14px;">
    <strong>Schlüsselrollen:</strong>
    Bauleitung <strong>{{ project.construction_manager or '—' }}</strong> ·
    Obermonteur <strong>{{ project.foreman or '—' }}</strong> ·
    Projektverantwortlich <strong>{{ project.responsible or '—' }}</strong>
  </div>
</section>

<section class="card">
  <h2>Lager &amp; Material</h2>
  <p>Standorte und Mengen pro Abschnitt werden in <a href="/api/templates/material_werkzeug/render/{{ project.slug }}">Material &amp; Werkzeug</a> dynamisch gepflegt.</p>
  {% if material_items %}
  <p class="hero-sub">{{ material_items | length }} Material-/Werkzeugeinträge erfasst (zur Übersicht im Material-Template).</p>
  {% endif %}
</section>

<section class="card">
  <h2>Arbeitszeit &amp; Pausen</h2>
  <div class="note info">
    Montag–Donnerstag <strong>07:00–16:00</strong> mit 1 h flexibler Pause (= 8 h)<br>
    Freitag <strong>07:00–13:00</strong> ohne Pause (= 6 h)<br>
    Wochenende Sa+So frei · <strong>Wochensumme 38 h</strong>
  </div>
</section>

<section class="card">
  <h2>Notfall &amp; Erste Hilfe</h2>
  <table class="kv-table">
    <tr><th>Notruf (Polizei)</th><td>110</td></tr>
    <tr><th>Notruf (Feuerwehr / Rettungsdienst)</th><td>112</td></tr>
    <tr><th>Gas-Störung</th><td><span class="offener-punkt">örtlichen Anbieter eintragen</span></td></tr>
    <tr><th>Strom-Störung</th><td><span class="offener-punkt">örtlichen Anbieter eintragen</span></td></tr>
    <tr><th>Erste-Hilfe-Kasten</th><td><span class="offener-punkt">Standort vor Ort eintragen</span></td></tr>
  </table>
</section>

<div class="note offen">
  <span class="note-title">Offene Punkte</span>
  <ul>
    <li>Konkrete Telefon-/E-Mail-Daten der Beteiligten in <a href="/api/templates/kontakte/render/{{ project.slug }}">Kontakte</a> nachtragen.</li>
    <li>Parkhaus/Zufahrt mit Hausverwaltung abklären und oben eintragen.</li>
  </ul>
</div>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 2. tagescheckliste (01_Monteur) — pro Tag ein Datensatz, leer ausfüllen
# ───────────────────────────────────────────────────────────────────────────
TAGESCHECKLISTE = _wrap(
    "Tagescheckliste – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Tagescheckliste Monteur</h1>
  <p class="hero-sub">{{ project.name }} · {{ project.address or '—' }}</p>
</section>

<div class="note info">Diese Checkliste wird pro Arbeitstag ausgefüllt. Speichern legt einen Tagesbericht für das gewählte Datum an.</div>

<section class="card">
  <h2>Tagesinformation</h2>
  <div class="field-row">
    <div><label>Datum *</label><input type="date" name="day" required></div>
    <div><label>Monteur *</label><input type="text" name="monteur" placeholder="{{ project.foreman or 'Name' }}" required></div>
    <div><label>Abschnitt *</label>
      <select name="section_number" required><option value="">— wählen —</option>
        {% for s in sections %}<option value="{{ s.number }}">{{ s.number }} – {{ s.name }}</option>{% endfor %}
      </select></div>
    <div><label>Wetter</label>
      <select name="wetter"><option value="">—</option><option>Trocken</option><option>Regen</option><option>Schnee</option><option>Wind</option><option>Hitze (&gt;30 °C)</option></select></div>
  </div>
</section>

<section class="card">
  <h2>Prüfpunkte vor Arbeitsbeginn</h2>
  <p><label><input type="checkbox"> PSA komplett (Helm, Brille, Handschuhe, S3-Schuhe)</label></p>
  <p><label><input type="checkbox"> Werkzeug funktionsfähig, kein Defekt</label></p>
  <p><label><input type="checkbox"> Material für den Tag bereitgestellt</label></p>
  <p><label><input type="checkbox"> Arbeitsbereich abgesichert, Fluchtwege frei</label></p>
  <p><label><input type="checkbox"> Anlagenstillstand / Freigabe vorhanden</label></p>
</section>

<section class="card">
  <h2>Tagesziel &amp; Ausführung</h2>
  <label>Tagesziel</label><textarea name="ziel" placeholder="Was soll heute geschafft werden?"></textarea>
  <label>Erledigte Arbeiten</label><textarea name="erledigt" placeholder="Stichpunkte zum Arbeitsergebnis"></textarea>
  <label>Probleme / Blockaden</label><textarea name="probleme" placeholder="Was hat nicht funktioniert? Welche Entscheidung wird gebraucht?"></textarea>
  <div class="field-row">
    <div><label>Ist-Stunden (netto)</label><input type="number" step="0.5" name="ist_hours" placeholder="z. B. 7,5"></div>
    <div><label>Tagesstatus</label>
      <select name="status"><option value="green">Grün — im Plan</option><option value="yellow">Gelb — Achtung</option><option value="red">Rot — Blockade</option></select></div>
  </div>
</section>

<section class="card">
  <h2>Material-Bewegung des Tages</h2>
  <label>Verbrauchtes Material / Werkzeug</label>
  <textarea name="verbraucht" placeholder="Stichpunkte: was wurde verbaut?"></textarea>
  <label>Nachbestellungen / Fehlmengen</label>
  <textarea name="nachbestellung" placeholder="Was muss morgen oder die nächsten Tage geliefert werden?"></textarea>
</section>

<div class="note offen">
  <span class="note-title">Hinweis</span>
  <ul>
    <li>Speichern wird mit der Daily-Reports-Domäne verbunden, sobald wir die Tageschecks-Form mit dem Backend verknüpfen — heute dient die Liste als Druckvorlage.</li>
    <li>Für strukturierte Tagesberichte über die App: <code>/api/projects/{{ project.slug }}/daily-reports</code></li>
  </ul>
</div>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 3. inbetriebnahmeprotokoll (04_Projektleitung)
# ───────────────────────────────────────────────────────────────────────────
INBETRIEBNAHMEPROTOKOLL = _wrap(
    "Inbetriebnahmeprotokoll – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <h1>Inbetriebnahmeprotokoll</h1>
  <p class="hero-sub">{{ project.name }} · {{ project.address or '—' }}</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauleitung</span><span class="value">{{ project.construction_manager or '—' }}</span></div>
    <div class="item"><span class="label">Obermonteur</span><span class="value">{{ project.foreman or '—' }}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
    <div class="item"><span class="label">IBN-Datum</span><span class="value"><input type="date" name="ibn_datum" style="max-width:160px;display:inline-block;"></span></div>
  </div>
</section>

<section class="card">
  <h2>Anlagenkomponenten</h2>
  <p class="hero-sub">Aus den Heizungsdaten der Hydraulik-Auslegung. Felder ohne Wert sind direkt im Formular zu ergänzen.</p>
  <table class="kv-table">
    <tr><th>System-Typ</th><td>{{ heating.system_type or 'Fernwärme-Hausstation' }}</td></tr>
    <tr><th>Vorlauf</th><td>{% if heating.supply_temp_c %}{{ heating.supply_temp_c }} °C{% else %}<input type="number" step="0.1" name="vorlauf_c" placeholder="z. B. 70">{% endif %}</td></tr>
    <tr><th>Rücklauf</th><td>{% if heating.return_temp_c %}{{ heating.return_temp_c }} °C{% else %}<input type="number" step="0.1" name="ruecklauf_c" placeholder="z. B. 55">{% endif %}</td></tr>
    <tr><th>Spreizung ΔT</th><td>{% if heating.delta_t_k %}{{ heating.delta_t_k }} K{% else %}<input type="number" step="0.1" name="delta_t" placeholder="z. B. 15">{% endif %}</td></tr>
    <tr><th>Gesamt-Volumenstrom</th><td>{% if heating.total_volume_flow_lph %}{{ heating.total_volume_flow_lph }} l/h{% else %}<input type="number" step="0.1" name="volumenstrom" placeholder="z. B. 5760">{% endif %}</td></tr>
    <tr><th>Pumpe</th><td>{{ heating.pump_model or 'Grundfos MAGNA3 50-100 F (oder gleichwertig)' }}</td></tr>
  </table>
</section>

<section class="card">
  <h2>Druck- und Dichtheitsprüfung</h2>
  <div class="field-row">
    <div><label>Prüfdruck</label><input type="text" name="pruefdruck" placeholder="z. B. 6 bar"></div>
    <div><label>Prüfdauer</label><input type="text" name="pruefdauer" placeholder="z. B. 30 min"></div>
    <div><label>Druckabfall</label><input type="text" name="druckabfall" placeholder="z. B. 0,0 bar"></div>
    <div><label>Ergebnis</label><select name="ergebnis"><option value="">—</option><option>Bestanden</option><option>Nicht bestanden</option></select></div>
  </div>
</section>

<section class="card">
  <h2>Spülung &amp; Befüllung</h2>
  <p><label><input type="checkbox"> Anlage gespült (VDI 2035)</label></p>
  <p><label><input type="checkbox"> Entlüftung an allen Strängen erfolgt</label></p>
  <p><label><input type="checkbox"> Heizungswasser nach VDI 2035 befüllt</label></p>
  <p><label><input type="checkbox"> Ausdehnungsgefäß auf Soll-Vordruck eingestellt</label></p>
  <div class="field-row">
    <div><label>Wasservolumen (l)</label><input type="number" step="1" name="wasservolumen"></div>
    <div><label>Härte (°dH)</label><input type="number" step="0.1" name="haerte"></div>
    <div><label>Leitfähigkeit (µS/cm)</label><input type="number" step="1" name="leitfaehigkeit"></div>
  </div>
</section>

<section class="card">
  <h2>Funktion &amp; Regelung</h2>
  <p><label><input type="checkbox"> Pumpe läuft, Förderhöhe geprüft</label></p>
  <p><label><input type="checkbox"> Regelung in Betrieb, Sollwerte gesetzt</label></p>
  <p><label><input type="checkbox"> Sicherheits-/Überdruckventile geprüft</label></p>
  <p><label><input type="checkbox"> Heizkreise auf Voreinstellung kontrolliert</label></p>
  <label>Bemerkungen</label><textarea name="bemerkungen" placeholder="Auffälligkeiten, Restpunkte, weitere Hinweise"></textarea>
</section>

<section class="card">
  <h2>Übergabe &amp; Einweisung</h2>
  <p><label><input type="checkbox"> Bedienungsanleitung übergeben</label></p>
  <p><label><input type="checkbox"> Wartungshinweise erläutert</label></p>
  <p><label><input type="checkbox"> Notruf-Kontaktdaten übergeben</label></p>
  <div class="signature-row">
    <div class="signature-box"><strong>Inbetriebnahme durch</strong>{{ project.construction_manager or '____________' }} · Datum / Unterschrift</div>
    <div class="signature-box"><strong>Übernahme</strong>{{ project.responsible or '____________' }} · Datum / Unterschrift</div>
  </div>
</section>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 4. kfw_fachunternehmererklaerung (04_Projektleitung)
# ───────────────────────────────────────────────────────────────────────────
KFW_FACHUNTERNEHMERERKLAERUNG = _wrap(
    "KfW-Fachunternehmererklärung – {{ project.name }}",
    r"""
<span class="doc-badge formular">Formular</span>

<section class="hero">
  <div class="hero-row">
    <div>
      <h1>Fachunternehmererklärung KfW</h1>
      <p class="hero-sub">Heizungsanlage – Erneuerung und Optimierung</p>
    </div>
    <div class="briefkopf-box" style="min-width:240px;"><strong>Fachunternehmen</strong>Mitra Sanitär GmbH · Firmenstempel ergänzen</div>
  </div>
  <div class="hero-grid">
    <div class="item"><span class="label">Bauvorhaben</span><span class="value">{{ project.address or '—' }}</span></div>
    <div class="item"><span class="label">Bauherr / Auftraggeber</span><span class="value">{{ project.responsible or '—' }}</span></div>
    <div class="item"><span class="label">Projekt-Nr.</span><span class="value">{{ project.slug }}</span></div>
    <div class="item"><span class="label">Datum</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<div class="note info"><strong>Rechtliche Grundlage:</strong> Bestätigung der ordnungsgemäßen Ausführung gemäß den KfW-Förderbedingungen für Einzelmaßnahmen am Heizungssystem nach BEG EM / GEG.</div>

<section class="card">
  <h2>Erklärung des Fachunternehmens</h2>
  <p>Hiermit bestätigt das Fachunternehmen <strong>Mitra Sanitär GmbH</strong>, dass die nachfolgend aufgeführten Maßnahmen am Heizungssystem fachgerecht und gemäß den Anforderungen der KfW-Förderung sowie den anerkannten Regeln der Technik (DIN, GEG, VDI) ausgeführt wurden.</p>
</section>

<section class="card">
  <h2>Durchgeführte Maßnahmen</h2>
  <div class="table-wrap"><table>
    <thead><tr><th style="width:60px;">Nr.</th><th>Maßnahme</th><th>Beschreibung</th><th style="width:100px;">Ausgeführt</th></tr></thead>
    <tbody>
      {% for s in sections %}
      <tr><td><span class="abschnitt-num">{{ s.number }}</span></td>
        <td><strong>{{ s.name }}</strong></td>
        <td>{{ s.goal or '—' }}</td>
        <td><label><input type="checkbox" checked> ja</label></td></tr>
      {% endfor %}
    </tbody>
  </table></div>
</section>

<section class="card">
  <h2>Hydraulischer Abgleich (Verfahren B)</h2>
  <p><label><input type="checkbox"> Hydraulischer Abgleich nach Verfahren B wurde durchgeführt</label></p>
  <table class="kv-table">
    <tr><th>Auslegungs-Vorlauftemperatur</th><td>{% if heating.supply_temp_c %}{{ heating.supply_temp_c }} °C{% else %}<input type="number" step="0.1" placeholder="°C">{% endif %}</td></tr>
    <tr><th>Auslegungs-Rücklauftemperatur</th><td>{% if heating.return_temp_c %}{{ heating.return_temp_c }} °C{% else %}<input type="number" step="0.1" placeholder="°C">{% endif %}</td></tr>
    <tr><th>Gebäude-Heizlast (gem. DIN EN 12831)</th><td><input type="text" placeholder="z. B. 100,42 kW"></td></tr>
    <tr><th>Pumpentyp (Hocheffizienzpumpe)</th><td>{{ heating.pump_model or '—' }}</td></tr>
    <tr><th>Heizkreise mit Voreinstellung</th><td>{{ heating.circuits | length }} (siehe Hydraulik-Dokumentation)</td></tr>
  </table>
</section>

<section class="card">
  <h2>Nachweis und Dokumentation</h2>
  <p><label><input type="checkbox"> Rechnung mit Ausweis der Mehrwertsteuer wurde erstellt</label></p>
  <p><label><input type="checkbox"> Hydraulik-Auslegung dokumentiert (Excel/PDF) und an Bauherrn übergeben</label></p>
  <p><label><input type="checkbox"> Inbetriebnahmeprotokoll wurde erstellt und unterschrieben</label></p>
  <p><label><input type="checkbox"> Wartungsempfehlungen wurden übergeben</label></p>
</section>

<section class="card">
  <h2>Unterschrift</h2>
  <div class="signature-row">
    <div class="signature-box"><strong>Bauherr / Auftraggeber</strong>{{ project.responsible or '____________' }} · Ort, Datum, Unterschrift</div>
    <div class="signature-box"><strong>Fachunternehmen</strong>{{ project.construction_manager or 'Mitra Sanitär GmbH' }} · Ort, Datum, Unterschrift &amp; Stempel</div>
  </div>
</section>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 5. dokumentenindex (05_Allgemein) — Index aller verfügbaren Dokumente
# ───────────────────────────────────────────────────────────────────────────
DOKUMENTENINDEX = _wrap(
    "Dokumentenindex – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Dokumentenindex</h1>
  <p class="hero-sub">Vollständiger Index aller Projektdokumente — gruppiert nach Rollenbereich.</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projekt</span><span class="value">{{ project.name }}</span></div>
    <div class="item"><span class="label">Projekt-Nr.</span><span class="value">{{ project.slug }}</span></div>
    <div class="item"><span class="label">Dokumente</span><span class="value">{{ template_index | length }}</span></div>
    <div class="item"><span class="label">Bereiche</span><span class="value">{{ template_index | map(attribute='category') | unique | list | length }}</span></div>
  </div>
</section>

<div class="kpi-row">
  <div class="kpi-card"><span class="kpi-value">{{ template_index | length }}</span><span class="kpi-label">Dokument-Vorlagen</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ uploads | length }}</span><span class="kpi-label">Hochgeladene Unterlagen</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ totals.section_count }}</span><span class="kpi-label">Bauabschnitte</span></div>
  <div class="kpi-card"><span class="kpi-value">{{ members | length }}</span><span class="kpi-label">Mitglieder</span></div>
</div>

{% set current_cat = namespace(name=None) %}
{% for t in template_index %}
  {% if t.category != current_cat.name %}
    {% if current_cat.name is not none %}</tbody></table></div></section>{% endif %}
    <section class="card">
      <h2>{{ t.category }}</h2>
      <div class="table-wrap"><table><thead><tr><th>Dokument</th><th>Beschreibung</th><th style="width:120px;">Aktion</th></tr></thead><tbody>
    {% set current_cat.name = t.category %}
  {% endif %}
  <tr><td><strong>{{ t.title }}</strong></td><td><code>{{ t.slug }}</code></td>
    <td><a href="/api/templates/{{ t.slug }}/render/{{ project.slug }}">Öffnen</a></td></tr>
{% endfor %}
{% if current_cat.name is not none %}</tbody></table></div></section>{% endif %}

<div class="note info">Diese Liste ist selbst-aktualisierend. Jedes in der Datenbank angelegte Template erscheint hier automatisch.</div>
""",
)


# ───────────────────────────────────────────────────────────────────────────
# 6. projektunterlagen (05_Allgemein) — Liste der hochgeladenen Dateien
# ───────────────────────────────────────────────────────────────────────────
PROJEKTUNTERLAGEN = _wrap(
    "Projektunterlagen – {{ project.name }}",
    r"""
<span class="doc-badge info">Informativ</span>

<section class="hero">
  <h1>Projektunterlagen</h1>
  <p class="hero-sub">Hochgeladene Quelldokumente (Angebote, Excel-Heizungsauslegung, PDFs, Sprachnotizen-Transkripte).</p>
  <div class="hero-grid">
    <div class="item"><span class="label">Projekt</span><span class="value">{{ project.name }}</span></div>
    <div class="item"><span class="label">Bauvorhaben</span><span class="value">{{ project.address or '—' }}</span></div>
    <div class="item"><span class="label">Unterlagen</span><span class="value">{{ uploads | length }}</span></div>
    <div class="item"><span class="label">Stand</span><span class="value">{{ today | de_date }}</span></div>
  </div>
</section>

<section class="card">
  <h2>Übersicht aller Uploads</h2>
  {% if uploads %}
  <div class="table-wrap"><table>
    <thead><tr><th>Dateiname</th><th>Typ</th><th>Hochgeladen am</th></tr></thead>
    <tbody>
      {% for u in uploads %}
      <tr><td><strong>{{ u.filename }}</strong></td><td><code>{{ u.content_type or '—' }}</code></td><td>{{ u.created_at | de_date }}</td></tr>
      {% endfor %}
    </tbody>
  </table></div>
  {% else %}<p class="hero-sub">Noch keine Unterlagen hochgeladen. Über die Projekt-Verwaltung „Uploads" können Dateien zugeordnet werden.</p>{% endif %}
</section>

<section class="card">
  <h2>Kategorien</h2>
  <ul>
    <li><strong>Angebote (ANG-XXX):</strong> Leistungsbeschreibung, Mengen, Preise je Gewerk</li>
    <li><strong>Heizungsauslegung:</strong> Excel/CSV mit Heizkreis-Daten — wird über den Hydraulik-Importer in die Datenbank übernommen</li>
    <li><strong>Briefing &amp; Vorgabedokumente:</strong> Zusammenfassung der Projektanforderungen</li>
    <li><strong>Sprachnotizen:</strong> Tonaufnahmen vom Bauleiter/Obermonteur, automatisch transkribiert</li>
    <li><strong>Fotos:</strong> Foto-Dokumentation der Baustelle (separate Galerie)</li>
  </ul>
</section>

<div class="note info">
  <strong>Hinweis:</strong> Inhalte aus diesen Dateien werden vom Daten-Extraktor automatisch in die strukturierten Domänen (Bauabschnitte, Personal, Material, Risiken, Heizungsdaten) übernommen und erscheinen in den jeweiligen Rolle-Dokumenten.
</div>
""",
)


SEEDS = [
    ("baustellenhinweise",            "01_Monteur",        "Baustellenhinweise",            "Zugang, Schlüsselrollen, Lager, Arbeitszeit, Notfall-Kontakte für die Baustelle."),
    ("tagescheckliste",               "01_Monteur",        "Tagescheckliste",               "Tagesbezogene Checkliste mit Prüfpunkten, Tagesziel, Probleme, Ist-Stunden und Material-Bewegung."),
    ("inbetriebnahmeprotokoll",       "04_Projektleitung", "Inbetriebnahmeprotokoll",       "Anlagenkomponenten, Druckprüfung, Spülung/Befüllung, Funktion/Regelung, Übergabe."),
    ("kfw_fachunternehmererklaerung", "04_Projektleitung", "KfW-Fachunternehmererklärung",  "Bestätigung der ordnungsgemäßen Ausführung gemäß KfW-Förderbedingungen, Hydraulik-Abgleich Verfahren B."),
    ("dokumentenindex",               "05_Allgemein",      "Dokumentenindex",               "Vollständiger, auto-generierter Index aller Projektdokumente gruppiert nach Rolle."),
    ("projektunterlagen",             "05_Allgemein",      "Projektunterlagen",             "Liste aller hochgeladenen Quelldateien (Angebote, Excels, Briefings, Sprachnotizen)."),
]

TEMPLATES_HTML = {
    "baustellenhinweise":            BAUSTELLENHINWEISE,
    "tagescheckliste":               TAGESCHECKLISTE,
    "inbetriebnahmeprotokoll":       INBETRIEBNAHMEPROTOKOLL,
    "kfw_fachunternehmererklaerung": KFW_FACHUNTERNEHMERERKLAERUNG,
    "dokumentenindex":               DOKUMENTENINDEX,
    "projektunterlagen":             PROJEKTUNTERLAGEN,
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
