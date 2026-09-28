"""Рендеринг страниц PDF в PNG для передачи в vision-модель."""
from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

import pymupdf

# Ограничение Anthropic API: сторона <= 8000 px, вес <= 5 МБ на изображение.
MAX_SIDE = 1800
JPEG_QUALITY = 85


@dataclass
class Page:
    index: int          # 0-based номер страницы в PDF
    png: bytes          # отрендеренная страница
    rotation: int = 0   # применённый поворот в градусах

    @property
    def b64(self) -> str:
        return base64.standard_b64encode(self.png).decode()


def render(pdf_path: Path, dpi: int = 150, pages: list[int] | None = None) -> list[Page]:
    """Рендерит страницы PDF в PNG, ужимая до MAX_SIDE по длинной стороне."""
    doc = pymupdf.open(pdf_path)
    try:
        indices = pages if pages is not None else range(len(doc))
        out = []
        for i in indices:
            pix = doc[i].get_pixmap(dpi=dpi)
            scale = MAX_SIDE / max(pix.width, pix.height)
            if scale < 1:
                pix = doc[i].get_pixmap(dpi=int(dpi * scale))
            out.append(Page(index=i, png=pix.tobytes("png")))
        return out
    finally:
        doc.close()


def rotate(page: Page, degrees: int) -> Page:
    """Поворачивает уже отрендеренную страницу (сканы бывают вверх ногами)."""
    if degrees % 360 == 0:
        return page
    from PIL import Image

    img = Image.open(io.BytesIO(page.png))
    img = img.rotate(-degrees, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Page(index=page.index, png=buf.getvalue(), rotation=degrees)
