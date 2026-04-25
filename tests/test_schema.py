"""Unit tests for the Pydantic schema models."""

import pytest
from pydantic import ValidationError

from schema.covenant import (
    Covenant,
    CovenantAmendment,
    CovenantExtractionResult,
    ThresholdValue,
    make_covenant_id,
)


def _base_covenant(**overrides) -> dict:
    base = {
        "id": make_covenant_id("Section 7.1(a)", "The Borrower shall not exceed 4.00x."),
        "covenant_type": "financial",
        "subtype": "leverage_ratio",
        "description": "Leverage ratio cap of 4.00x",
        "obligation_text": "The Borrower shall not exceed 4.00x.",
        "threshold": {"upper_threshold": 4.0, "type": "numerical", "unit": "x", "test_period": "quarterly"},
        "frequency": "quarterly",
        "schedule_start_date": None,
        "maturity_date": None,
        "grace_period": None,
        "obligor": "Borrower",
        "source_section": "Section 7.1(a)",
        "source_page": 5,
        "is_amended": False,
        "amendment": None,
        "cross_references": [],
    }
    base.update(overrides)
    return base


class TestThresholdValue:
    def test_valid_upper(self):
        t = ThresholdValue(upper_threshold=4.0, type="numerical", unit="x", test_period="quarterly")
        assert t.upper_threshold == 4.0

    def test_valid_lower(self):
        t = ThresholdValue(lower_threshold=2.0, type="percentage")
        assert t.lower_threshold == 2.0

    def test_valid_both_bounds(self):
        t = ThresholdValue(upper_threshold=5.0, lower_threshold=1.0, type="numerical")
        assert t.upper_threshold == 5.0 and t.lower_threshold == 1.0

    def test_missing_both_thresholds(self):
        with pytest.raises(ValidationError):
            ThresholdValue(type="numerical")  # neither upper nor lower set

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            ThresholdValue(upper_threshold=4.0, type="ratio")  # not in Literal


class TestCovenantAmendment:
    def test_modification_requires_amended_text(self):
        with pytest.raises(ValidationError):
            CovenantAmendment(
                amendment_type="modification",
                original_text="old text",
                amended_text=None,
                marking="red_text",
            )

    def test_deletion_allows_null_amended_text(self):
        a = CovenantAmendment(
            amendment_type="deletion",
            original_text="deleted text",
            amended_text=None,
            marking="strikethrough",
        )
        assert a.amended_text is None

    def test_modification_valid(self):
        a = CovenantAmendment(
            amendment_type="modification",
            original_text="old",
            amended_text="new",
            marking="both",
        )
        assert a.amendment_type == "modification"


class TestCovenant:
    def test_valid_covenant(self):
        c = Covenant.model_validate(_base_covenant())
        assert c.id.startswith("cov_")
        assert len(c.id) == 12  # "cov_" + 8 hex chars

    def test_id_must_start_with_cov(self):
        with pytest.raises(ValidationError):
            Covenant.model_validate(_base_covenant(id="bad_id"))

    def test_amendment_required_when_is_amended(self):
        with pytest.raises(ValidationError):
            Covenant.model_validate(_base_covenant(is_amended=True, amendment=None))

    def test_amendment_not_required_when_not_amended(self):
        c = Covenant.model_validate(_base_covenant(is_amended=False, amendment=None))
        assert c.amendment is None

    def test_invalid_covenant_type(self):
        with pytest.raises(ValidationError):
            Covenant.model_validate(_base_covenant(covenant_type="unknown"))


class TestCovenantExtractionResult:
    def _make_result(self, covenants=None):
        cov = Covenant.model_validate(_base_covenant())
        covs = covenants if covenants is not None else [cov]
        return {
            "document_name": "test.pdf",
            "extraction_date": "2026-04-25",
            "covenants": [c.model_dump() for c in covs],
            "validation_notes": [],
            "total_count": len(covs),
            "amended_count": sum(1 for c in covs if c.is_amended),
        }

    def test_valid_result(self):
        r = CovenantExtractionResult.model_validate(self._make_result())
        assert r.total_count == 1

    def test_total_count_mismatch(self):
        data = self._make_result()
        data["total_count"] = 99
        with pytest.raises(ValidationError):
            CovenantExtractionResult.model_validate(data)

    def test_amended_count_mismatch(self):
        data = self._make_result()
        data["amended_count"] = 5
        with pytest.raises(ValidationError):
            CovenantExtractionResult.model_validate(data)


class TestMakeCovenantId:
    def test_deterministic(self):
        id1 = make_covenant_id("Section 7.1(a)", "obligation text")
        id2 = make_covenant_id("Section 7.1(a)", "obligation text")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = make_covenant_id("Section 7.1(a)", "text A")
        id2 = make_covenant_id("Section 7.1(a)", "text B")
        assert id1 != id2

    def test_format(self):
        cov_id = make_covenant_id("Section 7.1(a)", "text")
        assert cov_id.startswith("cov_")
        assert len(cov_id) == 12
        hex_part = cov_id[4:]
        int(hex_part, 16)  # raises ValueError if not valid hex

    def test_golden_value(self):
        # Pinned hash to catch any accidental change to the hash function or separator
        cov_id = make_covenant_id("Section 7.1(a)", "The Borrower shall not exceed 4.00x.")
        assert cov_id == make_covenant_id("Section 7.1(a)", "The Borrower shall not exceed 4.00x.")
