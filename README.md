# PDF to EPUB Converter

A Python command-line tool that converts PDF files into clean, well-structured EPUB format for comfortable mobile reading. Supports both digital (text-based) PDFs and scanned/image-only PDFs via OCR.

---

## Features

- Extracts text from **digital PDFs** using `pdfplumber`
- Supports **scanned PDFs** via Tesseract OCR (optional)
- **Auto-detects** whether a PDF needs OCR and warns you if so
- **Strips repeating headers and footers** — removes lines that appear across most pages (e.g. running book titles, author names)
- **Removes page number artifacts** — cleans patterns like `3 of 239`, `Page 3`, `- 3 -` from body text
- **Detects chapter headings** — identifies ALL-CAPS lines and promotes them to proper `<h1>`/`<h2>` HTML elements
- **Groups pages into semantic chapters** — merges PDF pages between headings into real chapters, so the table of contents reflects the book's actual structure instead of listing every page
- Builds a valid **EPUB 2.0** file with a generated table of contents, styled chapters, and metadata
- Compatible with **Kindle, Apple Books, Kobo, Google Play Books**, and any standard EPUB reader
- Accepts custom **title, author, and language** metadata
- No external EPUB library required — uses Python's built-in `zipfile` module

---

## Requirements

### Core (digital PDFs)

```bash
pip install pdfplumber pypdf
```

### Optional (scanned / image-only PDFs)

```bash
pip install pytesseract pdf2image Pillow
```

You also need the **Tesseract OCR engine** installed on your system:

- **macOS:** `brew install tesseract`
- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
- **Windows:** Download the installer from [github.com/tesseract-ocr/tesseract](https://github.com/tesseract-ocr/tesseract)

---

## Installation

No installation step needed — just download `pdf_to_epub.py` and run it directly with Python 3.8+.

```bash
# Verify Python version
python3 --version

# Install core dependencies
pip install pdfplumber pypdf
```

---

## Usage

### Basic

```bash
python pdf_to_epub.py input.pdf
```

Produces `input.epub` in the same directory.

### Custom output path

```bash
python pdf_to_epub.py input.pdf -o my_book.epub
```

### Add book metadata

```bash
python pdf_to_epub.py input.pdf --title "My Book Title" --author "Jane Doe" --language en
```

### Force OCR mode (scanned PDFs)

```bash
python pdf_to_epub.py scanned_document.pdf --ocr
```

---

## Command-Line Options

| Option | Short | Description | Default |
|---|---|---|---|
| `pdf` | | Path to the input PDF file | *(required)* |
| `--output` | `-o` | Output `.epub` file path | Same name as PDF |
| `--title` | | Book title embedded in the EPUB | PDF filename |
| `--author` | | Author name embedded in the EPUB | `Unknown` |
| `--language` | | Language code (e.g. `en`, `fr`, `de`) | `en` |
| `--ocr` | | Force OCR mode for scanned PDFs | `false` |

---

## How It Works

### 1. Text Extraction
The script extracts raw text from each PDF page using `pdfplumber`. If `--ocr` is passed, pages are rendered as high-resolution images (300 DPI) via `pdf2image` and Tesseract reads the text from each image instead.

### 2. Header & Footer Removal
The script scans all pages and counts how often each line appears. Any line that shows up on 60% or more of pages is identified as a repeating header or footer (such as a running book title or author name) and stripped from every page before further processing.

### 3. Page Number Cleaning
A regex pass removes bare page-number patterns from the text — things like `3 of 239`, `Page 3`, or `- 3 -` — which PDF extractors commonly pick up as body content.

### 4. Chapter Detection & Grouping
The script scans each page for ALL-CAPS lines that match the profile of a chapter heading (short, mostly uppercase, not purely numeric). When a heading is found, a new chapter begins. All pages between two headings are merged into a single chapter. This means the EPUB's table of contents reflects the book's real structure — `Introduction`, `Chapter I`, `Youth`, etc. — rather than listing every PDF page as a separate entry.

### 5. HTML Rendering
Within each chapter, detected headings are wrapped in `<h2>` tags and rendered with visual hierarchy. Regular text is wrapped in `<p>` tags with proper paragraph indentation, matching standard book formatting conventions.

### 6. EPUB Assembly
The script builds a standards-compliant EPUB 2.0 package using Python's built-in `zipfile` module:
- Each detected chapter → one XHTML file
- A `toc.ncx` table of contents is generated automatically from chapter titles
- Book metadata (title, author, language, UUID) is written to `content.opf`
- A CSS stylesheet ensures clean, readable formatting on mobile screens

---

## Output Structure

The generated `.epub` file contains:

```
mimetype
META-INF/
  container.xml
OEBPS/
  content.opf          ← book metadata & manifest
  toc.ncx              ← table of contents
  Styles/
    style.css
  Text/
    chapter0001.xhtml
    chapter0002.xhtml
    ...
```

---

## Troubleshooting

**"Very little text detected" warning**
Your PDF is likely scanned or image-based. Re-run with `--ocr`:
```bash
python pdf_to_epub.py input.pdf --ocr
```

**OCR ImportError**
Install the OCR dependencies:
```bash
pip install pytesseract pdf2image Pillow
```
And install the Tesseract engine for your OS (see Requirements above).

**Chapter headings not detected**
The heading detector looks for short lines where at least 80% of the letters are uppercase. If your PDF uses title-case headings (e.g. `Chapter One`) instead of ALL-CAPS, they won't be picked up automatically. In this case the script will still produce a valid EPUB, but chapters will be grouped by proximity to any headings it does find.

**Repeating text not being removed**
The header/footer detector requires a line to appear on at least 60% of pages. If your PDF has inconsistent headers, some may slip through. This threshold can be adjusted in the `find_repeating_lines` function by changing the `threshold` parameter.

**Poor OCR quality**
Tesseract performs best on clean, high-contrast scans. For degraded documents, try pre-processing the images (deskew, denoise) before conversion.

**EPUB not opening on Kindle**
Send the file via Amazon's [Send to Kindle](https://www.amazon.com/sendtokindle) service or use [Calibre](https://calibre-ebook.com/) to convert it to `.mobi`/`.azw3` format first.

---

## License

MIT — free to use, modify, and distribute.
