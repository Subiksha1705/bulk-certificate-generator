import io
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.services.layout import (
    LAYOUT_SPECS,
    PAGE_HEIGHT_PT,
    PAGE_WIDTH_PT,
    FieldSpec,
    TemplateLayout,
    default_layout,
)

# Base asset paths
ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
DEFAULT_TEMPLATE_PATH = ASSETS_DIR / "template" / "certificate_template.png"

# Fonts to register
FONT_FILES = {
    "Lora-Regular": FONTS_DIR / "Lora-Regular.ttf",
    "Lora-Medium": FONTS_DIR / "Lora-Medium.ttf",
    "Lora-SemiBold": FONTS_DIR / "Lora-SemiBold.ttf",
    "Lora-Bold": FONTS_DIR / "Lora-Bold.ttf",
    "GreatVibes-Regular": FONTS_DIR / "GreatVibes-Regular.ttf",
}

_fonts_registered = False


class CertificateDataError(Exception):
    """Base exception for deterministic certificate data errors (non-retryable)."""


class UnsupportedCharacterError(CertificateDataError):
    """Raised when text contains characters not supported by the target font glyph map."""


class TextOverflowError(CertificateDataError):
    """Raised when text exceeds the maximum line width even at minimum font size."""


def register_fonts() -> None:
    """Register all required TTF fonts with ReportLab (idempotent)."""
    global _fonts_registered
    if _fonts_registered:
        return

    for font_name, font_path in FONT_FILES.items():
        if font_path.exists():
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
        else:
            raise FileNotFoundError(f"Font file missing at {font_path}")

    _fonts_registered = True


@dataclass(slots=True)
class CertificateData:
    """Input payload for generating a certificate PDF."""

    recipient_name: str
    event_name: str
    event_date: date
    organization_name: str
    authorized_signatory: str
    certificate_id: str
    verify_url: str | None = None


def check_glyphs(text: str, font_name: str) -> None:
    """Verify that every character in text exists in the font's glyph map."""
    register_fonts()
    font = pdfmetrics.getFont(font_name)
    glyph_map = font.face.charToGlyph

    for char in text:
        code_point = ord(char)
        if code_point not in glyph_map or glyph_map[code_point] in (0, ".notdef"):
            raise UnsupportedCharacterError(
                f"Font '{font_name}' does not support character '{char}' "
                f"(U+{code_point:04X}) in '{text}'"
            )


def fit_font_size(
    text: str,
    spec: FieldSpec,
    layout: TemplateLayout = default_layout,
) -> float:
    """
    Calculate the optimal font size in PDF points for text within spec.max_width_px.
    Checks character glyphs first, then steps down from start_px to min_px.
    """
    check_glyphs(text, spec.font_name)

    max_width_pt = layout.scale_width(spec.max_width_px)
    current_size_px = spec.start_px

    while current_size_px >= spec.min_px:
        font_size_pt = layout.scale_font_size(current_size_px)
        width_pt = pdfmetrics.stringWidth(text, spec.font_name, font_size_pt)
        if width_pt <= max_width_pt:
            return font_size_pt
        current_size_px -= 1.0

    # Still too wide at min_px
    msg = (
        f"Text '{text}' exceeds max width {spec.max_width_px}px "
        f"at minimum font size {spec.min_px}px"
    )
    raise TextOverflowError(msg)


def validate_text_renderable(text: str, field_name: str) -> None:
    """Public validator to verify text renderability during job ingestion."""
    spec = LAYOUT_SPECS.get(field_name)
    if not spec:
        return
    fit_font_size(text, spec, default_layout)


@lru_cache(maxsize=1)
def get_cached_template_reader(template_path: str) -> ImageReader:
    """Cache the template ImageReader to avoid disk re-reads on batch generation."""
    with Image.open(template_path) as img:
        img_copy = img.copy()
    return ImageReader(img_copy)


def format_certificate_date(d: date) -> str:
    """Format date as e.g. '10 October 2026'."""
    return f"{d.day} {d:%B %Y}"


def generate_certificate_pdf(
    data: CertificateData,
    template_path: Path | str = DEFAULT_TEMPLATE_PATH,
) -> bytes:
    """
    Generate a pixel-accurate, deterministic certificate PDF.
    Invariant=1 and pageCompression=1 guarantee identical bytes for identical input.
    """
    register_fonts()
    template_str = str(template_path)
    layout = TemplateLayout(template_str)

    buffer = io.BytesIO()
    c = canvas.Canvas(
        buffer,
        pagesize=(PAGE_WIDTH_PT, PAGE_HEIGHT_PT),
        invariant=1,
        pageCompression=1,
    )

    # 1. Set PDF metadata
    c.setTitle(f"Certificate – {data.recipient_name}")
    c.setAuthor(data.organization_name)
    c.setSubject(f"Certificate of Completion for {data.event_name}")

    # 2. Draw background template image
    template_reader = get_cached_template_reader(template_str)
    c.drawImage(
        template_reader,
        0,
        0,
        width=PAGE_WIDTH_PT,
        height=PAGE_HEIGHT_PT,
    )

    # 3. Text field mappings
    fields = [
        ("recipient_name", data.recipient_name),
        ("event_name", data.event_name),
        ("organization_name", data.organization_name),
        ("event_date", format_certificate_date(data.event_date)),
        ("authorized_signatory", data.authorized_signatory),
        ("organization_name_footer", data.organization_name),
        ("certificate_id", data.certificate_id),
    ]

    # 4. Render text fields
    for field_key, text_val in fields:
        spec = LAYOUT_SPECS[field_key]
        font_size_pt = fit_font_size(text_val, spec, layout)
        pdf_x, pdf_y = layout.px_to_pt(spec.center_x, spec.baseline_y)

        c.setFont(spec.font_name, font_size_pt)
        c.setFillColor(HexColor(spec.color))
        c.drawCentredString(pdf_x, pdf_y, text_val)

    # 5. Finalize page
    c.showPage()
    c.save()

    return buffer.getvalue()
