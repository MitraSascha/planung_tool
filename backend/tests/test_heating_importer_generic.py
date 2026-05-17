"""Unit tests for the generic Excel/CSV heating-design importer.

The importer must handle real-world quirks that we have observed in
external architect deliverables:
  * meta-data rows above the actual table,
  * arbitrary column ordering and unusual headers,
  * mixed unit suffixes ("[W]", "[kg/h]", "[mbar]", ...),
  * users overriding the auto-detected mapping via the preview UI,
  * empty / garbage uploads that must fail loudly.
"""
from __future__ import annotations

import io

import pytest

from app.services.heating_importers import (
    ColumnMapping,
    HeatingImporterError,
)
from app.services.heating_importers.generic_table import (
    GenericTableImporter,
    _convert_value,
    fuzzy_match_canonical,
    normalize_header,
)


# ----------------------------------------------------------------------
# normalize_header / fuzzy_match_canonical
# ----------------------------------------------------------------------


def test_normalize_header_strips_unit_brackets():
    assert normalize_header("Heizlast [W]") == "heizlast"
    assert normalize_header("Volumenstrom (l/h)") == "volumenstrom"
    assert normalize_header("Druckverlust {mbar}") == "druckverlust"


def test_normalize_header_replaces_umlauts():
    assert normalize_header("Rohrlänge") == "rohrlange"
    assert normalize_header("Räume") == "raume"
    assert normalize_header("Heizkörper-Typ") == "heizkorpertyp"
    assert normalize_header("Größe") == "grosse"


def test_normalize_header_handles_empty_and_none():
    assert normalize_header("") == ""
    assert normalize_header(None) == ""  # type: ignore[arg-type]
    assert normalize_header("   ") == ""


def test_fuzzy_match_finds_canonical_for_common_headers():
    assert fuzzy_match_canonical("Heizlast [W]")[0] == "heat_load_w"
    assert fuzzy_match_canonical("Durchfluss [kg/h]")[0] == "volume_flow_lph"
    assert fuzzy_match_canonical("Druckverlust [mbar]")[0] == "pressure_drop_pa"
    assert fuzzy_match_canonical("Rohrlänge [m]")[0] == "pipe_length_m"
    assert fuzzy_match_canonical("Voreinstellwert")[0] == "valve_preset"
    assert fuzzy_match_canonical("Raumbezeichnung")[0] == "room"
    assert fuzzy_match_canonical("Strang")[0] == "strand"
    assert fuzzy_match_canonical("Etage")[0] == "floor"
    assert fuzzy_match_canonical("Ventiltyp")[0] == "valve_type"
    assert fuzzy_match_canonical("kv-Wert")[0] == "kv_value"
    assert fuzzy_match_canonical("Bemerkung")[0] == "notes"


def test_fuzzy_match_returns_none_for_unrelated_headers():
    # Clearly unrelated strings must not score above the 0.5 cutoff.
    canonical, score = fuzzy_match_canonical("XYZ123")
    assert canonical is None
    assert score < 0.5


def test_fuzzy_match_score_is_higher_for_exact_match():
    _exact, exact_score = fuzzy_match_canonical("Heizlast")
    _typo, typo_score = fuzzy_match_canonical("Heizlast Norm")
    assert exact_score >= typo_score


# ----------------------------------------------------------------------
# _convert_value (unit conversion)
# ----------------------------------------------------------------------


def test_convert_kw_to_w():
    value, warning = _convert_value("heat_load_w", "1.2", "kW")
    assert value == pytest.approx(1200.0)
    assert warning is None


def test_convert_mbar_to_pa():
    value, _warn = _convert_value("pressure_drop_pa", "120", "mbar")
    assert value == pytest.approx(12_000.0)


def test_convert_hpa_to_pa():
    value, _warn = _convert_value("pressure_drop_pa", "5", "hPa")
    assert value == pytest.approx(500.0)


def test_convert_cm_to_m():
    value, _warn = _convert_value("pipe_length_m", "350", "cm")
    assert value == pytest.approx(3.5)


def test_convert_mm_to_m():
    value, _warn = _convert_value("pipe_length_m", "1500", "mm")
    assert value == pytest.approx(1.5)


def test_convert_m3h_to_lph():
    value, _warn = _convert_value("volume_flow_lph", "0.5", "m3/h")
    assert value == pytest.approx(500.0)


def test_convert_unknown_unit_emits_warning():
    value, warning = _convert_value("heat_load_w", "1000", "BTU/h")
    assert value == 1000.0
    assert warning is not None
    assert "BTU/h" in warning


