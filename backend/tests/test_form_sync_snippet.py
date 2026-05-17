"""Lightweight tests for the HTML snippet injector — checks placement
and idempotency, not the actual JS behaviour (the script runs in the
browser; integration testing belongs to the e2e harness)."""
from __future__ import annotations

from app.services.form_sync_snippet import FORM_SYNC_SNIPPET, inject_form_sync_snippet


def test_snippet_inserted_before_body_close():
    html = "<html><head></head><body><p>hi</p></body></html>"
    out = inject_form_sync_snippet(html)
    assert "<script>" in out
    assert out.index(FORM_SYNC_SNIPPET) < out.lower().index("</body>")
    # Original body content stays intact.
    assert "<p>hi</p>" in out


def test_snippet_appended_when_no_body_close():
    html = "<p>fragment without proper body</p>"
    out = inject_form_sync_snippet(html)
    assert out.startswith(html)
    assert FORM_SYNC_SNIPPET in out


def test_snippet_case_insensitive_body_match():
    html = "<HTML><BODY>x</BODY></HTML>"
    out = inject_form_sync_snippet(html)
    # Snippet must sit *before* the closing body, even if uppercase.
    assert out.lower().index("</body>") > out.index(FORM_SYNC_SNIPPET)


def test_snippet_only_inserted_once_per_call():
    html = "<html><body>x</body></html>"
    out1 = inject_form_sync_snippet(html)
    assert out1.count(FORM_SYNC_SNIPPET) == 1
