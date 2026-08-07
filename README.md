# PDF Form Organizer

Upload a scanned PDF (from your phone or desktop browser). The app:

1. Splits the PDF into individual pages.
2. Renders each page as an image and sends it to Claude's vision API to
   extract the **form number**, **serial number**, and **date** printed on
   that page.
3. Renames each page's single-page PDF to `FormNumber-SerialNumber.pdf`
   (the month is not put in the filename).
4. Creates a `YYYY-MM` folder per month based on the extracted date and
   moves each file into the correct folder.
5. Zips the organized result and gives you a summary + download link.

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
```

Run it:

```bash
python app.py
```

By default it listens on `0.0.0.0:5000`, so from your phone (on the same
Wi-Fi network) you can browse to `http://<your-computer's-LAN-IP>:5000`.
To expose it outside your local network for testing on a phone, use a
tunnel like `ngrok http 5000`, or deploy it to a small host (Fly.io,
Render, a VPS, etc.).

## How pages are organized

- **Filename**: `{FormNumber}-{SerialNumber}.pdf`. If either value is
  missing or unreadable, it's replaced with `UnknownForm` / `UnknownSerial`
  and the page is flagged as "needs review" in the summary — it's still
  renamed and filed, just with placeholders.
- **Folder**: `YYYY-MM` derived from the extracted date (e.g. `2026-03`).
  If no date could be read, the page goes into an `Unsorted` folder instead.
- **Duplicate filenames**: if two pages would produce the same filename in
  the same folder, `_2`, `_3`, etc. are appended.
- **Failed extraction** (API error, refusal, etc.): the page still ends up
  in the zip, under an `Errors` folder, named `Page_XXX.pdf`, so nothing is
  silently dropped.

## Notes / things you may want to tune

- **Model**: uses `claude-opus-5` (see `extraction.py`). Swap the `MODEL`
  constant if you want a cheaper/faster model for high page-volume batches.
- **Processing is synchronous**: the `/upload` request blocks until every
  page is processed (pages are extracted concurrently, up to `MAX_WORKERS`
  in `app.py`). For very large PDFs this can take a while and may hit
  browser/proxy timeouts — if you expect large documents regularly, this is
  the first thing to turn into a background job with polling.
- **Storage**: uploads and results are written to a temp directory
  (`pdfreader_jobs` under your OS temp dir) and cleaned up automatically
  after 2 hours (`JOB_TTL_SECONDS` in `app.py`). Nothing is persisted
  long-term.
- **Upload size limit**: 75 MB (`MAX_CONTENT_LENGTH` in `app.py`).

## Project layout

```
app.py            Flask routes / orchestration
extraction.py      Claude vision call + JSON schema for extraction
pdf_utils.py       Page splitting, rendering, filename/folder logic, zipping
templates/         Mobile-friendly upload page
static/            JS + CSS for the upload page
```
