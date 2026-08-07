"""PDF Form Organizer web app.

Upload a scanned PDF, split it into pages, use Claude's vision API to
extract a form number / serial number / date from each page, rename each
page to "FormNumber-SerialNumber.pdf", sort the pages into "YYYY-MM" month
folders based on the extracted date, and offer the organized result as a
downloadable zip.
"""

import logging
import os
import shutil
import tempfile
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
import pymupdf as fitz
from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request, send_file
from pypdf import PdfReader

from extraction import extract_page_fields
from pdf_utils import (
    PageResult,
    build_filename,
    month_folder_for_date,
    render_page_png,
    split_page_pdf,
    unique_path,
    zip_directory,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 75 * 1024 * 1024  # 75 MB upload cap

JOBS_ROOT = os.path.join(tempfile.gettempdir(), "pdfreader_jobs")
os.makedirs(JOBS_ROOT, exist_ok=True)

JOB_TTL_SECONDS = 2 * 60 * 60  # delete job directories older than this
MAX_WORKERS = 6  # concurrent Claude API calls


def cleanup_old_jobs() -> None:
    now = time.time()
    for name in os.listdir(JOBS_ROOT):
        path = os.path.join(JOBS_ROOT, name)
        try:
            if now - os.path.getmtime(path) > JOB_TTL_SECONDS:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    cleanup_old_jobs()

    uploaded = request.files.get("pdf")
    if not uploaded or uploaded.filename == "":
        return jsonify({"error": "No PDF file uploaded."}), 400
    if not uploaded.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Please upload a PDF file."}), 400

    try:
        client = anthropic.Anthropic()
    except Exception as exc:  # missing/invalid credentials
        return jsonify({"error": f"Could not initialize the Claude API client: {exc}"}), 500

    job_id = uuid.uuid4().hex
    job_dir = os.path.join(JOBS_ROOT, job_id)
    output_dir = os.path.join(job_dir, "output")
    os.makedirs(output_dir, exist_ok=True)

    input_path = os.path.join(job_dir, "input.pdf")
    uploaded.save(input_path)

    try:
        reader = PdfReader(input_path)
        page_count = len(reader.pages)
    except Exception as exc:
        return jsonify({"error": f"Could not read PDF: {exc}"}), 400

    if page_count == 0:
        return jsonify({"error": "The uploaded PDF has no pages."}), 400

    # Step 1: split pages and render page images. This touches the PDF
    # library objects, which aren't safe to share across threads, so it
    # runs sequentially in the main thread.
    doc = fitz.open(input_path)
    page_data = []
    for i in range(page_count):
        png_bytes = render_page_png(doc, i)
        pdf_bytes = split_page_pdf(reader, i)
        page_data.append((i, png_bytes, pdf_bytes))
    doc.close()

    # Step 2: run the Claude vision extraction concurrently, since that's
    # the slow, network-bound part.
    extraction_results = [None] * page_count

    def run_extraction(i: int, png_bytes: bytes):
        try:
            return i, extract_page_fields(client, png_bytes), None
        except Exception as exc:
            logger.exception("Extraction failed for page %s", i + 1)
            return i, None, str(exc)

    with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, page_count)) as executor:
        futures = [executor.submit(run_extraction, i, png) for i, png, _ in page_data]
        for future in as_completed(futures):
            i, fields, error = future.result()
            extraction_results[i] = (fields, error)

    # Step 3: build filenames/folders and write files. Sequential, cheap.
    results = []
    for i, _png_bytes, pdf_bytes in page_data:
        page_number = i + 1
        fields, error = extraction_results[i]
        result = PageResult(page_number=page_number)

        if error:
            result.error = error
            result.needs_review = True
            folder = "Errors"
            base_name = f"Page_{page_number:03d}"
        else:
            result.form_number = fields.get("form_number")
            result.serial_number = fields.get("serial_number")
            result.date = fields.get("date")
            base_name, missing_fields = build_filename(result.form_number, result.serial_number)
            folder, has_date = month_folder_for_date(result.date)
            result.needs_review = missing_fields or not has_date

        result.folder = folder
        dest_dir = os.path.join(output_dir, folder)
        dest_path = unique_path(dest_dir, base_name)
        with open(dest_path, "wb") as f:
            f.write(pdf_bytes)
        result.filename = os.path.basename(dest_path)
        results.append(result)

    zip_path = os.path.join(job_dir, "organized_forms.zip")
    zip_directory(output_dir, zip_path)

    folder_counts: dict[str, int] = {}
    review_count = 0
    error_count = 0
    for r in results:
        folder_counts[r.folder] = folder_counts.get(r.folder, 0) + 1
        if r.needs_review:
            review_count += 1
        if r.error:
            error_count += 1

    summary = {
        "job_id": job_id,
        "total_pages": page_count,
        "processed": len(results),
        "needs_review": review_count,
        "errors": error_count,
        "folders": [
            {"name": name, "count": count} for name, count in sorted(folder_counts.items())
        ],
        "pages": [
            {
                "page_number": r.page_number,
                "folder": r.folder,
                "filename": r.filename,
                "form_number": r.form_number,
                "serial_number": r.serial_number,
                "date": r.date,
                "needs_review": r.needs_review,
                "error": r.error,
            }
            for r in results
        ],
        "download_url": f"/download/{job_id}",
    }

    return jsonify(summary)


@app.route("/download/<job_id>")
def download(job_id):
    if not job_id.isalnum():
        abort(404)
    zip_path = os.path.join(JOBS_ROOT, job_id, "organized_forms.zip")
    if not os.path.exists(zip_path):
        abort(404)
    return send_file(zip_path, as_attachment=True, download_name="organized_forms.zip")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
