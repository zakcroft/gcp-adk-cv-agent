"""Document conversion for the API boundary.

Uploads may be PDF or plain text; the pipeline works on text, so PDFs are
extracted to text here BEFORE anything reaches the guarded Runner (so the
input guardrails still see plain text and a scanned/empty PDF is caught by
the size check). The finished CV is rendered back to a PDF for download."""

import io

from fpdf import FPDF
from pypdf import PdfReader

# Typographic characters the core PDF fonts (latin-1) cannot encode, mapped
# to safe equivalents. CVs are British English, so this is the whole set in
# practice; anything else falls back to latin-1 replacement.
_TYPOGRAPHIC = {
    "–": "-",  # en dash
    "—": "-",  # em dash
    "‘": "'",  # left single quote
    "’": "'",  # right single quote / apostrophe
    "“": '"',  # left double quote
    "”": '"',  # right double quote
    "•": "-",  # bullet
    "…": "...",  # ellipsis
    " ": " ",  # non-breaking space
}


def is_pdf(data: bytes) -> bool:
    """A PDF always begins with the %PDF- signature — the reliable check,
    independent of filename or the browser's content-type guess."""
    return data[:5] == b"%PDF-"


def extract_pdf_text(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def to_text_bytes(data: bytes) -> bytes:
    """Normalise an upload to UTF-8 text bytes. PDFs are extracted; anything
    else is passed through unchanged and validated downstream (a non-text
    binary will fail the readable check)."""
    if is_pdf(data):
        return extract_pdf_text(data).encode("utf-8")
    return data


def _latin1(text: str) -> str:
    for bad, good in _TYPOGRAPHIC.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", "replace").decode("latin-1")


def render_pdf(cv_text: str) -> bytes:
    """Render the CV text as a simple A4 PDF (serif, generous line height)."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_margins(20, 20, 20)
    pdf.set_font("Times", size=11)
    pdf.multi_cell(0, 6, _latin1(cv_text))
    return bytes(pdf.output())
