# PDF Form Organizer

Upload a scanned PDF from your phone. The app:

1. Splits the PDF into individual pages.
2. Sends each page to Claude's vision API (as a native PDF document, so no
   local rasterization is needed) to extract the **form number**, **serial
   number**, and **date** printed on that page.
3. Renames each page `FormNumber-SerialNumber.pdf`.
4. Groups pages into month folders (e.g. `2026-08 August`) based on the
   extracted date. The month never appears in the filename, only the folder.
5. Packages everything into a ZIP you download, and shows a summary of how
   many pages were processed and how many landed in each folder.

Pages where the form number, serial number, or date couldn't be confidently
read are placed in an `_NeedsReview` folder instead of guessing.

## Setup

```bash
npm install
cp .env.example .env
# edit .env and set ANTHROPIC_API_KEY
npm start
```

Open `http://localhost:3000` (or your deployed URL) on your phone and
upload a PDF.

## Configuration

Environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | **Required.** Server-side Anthropic API key, never exposed to the browser. |
| `PORT` | `3000` | HTTP port. |
| `CLAUDE_MODEL` | `claude-sonnet-5` | Vision-capable Claude model used for extraction. |
| `CLAUDE_CONCURRENCY` | `3` | Max pages sent to Claude in parallel per upload. |

## How it works

- `src/pdfSplitter.js` — splits the uploaded PDF into single-page PDF buffers with `pdf-lib`.
- `src/claudeExtractor.js` — sends each single-page PDF to Claude as a `document` content block and parses the structured JSON it returns (`form_number`, `serial_number`, `date`).
- `src/organizer.js` — sanitizes filenames, picks the month folder from the extracted date, de-dupes filename collisions, and streams a ZIP with `archiver`.
- `src/server.js` — Express app: `POST /api/upload` splits and stages the PDF, `GET /api/process/:jobId` is a Server-Sent Events stream that processes pages with bounded concurrency and reports live progress, `GET /api/download/:jobId` serves the finished ZIP.
- `public/` — a single mobile-friendly page (file picker → progress bar → summary + download).

Jobs and their temp files live in memory / the OS temp dir and are cleaned
up automatically after 2 hours.

## Notes

- Only the primary date found on the page is used for folder assignment. If a page has no legible date, it goes to `_NeedsReview`.
- Filenames are sanitized (no `/ \ : * ? " < > |`) and de-duplicated within a folder (`Name (2).pdf`, `Name (3).pdf`, ...).
- This app calls the Claude API server-side; you are billed per Anthropic's API pricing for each page processed.
