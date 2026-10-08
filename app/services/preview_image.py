import io
from pathlib import Path

import pypdfium2 as pdfium


def render_pdf_png(path: Path, scale: float = 1.6) -> bytes:
    """Rasterize the first page so the browser can show the certificate itself."""

    document = pdfium.PdfDocument(str(path))
    try:
        bitmap = document[0].render(scale=scale)
        image = bitmap.to_pil()
    finally:
        document.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
