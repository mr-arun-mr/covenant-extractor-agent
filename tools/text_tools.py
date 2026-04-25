"""
Plain-text covenant extraction tools.

Amendment markers in .txt files:
  ~~deleted text~~   → strikethrough span
  [RED: new text]    → red text span

50 lines = one logical "page" (mirrors the PDF tool's page abstraction).
"""

from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path

logger = logging.getLogger("tools.text")

LINES_PER_PAGE = 50

_HEADING_RE = re.compile(
    r"^(Section\s+\d+[\.\d]*|Article\s+[IVXLC\d]+|\d+\.\s+[A-Z]|[A-Z][A-Z\s]{5,})\b"
)
_STRIKE_RE = re.compile(r"~~(.+?)~~", re.DOTALL)
_RED_RE = re.compile(r"\[RED:\s*(.+?)\]", re.DOTALL)
_ANY_MARKER_RE = re.compile(r"(~~.+?~~|\[RED:\s*.+?\])", re.DOTALL)


def _parse_amendment_markers(raw_text: str) -> dict:
    """
    Strip ~~...~~ and [RED: ...] markers from raw_text and return:
      {"text": clean_text, "red_spans": [...], "strikethrough_spans": [...]}

    Span start/end index into the returned clean text — same contract as
    _chars_to_annotated_text in pdf_tools.py.
    """
    red_spans: list[dict] = []
    strike_spans: list[dict] = []
    clean_parts: list[str] = []
    pos = 0  # current position in raw_text
    clean_len = 0  # accumulated length of clean_parts so far

    for m in _ANY_MARKER_RE.finditer(raw_text):
        # Append literal text between last marker and this one
        literal = raw_text[pos:m.start()]
        clean_parts.append(literal)
        clean_len += len(literal)

        token = m.group(0)
        if token.startswith("~~"):
            inner = _STRIKE_RE.match(token).group(1)
            span_start = clean_len
            clean_parts.append(inner)
            clean_len += len(inner)
            strike_spans.append({"text": inner, "start": span_start, "end": clean_len})
        else:  # [RED: ...]
            inner = _RED_RE.match(token).group(1)
            span_start = clean_len
            clean_parts.append(inner)
            clean_len += len(inner)
            red_spans.append({"text": inner, "start": span_start, "end": clean_len})

        pos = m.end()

    # Remaining literal text after the last marker
    tail = raw_text[pos:]
    clean_parts.append(tail)

    return {
        "text": "".join(clean_parts),
        "red_spans": red_spans,
        "strikethrough_spans": strike_spans,
    }


def _strip_markers(text: str) -> str:
    """Return text with all amendment markers removed (inner content preserved)."""
    text = _STRIKE_RE.sub(r"\1", text)
    text = _RED_RE.sub(r"\1", text)
    return text


def _page_lines(all_lines: list[str], page_num: int) -> list[str]:
    """Return the 0-indexed slice of lines for a 1-indexed page number."""
    start = (page_num - 1) * LINES_PER_PAGE
    end = start + LINES_PER_PAGE
    return all_lines[start:end]


# ---------------------------------------------------------------------------
# Public tool functions
# ---------------------------------------------------------------------------

def get_text_structure(file_path: str) -> str:
    """
    Return a JSON summary of the document structure: page count and section headings.
    Mirrors get_pdf_structure output shape.
    """
    path = Path(file_path)
    logger.debug("get_text_structure: %s", path.name)
    if not path.exists():
        logger.warning("get_text_structure: file not found: %s", file_path)
        return json.dumps({"error": f"File not found: {file_path}"})

    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    page_count = max(1, math.ceil(len(raw_lines) / LINES_PER_PAGE))

    headings: list[dict] = []
    scan_limit = min(60 * LINES_PER_PAGE, len(raw_lines))
    for i, line in enumerate(raw_lines[:scan_limit]):
        clean = _strip_markers(line).strip()
        if _HEADING_RE.match(clean) and len(clean) < 120:
            page_num = i // LINES_PER_PAGE + 1
            headings.append({"page": page_num, "heading": clean})

    logger.info(
        "Document structure: %d page(s), %d heading(s) found in %s",
        page_count, len(headings), path.name,
    )
    return json.dumps({
        "document": path.name,
        "page_count": page_count,
        "bookmarks": [],
        "headings": headings,
    }, indent=2)


