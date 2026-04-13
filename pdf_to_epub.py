#!/usr/bin/env python3
"""
pdf_to_epub.py — Convert a PDF file to an EPUB for mobile reading.

Supports:
  • Digital (text-based) PDFs via pdfplumber
  • Scanned / image-only PDFs via pytesseract OCR (optional, install separately)

Usage:
  python pdf_to_epub.py input.pdf                   # output: input.epub
  python pdf_to_epub.py input.pdf -o mybook.epub    # custom output name
  python pdf_to_epub.py input.pdf --ocr             # force OCR mode
  python pdf_to_epub.py input.pdf --title "My Book" --author "Jane Doe"

Requirements (install with pip):
  pip install pdfplumber pypdf
  pip install pytesseract pdf2image Pillow   # only needed for --ocr / scanned PDFs
  # Also install Tesseract OCR engine: https://github.com/tesseract-ocr/tesseract
"""

import argparse
import os
import re
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


def text_to_paragraphs(text: str) -> str:
    """Split raw text into <p> tags, collapsing blank lines into paragraph breaks."""
    paragraphs = re.split(r"\n{2,}", text.strip())
    parts = []
    for para in paragraphs:
        lines = " ".join(para.splitlines()).strip()
        if lines:
            parts.append(f"  <p>{escape_xml(lines)}</p>")
    return "\n".join(parts) if parts else "  <p> </p>"


