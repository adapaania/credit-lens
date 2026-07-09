"""Chunk parsed 10-K pages by markdown section, never splitting a table."""

import re
from typing import Literal, TypedDict

from app.ingestion.parse import ParsedPage

_HASH_HEADER_RE = re.compile(r"^#{1,6}\s+(.*)$")
_BOLD_LINE_RE = re.compile(r"^\*\*(.+)\*\*$")
_HAS_LETTERS_RE = re.compile(r"[A-Za-z]{3,}")

MAX_CHUNK_CHARS = 1500

BlockKind = Literal["text", "table"]


class Chunk(TypedDict):
    section: str
    page: int
    text: str


def _is_table_line(line: str) -> bool:
    return line.strip().startswith("|")


def _header_title(line: str) -> str | None:
    """Return the section title if `line` is a standalone section header."""
    stripped = line.strip()
    if not stripped:
        return None

    match = _HASH_HEADER_RE.match(stripped)
    if match:
        title = match.group(1).strip()
        return title if _HAS_LETTERS_RE.search(title) else None

    match = _BOLD_LINE_RE.match(stripped)
    if match:
        title = match.group(1).strip()
        # Bold+italic combos (e.g. "**_headline_**") are risk-factor-style
        # emphasis in SEC filings, not structural section headers. Real
        # section titles in this corpus are bold-only.
        if title.startswith("_") and title.endswith("_"):
            return None
        if (
            len(title) <= 150
            and "<br>" not in title
            and "$" not in title
            and _HAS_LETTERS_RE.search(title)
        ):
            return title
    return None


def _build_blocks(pages: list[ParsedPage]) -> list[tuple[int, BlockKind, list[str]]]:
    """Group lines into blank-line-separated blocks, tagging table blocks."""
    blocks: list[tuple[int, BlockKind, list[str]]] = []
    current_kind: BlockKind | None = None
    current_lines: list[str] = []
    current_page: int | None = None

    def flush() -> None:
        if current_lines:
            blocks.append((current_page, current_kind, list(current_lines)))

    for page in pages:
        for raw_line in page["text"].split("\n"):
            if not raw_line.strip():
                flush()
                current_lines.clear()
                current_kind = None
                continue

            kind: BlockKind = "table" if _is_table_line(raw_line) else "text"
            if current_kind is None:
                current_kind = kind
                current_page = page["page"]
                current_lines = [raw_line]
            elif kind == current_kind:
                current_lines.append(raw_line)
            else:
                flush()
                current_kind = kind
                current_page = page["page"]
                current_lines = [raw_line]
    flush()
    return blocks


def chunk_pages(pages: list[ParsedPage], max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """Chunk pages by markdown section header, keeping table blocks atomic."""
    blocks = _build_blocks(pages)
    chunks: list[Chunk] = []
    section = "Preamble"
    buffer_lines: list[str] = []
    buffer_page: int | None = None
    buffer_len = 0

    def flush_chunk() -> None:
        nonlocal buffer_lines, buffer_page, buffer_len
        text = "\n\n".join(buffer_lines).strip()
        if text:
            chunks.append({"section": section, "page": buffer_page, "text": text})
        buffer_lines = []
        buffer_page = None
        buffer_len = 0

    for page_number, kind, lines in blocks:
        if kind == "text" and len(lines) == 1:
            title = _header_title(lines[0])
            if title:
                flush_chunk()
                section = title
                continue

        block_text = "\n".join(lines)
        if buffer_lines and kind == "text" and buffer_len + len(block_text) > max_chars:
            flush_chunk()

        buffer_lines.append(block_text)
        buffer_page = buffer_page if buffer_page is not None else page_number
        buffer_len += len(block_text)

    flush_chunk()
    return chunks
