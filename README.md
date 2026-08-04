# PDFreader

Two tools, same job: split a scanned PDF into pages, use Claude's vision
API to read the **form number**, **serial number**, and **date** off each
page, rename each page `FormNumber-SerialNumber.pdf`, and file it into a
month folder based on the extracted date (the month is never part of the
filename, only the folder). Both print/show a summary when done.

- **`organize.py`** — a command-line tool for processing PDFs already on
  your machine.
- **`webapp/`** — a mobile-friendly web app: upload a PDF from your phone's
  browser and download a ZIP of the organized pages.

## CLI: `organize.py`

### Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

### Usage

```bash
python organize.py input.pdf
python organize.py input1.pdf input2.pdf -o ~/Documents/Organized
python organize.py ./scans -o ~/Documents/Organized --recursive
```

Options:

| Flag | Description |
| --- | --- |
| `inputs` | One or more PDF files and/or directories containing PDFs |
| `-o, --output-dir` | Where organized files go (default: `./organized`) |
| `-r, --recursive` | Recurse into subdirectories when an input is a directory |
| `--model` | Claude model to use for extraction (default: `claude-sonnet-4-5-20250929`, override with `ANTHROPIC_MODEL` or `--model`) |
| `--dpi` | Rendering resolution used for the vision extraction (default: `200`) |

### What it does

1. Splits each input PDF into single-page PDFs.
2. Renders each page to an image and asks Claude to extract the form
   number, serial number, and date via a structured tool call.
3. Renames the page `FormNumber-SerialNumber.pdf`.
4. Moves the file into `OUTPUT_DIR/YYYY-MM MonthName/` based on the
   extracted date (e.g. `organized/2026-03 March/`).
5. Pages where Claude couldn't find a form number or serial number, or
   where extraction failed, are moved to `OUTPUT_DIR/_needs_review/`
   instead, named after the source file and page number, so nothing is
   silently lost.
6. Prints a summary: total pages processed, how many were organized
   successfully, how many need review, how many errored, and a
   per-month breakdown.

## Web app: `webapp/`

Upload a scanned PDF from your phone's browser. The app:

1. Splits the PDF into individual pages.
2. Sends each page to Claude's vision API (as a native PDF document, so no
   local rasterization is needed) to extract the form number, serial
   number, and date.
3. Renames each page `FormNumber-SerialNumber.pdf`.
4. Groups pages into month folders (e.g. `2026-08 August`).
5. Packages everything into a ZIP you download, with a live progress bar
   and a summary of how many pages were processed.

Pages missing a required field land in an `_NeedsReview` folder instead of
being guessed.

### Setup

```bash
cd webapp
npm install
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
npm start
```

Open `http://localhost:3000` (or your deployed URL) on your phone and
upload a PDF.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Server-side Anthropic API key, never exposed to the browser. |
| `PORT` | `3000` | HTTP port. |
| `CLAUDE_MODEL` | `claude-sonnet-5` | Vision-capable Claude model used for extraction. |
| `CLAUDE_CONCURRENCY` | `3` | Max pages sent to Claude in parallel per upload. |

### How it works

- `src/pdfSplitter.js` — splits the uploaded PDF into single-page PDF buffers with `pdf-lib`.
- `src/claudeExtractor.js` — sends each single-page PDF to Claude as a `document` content block and parses the structured JSON it returns (`form_number`, `serial_number`, `date`).
- `src/organizer.js` — sanitizes filenames, picks the month folder from the extracted date, de-dupes filename collisions, and streams a ZIP with `archiver`.
- `src/server.js` — Express app: `POST /api/upload` splits and stages the PDF, `GET /api/process/:jobId` is a Server-Sent Events stream that processes pages with bounded concurrency and reports live progress, `GET /api/download/:jobId` serves the finished ZIP.
- `public/` — a single mobile-friendly page (file picker → progress bar → summary + download).

Jobs and their temp files live in memory / the OS temp dir and are cleaned
up automatically after 2 hours.

## Notes (both tools)

- Only the primary date found on a page is used for folder assignment. No legible date → `_needs_review` / `_NeedsReview`.
- Filenames are sanitized and de-duplicated within a folder (`Name (2).pdf`, `Name (3).pdf`, ...).
- Both call the Claude API; you're billed per Anthropic's API pricing for each page processed.
