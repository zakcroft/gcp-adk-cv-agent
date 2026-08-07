from api.documents import extract_pdf_text, is_pdf, render_pdf, to_text_bytes

CV = "Owen Prentice\nSoftware Developer\n\nEXPERIENCE\nBuilt Django services."


def test_render_pdf_produces_a_pdf():
    pdf = render_pdf(CV)
    assert pdf[:5] == b"%PDF-"
    assert len(pdf) > 500


def test_pdf_round_trips_back_to_text():
    # render a CV to PDF, then extract it — the words should survive
    pdf = render_pdf(CV)
    assert is_pdf(pdf)
    text = extract_pdf_text(pdf)
    assert "Owen Prentice" in text
    assert "Django" in text


def test_to_text_bytes_extracts_pdf_uploads():
    pdf = render_pdf(CV)
    out = to_text_bytes(pdf).decode("utf-8")
    assert "Owen Prentice" in out


def test_to_text_bytes_passes_plain_text_through():
    assert to_text_bytes(b"just some text") == b"just some text"


def test_render_pdf_handles_typographic_characters():
    # en dash, curly quotes, bullet — must not raise on the latin-1 core font
    pdf = render_pdf("Skills — Python, “React”, ‘Node’\n• built things")
    assert pdf[:5] == b"%PDF-"
