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


def unit_pdf_bytes(path: Path, page: int, top: float, bottom: float) -> bytes:
    """PDF ar vienu kvīti: vesela lapa vai tās daļa (ja lapā ir vairākas kvītis)."""
    whole_page = top <= 0.001 and bottom >= 0.999
    if whole_page and page_count(path) == 1:
        return as_pdf_bytes(path)
    if whole_page and not is_image(path):
        with pymupdf.open(path) as src, pymupdf.open() as out:
            out.insert_pdf(src, from_page=page, to_page=page)
            return out.tobytes(garbage=3, deflate=True)
    # Kvīts ir lapas daļa: izgriežam attēlu (lai PDF nesatur otru kvīti).
    if is_image(path):
        img = _open_image(path)
    else:
        img = render_page(path, page=page, dpi=200)
    crop = img.crop((0, int(top * img.height), img.width, int(bottom * img.height)))
    buf = io.BytesIO()
    crop.save(buf, "PDF", resolution=200.0)
    return buf.getvalue()
