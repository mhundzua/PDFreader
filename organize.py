#!/usr/bin/env python3
"""
Split PDFs into individual pages, use Claude's vision API to read the form
number, serial number, and date off each page, then rename and file each
page into a month folder.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python organize.py INPUT [INPUT ...] [-o OUTPUT_DIR] [--model MODEL]

INPUT may be one or more PDF files and/or directories containing PDFs.
"""

from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from anthropic import Anthropic

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

EXTRACTION_TOOL = {
    "name": "record_form_fields",
    "description": "Record the form number, serial number, and date found on the page.",
    "input_schema": {
        "type": "object",
        "properties": {
            "form_number": {
                "type": ["string", "null"],
                "description": (
                    "The form number/identifier printed on the page "
                    "(e.g. 'W-9', 'DD-214'). Null if not visible."
                ),
            },
            "serial_number": {
                "type": ["string", "null"],
                "description": (
                    "The serial number, document number, or unique ID "
                    "printed on the page. Null if not visible."
                ),
            },
            "date": {
                "type": ["string", "null"],
                "description": (
                    "The date printed on the page, normalized to ISO "
                    "format YYYY-MM-DD. Null if not visible or the day "
                    "cannot be determined."
                ),
            },
        },
        "required": ["form_number", "serial_number", "date"],
    },
}

FILENAME_SAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MONTH_PREFIX_RE = re.compile(r"^(\d{4})-(\d{2})(?:-\d{2})?")
MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def sanitize(value: Optional[str], fallback: str) -> str:
    value = (value or "").strip()
    if not value:
        return fallback
    value = FILENAME_SAFE_RE.sub("_", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or fallback


def month_folder_name(date_str: Optional[str]) -> str:
    if not date_str:
        return "Unknown-Date"
    match = MONTH_PREFIX_RE.match(date_str.strip())
    if not match:
        return "Unknown-Date"
    year, month = match.groups()
    try:
        name = MONTH_NAMES[int(month)]
    except (ValueError, IndexError):
        return "Unknown-Date"
    return f"{year}-{month} {name}"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 2
    while True:
        candidate = path.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


@dataclass
class PageResult:
    source_pdf: str
    page_number: int
    form_number: Optional[str] = None
    serial_number: Optional[str] = None
    date: Optional[str] = None
    output_path: Optional[str] = None
    status: str = "pending"  # ok, needs_review, error
    error: Optional[str] = None


def split_pdf(pdf_path: Path, tmp_dir: Path) -> list[Path]:
    doc = fitz.open(pdf_path)
    page_paths = []
    try:
        for i in range(len(doc)):
            single = fitz.open()
            single.insert_pdf(doc, from_page=i, to_page=i)
            out_path = tmp_dir / f"{pdf_path.stem}_page{i + 1:03d}.pdf"
            single.save(out_path)
            single.close()
            page_paths.append(out_path)
    finally:
        doc.close()
    return page_paths


def render_page_png(pdf_path: Path, dpi: int) -> bytes:
    doc = fitz.open(pdf_path)
    try:
        page = doc[0]
        zoom = dpi / 72
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
    finally:
        doc.close()


def extract_fields(client: Anthropic, model: str, png_bytes: bytes) -> dict:
    image_b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[EXTRACTION_TOOL],
        tool_choice={"type": "tool", "name": "record_form_fields"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "Look at this scanned page and find its form number, "
                            "serial number, and date. Use the record_form_fields "
                            "tool to report what you find. If a field is not "
                            "present on the page, use null for it rather than "
                            "guessing."
                        ),
                    },
                ],
            }
        ],
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "record_form_fields":
            return block.input
    raise RuntimeError("Claude did not return structured fields for this page")