def test_convert_handles_german_decimal_comma():
    value, _warn = _convert_value("heat_load_w", "1.234,5", "W")
    assert value == pytest.approx(1234.5)


def test_convert_handles_english_thousand_separator():
    value, _warn = _convert_value("heat_load_w", "1,234.5", "W")
    assert value == pytest.approx(1234.5)


def test_convert_non_numeric_returns_warning():
    value, warning = _convert_value("heat_load_w", "abc", "W")
    assert value is None
    assert warning is not None


def test_convert_keeps_string_fields_intact():
    value, warning = _convert_value("room", "Wohnzimmer", None)
    assert value == "Wohnzimmer"
    assert warning is None


def test_convert_empty_value_is_none():
    assert _convert_value("heat_load_w", "", "W") == (None, None)
    assert _convert_value("heat_load_w", None, "W") == (None, None)


# ----------------------------------------------------------------------
# parse() — CSV
# ----------------------------------------------------------------------


def test_parse_csv_with_meta_rows_and_semicolon_delimiter():
    csv_bytes = (
        "Projekt: Beispiel-MFH\n"
        "Vorlauf: 55 C\n"
        "Ruecklauf: 45 C\n"
        "Pumpe: Grundfos Alpha2\n"
        "Strang;Raum;Etage;Heizlast [W];Durchfluss [l/h];Druckverlust [mbar];Voreinstellung\n"
        "S1;Wohnzimmer;EG;1200;52;45;2\n"
        "S1;Bad;EG;800;35;30;1.5\n"
        "S2;Schlafzimmer;OG;950;41;38;2\n"
        "S2;Kinderzimmer;OG;900;38;36;2\n"
        "S3;Buero;DG;700;30;25;1.5\n"
    ).encode("utf-8")

    preview = GenericTableImporter().parse("strang_extern.csv", csv_bytes)

    assert preview.source == "generic_table"
    assert preview.source_file == "strang_extern.csv"
    assert len(preview.circuits) == 5
    # Auto-detection: every canonical field that the headers cover.
    assert preview.detected_columns["heat_load_w"] == "Heizlast [W]"
    assert preview.detected_columns["volume_flow_lph"] == "Durchfluss [l/h]"
    assert preview.detected_columns["pressure_drop_pa"] == "Druckverlust [mbar]"
    assert preview.detected_columns["strand"] == "Strang"
    assert preview.detected_columns["room"] == "Raum"
    # Unit conversion: mbar -> Pa.
    assert preview.circuits[0].pressure_drop_pa == pytest.approx(4_500.0)
    # Plant metadata harvested from the leading rows.
    assert preview.design.supply_temp_c == 55.0
    assert preview.design.return_temp_c == 45.0
    assert preview.design.delta_t_k == pytest.approx(10.0)
    assert preview.design.pump_model == "Grundfos Alpha2"


def test_parse_csv_with_comma_delimiter_and_utf8_bom():
    csv_bytes = (
        "﻿"
        "Strang,Raum,Heizlast [W],Volumenstrom [l/h],Voreinstellwert\n"
        "S1,Wohnzimmer,1200,52,2\n"
        "S1,Bad,800,35,1.5\n"
        "S2,Schlafzimmer,950,41,2\n"
    ).encode("utf-8")

    preview = GenericTableImporter().parse("export.csv", csv_bytes)
    assert len(preview.circuits) == 3
    assert preview.circuits[0].strand == "S1"
    assert preview.circuits[0].heat_load_w == 1200.0


# ----------------------------------------------------------------------
# parse() — XLSX
# ----------------------------------------------------------------------