def extract_text_sections(
    file_path: str,
    page_numbers: list[int],
    detect_amendments: bool = True,
) -> str:
    """
    Extract text from the requested logical pages (1-indexed, 50 lines each).
    Returns the same JSON shape as extract_pdf_pages.
    """
    path = Path(file_path)
    if not path.exists():
        return json.dumps({"error": f"File not found: {file_path}"})

    logger.debug(
        "extract_text_sections: %s, pages=%s, detect_amendments=%s",
        path.name, page_numbers, detect_amendments,
    )

    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = max(1, math.ceil(len(raw_lines) / LINES_PER_PAGE))
    results: list[dict] = []

    for pg in sorted(set(page_numbers)):
        if pg < 1 or pg > total:
            logger.warning("Page %d out of range (1–%d), skipping", pg, total)
            results.append({"page": pg, "error": f"Page {pg} out of range (1–{total})"})
            continue

        lines = _page_lines(raw_lines, pg)
        raw_text = "\n".join(lines)

        if detect_amendments:
            annotated = _parse_amendment_markers(raw_text)
            red_count = len(annotated["red_spans"])
            strike_count = len(annotated["strikethrough_spans"])
            logger.debug(
                "Page %d: %d red span(s), %d strikethrough span(s)",
                pg, red_count, strike_count,
            )
            results.append({
                "page": pg,
                "text": annotated["text"],
                "red_spans": annotated["red_spans"],
                "strikethrough_spans": annotated["strikethrough_spans"],
            })
        else:
            results.append({
                "page": pg,
                "text": _strip_markers(raw_text),
                "red_spans": [],
                "strikethrough_spans": [],
            })

    logger.info("extract_text_sections: processed %d page(s) from %s", len(results), path.name)
    return json.dumps({"pages": results}, indent=2)


def lookup_source_clause_text(
    file_path: str,
    search_text: str,
    page_hint: int | None = None,
) -> str:
    """
    Search the plain-text file for a text fragment and return context snippets.
    Markers are stripped before searching. Same output shape as lookup_source_clause.
    """
    path = Path(file_path)
    if not path.exists():
        return json.dumps({"error": f"File not found: {file_path}"})

    logger.debug("lookup_source_clause_text: query=%r, page_hint=%s", search_text, page_hint)

    query = search_text.strip().lower()
    if len(query) < 6:
        logger.warning("lookup_source_clause_text: query too short (%d chars)", len(query))
        return json.dumps({"error": "search_text must be at least 6 characters"})

    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    total = max(1, math.ceil(len(raw_lines) / LINES_PER_PAGE))

    if page_hint and 1 <= page_hint <= total:
        order = [page_hint] + [p for p in range(1, total + 1) if p != page_hint]
    else:
        order = list(range(1, total + 1))

    matches: list[dict] = []

    for pg in order:
        lines = _page_lines(raw_lines, pg)
        clean_text = _strip_markers("\n".join(lines))
        lower_text = clean_text.lower()
        idx = lower_text.find(query)
        while idx != -1:
            ctx_start = max(0, idx - 100)
            ctx_end = min(len(clean_text), idx + len(query) + 100)
            matches.append({
                "page": pg,
                "match_start": idx,
                "context": clean_text[ctx_start:ctx_end].strip(),
            })
            idx = lower_text.find(query, idx + 1)

        if len(matches) >= 10:
            break

    logger.info("lookup_source_clause_text: %d match(es) for %r", len(matches), search_text)
    return json.dumps({"query": search_text, "matches": matches}, indent=2)


# ---------------------------------------------------------------------------
# Tool definitions (same names as PDF tools — agent sees identical interface)
# ---------------------------------------------------------------------------

TEXT_TOOL_DEFINITIONS = [
    {
        "name": "get_pdf_structure",
        "description": (
            "Returns the document structure: page count, section headings, and a lightweight "
            "table of contents. Call this first to understand which pages contain covenants. "
            "(For plain-text files, one logical page = 50 lines.)"
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "extract_pdf_pages",
        "description": (
            "Extract text from specific logical pages (1-indexed, 50 lines each). "
            "Returns plain text plus red_spans and strikethrough_spans from amendment markers. "
            "In plain-text files, ~~deleted~~ marks strikethrough and [RED: new] marks red text. "
            "Use detect_amendments=true (the default) to get amendment markers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of 1-indexed logical page numbers to extract (max 10 at a time).",
                },
                "detect_amendments": {
                    "type": "boolean",
                    "description": "Whether to detect ~~strikethrough~~ and [RED: ...] markers. Default true.",
                    "default": True,
                },
            },
            "required": ["page_numbers"],
        },
    },
    {
        "name": "lookup_source_clause",
        "description": (
            "Search the document for a text fragment and return context snippets with page numbers. "
            "Use this during validation to verify that a covenant's obligation_text and threshold "
            "values actually appear in the source document."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "The text fragment to search for (minimum 6 characters).",
                },
                "page_hint": {
                    "type": "integer",
                    "description": "Optional logical page number to search first.",
                },
            },
            "required": ["search_text"],
        },
    },
]