def process_pdf(
    client: Anthropic,
    model: str,
    pdf_path: Path,
    output_dir: Path,
    tmp_dir: Path,
    dpi: int,
) -> list[PageResult]:
    try:
        page_paths = split_pdf(pdf_path, tmp_dir)
    except Exception as e:  # noqa: BLE001 - report and continue with other files
        return [
            PageResult(
                source_pdf=str(pdf_path),
                page_number=0,
                status="error",
                error=f"Failed to split PDF: {e}",
            )
        ]

    results = []
    for i, page_path in enumerate(page_paths, start=1):
        result = PageResult(source_pdf=str(pdf_path), page_number=i)
        try:
            png_bytes = render_page_png(page_path, dpi)
            fields = extract_fields(client, model, png_bytes)
            result.form_number = fields.get("form_number")
            result.serial_number = fields.get("serial_number")
            result.date = fields.get("date")
        except Exception as e:  # noqa: BLE001 - keep going, file goes to review
            result.error = str(e)

        if result.form_number and result.serial_number and not result.error:
            folder = output_dir / month_folder_name(result.date)
            filename = (
                f"{sanitize(result.form_number, 'UnknownForm')}-"
                f"{sanitize(result.serial_number, 'UnknownSerial')}.pdf"
            )
            result.status = "ok"
        else:
            folder = output_dir / "_needs_review"
            filename = f"{pdf_path.stem}_page{i:03d}.pdf"
            result.status = "error" if result.error else "needs_review"

        folder.mkdir(parents=True, exist_ok=True)
        dest = unique_path(folder / filename)
        page_path.replace(dest)
        result.output_path = str(dest)
        results.append(result)

    return results


def gather_inputs(paths: list[str], recursive: bool) -> list[Path]:
    pdfs: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            pattern = "**/*.pdf" if recursive else "*.pdf"
            pdfs.extend(sorted(p.glob(pattern)))
        elif p.suffix.lower() == ".pdf":
            pdfs.append(p)
        else:
            print(f"Skipping non-PDF input: {p}", file=sys.stderr)
    return pdfs


def print_summary(results: list[PageResult], output_dir: Path) -> None:
    total = len(results)
    ok = [r for r in results if r.status == "ok"]
    needs_review = [r for r in results if r.status == "needs_review"]
    errors = [r for r in results if r.status == "error"]

    by_month: dict[str, int] = {}
    for r in ok:
        month = month_folder_name(r.date)
        by_month[month] = by_month.get(month, 0) + 1

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Pages processed: {total}")
    print(f"  Organized successfully: {len(ok)}")
    print(f"  Needs review (missing form/serial number): {len(needs_review)}")
    print(f"  Errors: {len(errors)}")

    if by_month:
        print("\nBy month:")
        for month, count in sorted(by_month.items()):
            print(f"  {month}: {count} file(s)")

    if needs_review:
        print("\nNeeds review:")
        for r in needs_review:
            print(f"  {r.source_pdf} (page {r.page_number}) -> {r.output_path}")

    if errors:
        print("\nErrors:")
        for r in errors:
            print(f"  {r.source_pdf} (page {r.page_number}): {r.error}")

    print(f"\nOutput directory: {output_dir.resolve()}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs", nargs="+", help="PDF file(s) or directory(ies) containing PDFs"
    )
    parser.add_argument(
        "-o", "--output-dir", default="organized",
        help="Directory to write organized files into (default: ./organized)",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Claude model to use for vision extraction (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--dpi", type=int, default=200,
        help="Resolution used when rendering pages for vision extraction (default: 200)",
    )
    parser.add_argument(
        "-r", "--recursive", action="store_true",
        help="Recurse into subdirectories when an input is a directory",
    )
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    pdfs = gather_inputs(args.inputs, args.recursive)
    if not pdfs:
        print("No PDF files found.", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    client = Anthropic(api_key=api_key)

    all_results: list[PageResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        for pdf_path in pdfs:
            print(f"Processing {pdf_path} ...")
            results = process_pdf(client, args.model, pdf_path, output_dir, tmp_dir, args.dpi)
            all_results.extend(results)

    print_summary(all_results, output_dir)


if __name__ == "__main__":
    main()
