"""PDF splitting, page rendering, filename/folder logic, and zipping."""

import io
import os
import re
import zipfile
from dataclasses import dataclass
from typing import Optional

import pymupdf as fitz
from pypdf import PdfReader, PdfWriter

RENDER_ZOOM = 150 / 72  # ~150 DPI, plenty for text extraction

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_component(value: Optional[str], fallback: str) -> str:
    """Make a value safe to use as a filename/folder component."""
    value = (value or "").strip()
    value = INVALID_CHARS.sub("", value)
    value = re.sub(r"\s+", "_", value)
    value = value.strip("._")
    return value or fallback


def render_page_png(doc: fitz.Document, page_index: int) -> bytes:
    page = doc.load_page(page_index)
    pix = page.get_pixmap(matrix=fitz.Matrix(RENDER_ZOOM, RENDER_ZOOM))
    return pix.tobytes("png")


def split_page_pdf(reader: PdfReader, page_index: int) -> bytes:
    writer = PdfWriter()
    writer.add_page(reader.pages[page_index])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@dataclass
class PageResult:
    page_number: int  # 1-indexed
    form_number: Optional[str] = None
    serial_number: Optional[str] = None
    date: Optional[str] = None
    folder: str = "Unsorted"
    filename: str = ""
    error: Optional[str] = None
    needs_review: bool = False


def month_folder_for_date(date_str: Optional[str]):
    """Return (folder_name, is_valid_date) for a YYYY-MM-DD-ish string."""
    if not date_str:
        return "Unsorted", False
    match = re.match(r"^(\d{4})-(\d{2})", date_str)
    if not match:
        return "Unsorted", False
    year, month = match.groups()
    if not (1 <= int(month) <= 12):
        return "Unsorted", False
    return f"{year}-{month}", True


def build_filename(form_number: Optional[str], serial_number: Optional[str]):
    """Return (base_filename_without_ext, needs_review)."""
    needs_review = not form_number or not serial_number
    form_part = sanitize_component(form_number, "UnknownForm")
    serial_part = sanitize_component(serial_number, "UnknownSerial")
    return f"{form_part}-{serial_part}", needs_review


def unique_path(directory: str, base_name: str, ext: str = ".pdf") -> str:
    os.makedirs(directory, exist_ok=True)
    candidate = f"{base_name}{ext}"
    path = os.path.join(directory, candidate)
    counter = 2
    while os.path.exists(path):
        candidate = f"{base_name}_{counter}{ext}"
        path = os.path.join(directory, candidate)
        counter += 1
    return path


def zip_directory(source_dir: str, zip_path: str) -> str:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(source_dir):
            for f in files:
                full_path = os.path.join(root, f)
                arcname = os.path.relpath(full_path, source_dir)
                zf.write(full_path, arcname)
    return zip_path
