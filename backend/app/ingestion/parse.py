"""Parse 10-K PDFs into per-page markdown text, preserving page numbers."""

import re
from pathlib import Path
from typing import TypedDict

import pymupdf4llm

_PAGE_BREAK_RE = re.compile(r"^-{3,}$")
_LONE_PAGE_NUMBER_RE = re.compile(r"^\d{1,4}$")


class ParsedPage(TypedDict):
    page: int
    text: str


def _clean_page_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if _PAGE_BREAK_RE.match(stripped) or _LONE_PAGE_NUMBER_RE.match(stripped):
            cleaned.append("")
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


def parse_filing_pdf(pdf_path: str | Path) -> list[ParsedPage]:
    """Extract markdown text per page from a 10-K PDF using pymupdf4llm.

    Page numbers are 1-indexed and reflect position in the PDF, which is
    itself a direct print of the official SEC EDGAR filing.
    """
    pages = pymupdf4llm.to_markdown(str(pdf_path), page_chunks=True, show_progress=False)
    parsed: list[ParsedPage] = []
    for page in pages:
        page_number = page["metadata"]["page"]
        text = _clean_page_text(page["text"])
        if text:
            parsed.append({"page": page_number, "text": text})
    return parsed