def make_xhtml(title: str, body_html: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN"
  "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en">
<head>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <title>{escape_xml(title)}</title>
  <link rel="stylesheet" type="text/css" href="../Styles/style.css"/>
</head>
<body>
{body_html}
</body>
</html>
"""


# ── text extraction ───────────────────────────────────────────────────────────

def extract_text_digital(pdf_path: str) -> list[str]:
    """Extract text from a digital (non-scanned) PDF. Returns list of page texts."""
    import pdfplumber
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages.append(text)
    return pages


def extract_text_ocr(pdf_path: str) -> list[str]:
    """Extract text from a scanned PDF using Tesseract OCR."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        print(
            "ERROR: OCR mode requires pytesseract, pdf2image, and Pillow.\n"
            "Install them with:\n"
            "  pip install pytesseract pdf2image Pillow\n"
            "And install the Tesseract engine from: https://github.com/tesseract-ocr/tesseract",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Converting PDF pages to images for OCR …")
    images = convert_from_path(pdf_path, dpi=300)
    pages = []
    for i, img in enumerate(images, 1):
        print(f"  OCR page {i}/{len(images)} …")
        text = pytesseract.image_to_string(img)
        pages.append(text)
    return pages


def is_scanned_pdf(pdf_path: str, sample_pages: int = 3) -> bool:
    """Heuristic: if the first few pages yield almost no text, assume scanned."""
    import pdfplumber
    total_chars = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages[:sample_pages]:
            text = page.extract_text() or ""
            total_chars += len(text.strip())
    avg = total_chars / min(sample_pages, 1)
    return avg < 50  # fewer than 50 chars per page → likely scanned


# ── EPUB builder ─────────────────────────────────────────────────────────────

CSS = """\
body {
  font-family: Georgia, serif;
  font-size: 1em;
  line-height: 1.6;
  margin: 1em 2em;
  color: #222;
}
h1, h2 {
  font-family: Arial, Helvetica, sans-serif;
  color: #333;
}
p {
  margin: 0.5em 0;
  text-align: justify;
}
"""


def build_epub(
    pages: list[str],
    output_path: str,
    title: str,
    author: str,
    language: str = "en",
) -> None:
    book_id = str(uuid.uuid4())
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    num_pages = len(pages)

    # Build per-page chapter data
    chapters = []
    for i, text in enumerate(pages, 1):
        chapter_title = f"Page {i}"
        body = text_to_paragraphs(text) if text.strip() else "  <p>[No text detected on this page]</p>"
        xhtml = make_xhtml(chapter_title, f"  <h2>{escape_xml(chapter_title)}</h2>\n{body}")
        chapters.append((f"page{i:04d}.xhtml", chapter_title, xhtml))

    # OPF manifest items
    manifest_items = "\n".join(
        f'    <item id="page{i}" href="Text/{fname}" media-type="application/xhtml+xml"/>'
        for i, (fname, _, _) in enumerate(chapters, 1)
    )
    spine_items = "\n".join(
        f'    <itemref idref="page{i}"/>'
        for i in range(1, num_pages + 1)
    )
    nav_points = "\n".join(
        f"""    <navPoint id="navpoint-{i}" playOrder="{i}">
      <navLabel><text>{escape_xml(ctitle)}</text></navLabel>
      <content src="Text/{fname}"/>
    </navPoint>"""
        for i, (fname, ctitle, _) in enumerate(chapters, 1)
    )

    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" unique-identifier="bookid" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"
            xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>{escape_xml(title)}</dc:title>
    <dc:creator opf:role="aut">{escape_xml(author)}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:identifier id="bookid">urn:uuid:{book_id}</dc:identifier>
    <dc:date>{now}</dc:date>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="Styles/style.css" media-type="text/css"/>
{manifest_items}
  </manifest>
  <spine toc="ncx">
{spine_items}
  </spine>
</package>
"""

    toc_ncx = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
  "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head>
    <meta name="dtb:uid" content="urn:uuid:{book_id}"/>
    <meta name="dtb:depth" content="1"/>
    <meta name="dtb:totalPageCount" content="0"/>
    <meta name="dtb:maxPageNormalLength" content="0"/>
  </head>
  <docTitle><text>{escape_xml(title)}</text></docTitle>
  <navMap>
{nav_points}
  </navMap>
</ncx>
"""

    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as epub:
        # mimetype must be first and uncompressed
        epub.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        epub.writestr("META-INF/container.xml", container_xml)
        epub.writestr("OEBPS/content.opf", content_opf)
        epub.writestr("OEBPS/toc.ncx", toc_ncx)
        epub.writestr("OEBPS/Styles/style.css", CSS)
        for fname, _, xhtml in chapters:
            epub.writestr(f"OEBPS/Text/{fname}", xhtml)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF file to EPUB for mobile reading."
    )
    parser.add_argument("pdf", help="Path to the input PDF file")
    parser.add_argument("-o", "--output", help="Output .epub file path (default: same name as PDF)")
    parser.add_argument("--title", help="Book title (default: PDF filename)")
    parser.add_argument("--author", default="Unknown", help="Author name (default: Unknown)")
    parser.add_argument("--language", default="en", help="Language code, e.g. en, fr, de (default: en)")
    parser.add_argument(
        "--ocr",
        action="store_true",
        help="Force OCR mode (needed for scanned/image-only PDFs)",
    )
    args = parser.parse_args()

    pdf_path = args.pdf
    if not os.path.isfile(pdf_path):
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    stem = Path(pdf_path).stem
    output_path = args.output or f"{stem}.epub"
    title = args.title or stem.replace("_", " ").replace("-", " ").title()

    print(f"Input  : {pdf_path}")
    print(f"Output : {output_path}")
    print(f"Title  : {title}")
    print(f"Author : {args.author}")

    # Choose extraction strategy
    if args.ocr:
        print("Mode   : OCR (forced)")
        pages = extract_text_ocr(pdf_path)
    else:
        print("Mode   : Digital text extraction")
        pages = extract_text_digital(pdf_path)
        # Auto-fallback to OCR if almost no text was found
        total_text = sum(len(p.strip()) for p in pages)
        if total_text < 100:
            print(
                "WARNING: Very little text detected — the PDF may be scanned.\n"
                "Re-run with --ocr to use OCR, or install pytesseract for automatic OCR."
            )

    print(f"Pages  : {len(pages)}")
    print("Building EPUB …")
    build_epub(pages, output_path, title=title, author=args.author, language=args.language)
    size_kb = os.path.getsize(output_path) / 1024
    print(f"Done!  → {output_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
