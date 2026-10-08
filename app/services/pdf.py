from datetime import date
from pathlib import Path

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from app.exceptions import CertificateRenderError

PAGE = landscape(A4)
PAGE_WIDTH, PAGE_HEIGHT = PAGE

NAVY = HexColor("#1B3A4B")
GOLD = HexColor("#B8956A")
GOLD_SOFT = HexColor("#E7D3B0")
INK = HexColor("#1C1917")
MUTED = HexColor("#57534E")
CREAM = HexColor("#FBF7EF")
SEAL_FILL = HexColor("#F8F1E4")

_FONTS_READY = False

_FONT_FILES = {
    "DejaVuSans": "DejaVuSans.ttf",
    "DejaVuSans-Bold": "DejaVuSans-Bold.ttf",
    "DejaVuSerif": "DejaVuSerif.ttf",
    "DejaVuSerif-Bold": "DejaVuSerif-Bold.ttf",
    "DejaVuSerif-Italic": "DejaVuSerif-Italic.ttf",
    "DejaVuSerif-BoldItalic": "DejaVuSerif-BoldItalic.ttf",
}


def ensure_fonts() -> None:
    global _FONTS_READY
    if _FONTS_READY:
        return
    font_dir = Path(__file__).resolve().parents[1] / "fonts"
    for name, filename in _FONT_FILES.items():
        path = font_dir / filename
        if not path.is_file():
            raise CertificateRenderError(f"Certificate font is missing: {filename}")
        pdfmetrics.registerFont(TTFont(name, str(path)))
    _FONTS_READY = True


def render_certificate(
    *,
    destination: Path,
    recipient_name: str,
    event_title: str,
    issuer: str,
    issue_date: date,
    description: str,
    detail: str | None,
    certificate_number: str,
    verify_url: str,
    signatory_name: str,
    signatory_title: str,
) -> None:
    ensure_fonts()
    _ensure_drawable(
        [
            ("Recipient name", recipient_name),
            ("Event title", event_title),
            ("Issuer", issuer),
            ("Description", description),
            ("Detail", detail or ""),
            ("Signatory", signatory_name),
            ("Signatory title", signatory_title),
        ]
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(destination), pagesize=PAGE)
    pdf.setTitle(f"{event_title} — {recipient_name}")
    pdf.setAuthor(issuer)
    pdf.setSubject(certificate_number)
    pdf.setCreator("Bulk Certificate Generator")
    _draw(
        pdf,
        recipient_name=recipient_name,
        event_title=event_title,
        issuer=issuer,
        issue_date=issue_date,
        description=description,
        detail=detail,
        certificate_number=certificate_number,
        verify_url=verify_url,
        signatory_name=signatory_name,
        signatory_title=signatory_title,
    )
    pdf.showPage()
    pdf.save()


def _ensure_drawable(labeled_texts: list[tuple[str, str]]) -> None:
    face = pdfmetrics.getFont("DejaVuSerif").face
    for label, text in labeled_texts:
        for character in text:
            if character.isspace():
                continue
            glyph = face.charToGlyph.get(ord(character))
            if glyph in (None, 0):
                raise CertificateRenderError(
                    f"{label} contains a character the certificate font cannot draw: {character!r}"
                )


def _draw(pdf: canvas.Canvas, **fields) -> None:
    _frame(pdf)
    y = _header(pdf, fields["issuer"])
    y = _recipient_block(
        pdf,
        y,
        name=fields["recipient_name"],
        description=fields["description"],
        event_title=fields["event_title"],
        detail=fields["detail"],
    )
    _footer(
        pdf,
        y,
        issue_date=fields["issue_date"],
        certificate_number=fields["certificate_number"],
        verify_url=fields["verify_url"],
        signatory_name=fields["signatory_name"],
        signatory_title=fields["signatory_title"],
    )


def _frame(pdf: canvas.Canvas) -> None:
    pdf.setFillColor(CREAM)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)

    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(2.6)
    pdf.rect(16, 16, PAGE_WIDTH - 32, PAGE_HEIGHT - 32, stroke=1, fill=0)

    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.9)
    pdf.rect(24, 24, PAGE_WIDTH - 48, PAGE_HEIGHT - 48, stroke=1, fill=0)

    pdf.setStrokeColor(GOLD_SOFT)
    pdf.setLineWidth(0.6)
    pdf.rect(30, 30, PAGE_WIDTH - 60, PAGE_HEIGHT - 60, stroke=1, fill=0)

    for x, y in (
        (40, PAGE_HEIGHT - 40),
        (PAGE_WIDTH - 40, PAGE_HEIGHT - 40),
        (40, 40),
        (PAGE_WIDTH - 40, 40),
    ):
        _diamond(pdf, x, y, 3.5)


def _header(pdf: canvas.Canvas, issuer: str) -> float:
    y = PAGE_HEIGHT - 62
    _text(pdf, issuer.upper(), y, "DejaVuSans", 10, NAVY, width=PAGE_WIDTH - 180)
    y -= 16
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.line(PAGE_WIDTH / 2 - 78, y, PAGE_WIDTH / 2 + 78, y)
    y -= 42
    _text(pdf, "CERTIFICATE", y, "DejaVuSerif-Bold", 34, NAVY, char_space=2.4)
    y -= 20
    _text(pdf, "OF COMPLETION", y, "DejaVuSans", 10, GOLD, char_space=3.4)
    return y - 34


