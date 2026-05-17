"""Tests for ``app.services.generator_runner.build_generation_tasks``.

These tests pin the four mandatory documentation tasks added per
``planung/IMPLEMENTIERUNGSPLAN_V2.md`` Abschnitte 10.2, 10.3, 10.5, 10.6:

* Hydraulischer Abgleich (VdZ)        -> 03_Bauleitung
* Inbetriebnahmeprotokoll (IBN)       -> 04_Projektleitung
* Uebergabe-/Abnahmeprotokoll         -> 05_Allgemein
* Gefaehrdungsbeurteilung / SiGe      -> 03_Bauleitung
"""
from __future__ import annotations

from app.services.generator_runner import GenerationTask, build_generation_tasks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_files(tasks: list[GenerationTask]) -> set[str]:
    """Flatten task -> file list to a flat set for membership checks."""
    out: set[str] = set()
    for task in tasks:
        for filename in task.files:
            out.add(f"{task.folder}/{filename}")
    return out


def _task_for_file(tasks: list[GenerationTask], file_name: str) -> GenerationTask:
    for task in tasks:
        if file_name in task.files:
            return task
    raise AssertionError(f"No task produces {file_name!r}; got tasks: {[t.label for t in tasks]}")


# ---------------------------------------------------------------------------
# Standard project: all four mandatory docs must be planned
# ---------------------------------------------------------------------------


def test_standard_plan_contains_all_four_mandatory_docs() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    files = _all_files(tasks)

    assert "03_Bauleitung/BAULEITUNG_Hydraulischer_Abgleich.html" in files
    assert "04_Projektleitung/PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html" in files
    assert "05_Allgemein/ALLGEMEIN_Uebergabeprotokoll.html" in files
    assert "03_Bauleitung/BAULEITUNG_Gefaehrdungsbeurteilung.html" in files


def test_standard_plan_has_dedicated_task_labels_for_each_mandatory_doc() -> None:
    """Each mandatory doc gets its own task so the prompt can be tightly scoped
    and so the generator can dispatch them in parallel against any provider."""
    tasks = build_generation_tasks("standard", section_count=3)
    labels = {task.label for task in tasks}

    assert "03_Bauleitung_Hydraulischer_Abgleich" in labels
    assert "04_Projektleitung_Inbetriebnahmeprotokoll" in labels
    assert "05_Allgemein_Uebergabeprotokoll" in labels
    assert "03_Bauleitung_Gefaehrdungsbeurteilung" in labels


def test_standard_plan_mandatory_tasks_are_not_marked_final() -> None:
    """Final tasks run sequentially after the parallel batch; mandatory
    docs must run in the parallel batch so the navigation step (the only
    ``final`` task) can already link to them."""
    tasks = build_generation_tasks("standard", section_count=3)
    mandatory_labels = {
        "03_Bauleitung_Hydraulischer_Abgleich",
        "04_Projektleitung_Inbetriebnahmeprotokoll",
        "05_Allgemein_Uebergabeprotokoll",
        "03_Bauleitung_Gefaehrdungsbeurteilung",
    }
    for task in tasks:
        if task.label in mandatory_labels:
            assert not task.final, f"Mandatory doc task {task.label} must not be final"


# ---------------------------------------------------------------------------
# Small project: IBN + Uebergabe always, SiGe never, Hydraulik only on demand
# ---------------------------------------------------------------------------


def test_small_plan_contains_ibn_and_uebergabe_but_not_sige() -> None:
    tasks = build_generation_tasks("small", section_count=1)
    files = _all_files(tasks)

    assert "04_Projektleitung/PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html" in files
    assert "05_Allgemein/ALLGEMEIN_Uebergabeprotokoll.html" in files
    # SiGe / Gefaehrdungsbeurteilung must NOT appear for small projects.
    assert "03_Bauleitung/BAULEITUNG_Gefaehrdungsbeurteilung.html" not in files


def test_small_plan_omits_hydraulic_balance_by_default() -> None:
    tasks = build_generation_tasks("small", section_count=1)
    files = _all_files(tasks)
    assert "03_Bauleitung/BAULEITUNG_Hydraulischer_Abgleich.html" not in files


def test_small_plan_includes_hydraulic_balance_when_heating_design_present() -> None:
    tasks = build_generation_tasks(
        "small", section_count=1, has_heating_design=True
    )
    files = _all_files(tasks)
    assert "03_Bauleitung/BAULEITUNG_Hydraulischer_Abgleich.html" in files


# ---------------------------------------------------------------------------
# Prompt content: each mandatory task's prompt must mention its target file
# and the hydraulic-balance prompt must reference heating_design.json.
# ---------------------------------------------------------------------------


def test_each_mandatory_prompt_references_its_target_filename() -> None:
    tasks = build_generation_tasks("standard", section_count=3)

    for filename, expected_folder in [
        ("BAULEITUNG_Hydraulischer_Abgleich.html", "03_Bauleitung"),
        ("PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html", "04_Projektleitung"),
        ("ALLGEMEIN_Uebergabeprotokoll.html", "05_Allgemein"),
        ("BAULEITUNG_Gefaehrdungsbeurteilung.html", "03_Bauleitung"),
    ]:
        task = _task_for_file(tasks, filename)
        assert task.folder == expected_folder
        assert filename in task.prompt, (
            f"Prompt for {filename!r} does not mention its filename. "
            f"Got prompt head: {task.prompt[:200]!r}"
        )


