"""Tests for ``app.services.pdf_export``.

WeasyPrint pulls in heavy system libraries (pango, cairo, gdk-pixbuf,
harfbuzz). On dev machines without those libraries the import fails at
the C-extension boundary; in that case we skip these tests rather than
fail the entire suite, because the production image (Dockerfile) does
install them.
"""
from __future__ import annotations

from pathlib import Path

import pytest


# ``weasyprint`` itself imports cffi-bound shared libraries at module-load
# time; if any of them are missing we want a clean skip, not a collection
# error.
weasyprint = pytest.importorskip(
    "weasyprint",
    reason="WeasyPrint is not installed in this test environment. "
    "Install 'weasyprint' and system libs (pango, cairo, gdk-pixbuf, harfbuzz).",
)

from app.services.pdf_export import (  # noqa: E402  (after importorskip)
    PdfRenderError,
    default_print_css,
    render_html_to_pdf,
)


MINIMAL_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>PDF Export Test</title>
</head>
<body>
  <h1>Inbetriebnahmeprotokoll</h1>
  <p>Dieses Dokument testet den PDF-Export.</p>
  <table>
    <thead><tr><th>Pos</th><th>Wert</th></tr></thead>
    <tbody>
      <tr><td>Druck</td><td>2,5 bar</td></tr>
      <tr><td>Temperatur</td><td>65 &deg;C</td></tr>
    </tbody>
  </table>
</body>
</html>
"""


def test_render_html_to_pdf_returns_pdf_bytes(tmp_path: Path) -> None:
    html_path = tmp_path / "doc.html"
    html_path.write_text(MINIMAL_HTML, encoding="utf-8")

    pdf_bytes = render_html_to_pdf(html_path)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF"), "Result does not look like a PDF stream"


def test_render_html_to_pdf_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.html"
    with pytest.raises(FileNotFoundError):
        render_html_to_pdf(missing)


def test_render_html_to_pdf_uses_custom_base_url(tmp_path: Path) -> None:
    """A custom ``base_url`` should let WeasyPrint resolve relative
    references against that location.  We just exercise the code path:
    the renderer must succeed even when the HTML references a missing
    sibling image (WeasyPrint logs a warning but still produces a PDF)."""
    html = (
        '<html><body><img src="missing.png" alt="x">'
        '<p>hi</p></body></html>'
    )
    html_path = tmp_path / "with_img.html"
    html_path.write_text(html, encoding="utf-8")

    pdf_bytes = render_html_to_pdf(html_path, base_url=tmp_path)

    assert pdf_bytes.startswith(b"%PDF")


def test_render_html_to_pdf_handles_latin1_fallback(tmp_path: Path) -> None:
    """Files with legacy encodings should still render via the latin-1 fallback."""
    html_path = tmp_path / "legacy.html"
    # 'Drücken' encoded in latin-1; not valid UTF-8.
    html_path.write_bytes(b"<html><body><p>Dr\xfccken</p></body></html>")

    pdf_bytes = render_html_to_pdf(html_path)
    assert pdf_bytes.startswith(b"%PDF")


def test_default_print_css_contains_page_rule() -> None:
    css = default_print_css()
    assert "@page" in css
    assert "A4" in css
    assert "page-break" in css


def test_render_html_to_pdf_render_error_wraps_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force WeasyPrint to fail and ensure we surface a ``PdfRenderError``."""
    html_path = tmp_path / "doc.html"
    html_path.write_text("<html><body>ok</body></html>", encoding="utf-8")

    from app.services import pdf_export as module

    class _BoomHTML:  # noqa: D401 - test double
        def __init__(self, *_args, **_kwargs) -> None:
            raise RuntimeError("synthetic weasyprint failure")

    monkeypatch.setattr(module, "render_html_to_pdf", render_html_to_pdf)
    # Patch the lazy import: replace the HTML class inside weasyprint with a
    # stub that raises during construction.  ``render_html_to_pdf`` imports
    # ``HTML`` from ``weasyprint`` inside the function body, so patching the
    # attribute on the real module is enough.
    monkeypatch.setattr("weasyprint.HTML", _BoomHTML)

    with pytest.raises(PdfRenderError) as excinfo:
        render_html_to_pdf(html_path)
    assert "synthetic weasyprint failure" in str(excinfo.value)
