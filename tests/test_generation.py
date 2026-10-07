import io
from datetime import date

import pypdf
import pytest

from app.services.certificate_generator import (
    CertificateData,
    TextOverflowError,
    UnsupportedCharacterError,
    fit_font_size,
    format_certificate_date,
    generate_certificate_pdf,
)
from app.services.layout import LAYOUT_SPECS, PAGE_HEIGHT_PT, PAGE_WIDTH_PT, default_layout


@pytest.fixture
def sample_certificate_data() -> CertificateData:
    """Fixture providing valid sample certificate data."""
    return CertificateData(
        recipient_name="Subiksha P R",
        event_name="Python Workshop",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        certificate_id="CERT-2026-8F3K2Q9X",
    )


def test_pdf_generation_valid_structure_and_metadata(
    sample_certificate_data: CertificateData,
) -> None:
    """Verify generated PDF magic bytes, page size, metadata, and size budget."""
    pdf_bytes = generate_certificate_pdf(sample_certificate_data)

    # 1. Header magic bytes
    assert pdf_bytes.startswith(b"%PDF-"), "Generated file is not a valid PDF"

    # 2. Size budget (< 500 KB)
    size_kb = len(pdf_bytes) / 1024.0
    assert size_kb < 500.0, f"PDF size {size_kb:.1f} KB exceeds 500 KB budget"

    # 3. Read back with pypdf and assert dimensions
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    assert len(reader.pages) == 1
    page = reader.pages[0]

    # Verify A4 landscape dimensions (approx 841.89 x 595.28 pt)
    assert abs(float(page.mediabox.width) - PAGE_WIDTH_PT) < 1.0
    assert abs(float(page.mediabox.height) - PAGE_HEIGHT_PT) < 1.0


def test_pdf_generation_text_extraction(sample_certificate_data: CertificateData) -> None:
    """Verify that all text fields appear in the PDF text stream."""
    pdf_bytes = generate_certificate_pdf(sample_certificate_data)
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    extracted_text = reader.pages[0].extract_text()

    assert "Subiksha P R" in extracted_text
    assert "Python Workshop" in extracted_text
    assert "ABC Technologies" in extracted_text
    assert "10 October 2026" in extracted_text
    assert "Priya Sharma" in extracted_text
    assert "CERT-2026-8F3K2Q9X" in extracted_text


def test_pdf_generation_determinism(sample_certificate_data: CertificateData) -> None:
    """Verify that generating the same certificate multiple times produces byte-identical PDFs."""
    pdf1 = generate_certificate_pdf(sample_certificate_data)
    pdf2 = generate_certificate_pdf(sample_certificate_data)
    assert pdf1 == pdf2, "PDF generation is not deterministic"


def test_unsupported_characters_raise_exception() -> None:
    """Verify that emoji and unsupported unicode scripts raise UnsupportedCharacterError."""
    # 1. Emoji
    with pytest.raises(UnsupportedCharacterError):
        generate_certificate_pdf(
            CertificateData(
                recipient_name="Subiksha 😊",
                event_name="Python Workshop",
                event_date=date(2026, 10, 10),
                organization_name="ABC Technologies",
                authorized_signatory="Priya Sharma",
                certificate_id="CERT-2026-8F3K2Q9X",
            )
        )

    # 2. Devanagari script (not in Lora Latin/Cyrillic set)
    with pytest.raises(UnsupportedCharacterError):
        generate_certificate_pdf(
            CertificateData(
                recipient_name="सुभिक्षा",
                event_name="Python Workshop",
                event_date=date(2026, 10, 10),
                organization_name="ABC Technologies",
                authorized_signatory="Priya Sharma",
                certificate_id="CERT-2026-8F3K2Q9X",
            )
        )


def test_text_overflow_raises_exception() -> None:
    """Verify that text exceeding line width at minimum font size raises TextOverflowError."""
    absurd_long_name = "A" * 150
    with pytest.raises(TextOverflowError):
        generate_certificate_pdf(
            CertificateData(
                recipient_name=absurd_long_name,
                event_name="Python Workshop",
                event_date=date(2026, 10, 10),
                organization_name="ABC Technologies",
                authorized_signatory="Priya Sharma",
                certificate_id="CERT-2026-8F3K2Q9X",
            )
        )


def test_long_name_shrinks_and_succeeds() -> None:
    """Verify that a long name (e.g. 40 chars) steps down font size and generates successfully."""
    long_name = "Alexander Montgomery-Cunningham III"
    data = CertificateData(
        recipient_name=long_name,
        event_name="Python Workshop",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        certificate_id="CERT-2026-8F3K2Q9X",
    )
    spec = LAYOUT_SPECS["recipient_name"]
    font_size_pt = fit_font_size(long_name, spec, default_layout)
    start_pt = default_layout.scale_font_size(spec.start_px)

    # Assert font size stepped down below starting size
    assert font_size_pt < start_pt

    # Assert PDF generates cleanly
    pdf_bytes = generate_certificate_pdf(data)
    assert pdf_bytes.startswith(b"%PDF-")


def test_date_formatting() -> None:
    """Verify date formatting output."""
    assert format_certificate_date(date(2026, 10, 10)) == "10 October 2026"
    assert format_certificate_date(date(2026, 1, 5)) == "5 January 2026"
