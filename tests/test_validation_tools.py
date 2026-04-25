"""Unit tests for the schema validation tool."""

import json

import pytest

from schema.covenant import make_covenant_id
from tools.validation_tools import validate_covenants


def _valid_covenant(**overrides) -> dict:
    base = {
        "id": make_covenant_id("Section 7.1(a)", "The Borrower shall not exceed 4.00x."),
        "covenant_type": "financial",
        "subtype": "leverage_ratio",
        "description": "Leverage ratio cap",
        "obligation_text": "The Borrower shall not exceed 4.00x.",
        "threshold": {"value": 4.0, "operator": "<=", "unit": "x", "test_period": "quarterly"},
        "test_frequency": "quarterly",
        "obligor": "Borrower",
        "source_section": "Section 7.1(a)",
        "source_page": 5,
        "is_amended": False,
        "amendment": None,
        "cross_references": [],
    }
    base.update(overrides)
    return base


class TestValidateCovenants:
    def test_valid_single_covenant(self):
        result = json.loads(validate_covenants([_valid_covenant()]))
        assert result["status"] == "valid"
        assert result["count"] == 1

    def test_valid_multiple_covenants(self):
        cov2 = _valid_covenant(
            id=make_covenant_id("Section 7.2(a)", "No additional debt."),
            covenant_type="negative",
            subtype="no_additional_indebtedness",
            obligation_text="No additional debt.",
            source_section="Section 7.2(a)",
            source_page=6,
            threshold=None,
            test_frequency=None,
        )
        result = json.loads(validate_covenants([_valid_covenant(), cov2]))
        assert result["status"] == "valid"
        assert result["count"] == 2

    def test_invalid_covenant_type(self):
        bad = _valid_covenant(covenant_type="unknown_type")
        result = json.loads(validate_covenants([bad]))
        assert result["status"] == "invalid"
        assert result["error_count"] == 1
        assert result["errors"][0]["index"] == 0

    def test_missing_required_field(self):
        bad = _valid_covenant()
        del bad["obligor"]
        result = json.loads(validate_covenants([bad]))
        assert result["status"] == "invalid"

    def test_empty_list_is_valid(self):
        result = json.loads(validate_covenants([]))
        assert result["status"] == "valid"
        assert result["count"] == 0

    def test_mixed_valid_invalid(self):
        bad = _valid_covenant(covenant_type="bad_type")
        result = json.loads(validate_covenants([_valid_covenant(), bad]))
        assert result["status"] == "invalid"
        assert result["error_count"] == 1
        assert result["errors"][0]["index"] == 1
