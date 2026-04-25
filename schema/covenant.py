import hashlib
from typing import Literal, Optional
from pydantic import BaseModel, field_validator, model_validator


class ThresholdValue(BaseModel):
    value: float
    operator: Literal[">=", "<=", ">", "<", "="]
    unit: Optional[str] = None       # e.g., "x", "%", "USD millions"
    test_period: Optional[str] = None  # e.g., "trailing 12 months"


class CovenantAmendment(BaseModel):
    amendment_type: Literal["deletion", "modification"]
    original_text: str
    amended_text: Optional[str] = None  # None if deleted
    marking: Literal["strikethrough", "red_text", "both"]

    @model_validator(mode="after")
    def amended_text_required_for_modification(self) -> "CovenantAmendment":
        if self.amendment_type == "modification" and not self.amended_text:
            raise ValueError("amended_text is required when amendment_type is 'modification'")
        return self


class Covenant(BaseModel):
    id: str                          # "cov_" + sha256(source_section + obligation_text)[:8]
    covenant_type: Literal["financial", "negative", "affirmative", "reporting", "other"]
    subtype: str                     # e.g., "leverage_ratio", "no_additional_debt"
    description: str                 # one-line human summary
    obligation_text: str             # verbatim clause text from the document
    threshold: Optional[ThresholdValue] = None
    test_frequency: Optional[str] = None   # e.g., "quarterly", "annually"
    obligor: str                     # borrower, guarantor, etc.
    source_section: str              # e.g., "Section 7.1(a)"
    source_page: int
    is_amended: bool = False
    amendment: Optional[CovenantAmendment] = None
    cross_references: list[str] = []

    @field_validator("id")
    @classmethod
    def id_must_be_cov_prefixed(cls, v: str) -> str:
        if not v.startswith("cov_"):
            raise ValueError("id must start with 'cov_'")
        return v

    @model_validator(mode="after")
    def amendment_required_when_amended(self) -> "Covenant":
        if self.is_amended and self.amendment is None:
            raise ValueError("amendment details required when is_amended is True")
        return self


class CovenantExtractionResult(BaseModel):
    document_name: str
    extraction_date: str             # ISO-8601 date string; excluded from determinism checks
    covenants: list[Covenant]
    validation_notes: list[str] = []
    total_count: int
    amended_count: int

    @model_validator(mode="after")
    def counts_match_covenants(self) -> "CovenantExtractionResult":
        if self.total_count != len(self.covenants):
            raise ValueError(f"total_count {self.total_count} does not match len(covenants) {len(self.covenants)}")
        amended = sum(1 for c in self.covenants if c.is_amended)
        if self.amended_count != amended:
            raise ValueError(f"amended_count {self.amended_count} does not match actual amended count {amended}")
        return self


def make_covenant_id(source_section: str, obligation_text: str) -> str:
    """Deterministic ID derived from section + obligation text."""
    raw = f"{source_section}||{obligation_text}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"cov_{digest}"