def _xlsx_bytes(rows: list[list]) -> bytes:
    """Build an in-memory .xlsx file from a list of row-lists."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def test_parse_xlsx_with_unusual_column_order():
    rows = [
        ["Berechnung: Strangtabelle"],
        ["Vorlauftemperatur: 60 C"],
        ["Ruecklauftemperatur: 50 C"],
        [],  # blank
        # Header row deliberately in an unusual order, with mixed units:
        [
            "Voreinstellung",
            "Druckverlust [hPa]",
            "Bemerkung",
            "Raumbezeichnung",
            "Q [kW]",
            "Massenstrom [kg/h]",
            "Strang",
            "Rohrlänge [m]",
        ],
        ["2", "5", "lautes Ventil", "Wohnzimmer", "1.2", "52", "S1", "8.5"],
        ["1.5", "3", "", "Bad", "0.8", "35", "S1", "5.2"],
        ["2", "4", "", "Schlafzimmer", "0.95", "41", "S2", "7.0"],
    ]

    preview = GenericTableImporter().parse("test.xlsx", _xlsx_bytes(rows))

    assert len(preview.circuits) == 3
    # kW -> W conversion.
    assert preview.circuits[0].heat_load_w == pytest.approx(1200.0)
    # hPa -> Pa conversion.
    assert preview.circuits[0].pressure_drop_pa == pytest.approx(500.0)
    # kg/h treated as l/h for water (vereinfacht).
    assert preview.circuits[0].volume_flow_lph == pytest.approx(52.0)
    # Notes column is non-empty for the first row.
    assert preview.circuits[0].notes == "lautes Ventil"
    # detected_columns reflects the auto-detection:
    assert preview.detected_columns["heat_load_w"] == "Q [kW]"
    assert preview.detected_columns["volume_flow_lph"] == "Massenstrom [kg/h]"
    assert preview.detected_columns["pressure_drop_pa"] == "Druckverlust [hPa]"
    assert preview.detected_columns["valve_preset"] == "Voreinstellung"
    # Metadata harvested.
    assert preview.design.supply_temp_c == 60.0
    assert preview.design.return_temp_c == 50.0


def test_parse_xlsx_with_explicit_mapping_overrides_auto_detection():
    rows = [
        ["KreisNr", "BezeichnungLang", "WattWert", "DurchflussZahl"],
        ["A1", "Treppenhaus", "1500", "70"],
        ["A2", "Foyer", "2000", "90"],
    ]
    # The auto-detector will not match these obscure headers — pass an
    # explicit mapping so the user-corrected UI flow is exercised.
    mapping = ColumnMapping(
        circuit_columns={
            "strand": "KreisNr",
            "room": "BezeichnungLang",
            "heat_load_w": "WattWert",
            "volume_flow_lph": "DurchflussZahl",
        },
    )

    preview = GenericTableImporter().parse(
        "obscure.xlsx", _xlsx_bytes(rows), mapping=mapping
    )
    # The explicit mapping has to override whatever auto-detection produced.
    assert preview.detected_columns == mapping.circuit_columns
    assert len(preview.circuits) == 2
    assert preview.circuits[0].strand == "A1"
    assert preview.circuits[0].room == "Treppenhaus"
    assert preview.circuits[0].heat_load_w == 1500.0
    assert preview.circuits[1].volume_flow_lph == 90.0


def test_parse_xlsx_with_explicit_mapping_warns_for_missing_columns():
    rows = [
        ["Strang", "Raum", "Heizlast [W]"],
        ["S1", "Bad", "800"],
    ]
    mapping = ColumnMapping(
        circuit_columns={
            "strand": "Strang",
            "room": "Raum",
            "heat_load_w": "Heizlast [W]",
            "pipe_length_m": "TotalNonExistentColumn",
        },
    )
    preview = GenericTableImporter().parse(
        "x.xlsx", _xlsx_bytes(rows), mapping=mapping
    )
    assert any(
        "TotalNonExistentColumn" in w for w in preview.warnings
    ), preview.warnings


# ----------------------------------------------------------------------
# Failure modes
# ----------------------------------------------------------------------


def test_parse_empty_file_raises():
    with pytest.raises(HeatingImporterError):
        GenericTableImporter().parse("empty.csv", b"")


def test_parse_garbage_file_raises():
    # No row contains 3+ recognisable headers.
    garbage = (
        b"foo,bar,baz\n"
        b"1,2,3\n"
        b"4,5,6\n"
    )
    with pytest.raises(HeatingImporterError):
        GenericTableImporter().parse("garbage.csv", garbage)


def test_parse_warns_about_unmapped_columns():
    csv_bytes = (
        "Strang;Raum;Heizlast [W];Durchfluss [l/h];Voreinstellung;Lieferdatum\n"
        "S1;Wohnzimmer;1200;52;2;2026-01-15\n"
        "S2;Bad;800;35;1.5;2026-01-15\n"
    ).encode("utf-8")
    preview = GenericTableImporter().parse("x.csv", csv_bytes)
    assert any("Lieferdatum" in w for w in preview.warnings)


def test_can_handle_recognizes_extensions():
    imp = GenericTableImporter()
    assert imp.can_handle("strang.xlsx", b"") is True
    assert imp.can_handle("strang.xls", b"") is True
    assert imp.can_handle("strang.csv", b"") is True
    assert imp.can_handle("STRANG.CSV", b"") is True
    assert imp.can_handle("plan.pdf", b"") is False
