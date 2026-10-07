import argparse
import io
import sys
import time
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path for direct script invocation
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reportlab.lib.colors import HexColor, blue, gray, red  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from app.services.certificate_generator import (  # noqa: E402
    DEFAULT_TEMPLATE_PATH,
    CertificateData,
    fit_font_size,
    format_certificate_date,
    generate_certificate_pdf,
    get_cached_template_reader,
    register_fonts,
)
from app.services.layout import (  # noqa: E402
    LAYOUT_SPECS,
    PAGE_HEIGHT_PT,
    PAGE_WIDTH_PT,
    QR_CODE_BOX,
    default_layout,
)

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"


def render_sample_pdf(output_path: Path) -> None:
    """Generate sample certificate PDF for Subiksha P R."""
    data = CertificateData(
        recipient_name="Subiksha P R",
        event_name="Python Workshop",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        certificate_id="CERT-2026-8F3K2Q9X",
    )
    pdf_bytes = generate_certificate_pdf(data)
    output_path.write_bytes(pdf_bytes)
    print(f"✓ Created sample PDF at {output_path} ({len(pdf_bytes) / 1024:.1f} KB)")


def render_calibration_pdf(output_path: Path) -> None:
    """
    Generate calibration PDF with a 100px grid, coordinate labels,
    red baseline ticks, dashed bounding boxes, and field anchors.
    """
    register_fonts()
    layout = default_layout
    template_str = str(DEFAULT_TEMPLATE_PATH)

    buffer = io.BytesIO()
    c = canvas.Canvas(
        buffer,
        pagesize=(PAGE_WIDTH_PT, PAGE_HEIGHT_PT),
        invariant=1,
        pageCompression=1,
    )
    c.setTitle("Certificate Template Calibration Sheet")

    # 1. Background template
    c.drawImage(
        get_cached_template_reader(template_str),
        0,
        0,
        width=PAGE_WIDTH_PT,
        height=PAGE_HEIGHT_PT,
    )

    # 2. Draw 100px pixel grid
    c.setFont("Helvetica", 6)
    c.setLineWidth(0.4)

    # Vertical grid lines (every 100 px)
    for x_px in range(100, int(layout.width_px), 100):
        pt_x, _ = layout.px_to_pt(float(x_px), 0)
        c.setStrokeColor(gray, alpha=0.35)
        c.line(pt_x, 0, pt_x, PAGE_HEIGHT_PT)
        c.setFillColor(gray)
        c.drawString(pt_x + 1, PAGE_HEIGHT_PT - 8, f"{x_px}")
        c.drawString(pt_x + 1, 3, f"{x_px}")

    # Horizontal grid lines (every 100 px)
    for y_px in range(100, int(layout.height_px), 100):
        _, pt_y = layout.px_to_pt(0, float(y_px))
        c.setStrokeColor(gray, alpha=0.35)
        c.line(0, pt_y, PAGE_WIDTH_PT, pt_y)
        c.setFillColor(gray)
        c.drawString(3, pt_y + 1, f"{y_px}")
        c.drawString(PAGE_WIDTH_PT - 22, pt_y + 1, f"{y_px}")

    # 3. Draw field specs, max-width boxes, baselines and text
    sample_texts = {
        "recipient_name": "Subiksha P R",
        "event_name": "Advanced Python & Distributed Systems",
        "organization_name": "ABC Technologies Private Limited",
        "event_date": "10 October 2026",
        "authorized_signatory": "Priya Sharma",
        "organization_name_footer": "ABC Technologies Private Limited",
        "certificate_id": "CERT-2026-8F3K2Q9X",
    }

    for key, spec in LAYOUT_SPECS.items():
        text_val = sample_texts[key]
        font_size_pt = fit_font_size(text_val, spec, layout)
        center_pt_x, baseline_pt_y = layout.px_to_pt(spec.center_x, spec.baseline_y)

        half_width_pt = layout.scale_width(spec.max_width_px / 2.0)
        box_left = center_pt_x - half_width_pt
        box_right = center_pt_x + half_width_pt
        box_height_pt = layout.scale_font_size(spec.start_px * 1.2)

        # Red baseline line
        c.setStrokeColor(red)
        c.setLineWidth(1.0)
        c.line(box_left, baseline_pt_y, box_right, baseline_pt_y)
        # Baseline ticks
        c.line(box_left, baseline_pt_y - 4, box_left, baseline_pt_y + 4)
        c.line(box_right, baseline_pt_y - 4, box_right, baseline_pt_y + 4)
        c.line(center_pt_x, baseline_pt_y - 6, center_pt_x, baseline_pt_y + 6)

        # Blue dashed max-width box
        c.setStrokeColor(blue, alpha=0.6)
        c.setDash([3, 3])
        c.setLineWidth(0.8)
        c.rect(box_left, baseline_pt_y, 2 * half_width_pt, box_height_pt, stroke=1, fill=0)
        c.setDash()

        # Render field label & coordinates
        c.setFont("Helvetica-Bold", 7)
        c.setFillColor(red)
        label = (
            f"[{key}] cx={spec.center_x:.0f} by={spec.baseline_y:.0f} "
            f"max_w={spec.max_width_px:.0f}px"
        )
        c.drawString(box_left, baseline_pt_y - 9, label)

        # Draw centered sample text
        c.setFont(spec.font_name, font_size_pt)
        c.setFillColor(HexColor(spec.color))
        c.drawCentredString(center_pt_x, baseline_pt_y, text_val)

    # 4. Draw QR code box (for Phase 8 reference)
    qr_left, qr_top = layout.px_to_pt(QR_CODE_BOX.x_min, QR_CODE_BOX.y_min)
    qr_w = layout.scale_width(QR_CODE_BOX.width_px)
    qr_h = layout.scale_font_size(QR_CODE_BOX.height_px)
    c.setStrokeColor(HexColor("#107C41"), alpha=0.8)
    c.setDash([2, 2])
    c.rect(qr_left, qr_top - qr_h, qr_w, qr_h, stroke=1, fill=0)
    c.setDash()
    c.setFont("Helvetica-Bold", 6)
    c.setFillColor(HexColor("#107C41"))
    c.drawString(qr_left, qr_top + 2, "QR Code Box (110x110 px)")

    c.showPage()
    c.save()

    output_path.write_bytes(buffer.getvalue())
    print(f"✓ Created calibration PDF at {output_path} ({len(buffer.getvalue()) / 1024:.1f} KB)")


