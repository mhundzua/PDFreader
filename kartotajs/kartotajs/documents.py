"""Atbalstītie failu veidi: PDF un attēli (JPG, PNG, HEIC u.c.)."""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image, ImageOps

try:  # iPhone fotogrāfijas (HEIC)
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIC_SUPPORTED = True
except ImportError:
    HEIC_SUPPORTED = False

PDF_EXTS = {".pdf"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".bmp"}
if HEIC_SUPPORTED:
    IMAGE_EXTS |= {".heic", ".heif"}
SUPPORTED_EXTS = PDF_EXTS | IMAGE_EXTS

# Lielas telefona fotogrāfijas OCR vajadzībām samazinām līdz šim platumam.
MAX_IMAGE_WIDTH = 2400


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTS


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def _open_image(path: Path) -> Image.Image:
    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)  # telefona foto pareizajā orientācijā
        return img.convert("RGB")


def render_page(path: Path, page: int = 0, dpi: int = 200) -> Image.Image:
    if is_image(path):
        img = _open_image(path)
        if img.width > MAX_IMAGE_WIDTH:
            img = img.resize((MAX_IMAGE_WIDTH, round(img.height * MAX_IMAGE_WIDTH / img.width)))
        return img
    with pymupdf.open(path) as doc:
        pix = doc[page].get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def page_count(path: Path) -> int:
    if is_image(path):
        return 1
    with pymupdf.open(path) as doc:
        return doc.page_count


def as_pdf_bytes(path: Path) -> bytes:
    """PDF saturs saglabāšanai: PDF paliek nemainīts, attēls tiek pārvērsts PDF."""
    if not is_image(path):
        return path.read_bytes()
    img = _open_image(path)
    buf = io.BytesIO()
    # 200 dpi: A5/A4 kvīts drukājot būs aptuveni dabiskā izmērā.
    img.save(buf, "PDF", resolution=200.0)
    return buf.getvalue()


def content_box(img: Image.Image, margin: float = 0.015):
    """Kur lapā ir saturs (kvīts), ja apkārt ir tukšs papīrs. None, ja nogriezt nav ko."""
    import numpy as np

    small = img.convert("L")
    scale = 600 / max(small.size)
    if scale < 1:
        small = small.resize((max(1, int(small.width * scale)), max(1, int(small.height * scale))))
    a = np.asarray(small) < 170  # tumši pikseļi: teksts, līnijas, rokraksts
    rows = np.where(a.sum(1) > a.shape[1] * 0.01)[0]
    cols = np.where(a.sum(0) > a.shape[0] * 0.01)[0]
    if len(rows) == 0 or len(cols) == 0:
        return None
    h, w = a.shape
    y0, y1, x0, x1 = rows[0], rows[-1] + 1, cols[0], cols[-1] + 1
    # Nogriežam tikai tad, ja tukšā daļa ir ievērojama (piem. A5 kvīts uz A4 lapas).
    if (y1 - y0) > 0.85 * h and (x1 - x0) > 0.85 * w:
        return None
    my, mx = int(margin * h), int(margin * w)
    y0, y1 = max(0, y0 - my), min(h, y1 + my)
    x0, x1 = max(0, x0 - mx), min(w, x1 + mx)
    k = img.width / w
    return (int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k))


def unit_pdf_bytes(path: Path, page: int, top: float, bottom: float) -> bytes:
    """PDF ar vienu kvīti: vesela lapa vai tās daļa (ja lapā ir vairākas kvītis).

    Tukšo papīru ap kvīti (piem. viena A5 kvīts, skenēta kā A4) nogriež.
    """
    whole_page = top <= 0.001 and bottom >= 0.999
    if is_image(path):
        img = _open_image(path)
    else:
        img = render_page(path, page=page, dpi=200)
    region = img.crop((0, int(top * img.height), img.width, int(bottom * img.height)))
    box = content_box(region)
    if box is None and whole_page:
        # Nekas nav jānogriež: saglabājam oriģinālu bez pārkodēšanas.
        if page_count(path) == 1:
            return as_pdf_bytes(path)
        if not is_image(path):
            with pymupdf.open(path) as src, pymupdf.open() as out:
                out.insert_pdf(src, from_page=page, to_page=page)
                return out.tobytes(garbage=3, deflate=True)
    if box is not None:
        region = region.crop(box)
    buf = io.BytesIO()
    region.save(buf, "PDF", resolution=200.0)
    return buf.getvalue()
