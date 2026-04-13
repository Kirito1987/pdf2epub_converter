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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


# ── helpers ───────────────────────────────────────────────────────────────────

def escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )


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


# ── text cleaning ─────────────────────────────────────────────────────────────

def find_repeating_lines(pages: list[str], threshold: float = 0.6) -> set[str]:
    """
    Identify lines that appear on a large fraction of pages — these are
    almost certainly running headers or footers baked in by the PDF.
    threshold: fraction of pages a line must appear on to be flagged.
    """
    line_counts: Counter = Counter()
    total_pages = len(pages)

    for page_text in pages:
        # Use a set per page so the same line only counts once per page
        seen_on_this_page = set()
        for line in page_text.splitlines():
            stripped = line.strip()
            if stripped and stripped not in seen_on_this_page:
                line_counts[stripped] += 1
                seen_on_this_page.add(stripped)

    min_count = max(2, int(total_pages * threshold))
    return {line for line, count in line_counts.items() if count >= min_count}


def strip_page_artifacts(text: str, repeating_lines: set[str]) -> str:
    """
    Remove from a page's text:
      1. Repeating header/footer lines detected across pages
      2. Page-number patterns like "3 of 239", "Page 3", "- 3 -"
    """
    cleaned_lines = []
    for line in text.splitlines():
        stripped = line.strip()

        # Drop repeating headers/footers
        if stripped in repeating_lines:
            continue

        # Drop bare page-number patterns
        if re.fullmatch(
            r"(\d+\s+of\s+\d+|page\s+\d+(\s+of\s+\d+)?|-\s*\d+\s*-|\d+)",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def is_heading(line: str) -> bool:
    """
    Heuristic: a line is a chapter heading if it is:
      • Short (≤ 60 chars)
      • Mostly uppercase letters (≥ 80 % of alpha chars are uppercase)
      • Not purely numeric
      • Has at least 2 characters
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 2 or len(stripped) > 60:
        return False
    if stripped.isdigit():
        return False
    alpha = [c for c in stripped if c.isalpha()]
    if not alpha:
        return False
    upper_ratio = sum(1 for c in alpha if c.isupper()) / len(alpha)
    return upper_ratio >= 0.80


def parse_lines_to_html(text: str) -> str:
    """
    Convert a block of plain text into XHTML, detecting headings and
    grouping remaining lines into <p> paragraphs.
    Returns a string of XHTML elements (no outer wrapper).
    """
    parts = []
    # Split into logical paragraphs first (blank-line separated)
    raw_paragraphs = re.split(r"\n{2,}", text.strip())

    for para in raw_paragraphs:
        lines = [l.strip() for l in para.splitlines() if l.strip()]
        if not lines:
            continue

        # If the paragraph is a single short ALL-CAPS line → heading
        if len(lines) == 1 and is_heading(lines[0]):
            parts.append(f'  <h2>{escape_xml(lines[0].title())}</h2>')
        else:
            # Check whether the first line of a multi-line paragraph is a heading
            if is_heading(lines[0]):
                parts.append(f'  <h2>{escape_xml(lines[0].title())}</h2>')
                lines = lines[1:]
            if lines:
                body = " ".join(lines)
                parts.append(f"  <p>{escape_xml(body)}</p>")

    return "\n".join(parts) if parts else "  <p>[No text detected on this page]</p>"


# ── chapter grouping ──────────────────────────────────────────────────────────

def group_into_chapters(pages: list[str]) -> list[tuple[str, str]]:
    """
    Merge raw page texts into semantic chapters.

    Strategy:
      • Scan every page for heading lines.
      • When a heading is found, start a new chapter.
      • Pages with no heading continue the current chapter.
      • Returns list of (chapter_title, combined_text).
    """
    # Regex to find a heading line anywhere in a page
    # Use [^\S\n] (whitespace except newline) to avoid spanning multiple lines
    HEADING_RE = re.compile(r"^[A-Z][A-Z\t .\-\'\,\:]{1,58}[A-Z.]$", re.MULTILINE)

    chapters: list[tuple[str, list[str]]] = []  # (title, [page_texts])
    current_title = "Introduction"
    current_pages: list[str] = []

    for page_text in pages:
        # Look for the first heading on this page
        match = HEADING_RE.search(page_text)
        if match:
            heading_candidate = match.group(0).strip()
            # Save the content before the heading to the current chapter
            before = page_text[: match.start()].strip()
            after  = page_text[match.end():].strip()

            if before:
                current_pages.append(before)

            # Flush current chapter if it has content
            if current_pages:
                chapters.append((current_title, current_pages))

            # Start a new chapter
            current_title = heading_candidate.title()
            current_pages = [after] if after else []
        else:
            current_pages.append(page_text)

    # Flush the last chapter
    if current_pages:
        chapters.append((current_title, current_pages))

    # If no chapters were detected at all, fall back to one chapter per page
    if not chapters:
        return [(f"Page {i+1}", text) for i, text in enumerate(pages)]

    # Convert list[str] page accumulations into a single string per chapter
    return [(title, "\n\n".join(p for p in page_list if p.strip()))
            for title, page_list in chapters]


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


# ── EPUB builder ──────────────────────────────────────────────────────────────

CSS = """\
body {
  font-family: Georgia, serif;
  font-size: 1em;
  line-height: 1.7;
  margin: 1.5em 2em;
  color: #1a1a1a;
}
h1 {
  font-family: Arial, Helvetica, sans-serif;
  font-size: 1.6em;
  font-weight: bold;
  color: #111;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  border-bottom: 1px solid #ccc;
  padding-bottom: 0.3em;
}
h2 {
  font-family: Arial, Helvetica, sans-serif;
  font-size: 1.2em;
  font-weight: bold;
  color: #222;
  margin-top: 1.4em;
  margin-bottom: 0.4em;
}
p {
  margin: 0.6em 0;
  text-align: justify;
  text-indent: 1.2em;
}
p:first-of-type {
  text-indent: 0;
}
"""


def build_epub(
    chapters: list[tuple[str, str]],
    output_path: str,
    title: str,
    author: str,
    language: str = "en",
) -> None:
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Build XHTML files for each chapter
    chapter_files = []
    for i, (ch_title, ch_text) in enumerate(chapters, 1):
        body_html = parse_lines_to_html(ch_text)
        xhtml = make_xhtml(
            ch_title,
            f'  <h1>{escape_xml(ch_title)}</h1>\n{body_html}'
        )
        chapter_files.append((f"chapter{i:04d}.xhtml", ch_title, xhtml))

    num_chapters = len(chapter_files)

    manifest_items = "\n".join(
        f'    <item id="ch{i}" href="Text/{fname}" media-type="application/xhtml+xml"/>'
        for i, (fname, _, _) in enumerate(chapter_files, 1)
    )
    spine_items = "\n".join(
        f'    <itemref idref="ch{i}"/>'
        for i in range(1, num_chapters + 1)
    )
    nav_points = "\n".join(
        f"""    <navPoint id="navpoint-{i}" playOrder="{i}">
      <navLabel><text>{escape_xml(ctitle)}</text></navLabel>
      <content src="Text/{fname}"/>
    </navPoint>"""
        for i, (fname, ctitle, _) in enumerate(chapter_files, 1)
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
        epub.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        epub.writestr("META-INF/container.xml", container_xml)
        epub.writestr("OEBPS/content.opf", content_opf)
        epub.writestr("OEBPS/toc.ncx", toc_ncx)
        epub.writestr("OEBPS/Styles/style.css", CSS)
        for fname, _, xhtml in chapter_files:
            epub.writestr(f"OEBPS/Text/{fname}", xhtml)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Convert a PDF file to EPUB for mobile reading."
    )
    parser.add_argument("pdf", help="Path to the input PDF file")
    parser.add_argument("-o", "--output", help="Output .epub file path (default: same name as PDF)")
    parser.add_argument("--title",  help="Book title (default: PDF filename)")
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

    # ── Step 1: Extract raw page texts ────────────────────────────────────────
    if args.ocr:
        print("Mode   : OCR (forced)")
        pages = extract_text_ocr(pdf_path)
    else:
        print("Mode   : Digital text extraction")
        pages = extract_text_digital(pdf_path)
        total_text = sum(len(p.strip()) for p in pages)
        if total_text < 100:
            print(
                "WARNING: Very little text detected — the PDF may be scanned.\n"
                "Re-run with --ocr to use OCR, or install pytesseract for automatic OCR."
            )

    print(f"Pages  : {len(pages)}")

    # ── Step 2: Detect and strip repeating headers/footers ────────────────────
    print("Cleaning headers, footers, and page numbers …")
    repeating = find_repeating_lines(pages)
    if repeating:
        print(f"  Removed {len(repeating)} repeating line(s): "
              + ", ".join(f'"{r}"' for r in list(repeating)[:5])
              + (" …" if len(repeating) > 5 else ""))
    pages = [strip_page_artifacts(p, repeating) for p in pages]

    # ── Step 3: Group pages into semantic chapters ────────────────────────────
    print("Grouping pages into chapters …")
    chapters = group_into_chapters(pages)
    print(f"Chapters: {len(chapters)}")
    for ch_title, _ in chapters[:10]:
        print(f"  • {ch_title}")
    if len(chapters) > 10:
        print(f"  … and {len(chapters) - 10} more")

    # ── Step 4: Build EPUB ────────────────────────────────────────────────────
    print("Building EPUB …")
    build_epub(chapters, output_path, title=title, author=args.author, language=args.language)
    size_kb = os.path.getsize(output_path) / 1024
    print(f"Done!  → {output_path}  ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()