def _recipient_block(
    pdf: canvas.Canvas,
    y: float,
    *,
    name: str,
    description: str,
    event_title: str,
    detail: str | None,
) -> float:
    _text(pdf, "This is to certify that", y, "DejaVuSerif-Italic", 12, MUTED)
    y -= 42
    name_font = "DejaVuSerif-BoldItalic"
    name_width_limit = PAGE_WIDTH - 170
    name_size = 30
    while name_size > 16 and stringWidth(name, name_font, name_size) > name_width_limit:
        name_size -= 1
    name_lines = _wrap(name, name_font, name_size, name_width_limit)
    if len(name_lines) > 2:
        name_size = 14
        name_lines = _wrap(name, name_font, name_size, name_width_limit)[:2]
    for line in name_lines:
        _text(pdf, line, y, name_font, name_size, INK)
        y -= name_size + 2
    y += name_size + 2
    name_width = min(
        max(max(stringWidth(line, name_font, name_size) for line in name_lines), 160),
        PAGE_WIDTH - 240,
    )
    y -= 12
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1)
    pdf.line(PAGE_WIDTH / 2 - name_width / 2, y, PAGE_WIDTH / 2 + name_width / 2, y)
    y -= 30

    for line in _wrap(description, "DejaVuSerif-Italic", 12, PAGE_WIDTH - 200)[:3]:
        _text(pdf, line, y, "DejaVuSerif-Italic", 12, MUTED)
        y -= 16
    y -= 12

    title_size = _fit_size(event_title, "DejaVuSerif-Bold", 18, 12, PAGE_WIDTH - 180)
    for line in _wrap(event_title, "DejaVuSerif-Bold", title_size, PAGE_WIDTH - 180)[:2]:
        _text(pdf, line, y, "DejaVuSerif-Bold", title_size, NAVY)
        y -= title_size + 4

    if detail:
        y -= 6
        detail_size = _fit_size(detail, "DejaVuSans", 11, 8, PAGE_WIDTH - 200)
        _text(pdf, detail, y, "DejaVuSans", detail_size, MUTED)
        y -= 16
    return y


def _footer(
    pdf: canvas.Canvas,
    _content_bottom: float,
    *,
    issue_date: date,
    certificate_number: str,
    verify_url: str,
    signatory_name: str,
    signatory_title: str,
) -> None:
    pdf.setStrokeColor(GOLD_SOFT)
    pdf.setLineWidth(0.6)
    pdf.line(72, 168, PAGE_WIDTH - 72, 168)

    line_x = 78
    pdf.setStrokeColor(NAVY)
    pdf.setLineWidth(0.8)
    pdf.line(line_x, 124, line_x + 180, 124)
    _left_text(pdf, signatory_name, line_x, 106, "DejaVuSerif-Bold", 10, INK, 180)
    _left_text(pdf, signatory_title, line_x, 90, "DejaVuSans", 8, MUTED, 180)

    seal_x = PAGE_WIDTH / 2
    _seal(pdf, seal_x, 112, issue_date.year)
    issued = f"{issue_date.day} {issue_date.strftime('%B')} {issue_date.year}"
    _text(pdf, issued, 62, "DejaVuSans", 9, NAVY)

    qr_size = 78
    qr_x = PAGE_WIDTH - 78 - qr_size
    qr_y = 78
    pdf.drawImage(
        _qr_image(verify_url),
        qr_x,
        qr_y,
        width=qr_size,
        height=qr_size,
        mask="auto",
    )
    _text_at(pdf, "Scan to verify", qr_x + qr_size / 2, 64, "DejaVuSans", 7.5, MUTED)
    _text_at(pdf, certificate_number, qr_x + qr_size / 2, 52, "DejaVuSans", 6.5, NAVY)


def _seal(pdf: canvas.Canvas, x: float, y: float, year: int) -> None:
    pdf.setFillColor(SEAL_FILL)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.5)
    pdf.circle(x, y, 32, stroke=1, fill=1)
    pdf.setLineWidth(0.6)
    pdf.circle(x, y, 27, stroke=1, fill=0)
    _text_at(pdf, "CERTIFIED", x, y + 4, "DejaVuSans", 6.5, NAVY)
    _text_at(pdf, str(year), x, y - 10, "DejaVuSerif-Bold", 9, NAVY)


def _diamond(pdf: canvas.Canvas, x: float, y: float, radius: float) -> None:
    pdf.setStrokeColor(GOLD)
    pdf.setFillColor(GOLD)
    pdf.setLineWidth(0.4)
    path = pdf.beginPath()
    path.moveTo(x, y + radius)
    path.lineTo(x + radius, y)
    path.lineTo(x, y - radius)
    path.lineTo(x - radius, y)
    path.close()
    pdf.drawPath(path, stroke=1, fill=1)


def _qr_image(value: str) -> ImageReader:
    code = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=8, border=1)
    code.add_data(value)
    code.make(fit=True)
    image = code.make_image(fill_color="#1B3A4B", back_color="#FBF7EF")
    return ImageReader(image.get_image())


def _text(
    pdf: canvas.Canvas,
    text: str,
    y: float,
    font: str,
    size: float,
    color,
    *,
    width: float | None = None,
    char_space: float = 0,
) -> None:
    if width is not None:
        size = _fit_size(text, font, size, max(size - 3, 7), width)
    _text_at(pdf, text, PAGE_WIDTH / 2, y, font, size, color, char_space=char_space)


def _text_at(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font: str,
    size: float,
    color,
    *,
    char_space: float = 0,
) -> None:
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    pdf.drawCentredString(x, y, text, charSpace=char_space)


def _left_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    font: str,
    size: float,
    color,
    width: float,
) -> None:
    fitted = _fit_size(text, font, size, 7, width)
    pdf.setFillColor(color)
    pdf.setFont(font, fitted)
    pdf.drawString(x, y, text)


def _fit_size(text: str, font: str, maximum: float, minimum: float, width: float) -> float:
    size = maximum
    while size > minimum and stringWidth(text, font, size) > width:
        size -= 0.5
    return size


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if stringWidth(trial, font, size) <= width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
