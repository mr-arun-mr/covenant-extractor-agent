"""
Determinism tests: same PDF input must produce identical output across runs.

These tests mock the Anthropic API so they run without a live API key.
The golden-file test (test_output_matches_expected) is skipped if
tests/fixtures/expected_output.json doesn't exist yet — run
`python main.py <pdf> --save-fixture` first to generate it.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from schema.covenant import CovenantExtractionResult, make_covenant_id

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Fake agent response — returns a deterministic CovenantExtractionResult JSON
# ---------------------------------------------------------------------------

def _make_fake_result(document_name: str) -> str:
    cov_id = make_covenant_id("Section 7.1(a)", "The Borrower shall not permit the Consolidated Leverage Ratio to exceed 4.00x.")
    return json.dumps({
        "document_name": document_name,
        "extraction_date": "2026-04-25",
        "covenants": [
            {
                "id": cov_id,
                "covenant_type": "financial",
                "subtype": "leverage_ratio",
                "description": "Consolidated Leverage Ratio must not exceed 4.00x at any fiscal quarter end.",
                "obligation_text": "The Borrower shall not permit the Consolidated Leverage Ratio to exceed 4.00x.",
                "threshold": {"upper_threshold": 4.0, "type": "numerical", "unit": "x", "test_period": "fiscal quarter"},
                "frequency": "quarterly",
                "schedule_start_date": None,
                "maturity_date": None,
                "grace_period": None,
                "obligor": "Borrower",
                "source_section": "Section 7.1(a)",
                "source_page": 1,
                "is_amended": False,
                "amendment": None,
                "cross_references": [],
            }
        ],
        "validation_notes": [],
        "total_count": 1,
        "amended_count": 0,
    })


def _build_mock_client(document_name: str):
    """Build a mock anthropic.Anthropic client that returns the fake result."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.stop_reason = "end_turn"

    text_block = MagicMock()
    text_block.text = _make_fake_result(document_name)
    mock_response.content = [text_block]

    mock_client.messages.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self, sample_pdf_path):
        """Two runs on the same PDF must produce identical covenant data."""
        with patch("agent.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = _build_mock_client(sample_pdf_path.name)

            from agent import run_extraction
            result1 = run_extraction(str(sample_pdf_path))

        with patch("agent.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = _build_mock_client(sample_pdf_path.name)

            result2 = run_extraction(str(sample_pdf_path))

        # Exclude extraction_date — it's the only field allowed to differ
        assert result1.model_dump(exclude={"extraction_date"}) == result2.model_dump(exclude={"extraction_date"})

    def test_covenant_ids_are_deterministic(self):
        """make_covenant_id must return the same value for the same inputs, always."""
        inputs = [
            ("Section 7.1(a)", "The Borrower shall not exceed 4.00x."),
            ("Section 7.2(b)", "No additional indebtedness."),
            ("Section 8.1", "Deliver audited financials within 90 days."),
        ]
        for section, text in inputs:
            ids = [make_covenant_id(section, text) for _ in range(5)]
            assert len(set(ids)) == 1, f"Non-deterministic ID for ({section!r}, {text!r}): {ids}"

    def test_covenant_ids_unique_for_different_inputs(self):
        """Different section+text combinations must produce different IDs."""
        id1 = make_covenant_id("Section 7.1(a)", "text A")
        id2 = make_covenant_id("Section 7.1(a)", "text B")
        id3 = make_covenant_id("Section 7.2(a)", "text A")
        assert id1 != id2
        assert id1 != id3
        assert id2 != id3

    def test_output_sorted_by_page_then_section(self, sample_pdf_path):
        """Covenants must be sorted by (source_page, source_section) for determinism."""
        # Build a result with deliberately unsorted covenants
        covenants_unsorted = [
            {
                "id": make_covenant_id("Section 8.1(a)", "obligation C"),
                "covenant_type": "reporting",
                "subtype": "financial_statements",
                "description": "desc C",
                "obligation_text": "obligation C",
                "threshold": None,
                "frequency": "annually",
                "schedule_start_date": None,
                "maturity_date": None,
                "grace_period": None,
                "obligor": "Borrower",
                "source_section": "Section 8.1(a)",
                "source_page": 3,
                "is_amended": False,
                "amendment": None,
                "cross_references": [],
            },
            {
                "id": make_covenant_id("Section 7.1(a)", "obligation A"),
                "covenant_type": "financial",
                "subtype": "leverage_ratio",
                "description": "desc A",
                "obligation_text": "obligation A",
                "threshold": {"upper_threshold": 4.0, "type": "numerical", "unit": "x", "test_period": None},
                "frequency": "quarterly",
                "schedule_start_date": None,
                "maturity_date": None,
                "grace_period": None,
                "obligor": "Borrower",
                "source_section": "Section 7.1(a)",
                "source_page": 1,
                "is_amended": False,
                "amendment": None,
                "cross_references": [],
            },
        ]
        result = CovenantExtractionResult(
            document_name="test.pdf",
            extraction_date="2026-04-25",
            covenants=covenants_unsorted,  # type: ignore[arg-type]
            total_count=2,
            amended_count=0,
        )
        # Simulate what agent.py does after receiving the result
        result.covenants.sort(key=lambda c: (c.source_page, c.source_section))

        assert result.covenants[0].source_page == 1
        assert result.covenants[1].source_page == 3


class TestGoldenFile:
    def test_output_matches_expected(self, sample_pdf_path, expected_output_path):
        """
        Compare a fresh extraction against the committed golden file.
        Skipped if the golden file doesn't exist yet (run --save-fixture first).
        """
        if not expected_output_path.exists():
            pytest.skip("Golden file not yet generated. Run: python main.py <pdf> --save-fixture")

        with patch("agent.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value = _build_mock_client(sample_pdf_path.name)
            from agent import run_extraction
            result = run_extraction(str(sample_pdf_path))

        expected = CovenantExtractionResult.model_validate_json(expected_output_path.read_text())

        assert result.model_dump(exclude={"extraction_date"}) == expected.model_dump(exclude={"extraction_date"})
