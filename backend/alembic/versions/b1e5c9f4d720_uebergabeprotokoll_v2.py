"""uebergabeprotokoll v2 — persistente Felder, Goal-Bullets, Foto-Galerie

Revision ID: b1e5c9f4d720
Revises: a8e4b2f1c635
Create Date: 2026-05-18 16:00:00.000000

Drei Fixes am Übergabeprotokoll-Template:

1. Mängelliste + Vorbehalts-Tabelle: jede ``<td contenteditable>``-Zelle
   bekommt ein eindeutiges ``data-field-id``. Damit greift der zur Laufzeit
   injizierte form-sync-snippet und persistiert die Eingaben über
   ``/api/projects/{slug}/form-responses/<doc>``. Vorher gingen alle
   Eingaben beim Reload verloren.

   Field-ID Konvention: ``allgemein.uebergabe.<bereich>.r<n>.<feld>``

2. Leistungsbeschreibung: ``section.goal`` wird durch den neuen
   ``bullets``-Filter geschoben, der ``- ``-Bindestrich-Listen in echte
   ``<ul><li>…</li></ul>`` umwandelt statt sie als Rohtext ins ``<li>``
   zu kippen.

3. Foto-Galerie-Sektion: rendert ``photos_by_section`` aus dem
   Render-Context (siehe Renderer-Änderung im gleichen Patch). Damit ist
   der bisher offene Punkt „Foto-Dokumentation einbetten" erledigt.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "b1e5c9f4d720"
down_revision: Union[str, None] = "a8e4b2f1c635"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Kopiert aus f3a8c2e6d109_mitra_branded_templates.py — selbst-enthaltend,
# damit die Migration nicht von externen Helpern abhängt.
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


_BODY = r"""
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
    <div><label>Datum der Abnahme *</label><input type="date" data-field-id="allgemein.uebergabe.abnahme.datum" required></div>
    <div><label>Abnahme erfolgt durch</label><input type="text" data-field-id="allgemein.uebergabe.abnahme.erfolgt_durch" placeholder="{{ project.responsible or 'Auftraggeber' }}"></div>
  </div>
  <div class="note info"><strong>Rechtlicher Hinweis:</strong> Mit Unterschrift beginnt die Gewährleistungsfrist gemäß BGB § 634a.</div>
</section>

<section class="card">
  <h2>Leistungsbeschreibung</h2>
  <p>Die nachstehenden Punkte sind aus den im Projekt hinterlegten Bauabschnitten abgeleitet und beschreiben die zur Abnahme vorgelegten Leistungen je Abschnitt.</p>
  {% for s in sections %}
  <div class="abschnitt-card">
    <div class="abschnitt-head"><span class="abschnitt-num">{{ s.number }}</span><h3>{{ s.name }}</h3></div>
    {{ s.goal | bullets }}
  </div>
  {% endfor %}
</section>

{% if photos %}
<section class="card">
  <h2>Foto-Dokumentation</h2>
  <p>Bilder aus dem Projekt — gruppiert nach Bauabschnitt. Quelle: Foto-Galerie der Mitra-App.</p>
  {% for s in sections %}
    {% set sec_photos = photos_by_section.get(s.number, []) %}
    {% if sec_photos %}
    <h3>Abschnitt {{ s.number }} – {{ s.name }}</h3>
    <div class="photo-grid">
      {% for p in sec_photos %}
      <figure class="photo-tile">
        <a href="{{ p.annotated_url or p.view_url }}" target="_blank" rel="noopener">
          <img src="{{ p.view_url }}" alt="{{ p.caption or p.filename }}" loading="lazy">
        </a>
        {% if p.caption %}<figcaption>{{ p.caption }}</figcaption>{% endif %}
      </figure>
      {% endfor %}
    </div>
    {% endif %}
  {% endfor %}
  {% set unassigned = photos_by_section.get(None, []) %}
  {% if unassigned %}
  <h3>Ohne Abschnittszuordnung</h3>
  <div class="photo-grid">
    {% for p in unassigned %}
    <figure class="photo-tile">
      <a href="{{ p.annotated_url or p.view_url }}" target="_blank" rel="noopener">
        <img src="{{ p.view_url }}" alt="{{ p.caption or p.filename }}" loading="lazy">
      </a>
      {% if p.caption %}<figcaption>{{ p.caption }}</figcaption>{% endif %}
    </figure>
    {% endfor %}
  </div>
  {% endif %}
</section>
<style>
  .photo-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; margin: 10px 0 18px; }
  .photo-tile { margin: 0; background: #fafbfc; border: 1px solid var(--card-border); border-radius: var(--radius-sm); overflow: hidden; }
  .photo-tile a { display: block; border: none; }
  .photo-tile img { width: 100%; height: 140px; object-fit: cover; display: block; }
  .photo-tile figcaption { padding: 6px 10px; font-size: 12px; color: var(--text-muted); border-top: 1px solid var(--card-border); }
  @media print { .photo-tile img { height: auto; max-height: 200px; } .photo-grid { grid-template-columns: repeat(3, 1fr); gap: 8px; } }
</style>
{% endif %}

<section class="card">
  <h2>Mängelliste und Restleistungen</h2>
  <h3>Festgestellte Punkte bei der Abnahme</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>Bereich / Abschnitt</th><th>Festgestellter Mangel oder Restleistung</th><th style="width:200px;">Frist / Verantwortlich</th></tr></thead>
    <tbody>{% for n in range(1, 5) %}<tr>
      <td contenteditable="true" data-field-id="allgemein.uebergabe.maengel.r{{ n }}.bereich">&nbsp;</td>
      <td contenteditable="true" data-field-id="allgemein.uebergabe.maengel.r{{ n }}.mangel">&nbsp;</td>
      <td contenteditable="true" data-field-id="allgemein.uebergabe.maengel.r{{ n }}.frist">&nbsp;</td>
    </tr>{% endfor %}</tbody>
  </table></div>
</section>

<section class="card">
  <h2>Vorbehalte</h2>
  <h3>Hinweise des Kunden oder der Bauleitung</h3>
  <div class="table-wrap"><table>
    <thead><tr><th>Vorbehalt</th><th>Bezug / Begründung</th></tr></thead>
    <tbody>{% for n in range(1, 4) %}<tr>
      <td contenteditable="true" data-field-id="allgemein.uebergabe.vorbehalt.r{{ n }}.text">&nbsp;</td>
      <td contenteditable="true" data-field-id="allgemein.uebergabe.vorbehalt.r{{ n }}.begruendung">&nbsp;</td>
    </tr>{% endfor %}</tbody>
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
    <li>Konkrete Termin-/Fristzusagen für Restleistungen sind festzulegen.</li>
  </ul>
</div>
"""


UEBERGABEPROTOKOLL_HTML = (
    _HEAD.replace("{TITLE}", "Übergabeprotokoll – {{ project.name }}")
    + _BODY
    + _FOOT
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE document_templates
        SET html_template = $body${UEBERGABEPROTOKOLL_HTML}$body$,
            version = version + 1
        WHERE slug = 'uebergabeprotokoll';
        """
    )


def downgrade() -> None:
    # Vorgängerversion ist in f3a8c2e6d109 abgelegt; ein verbatim-Restore
    # ist hier nicht praktikabel. Nur Version dekrementieren, damit ein
    # erneutes upgrade die Migration wieder anwendet.
    op.execute(
        "UPDATE document_templates SET version = version - 1 "
        "WHERE slug = 'uebergabeprotokoll';"
    )
