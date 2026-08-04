# PDFreader

Splits a PDF into individual pages, uses Claude's vision API to read the
**form number**, **serial number**, and **date** off each page, then renames
each page `FormNumber-SerialNumber.pdf` and files it into a month folder
based on the extracted date. Prints a summary when it's done.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

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

## What it does

1. Splits each input PDF into single-page PDFs.
2. Renders each page to an image and asks Claude to extract the form
   number, serial number, and date via a structured tool call.
3. Renames the page `FormNumber-SerialNumber.pdf` (the month/date is **not**
   included in the filename, only used to pick the folder).
4. Moves the file into `OUTPUT_DIR/YYYY-MM MonthName/` based on the
   extracted date (e.g. `organized/2026-03 March/`).
5. Pages where Claude couldn't find a form number or serial number, or
   where extraction failed, are moved to `OUTPUT_DIR/_needs_review/`
   instead, named after the source file and page number, so nothing is
   silently lost.
6. Prints a summary: total pages processed, how many were organized
   successfully, how many need review, how many errored, and a
   per-month breakdown.

## Notes

- If two pages resolve to the same `FormNumber-SerialNumber.pdf` in the
  same month folder, later files get a `(2)`, `(3)`, ... suffix rather
  than overwriting.
- Extraction accuracy depends on scan quality and the vision model; always
  check the `_needs_review` folder after a run.
