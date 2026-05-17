"""HTML-to-PDF rendering for generator outputs.

The HEZ generator produces self-contained HTML documents under
``storage/projects/<slug>/<role>/`` (e.g. ``04_Projektleitung/
PROJEKTLEITUNG_Projektuebersicht.html``). For inline preview / download we
render those documents to PDF on demand with WeasyPrint.

WeasyPrint is the chosen renderer because:

- it is a pure-Python HTML+CSS renderer (no headless browser process to keep
  alive),
- it understands @page rules and CSS print extensions, which is exactly what
  the generator templates need, and
- it resolves relative ``<img>`` / ``<link rel="stylesheet">`` references
  against a configurable ``base_url`` so the generator output can reference
  sibling assets without any rewriting.

System libraries required at runtime (added in the Dockerfile): pango,
cairo, gdk-pixbuf, harfbuzz.
"""
from __future__ import annotations

from pathlib import Path


class PdfRenderError(RuntimeError):
    """Raised when WeasyPrint fails to render an HTML document to PDF."""


def default_print_css() -> str:
    """Inline CSS the generator should embed into produced HTML files.

    Keeping the rules here (and not only inside the generator prompt) gives us
    a single source of truth: if a generated HTML file does not bring its own
    print styles, callers can inject this stylesheet at render time so the
    resulting PDF still has sane margins, font sizes and page-break behaviour.

    Returned string is a CSS fragment (no ``<style>`` tag), suitable both
    for being inlined into a ``<style>`` element by the generator and for
    being passed to WeasyPrint as a ``CSS(string=...)`` stylesheet.
    """
    return """
@page {
    size: A4;
    margin: 20mm 18mm;
}

html, body {
    font-family: "DejaVu Sans", "Liberation Sans", Arial, sans-serif;
    font-size: 11pt;
    line-height: 1.4;
    color: #1a1a1a;
}

h1, h2, h3 {
    page-break-after: avoid;
    color: #14304a;
}

h1 { font-size: 20pt; margin: 0 0 10pt; }
h2 { font-size: 14pt; margin: 14pt 0 6pt; }
h3 { font-size: 12pt; margin: 10pt 0 4pt; }

p, ul, ol { margin: 0 0 6pt; }

section, .section, .doc-block, table {
    page-break-inside: avoid;
}

table {
    border-collapse: collapse;
    width: 100%;
    margin: 6pt 0 10pt;
}

th, td {
    border: 1px solid #888;
    padding: 4pt 6pt;
    vertical-align: top;
    text-align: left;
}

th {
    background: #eef2f7;
    font-weight: 600;
}

tr { page-break-inside: avoid; }

code, pre {
    font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
    font-size: 9.5pt;
}

.no-print { display: none !important; }
""".strip()


def render_html_to_pdf(html_path: Path, base_url: Path | None = None) -> bytes:
    """Render an HTML file (with relative CSS/img references) into a PDF.

    Parameters
    ----------
    html_path:
        Path to the HTML file on disk. The file is read as UTF-8 (with a
        permissive fallback) and handed to WeasyPrint.
    base_url:
        Base URL used for resolving relative URLs in the HTML (CSS files,
        images, fonts, ...). Defaults to ``html_path.parent`` so that
        ``<img src="images/foo.png">`` resolves to a sibling file.

    Returns
    -------
    bytes
        The full PDF byte stream, starting with ``%PDF``.

    Raises
    ------
    FileNotFoundError
        If ``html_path`` does not exist or is not a regular file.
    PdfRenderError
        If WeasyPrint raises during parsing or rendering. The original
        exception is chained.
    """
    if not html_path.exists() or not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    raw_bytes = html_path.read_bytes()
    try:
        html_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        # Fallback for legacy encodings — the generator emits UTF-8, but
        # be lenient for hand-edited templates.
        html_text = raw_bytes.decode("latin-1")

    return render_html_string_to_pdf(
        html_text,
        base_url=base_url or html_path.parent,
        source_label=html_path.name,
    )


def render_html_string_to_pdf(
    html_text: str,
    base_url: Path,
    source_label: str = "<inline-html>",
) -> bytes:
    """Render an in-memory HTML string into a PDF.

    Used when the HTML needs to be transformed before printing (e.g. PII
    reidentification at serve-time) and writing it back to disk first
    would be wasteful or leak sensitive data.
    """
    try:
        # WeasyPrint is heavy and pulls in system libraries (pango, cairo).
        # Import lazily so importing this module does not blow up in
        # environments that have not installed the binary deps yet.
        from weasyprint import CSS, HTML
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise PdfRenderError(
            "WeasyPrint is not installed. Install 'weasyprint' and its system "
            "libraries (pango, cairo, gdk-pixbuf, harfbuzz)."
        ) from exc

    try:
        document = HTML(string=html_text, base_url=str(base_url.resolve()))
        stylesheet = CSS(string=default_print_css())
        return document.write_pdf(stylesheets=[stylesheet])
    except Exception as exc:  # noqa: BLE001 - upstream raises various types
        raise PdfRenderError(
            f"Failed to render {source_label} to PDF: {exc}"
        ) from exc
