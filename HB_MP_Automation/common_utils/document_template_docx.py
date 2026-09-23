"""Build .docx files for Autotest Document Template uploads.

HB Create New Template requires Upload Word document (.docx) on the
Save Document modal (stage 2026-09-20) — TinyMCE alone is not enough.
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
DOCX_DIR = ROOT / "config" / "test_data" / "document_templates"
# One brand for UI titles and .docx filenames.
TEMPLATE_BRAND = "HB_MP_Automation"
_UI_NAME_PREFIXES = (
    f"{TEMPLATE_BRAND} - ",
    f"{TEMPLATE_BRAND} – ",  # en-dash
    # Legacy titles from earlier Autotest runs (strip if still passed as stem).
    "Autotest HB MP - ",
    "Autotest HB MP – ",
)


def _html_to_paragraphs(html: str) -> list[tuple[str, str]]:
    """Return (style, text) where style is Heading1/Heading2/Normal."""
    parts: list[tuple[str, str]] = []
    chunks = re.split(r"(?i)(</?h1>|</?h2>|</?p>|</?em>|</?strong>)", html)
    # Simpler: strip tags per block.
    for block in re.findall(
        r"(?is)<h1[^>]*>(.*?)</h1>|<h2[^>]*>(.*?)</h2>|<p[^>]*>(.*?)</p>",
        html,
    ):
        if block[0]:
            parts.append(("Heading 1", _strip_tags(block[0])))
        elif block[1]:
            parts.append(("Heading 2", _strip_tags(block[1])))
        elif block[2]:
            text = _strip_tags(block[2])
            if text:
                parts.append(("Normal", text))
    if not parts:
        text = _strip_tags(html)
        for line in text.splitlines():
            line = line.strip()
            if line:
                parts.append(("Normal", line))
    return parts


def _strip_tags(html: str) -> str:
    text = re.sub(r"(?is)<br\s*/?>", "\n", html)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = (
        text.replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&nbsp;", " ")
    )
    return re.sub(r"[ \t]+", " ", text).strip()


def _docx_filename_stem(stem: str) -> str:
    """Build HB_MP_Automation_<Category> from a template title or category."""
    label = (stem or "").strip()
    for prefix in _UI_NAME_PREFIXES:
        if label.lower().startswith(prefix.lower()):
            label = label[len(prefix) :].strip()
            break
    label = re.sub(r"[^\w.\-]+", "_", label).strip("._") or "template"
    label = re.sub(r"_+", "_", label)[:60]
    return f"{TEMPLATE_BRAND}_{label}"


def write_template_docx(stem: str, html_body: str, merge_labels: list[str]) -> Path:
    """Write a .docx under config/test_data/document_templates and return its path.

    Filenames: ``HB_MP_Automation_<Category>.docx``.
    HB library titles: ``HB_MP_Automation - …`` (passed in as ``stem``).
    """
    DOCX_DIR.mkdir(parents=True, exist_ok=True)
    path = DOCX_DIR / f"{_docx_filename_stem(stem)}.docx"
    doc = Document()
    for style, text in _html_to_paragraphs(html_body):
        if style.startswith("Heading"):
            doc.add_heading(text, level=1 if "1" in style else 2)
        else:
            doc.add_paragraph(text)
    if merge_labels:
        doc.add_heading("Merge field anchors (for HB Merge Fields)", level=2)
        for label in merge_labels:
            doc.add_paragraph(f"{label}: [{label}]")
    doc.save(path)
    return path
