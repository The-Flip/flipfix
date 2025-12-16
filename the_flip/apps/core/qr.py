"""QR code generation utilities."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import qrcode
from PIL import Image, ImageOps
from PIL.Image import Resampling

# QR code configuration
QR_BOX_SIZE_SINGLE = 10  # Larger boxes for single QR display
QR_BOX_SIZE_BULK = 8  # Smaller boxes for bulk printing
QR_BORDER = 4
QR_LOGO_SIZE_RATIO = 0.28  # Logo takes 28% of QR width (within 30% error correction)
QR_LOGO_SIZE_RATIO_BULK = 0.25  # Slightly smaller for bulk
QR_LOGO_PADDING = 4

# Path to logo image
LOGO_PATH = Path(__file__).resolve().parent.parent.parent / "static/core/images/logo_white.png"


def _load_and_invert_logo() -> Image.Image | None:
    """Load the logo image and invert white to black for QR overlay.

    Returns:
        Inverted RGBA logo image, or None if logo doesn't exist.
    """
    if not LOGO_PATH.exists():
        return None

    logo = Image.open(LOGO_PATH).convert("RGBA")
    r, g, b, a = logo.split()
    rgb = Image.merge("RGB", (r, g, b))
    inverted = ImageOps.invert(rgb)
    return Image.merge("RGBA", (*inverted.split(), a))


def _add_logo_to_qr(qr_img: Image.Image, logo: Image.Image, logo_size_ratio: float) -> None:
    """Add a centered logo with white background to a QR code image.

    Args:
        qr_img: QR code image to modify in place.
        logo: Logo image (RGBA) to overlay.
        logo_size_ratio: Logo size as fraction of QR width.
    """
    qr_width, qr_height = qr_img.size
    logo_size = int(qr_width * logo_size_ratio)

    # Resize logo maintaining aspect ratio
    logo_copy = logo.copy()
    logo_copy.thumbnail((logo_size, logo_size), Resampling.LANCZOS)

    # Add white background/padding for better contrast
    logo_with_bg = Image.new(
        "RGB",
        (logo_copy.size[0] + QR_LOGO_PADDING * 2, logo_copy.size[1] + QR_LOGO_PADDING * 2),
        "white",
    )
    logo_with_bg.paste(
        logo_copy,
        (QR_LOGO_PADDING, QR_LOGO_PADDING),
        logo_copy if logo_copy.mode == "RGBA" else None,
    )

    # Center and paste logo
    logo_position = (
        (qr_width - logo_with_bg.size[0]) // 2,
        (qr_height - logo_with_bg.size[1]) // 2,
    )
    qr_img.paste(logo_with_bg, logo_position)


def generate_qr_code(url: str, box_size: int = QR_BOX_SIZE_SINGLE) -> Image.Image:
    """Generate a QR code image with embedded logo.

    Args:
        url: URL to encode in the QR code.
        box_size: Size of each box in the QR code grid.

    Returns:
        RGB PIL Image of the QR code.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction (30%)
        box_size=box_size,
        border=QR_BORDER,
    )
    qr.add_data(url)
    qr.make(fit=True)

    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Add logo if available
    logo = _load_and_invert_logo()
    if logo:
        logo_ratio = (
            QR_LOGO_SIZE_RATIO if box_size >= QR_BOX_SIZE_SINGLE else QR_LOGO_SIZE_RATIO_BULK
        )
        _add_logo_to_qr(qr_img, logo, logo_ratio)

    return qr_img


def generate_qr_code_base64(url: str, box_size: int = QR_BOX_SIZE_SINGLE) -> str:
    """Generate a QR code and return as base64-encoded PNG string.

    Args:
        url: URL to encode in the QR code.
        box_size: Size of each box in the QR code grid.

    Returns:
        Base64-encoded PNG image data.
    """
    qr_img = generate_qr_code(url, box_size)
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
