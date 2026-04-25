"""Unit tests for the PDF tool implementations."""

import json
from pathlib import Path

import pytest

from tools.pdf_tools import extract_pdf_pages, get_pdf_structure, lookup_source_clause


class TestGetPdfStructure:
    def test_returns_valid_json(self, sample_pdf_path):
        raw = get_pdf_structure(str(sample_pdf_path))
        data = json.loads(raw)
        assert "page_count" in data
        assert data["page_count"] >= 1

    def test_missing_file(self, tmp_path):
        raw = get_pdf_structure(str(tmp_path / "nonexistent.pdf"))
        data = json.loads(raw)
        assert "error" in data

    def test_headings_is_a_list(self, sample_pdf_path):
        raw = get_pdf_structure(str(sample_pdf_path))
        data = json.loads(raw)
        # headings is best-effort; the key must exist and be a list
        assert isinstance(data.get("headings"), list)
        for h in data["headings"]:
            assert "page" in h and "heading" in h


class TestExtractPdfPages:
    def test_extracts_text(self, sample_pdf_path):
        raw = extract_pdf_pages(str(sample_pdf_path), [1])
        data = json.loads(raw)
        assert "pages" in data
        page = data["pages"][0]
        assert page["page"] == 1
        assert "text" in page
        assert len(page["text"]) > 0

    def test_out_of_range_page(self, sample_pdf_path):
        raw = extract_pdf_pages(str(sample_pdf_path), [999])
        data = json.loads(raw)
        page = data["pages"][0]
        assert "error" in page

    def test_no_amendments_in_clean_pdf(self, sample_pdf_path):
        raw = extract_pdf_pages(str(sample_pdf_path), [1], detect_amendments=True)
        data = json.loads(raw)
        page = data["pages"][0]
        # Synthetic PDF has no red/strikethrough — spans should be empty
        assert page["red_spans"] == []
        assert page["strikethrough_spans"] == []

    def test_missing_file(self, tmp_path):
        raw = extract_pdf_pages(str(tmp_path / "nonexistent.pdf"), [1])
        data = json.loads(raw)
        assert "error" in data

    def test_multiple_pages(self, sample_pdf_path):
        raw = extract_pdf_pages(str(sample_pdf_path), [1])
        data = json.loads(raw)
        assert len(data["pages"]) == 1


class TestLookupSourceClause:
    def test_finds_known_text(self, sample_pdf_path):
        raw = lookup_source_clause(str(sample_pdf_path), "Leverage Ratio")
        data = json.loads(raw)
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["page"] == 1

    def test_no_match_returns_empty(self, sample_pdf_path):
        raw = lookup_source_clause(str(sample_pdf_path), "xyznonexistenttextxyz")
        data = json.loads(raw)
        assert data["matches"] == []

    def test_short_query_returns_error(self, sample_pdf_path):
        raw = lookup_source_clause(str(sample_pdf_path), "abc")
        data = json.loads(raw)
        assert "error" in data

    def test_missing_file(self, tmp_path):
        raw = lookup_source_clause(str(tmp_path / "nonexistent.pdf"), "leverage ratio")
        data = json.loads(raw)
        assert "error" in data

    def test_page_hint_prioritises_results(self, sample_pdf_path):
        raw = lookup_source_clause(str(sample_pdf_path), "Borrower shall", page_hint=1)
        data = json.loads(raw)
        assert len(data["matches"]) >= 1
        assert data["matches"][0]["page"] == 1
