"""
PDF inspection tools for the covenant extractor agent.

pdfplumber gives character-level access including color data and annotation objects,
which lets us detect red text and strikethrough markings that indicate amendments.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pdfplumber

# Threshold for classifying a character's color as "red".
# pdfplumber returns RGB components in [0, 1] range.
_RED_R_MIN = 0.6
_RED_G_MAX = 0.35
_RED_B_MAX = 0.35


def _is_red(color: Any) -> bool:
    """Return True if the given pdfplumber color value is predominantly red."""
    if not color or not isinstance(color, (list, tuple)) or len(color) < 3:
        return False
    r, g, b = float(color[0]), float(color[1]), float(color[2])
    return r >= _RED_R_MIN and g <= _RED_G_MAX and b <= _RED_B_MAX


def _classify_char_annotations(
    chars: list[dict],
    annots: list[dict],
    lines: list[dict] | None = None,
) -> list[dict]:
    """
    Tag each character dict with amendment markers:
    - is_red: True if the character's non-stroking color is red
    - is_strikethrough: True if a line annotation or drawn line overlaps the char bbox

    `lines` is pdfplumber's page.lines list; thin horizontal drawn lines are
    treated as strikethrough (coordinates are top-based, matching char.top/bottom).
    """
    # Build list of strikethrough bboxes in pdfplumber top-based coordinates.
    # Each entry is (x0, top, x1, bottom).
    strike_rects: list[tuple[float, float, float, float]] = []

    # --- PDF annotation objects (StrikeOut / thin Line annotations) ----------
    for annot in (annots or []):
        subtype = annot.get("data", {}).get("Subtype", "")
        if subtype in ("/StrikeOut", "StrikeOut"):
            rect = annot.get("data", {}).get("Rect")
            if rect and len(rect) == 4:
                strike_rects.append(tuple(rect))
        elif subtype in ("/Line", "Line"):
            rect = annot.get("data", {}).get("Rect")
            if rect and len(rect) == 4:
                x0, y0, x1, y1 = rect
                if abs(y1 - y0) < 3:
                    strike_rects.append(tuple(rect))

    # --- Content-stream drawn lines (top-based coords from pdfplumber) -------
    # pdfplumber normalises page.lines to top/bottom (distance from page top),
    # consistent with char.top / char.bottom.  A thin horizontal line whose
    # vertical midpoint falls inside a character's bounding box is treated as
    # strikethrough.  We skip very short lines to avoid detecting punctuation
    # or tick marks.
    for ln in (lines or []):
        lx0 = ln.get("x0", 0)
        lx1 = ln.get("x1", 0)
        ltop = ln.get("top", 0)
        lbottom = ln.get("bottom", 0)
        width = abs(lx1 - lx0)
        height = abs(lbottom - ltop)
        if height < 3 and width > 10:
            strike_rects.append((lx0, ltop, lx1, lbottom))

    tagged = []
    for char in chars:
        cx0 = char.get("x0", 0)
        cx1 = char.get("x1", 0)
        cy0 = char.get("top", 0)
        cy1 = char.get("bottom", 0)

        color = char.get("non_stroking_color")
        is_red = _is_red(color)

        is_strike = False
        for sx0, sy0, sx1, sy1 in strike_rects:
            # Check horizontal overlap and that the strike line crosses the char vertically
            h_overlap = cx0 < sx1 and cx1 > sx0
            v_overlap = cy0 < max(sy0, sy1) and cy1 > min(sy0, sy1)
            if h_overlap and v_overlap:
                is_strike = True
                break

        tagged.append({**char, "is_red": is_red, "is_strikethrough": is_strike})

    return tagged


def _chars_to_annotated_text(tagged_chars: list[dict]) -> dict:
    """
    Collapse tagged characters into plain text plus amendment spans.

    Returns:
        {
            "text": <full page text>,
            "red_spans": [{"text": str, "start": int, "end": int}, ...],
            "strikethrough_spans": [{"text": str, "start": int, "end": int}, ...],
        }
    """
    chars_text = ""
    red_spans: list[dict] = []
    strike_spans: list[dict] = []

    in_red = False
    in_strike = False
    red_start = 0
    strike_start = 0

    for ch in tagged_chars:
        c = ch.get("text", "")
        pos = len(chars_text)

        if ch["is_red"] and not in_red:
            in_red = True
            red_start = pos
        elif not ch["is_red"] and in_red:
            red_spans.append({"text": chars_text[red_start:pos], "start": red_start, "end": pos})
            in_red = False

        if ch["is_strikethrough"] and not in_strike:
            in_strike = True
            strike_start = pos
        elif not ch["is_strikethrough"] and in_strike:
            strike_spans.append({"text": chars_text[strike_start:pos], "start": strike_start, "end": pos})
            in_strike = False

        chars_text += c

    # Close any open spans at end of page
    if in_red:
        red_spans.append({"text": chars_text[red_start:], "start": red_start, "end": len(chars_text)})
    if in_strike:
        strike_spans.append({"text": chars_text[strike_start:], "start": strike_start, "end": len(chars_text)})

    return {"text": chars_text, "red_spans": red_spans, "strikethrough_spans": strike_spans}


# ---------------------------------------------------------------------------
# Public tool functions (called by the agent dispatcher)
# ---------------------------------------------------------------------------

def get_pdf_structure(pdf_path: str) -> str:
    """
    Return a JSON summary of the document structure: page count, bookmarks/TOC,
    and a list of lines that look like section headings (ALL CAPS or numbered).
    """
    path = Path(pdf_path)
    if not path.exists():
        return json.dumps({"error": f"File not found: pdf_path"})

    with pdfplumber.open(str(path)) as pdf:
        page_count = len(pdf.pages)

        # Extract bookmarks from the PDF metadata if available
        bookmarks: list[dict] = []
        try:
            raw_bm = pdf.doc.pdf.trailer.get("/Root", {}).get("/Outlines")
            # pdfplumber doesn't expose a clean bookmark API; skip silently
        except Exception:
            pass

        # Scan first 60 pages for section headings to build a lightweight TOC
        headings: list[dict] = []
        heading_re = re.compile(
            r"^(Section\s+\d+[\.\d]*|Article\s+[IVXLC\d]+|\d+\.\s+[A-Z]|[A-Z][A-Z\s]{5,})\b"
        )
        scan_limit = min(60, page_count)
        for page_num in range(scan_limit):
            page = pdf.pages[page_num]
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if heading_re.match(line) and len(line) < 120:
                    headings.append({"page": page_num + 1, "heading": line})

    return json.dumps({
        "document": path.name,
        "page_count": page_count,
        "bookmarks": bookmarks,
        "headings": headings,
    }, indent=2)


def extract_pdf_pages(pdf_path: str, page_numbers: list[int], detect_amendments: bool = True) -> str:
    """
    Extract text from the requested pages (1-indexed) with optional amendment detection.

    Returns JSON with per-page content including plain text, red_spans, and
    strikethrough_spans so the agent can identify amended clauses.
    """
    path = Path(pdf_path)
    if not path.exists():
        return json.dumps({"error": f"File not found: pdf_path"})

    results: list[dict] = []

    with pdfplumber.open(str(path)) as pdf:
        total = len(pdf.pages)
        for pg in sorted(set(page_numbers)):
            if pg < 1 or pg > total:
                results.append({"page": pg, "error": f"Page {pg} out of range (1–{total})"})
                continue

            page = pdf.pages[pg - 1]

            if detect_amendments:
                chars = page.chars or []
                annots = page.annots or []
                tagged = _classify_char_annotations(chars, annots, page.lines or [])
                annotated = _chars_to_annotated_text(tagged)
                results.append({
                    "page": pg,
                    "text": annotated["text"],
                    "red_spans": annotated["red_spans"],
                    "strikethrough_spans": annotated["strikethrough_spans"],
                })
            else:
                results.append({
                    "page": pg,
                    "text": page.extract_text() or "",
                    "red_spans": [],
                    "strikethrough_spans": [],
                })

    return json.dumps({"pages": results}, indent=2)


def lookup_source_clause(pdf_path: str, search_text: str, page_hint: int | None = None) -> str:
    """
    Search the PDF for a text fragment and return matching context snippets.

    Searches up to 20 characters of context around each match. If page_hint is
    provided, that page is searched first and its results ranked higher.
    """
    path = Path(pdf_path)
    if not path.exists():
        return json.dumps({"error": f"File not found: pdf_path"})

    query = search_text.strip().lower()
    if len(query) < 6:
        return json.dumps({"error": "search_text must be at least 6 characters"})

    matches: list[dict] = []

    with pdfplumber.open(str(path)) as pdf:
        total = len(pdf.pages)
        # Build page order: page_hint first, then the rest in order
        if page_hint and 1 <= page_hint <= total:
            order = [page_hint] + [p for p in range(1, total + 1) if p != page_hint]
        else:
            order = list(range(1, total + 1))

        for pg in order:
            page = pdf.pages[pg - 1]
            text = page.extract_text() or ""
            lower_text = text.lower()
            idx = lower_text.find(query)
            while idx != -1:
                ctx_start = max(0, idx - 100)
                ctx_end = min(len(text), idx + len(query) + 100)
                matches.append({
                    "page": pg,
                    "match_start": idx,
                    "context": text[ctx_start:ctx_end].strip(),
                })
                idx = lower_text.find(query, idx + 1)

            if len(matches) >= 10:
                break

    return json.dumps({"query": search_text, "matches": matches}, indent=2)


# ---------------------------------------------------------------------------
# Tool definitions for the Anthropic SDK
# ---------------------------------------------------------------------------

PDF_TOOL_DEFINITIONS = [
    {
        "name": "get_pdf_structure",
        "description": (
            "Returns the document structure: page count, section headings, and a lightweight "
            "table of contents. Call this first to understand which pages contain covenants."
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
            "Extract text from specific pages (1-indexed). Returns plain text plus "
            "red_spans and strikethrough_spans indicating amended or deleted text. "
            "Use detect_amendments=true (the default) to get amendment markers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "page_numbers": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of 1-indexed page numbers to extract (max 10 at a time).",
                },
                "detect_amendments": {
                    "type": "boolean",
                    "description": "Whether to detect red text and strikethrough. Default true.",
                    "default": True,
                },
            },
            "required": ["page_numbers"],
        },
    },
    {
        "name": "lookup_source_clause",
        "description": (
            "Search the PDF for a text fragment and return context snippets with page numbers. "
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
                    "description": "Optional page number to search first.",
                },
            },
            "required": ["search_text"],
        },
    },
]
