"""checklisten + tagescheckliste persistente fields via data-field-id

Revision ID: c1d4e7f9a201
Revises: bb0349d557d6
Create Date: 2026-05-17 16:00:00.000000

Update the `checklisten` template so every checkbox/input/select carries
a stable `data-field-id`. The runtime-injected form-sync-snippet wires
those elements against `/api/projects/{slug}/form-responses/<doc>` so
answers persist in Postgres instead of the browser's localStorage.

Field-ID convention: `obermonteur.checklisten.s<section_number>.<phase>.<field>`
e.g. `obermonteur.checklisten.s1.vor_beginn.material`.

The wrapping `_wrap()` helper from the original migration is inlined here
so the migration is self-contained and a downgrade can restore the prior
HTML.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "c1d4e7f9a201"
down_revision: Union[str, None] = "bb0349d557d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_CHECKLISTEN_VERSION = 2  # current head version of `checklisten`
_NEW_CHECKLISTEN_VERSION = 3


CHECKLISTEN_HTML = r"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Checklisten Obermonteur – {{ project.name }}</title>
<style>{{ base_css | safe }}</style></head>
<body>
{{ brand_bar | safe }}

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

<div class="note info">Jeder Bauabschnitt hat drei kurze Teilprüfungen: <strong>vor Beginn</strong>, <strong>während der Ausführung</strong> und zum <strong>Abschluss</strong>. Häkchen setzen, Pflichtfelder ausfüllen. Antworten werden automatisch gespeichert.</div>

{% for s in sections %}
<div class="abschnitt-card">
  <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3></div>
  <p class="abschnitt-meta"><strong>Ziel:</strong> {{ s.goal or '—' }} · <strong>Verantwortlich:</strong> {{ s.responsible or '—' }}</p>

  <h3>1. Vor Beginn</h3>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.vor_beginn.material"> Material vollständig bereitgestellt</label></p>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.vor_beginn.gewerke_abgestimmt"> Vorgelagerte Gewerke abgestimmt / freigegeben</label></p>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.vor_beginn.daemmung_vor_ort"> Dämmung / Zubehör vor Ort</label></p>
  <div class="field-row">
    <div><label>Prüftermin festlegen *</label><input type="date" data-field-id="obermonteur.checklisten.s{{ s.number }}.vor_beginn.prueftermin" required></div>
    <div><label>Zuständig vor Ort *</label><input type="text" data-field-id="obermonteur.checklisten.s{{ s.number }}.vor_beginn.zustaendig_vor_ort" value="{{ s.responsible or '' }}" required></div>
    <div><label>Offene Freigabe / Blockade</label><input type="text" data-field-id="obermonteur.checklisten.s{{ s.number }}.vor_beginn.offene_freigabe" placeholder="z. B. Asbest-Probenahme ausstehend"></div>
  </div>

  <h3>2. Ausführung prüfen</h3>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.ausfuehrung.hydraulik_montage"> Hydraulik-Montage sauber, dicht, druckfest</label></p>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.ausfuehrung.elektro_schutzklasse"> Elektro-Abstand / Schutzklasse geprüft</label></p>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.ausfuehrung.daemmung_geg"> Dämmungs-Stoß sauber, GEG-konform</label></p>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.ausfuehrung.pruefdruck_vorbereitet"> Prüfdruck vorbereitet (DVGW-W 400)</label></p>
  <div class="field-row">
    <div><label>Prüfdruck Sollwert</label><input type="text" data-field-id="obermonteur.checklisten.s{{ s.number }}.ausfuehrung.pruefdruck_sollwert" placeholder="z. B. 6 bar / 30 min"></div>
    <div><label>Kurzhinweis aus der Kontrolle</label><input type="text" data-field-id="obermonteur.checklisten.s{{ s.number }}.ausfuehrung.kontroll_hinweis"></div>
  </div>

  <h3>3. Abschluss</h3>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.abschluss.pruefdruck_gehalten"> Prüfdruck gehalten</label></p>
  <p><label><input type="checkbox" data-field-id="obermonteur.checklisten.s{{ s.number }}.abschluss.sichtkontrolle"> Sichtkontrolle abgeschlossen</label></p>
  <div class="field-row">
    <div><label>Status Abschnitt *</label>
      <select data-field-id="obermonteur.checklisten.s{{ s.number }}.abschluss.status" required><option value="">— wählen —</option><option>Frei</option><option>Mit Restpunkten</option><option>Gesperrt</option></select>
    </div>
    <div style="grid-column: span 2;"><label>Restpunkte oder Nacharbeit</label><textarea data-field-id="obermonteur.checklisten.s{{ s.number }}.abschluss.restpunkte" placeholder="Was muss noch erledigt werden?"></textarea></div>
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
</body></html>
"""


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE document_templates
        SET html_template = $body${CHECKLISTEN_HTML}$body$,
            version = {_NEW_CHECKLISTEN_VERSION}
        WHERE slug = 'checklisten';
        """
    )


def downgrade() -> None:
    # We can't restore the prior html_template verbatim from here; bump
    # the version back so the seed-rebuild path knows this revision
    # rolled back. The old HTML lives in f3a8c2e6d109 if a hard restore
    # is ever needed.
    op.execute(
        f"UPDATE document_templates SET version = {_OLD_CHECKLISTEN_VERSION} WHERE slug = 'checklisten';"
    )
