# PDF to EPUB Converter

A Python command-line tool that converts PDF files into EPUB format for comfortable mobile reading. Supports both digital (text-based) PDFs and scanned/image-only PDFs via OCR.

---

## Features

- Extracts text from **digital PDFs** using `pdfplumber`
- Supports **scanned PDFs** via Tesseract OCR (optional)
- **Auto-detects** whether a PDF needs OCR and warns you if so
- Builds a valid **EPUB 2.0** file with a table of contents, styled chapters, and metadata
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

1. **Text Extraction**  
   The script first tries to extract text digitally using `pdfplumber`. Each page's text is preserved as a separate chapter in the output EPUB.

2. **OCR Fallback**  
   If `--ocr` is passed (or if you manually trigger it), the PDF pages are rendered as high-resolution images (300 DPI) using `pdf2image`, and Tesseract reads the text from each image.

3. **EPUB Assembly**  
   The script builds a standards-compliant EPUB 2.0 package from scratch using Python's `zipfile` module:
   - Each PDF page → one XHTML chapter file
   - A `toc.ncx` table of contents is generated automatically
   - Book metadata (title, author, language, UUID) is written to `content.opf`
   - A simple CSS stylesheet ensures clean, readable formatting on mobile screens

---

## Output Structure

The generated `.epub` file contains:

```
mimetype
META-INF/
  container.xml
OEBPS/
  content.opf       ← book metadata & manifest
  toc.ncx           ← table of contents
  Styles/
    style.css
  Text/
    page0001.xhtml
    page0002.xhtml
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

**Poor OCR quality**  
Tesseract performs best on clean, high-contrast scans. For degraded documents, try pre-processing the images (deskew, denoise) before conversion.

**EPUB not opening on Kindle**  
Send the file via Amazon's [Send to Kindle](https://www.amazon.com/sendtokindle) service or use [Calibre](https://calibre-ebook.com/) to convert it to `.mobi`/`.azw3` format first.

---

## License

MIT — free to use, modify, and distribute.
