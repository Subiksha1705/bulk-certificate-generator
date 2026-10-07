from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# A4 Landscape dimensions in PDF points (72 points per inch)
PAGE_WIDTH_PT = 841.89
PAGE_HEIGHT_PT = 595.28

# Expected template dimensions in pixels
TEMPLATE_DEFAULT_WIDTH_PX = 2000.0
TEMPLATE_DEFAULT_HEIGHT_PX = 1414.0


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Specification for text placement on the certificate."""

    center_x: float
    baseline_y: float
    font_name: str
    start_px: float
    min_px: float
    max_width_px: float
    color: str = "#1A1A1A"


@dataclass(frozen=True, slots=True)
class BoxSpec:
    """Specification for a bounding box on the certificate (e.g. QR code)."""

    x_min: float
    y_min: float
    width_px: float
    height_px: float


# Field layout specs defined in template pixels (top-left origin, 2000x1414 px)
LAYOUT_SPECS: dict[str, FieldSpec] = {
    "recipient_name": FieldSpec(
        center_x=1398.0,
        baseline_y=534.0,
        font_name="Lora-SemiBold",
        start_px=56.0,
        min_px=26.0,
        max_width_px=740.0,
        color="#1A1A1A",
    ),
    "event_name": FieldSpec(
        center_x=1312.0,
        baseline_y=640.0,
        font_name="Lora-Medium",
        start_px=40.0,
        min_px=20.0,
        max_width_px=860.0,
        color="#1A1A1A",
    ),
    "organization_name": FieldSpec(
        center_x=1215.0,
        baseline_y=737.0,
        font_name="Lora-Medium",
        start_px=40.0,
        min_px=20.0,
        max_width_px=860.0,
        color="#1A1A1A",
    ),
    "event_date": FieldSpec(
        center_x=1011.0,
        baseline_y=846.0,
        font_name="Lora-Medium",
        start_px=40.0,
        min_px=24.0,
        max_width_px=480.0,
        color="#1A1A1A",
    ),
    "authorized_signatory": FieldSpec(
        center_x=491.0,
        baseline_y=1122.0,
        font_name="GreatVibes-Regular",
        start_px=60.0,
        min_px=24.0,
        max_width_px=380.0,
        color="#1F2A44",  # Deep navy signatory ink
    ),
    "organization_name_footer": FieldSpec(
        center_x=991.0,
        baseline_y=1121.0,
        font_name="Lora-Medium",
        start_px=30.0,
        min_px=14.0,
        max_width_px=380.0,
        color="#1A1A1A",
    ),
    "certificate_id": FieldSpec(
        center_x=1510.0,
        baseline_y=1121.0,
        font_name="Lora-Medium",
        start_px=30.0,
        min_px=20.0,
        max_width_px=380.0,
        color="#1A1A1A",
    ),
}

# QR code box spec defined for Phase 8
QR_CODE_BOX = BoxSpec(
    x_min=1454.0,
    y_min=970.0,
    width_px=110.0,
    height_px=110.0,
)


class TemplateLayout:
    """Coordinate converter from template pixels to PDF points."""

    def __init__(self, template_path: Path | str | None = None) -> None:
        if template_path and Path(template_path).exists():
            with Image.open(template_path) as img:
                self.width_px, self.height_px = float(img.width), float(img.height)
        else:
            self.width_px = TEMPLATE_DEFAULT_WIDTH_PX
            self.height_px = TEMPLATE_DEFAULT_HEIGHT_PX

        # Scale factor from template pixel to PDF point based on page height
        self.scale = PAGE_HEIGHT_PT / self.height_px
        # Horizontal ratio to adapt if template pixel width differs from 2000px
        self.horizontal_ratio = self.width_px / TEMPLATE_DEFAULT_WIDTH_PX

    def px_to_pt(self, x_px: float, y_px: float) -> tuple[float, float]:
        """Convert top-left pixel coordinates to bottom-left PDF point coordinates."""
        pdf_x = x_px * self.horizontal_ratio * self.scale
        pdf_y = PAGE_HEIGHT_PT - (y_px * self.scale)
        return pdf_x, pdf_y

    def scale_font_size(self, size_px: float) -> float:
        """Scale font size from pixel dimensions to PDF points."""
        return size_px * self.scale

    def scale_width(self, width_px: float) -> float:
        """Scale width from pixel dimensions to PDF points."""
        return width_px * self.horizontal_ratio * self.scale


# Default layout singleton
default_layout = TemplateLayout()
