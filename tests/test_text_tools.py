"""Tests for tools/text_tools.py — plain-text covenant extraction tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.text_tools import (
    LINES_PER_PAGE,
    TEXT_TOOL_DEFINITIONS,
    _parse_amendment_markers,
    _strip_markers,
    extract_text_sections,
    get_text_structure,
    lookup_source_clause_text,
)


# ---------------------------------------------------------------------------
# _parse_amendment_markers (private, but tested directly)
# ---------------------------------------------------------------------------

class TestParseAmendmentMarkers:
    def test_no_markers_returns_clean(self):
        result = _parse_amendment_markers("plain text here")
        assert result["text"] == "plain text here"
        assert result["red_spans"] == []
        assert result["strikethrough_spans"] == []

    def test_strike_marker_extracted(self):
        result = _parse_amendment_markers("before ~~deleted~~ after")
        assert result["text"] == "before deleted after"
        assert len(result["strikethrough_spans"]) == 1
        span = result["strikethrough_spans"][0]
        assert span["text"] == "deleted"
        assert result["text"][span["start"]:span["end"]] == "deleted"

    def test_red_marker_extracted(self):
        result = _parse_amendment_markers("before [RED: added] after")
        assert result["text"] == "before added after"
        assert len(result["red_spans"]) == 1
        span = result["red_spans"][0]
        assert span["text"] == "added"
        assert result["text"][span["start"]:span["end"]] == "added"

    def test_both_markers_on_same_line(self):
        result = _parse_amendment_markers("ratio ~~4.00x~~ [RED: 4.50x] quarterly")
        assert "4.00x" in result["text"]
        assert "4.50x" in result["text"]
        assert len(result["strikethrough_spans"]) == 1
        assert len(result["red_spans"]) == 1

    def test_span_indices_correct(self):
        """start/end must index into the returned clean text."""
        raw = "The ~~old value~~ [RED: new value] applies."
        result = _parse_amendment_markers(raw)
        for span in result["strikethrough_spans"] + result["red_spans"]:
            assert result["text"][span["start"]:span["end"]] == span["text"]

    def test_multiple_markers(self):
        raw = "~~a~~ then [RED: b] and ~~c~~"
        result = _parse_amendment_markers(raw)
        assert len(result["strikethrough_spans"]) == 2
        assert len(result["red_spans"]) == 1
        for span in result["strikethrough_spans"] + result["red_spans"]:
            assert result["text"][span["start"]:span["end"]] == span["text"]

    def test_red_with_spaces_after_colon(self):
        result = _parse_amendment_markers("[RED:  extra space  ]")
        assert len(result["red_spans"]) == 1
        assert result["red_spans"][0]["text"] == "extra space  "

    def test_multiline_strike_marker(self):
        raw = "~~line one\nline two~~"
        result = _parse_amendment_markers(raw)
        assert len(result["strikethrough_spans"]) == 1
        assert "line one" in result["strikethrough_spans"][0]["text"]


class TestStripMarkers:
    def test_strips_strike(self):
        assert _strip_markers("~~old~~") == "old"

    def test_strips_red(self):
        assert _strip_markers("[RED: new]") == "new"

    def test_plain_text_unchanged(self):
        assert _strip_markers("no markers") == "no markers"


# ---------------------------------------------------------------------------
# get_text_structure
# ---------------------------------------------------------------------------

class TestGetTextStructure:
    def test_valid_file_returns_json(self, sample_txt_path):
        raw = get_text_structure(str(sample_txt_path))
        data = json.loads(raw)
        assert "document" in data
        assert "page_count" in data
        assert isinstance(data["page_count"], int)
        assert data["page_count"] >= 1
        assert "bookmarks" in data
        assert "headings" in data

    def test_headings_is_list_with_correct_keys(self, sample_txt_path):
        data = json.loads(get_text_structure(str(sample_txt_path)))
        assert isinstance(data["headings"], list)
        for h in data["headings"]:
            assert "page" in h
            assert "heading" in h

    def test_detects_section_headings(self, sample_txt_path):
        data = json.loads(get_text_structure(str(sample_txt_path)))
        headings_text = [h["heading"] for h in data["headings"]]
        assert any("Section 7.1" in h or "Section 7.2" in h for h in headings_text)

    def test_missing_file_returns_error(self, tmp_path):
        raw = get_text_structure(str(tmp_path / "nonexistent.txt"))
        data = json.loads(raw)
        assert "error" in data

    def test_page_count_correct_for_padded_fixture(self, sample_txt_path):
        data = json.loads(get_text_structure(str(sample_txt_path)))
        # _SAMPLE_TXT_CONTENT has ~51 lines → 2 pages
        assert data["page_count"] == 2

    def test_bookmarks_is_empty_list(self, sample_txt_path):
        data = json.loads(get_text_structure(str(sample_txt_path)))
        assert data["bookmarks"] == []


# ---------------------------------------------------------------------------
# extract_text_sections
# ---------------------------------------------------------------------------

class TestExtractTextSections:
    def test_valid_page_returns_text(self, sample_txt_path):
        raw = extract_text_sections(str(sample_txt_path), [1])
        data = json.loads(raw)
        assert "pages" in data
        assert len(data["pages"]) == 1
        page = data["pages"][0]
        assert page["page"] == 1
        assert isinstance(page["text"], str)
        assert len(page["text"]) > 0

    def test_result_has_expected_keys(self, sample_txt_path):
        data = json.loads(extract_text_sections(str(sample_txt_path), [1]))
        page = data["pages"][0]
        assert set(page.keys()) >= {"page", "text", "red_spans", "strikethrough_spans"}

    def test_clean_file_has_empty_spans(self, sample_txt_path):
        data = json.loads(extract_text_sections(str(sample_txt_path), [1]))
        page = data["pages"][0]
        assert page["red_spans"] == []
        assert page["strikethrough_spans"] == []

    def test_out_of_range_page_returns_error(self, sample_txt_path):
        data = json.loads(extract_text_sections(str(sample_txt_path), [999]))
        page = data["pages"][0]
        assert "error" in page
        assert page["page"] == 999

    def test_detect_amendments_false_strips_markers(self, amended_txt_path):
        data = json.loads(extract_text_sections(str(amended_txt_path), [1], detect_amendments=False))
        page = data["pages"][0]
        assert "~~" not in page["text"]
        assert "[RED:" not in page["text"]
        assert page["red_spans"] == []
        assert page["strikethrough_spans"] == []

    def test_missing_file_returns_error(self, tmp_path):
        raw = extract_text_sections(str(tmp_path / "missing.txt"), [1])
        data = json.loads(raw)
        assert "error" in data

    def test_multiple_pages(self, sample_txt_path):
        data = json.loads(extract_text_sections(str(sample_txt_path), [1, 2]))
        assert len(data["pages"]) == 2
        page_nums = {p["page"] for p in data["pages"]}
        assert page_nums == {1, 2}


# ---------------------------------------------------------------------------
# lookup_source_clause_text
# ---------------------------------------------------------------------------

class TestLookupSourceClauseText:
    def test_finds_known_text(self, sample_txt_path):
        raw = lookup_source_clause_text(str(sample_txt_path), "Leverage Ratio")
        data = json.loads(raw)
        assert data["query"] == "Leverage Ratio"
        assert len(data["matches"]) >= 1

    def test_match_has_expected_keys(self, sample_txt_path):
        data = json.loads(lookup_source_clause_text(str(sample_txt_path), "Leverage Ratio"))
        m = data["matches"][0]
        assert "page" in m
        assert "match_start" in m
        assert "context" in m

    def test_no_match_returns_empty(self, sample_txt_path):
        data = json.loads(lookup_source_clause_text(str(sample_txt_path), "XYZZY_NOT_FOUND"))
        assert data["matches"] == []

    def test_short_query_returns_error(self, sample_txt_path):
        data = json.loads(lookup_source_clause_text(str(sample_txt_path), "hi"))
        assert "error" in data

    def test_missing_file_returns_error(self, tmp_path):
        data = json.loads(lookup_source_clause_text(str(tmp_path / "no.txt"), "Leverage Ratio"))
        assert "error" in data

    def test_page_hint_prioritises_page(self, sample_txt_path):
        data = json.loads(lookup_source_clause_text(str(sample_txt_path), "Leverage Ratio", page_hint=1))
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["page"] == 1

    def test_finds_text_after_marker_strip(self, amended_txt_path):
        # "4.50x" is inside [RED: 4.50x]; search against cleaned text using a longer phrase
        data = json.loads(lookup_source_clause_text(str(amended_txt_path), "not exceed"))
        assert len(data["matches"]) >= 1


# ---------------------------------------------------------------------------
# Amendment detection
# ---------------------------------------------------------------------------

class TestTextAmendmentDetection:
    def test_both_markers_page1(self, amended_txt_path):
        """Page 1 has ~~4.00x~~ [RED: 4.50x] — should produce both span types."""
        data = json.loads(extract_text_sections(str(amended_txt_path), [1]))
        page = data["pages"][0]
        assert len(page["strikethrough_spans"]) >= 1
        assert len(page["red_spans"]) >= 1

    def test_strike_only_page2(self, amended_txt_path):
        data = json.loads(extract_text_sections(str(amended_txt_path), [2]))
        page = data["pages"][0]
        assert len(page["strikethrough_spans"]) >= 1

    def test_red_only_page2(self, amended_txt_path):
        data = json.loads(extract_text_sections(str(amended_txt_path), [2]))
        page = data["pages"][0]
        assert len(page["red_spans"]) >= 1

    def test_strike_span_content_page2(self, amended_txt_path):
        data = json.loads(extract_text_sections(str(amended_txt_path), [2]))
        page = data["pages"][0]
        strike_texts = [s["text"] for s in page["strikethrough_spans"]]
        assert any("$50,000,000" in t for t in strike_texts)

    def test_red_span_content_page2(self, amended_txt_path):
        data = json.loads(extract_text_sections(str(amended_txt_path), [2]))
        page = data["pages"][0]
        red_texts = [s["text"] for s in page["red_spans"]]
        assert any("ESG" in t for t in red_texts)

    def test_clean_page_has_no_spans(self, sample_txt_path):
        data = json.loads(extract_text_sections(str(sample_txt_path), [1]))
        page = data["pages"][0]
        assert page["red_spans"] == []
        assert page["strikethrough_spans"] == []

    def test_markers_stripped_from_text_field(self, amended_txt_path):
        data = json.loads(extract_text_sections(str(amended_txt_path), [1]))
        page = data["pages"][0]
        assert "~~" not in page["text"]
        assert "[RED:" not in page["text"]

    def test_span_indices_correct(self, amended_txt_path):
        """span start/end must index into the page text field."""
        data = json.loads(extract_text_sections(str(amended_txt_path), [1, 2]))
        for page in data["pages"]:
            if "error" in page:
                continue
            for span in page["red_spans"] + page["strikethrough_spans"]:
                assert page["text"][span["start"]:span["end"]] == span["text"]


# ---------------------------------------------------------------------------
# Output shape compatibility with PDF tools
# ---------------------------------------------------------------------------

class TestOutputShapeCompatibility:
    """Text tool output keys must be identical to PDF tool output keys."""

    def test_structure_keys_match_pdf(self, sample_txt_path):
        data = json.loads(get_text_structure(str(sample_txt_path)))
        assert set(data.keys()) == {"document", "page_count", "bookmarks", "headings"}

    def test_extract_page_keys_match_pdf(self, sample_txt_path):
        data = json.loads(extract_text_sections(str(sample_txt_path), [1]))
        assert "pages" in data
        page = data["pages"][0]
        assert set(page.keys()) >= {"page", "text", "red_spans", "strikethrough_spans"}

    def test_lookup_keys_match_pdf(self, sample_txt_path):
        data = json.loads(lookup_source_clause_text(str(sample_txt_path), "Leverage Ratio"))
        assert "query" in data
        assert "matches" in data
        if data["matches"]:
            m = data["matches"][0]
            assert set(m.keys()) >= {"page", "match_start", "context"}

    def test_tool_definitions_use_same_names_as_pdf(self):
        tool_names = {t["name"] for t in TEXT_TOOL_DEFINITIONS}
        expected = {"get_pdf_structure", "extract_pdf_pages", "lookup_source_clause"}
        assert tool_names == expected