def test_hydraulic_balance_prompt_references_heating_design_json() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(tasks, "BAULEITUNG_Hydraulischer_Abgleich.html")

    assert "heating_design.json" in task.prompt, (
        "Hydraulischer-Abgleich-Prompt must point the model at heating_design.json"
    )
    # The prompt must also describe the VdZ Verfahren B context — that's the
    # whole point of this task.
    assert "VdZ" in task.prompt


def test_hydraulic_balance_prompt_handles_missing_heating_design_gracefully() -> None:
    """The prompt must instruct the model to flag missing data instead of
    fabricating heating-circuit rows."""
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(tasks, "BAULEITUNG_Hydraulischer_Abgleich.html")

    lowered = task.prompt.lower()
    assert "offene punkte" in lowered
    # Either an explicit "wenn ... nicht existiert" or "leer" clause must be
    # present so the prompt clearly tells the model what to do.
    assert ("nicht existiert" in lowered) or ("leer" in lowered)


def test_ibn_prompt_includes_signature_fields() -> None:
    """The IBN protocol must reserve two signature boxes for the signature
    pad (frontend feature 10.8). If this drifts, downstream stops working."""
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(tasks, "PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html")

    assert "Unterschrift Kunde" in task.prompt
    assert "Unterschrift Monteur" in task.prompt


def test_handover_prompt_references_bgb_640() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(tasks, "ALLGEMEIN_Uebergabeprotokoll.html")
    assert "BGB" in task.prompt
    assert "640" in task.prompt


def test_risk_assessment_prompt_lists_typical_shk_risks() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(tasks, "BAULEITUNG_Gefaehrdungsbeurteilung.html")

    lowered = task.prompt.lower()
    # A reasonable subset of the documented SHK risk catalogue must appear.
    for keyword in ("gas", "asbest", "absturz", "elektro"):
        assert keyword in lowered, f"Risk keyword {keyword!r} missing from SiGe prompt"


# ---------------------------------------------------------------------------
# Print-CSS hint lives in the per-task prompt, NOT in the global rules.
# ---------------------------------------------------------------------------


def test_mandatory_doc_prompts_include_print_css_hint() -> None:
    """Per project guidance the Print-CSS rules (A4, 20mm, 11pt,
    page-break-inside avoid) are repeated in each mandatory doc prompt so
    the dispatched LLM gets them in-context regardless of how ``_BASE_RULES``
    evolves (the parallel PDF-export agent owns that file too)."""
    tasks = build_generation_tasks("standard", section_count=3)
    for filename in (
        "BAULEITUNG_Hydraulischer_Abgleich.html",
        "PROJEKTLEITUNG_Inbetriebnahmeprotokoll.html",
        "ALLGEMEIN_Uebergabeprotokoll.html",
        "BAULEITUNG_Gefaehrdungsbeurteilung.html",
        "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html",
    ):
        task = _task_for_file(tasks, filename)
        assert "A4" in task.prompt
        assert "20mm" in task.prompt
        assert "page-break-inside" in task.prompt


# ---------------------------------------------------------------------------
# KfW-Fachunternehmererklaerung (IMPLEMENTIERUNGSPLAN_V2 10.4)
# ---------------------------------------------------------------------------


def test_standard_plan_contains_kfw_fachunternehmererklaerung() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    files = _all_files(tasks)
    assert (
        "04_Projektleitung/PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html"
        in files
    )


def test_small_plan_always_contains_kfw_fachunternehmererklaerung() -> None:
    """Kleinprojekte (Etagenheizung etc.) werden ebenfalls oft ueber KfW
    gefoerdert; das Dokument ist daher auch im Small-Plan IMMER dabei."""
    tasks = build_generation_tasks("small", section_count=1)
    files = _all_files(tasks)
    assert (
        "04_Projektleitung/PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html"
        in files
    )


def test_kfw_task_has_dedicated_label_and_is_not_final() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    labels = {task.label for task in tasks}
    assert "04_Projektleitung_KfW_Fachunternehmererklaerung" in labels
    task = _task_for_file(tasks, "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html")
    assert not task.final


def test_kfw_prompt_references_hydraulic_balance_anhang() -> None:
    """Die KfW-FUE muss in ihrem Prompt explizit den hydraulischen Abgleich
    referenzieren — beides ist KfW-foerderrelevant verkettet."""
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(
        tasks, "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html"
    )
    lowered = task.prompt.lower()
    assert "hydraulischen abgleich" in lowered or "hydraulischer abgleich" in lowered
    # Verweis auf die Schwester-Datei (Anhang)
    assert "BAULEITUNG_Hydraulischer_Abgleich.html" in task.prompt


def test_kfw_prompt_mentions_kfw_and_beg_em() -> None:
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(
        tasks, "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html"
    )
    assert "KfW" in task.prompt
    assert "BEG-EM" in task.prompt
    # Vordruck-Hinweis (152/430) sollte ebenfalls vorkommen.
    assert "152" in task.prompt and "430" in task.prompt


def test_kfw_prompt_handles_missing_applicant_data_gracefully() -> None:
    """Wenn Antragsteller-Daten in input.json fehlen, MUSS der Prompt die
    Anweisung enthalten, sie als Offene Punkte auszuweisen statt zu erfinden."""
    tasks = build_generation_tasks("standard", section_count=3)
    task = _task_for_file(
        tasks, "PROJEKTLEITUNG_KfW_Fachunternehmererklaerung.html"
    )
    lowered = task.prompt.lower()
    assert "offene punkte" in lowered
    assert "input.json" in lowered