def render_stress_pdf(output_path: Path) -> None:
    """Generate multi-page stress-test PDF testing name shrinking, accents, and long strings."""
    stress_cases = [
        CertificateData(
            recipient_name="Alexander Montgomery-Cunningham III",
            event_name="Cloud Architecture & Site Reliability Engineering",
            event_date=date(2026, 10, 10),
            organization_name="International Institute of Computing & Technology",
            authorized_signatory="Dr. Elizabeth Harrington",
            certificate_id="CERT-2026-STRESS01",
        ),
        CertificateData(
            recipient_name="D'Souza",
            event_name="Python Workshop",
            event_date=date(2026, 10, 10),
            organization_name="ABC Technologies",
            authorized_signatory="Priya Sharma",
            certificate_id="CERT-2026-STRESS02",
        ),
        CertificateData(
            recipient_name="José Silva",
            event_name="Full Stack Web Development Bootcamp",
            event_date=date(2026, 10, 10),
            organization_name="Instituto de Tecnologia Avançada",
            authorized_signatory="María Rodríguez",
            certificate_id="CERT-2026-STRESS03",
        ),
        CertificateData(
            recipient_name="Mary-Ann Watson-Smith",
            event_name="FastAPI & Async Systems Engineering",
            event_date=date(2026, 10, 10),
            organization_name="ABC Technologies",
            authorized_signatory="Priya Sharma",
            certificate_id="CERT-2026-STRESS04",
        ),
    ]

    register_fonts()
    template_str = str(DEFAULT_TEMPLATE_PATH)
    layout = default_layout

    buffer = io.BytesIO()
    c = canvas.Canvas(
        buffer,
        pagesize=(PAGE_WIDTH_PT, PAGE_HEIGHT_PT),
        invariant=1,
        pageCompression=1,
    )

    template_reader = get_cached_template_reader(template_str)

    for data in stress_cases:
        c.setTitle(f"Certificate – {data.recipient_name}")
        c.setAuthor(data.organization_name)
        c.drawImage(template_reader, 0, 0, width=PAGE_WIDTH_PT, height=PAGE_HEIGHT_PT)

        fields = [
            ("recipient_name", data.recipient_name),
            ("event_name", data.event_name),
            ("organization_name", data.organization_name),
            ("event_date", format_certificate_date(data.event_date)),
            ("authorized_signatory", data.authorized_signatory),
            ("organization_name_footer", data.organization_name),
            ("certificate_id", data.certificate_id),
        ]

        for field_key, text_val in fields:
            spec = LAYOUT_SPECS[field_key]
            font_size_pt = fit_font_size(text_val, spec, layout)
            pdf_x, pdf_y = layout.px_to_pt(spec.center_x, spec.baseline_y)

            c.setFont(spec.font_name, font_size_pt)
            c.setFillColor(HexColor(spec.color))
            c.drawCentredString(pdf_x, pdf_y, text_val)

        c.showPage()

    c.save()
    output_path.write_bytes(buffer.getvalue())
    print(f"✓ Created stress PDF at {output_path} ({len(buffer.getvalue()) / 1024:.1f} KB)")


def benchmark_generation(iterations: int = 50) -> tuple[float, float]:
    """Measure average generation speed and PDF size over N runs."""
    sample_data = CertificateData(
        recipient_name="Subiksha P R",
        event_name="Python Workshop",
        event_date=date(2026, 10, 10),
        organization_name="ABC Technologies",
        authorized_signatory="Priya Sharma",
        certificate_id="CERT-2026-8F3K2Q9X",
    )

    # Warm-up run
    sample_pdf = generate_certificate_pdf(sample_data)
    pdf_size_kb = len(sample_pdf) / 1024.0

    start_time = time.perf_counter()
    for _ in range(iterations):
        _ = generate_certificate_pdf(sample_data)
    total_time = time.perf_counter() - start_time
    avg_ms = (total_time / iterations) * 1000.0

    return avg_ms, pdf_size_kb


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render sample, calibration, and stress PDFs.")
    parser.add_argument("--stress", action="store_true", help="Generate stress-test PDF.")
    parser.add_argument("--benchmark", action="store_true", help="Run 50-iteration benchmark.")
    args = parser.parse_args()

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    render_sample_pdf(SAMPLES_DIR / "sample.pdf")
    render_calibration_pdf(SAMPLES_DIR / "calibration.pdf")
    if args.stress or True:  # Generate stress by default for review
        render_stress_pdf(SAMPLES_DIR / "stress.pdf")

    avg_ms, pdf_size_kb = benchmark_generation(50)
    print("\n--- Performance Benchmark (50 runs) ---")
    print(f"Mean Generation Time: {avg_ms:.2f} ms / certificate")
    print(f"Mean PDF Size:        {pdf_size_kb:.1f} KB (budget: < 500 KB)")
