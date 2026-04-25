# Covenant Extractor Agent

An AI agent that extracts credit covenants from credit agreement PDFs and structures them into a validated, deterministic JSON schema.

---

## Overview

Credit agreements are complex legal documents (100–300+ pages) containing covenants spread across multiple sections. Amendments are typically marked as **red-colored text** (modifications/additions) or **strikethrough text** (deletions). This tool uses a Claude-powered agent with PDF inspection tools to:

1. **Locate** covenant sections within the document (financial, negative, affirmative, reporting, events of default)
2. **Extract** each covenant clause verbatim, detecting any red/strikethrough amendments
3. **Structure** each covenant into a validated Pydantic schema
4. **Cross-validate** numeric thresholds against the source document before producing the final output

The output JSON is **deterministic** — the same PDF will produce identical output on every run.

---

## Why an Agent (not a simple prompt chain)?

A fixed prompt chain cannot handle this task reliably because:

| Challenge | Why it requires an agent |
|-----------|--------------------------|
| Amendment detection | Red text and strikethrough require PDF element-level inspection (color metadata, annotation objects), not plain text extraction |
| Document navigation | Covenant sections are spread across a 100–300 page document; the agent uses a table of contents tool to navigate efficiently |
| Validation feedback loop | After structuring covenants, the agent calls a validation tool and self-corrects errors before finishing |
| Threshold verification | Financial covenants contain numeric thresholds; the agent re-reads source clauses to verify them before outputting |

---

## Architecture

```
main.py              ← CLI entry point
agent.py             ← Anthropic SDK tool-use loop (temperature=0, prompt caching)
tools/
  pdf_tools.py       ← pdfplumber-based PDF inspection tools
  validation_tools.py← Pydantic schema validation tool
schema/
  covenant.py        ← Pydantic models: Covenant, ThresholdValue, CovenantExtractionResult
prompts/
  system.py          ← Agent system prompt with step-by-step extraction instructions
tests/               ← pytest test suite
```

**LLM:** `claude-haiku-4-5` via Anthropic SDK  
**PDF parsing:** `pdfplumber` (element-level color and annotation access)  
**Schema validation:** Pydantic v2  
**Prompt caching:** enabled on the system prompt to reduce token costs on repeated runs

### Agent Tools

| Tool | Purpose |
|------|---------|
| `get_pdf_structure` | Returns page count and section headings — lets the agent navigate without reading every page |
| `extract_pdf_pages` | Reads page text with character-level color metadata and annotation data to detect red text and strikethrough |
| `lookup_source_clause` | Searches the PDF for a specific phrase — used to cross-verify extracted threshold values |
| `validate_covenants` | Runs Pydantic validation on a list of covenant objects and returns field-level errors |

---

## Output Schema

Each extracted covenant conforms to the following structure:

```json
{
  "id": "cov_a3f1b2c4",
  "covenant_type": "financial",
  "subtype": "leverage_ratio",
  "description": "Leverage ratio must not exceed 4.00x on a trailing 12-month basis",
  "obligation_text": "The Borrower shall not permit the Leverage Ratio to exceed 4.00 to 1.00...",
  "threshold": {
    "upper_threshold": 4.0,
    "lower_threshold": null,
    "type": "numerical",
    "unit": "x",
    "test_period": "trailing 12 months"
  },
  "frequency": "quarterly",
  "schedule_start_date": "2024-03-31",
  "maturity_date": "2029-06-30",
  "grace_period": "30 days",
  "obligor": "Borrower",
  "source_section": "Section 7.1(a)",
  "source_page": 47,
  "is_amended": false,
  "amendment": null,
  "cross_references": ["Section 1.1", "Section 7.3"]
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Deterministic ID: `"cov_"` + first 8 hex chars of `sha256(source_section + "||" + obligation_text)` |
| `covenant_type` | `"financial" \| "negative" \| "affirmative" \| "reporting" \| "other"` | Category of covenant |
| `subtype` | `string` | Descriptive slug, e.g. `"leverage_ratio"`, `"no_additional_indebtedness"` |
| `description` | `string` | One-line plain-English summary |
| `obligation_text` | `string` | Verbatim clause text copied from the document |
| `threshold.upper_threshold` | `float \| null` | Maximum permitted value (e.g. max leverage ratio) |
| `threshold.lower_threshold` | `float \| null` | Minimum required value (e.g. min interest coverage ratio) |
| `threshold.type` | `"numerical" \| "percentage"` | Whether the threshold is a raw number or a percentage |
| `threshold.unit` | `string \| null` | Unit of measure, e.g. `"x"`, `"USD millions"` |
| `threshold.test_period` | `string \| null` | Measurement period, e.g. `"trailing 12 months"` |
| `frequency` | `string \| null` | Testing/reporting frequency, e.g. `"quarterly"`, `"annually"` |
| `schedule_start_date` | `string \| null` | When the covenant obligation begins (ISO-8601 or textual as in document) |
| `maturity_date` | `string \| null` | When the covenant obligation expires (ISO-8601 or textual as in document) |
| `grace_period` | `string \| null` | Cure period before a breach becomes an event of default, e.g. `"30 days"` |
| `obligor` | `string` | Party bearing the obligation, e.g. `"Borrower"`, `"Guarantor"` |
| `source_section` | `string` | Section reference, e.g. `"Section 7.1(a)"` |
| `source_page` | `integer` | 1-indexed page number in the source PDF |
| `is_amended` | `boolean` | Whether this covenant is marked as amended in the document |
| `amendment.amendment_type` | `"deletion" \| "modification"` | How it was amended |
| `amendment.original_text` | `string` | The struck-out or replaced text |
| `amendment.amended_text` | `string \| null` | The replacement text (`null` if deleted) |
| `amendment.marking` | `"strikethrough" \| "red_text" \| "both"` | How the amendment is visually indicated |
| `cross_references` | `string[]` | Other sections referenced within the clause |

### Top-level result wrapper

```json
{
  "document_name": "credit_agreement_2024.pdf",
  "extraction_date": "2026-04-25",
  "covenants": [...],
  "validation_notes": ["Section 8.3 references an exhibit not found in this document"],
  "total_count": 24,
  "amended_count": 3
}
```

---

## Amendment Detection

The agent detects two visual markers for amendments:

| Marker | Detected as | Schema result |
|--------|-------------|---------------|
| Red-colored text | New or replacement language | `is_amended=true`, `amendment_type="modification"`, `marking="red_text"` |
| Strikethrough text | Deleted or replaced language | `is_amended=true`, `amendment_type="deletion"`, `marking="strikethrough"` |
| Red text immediately following strikethrough | Replacement of deleted language | `is_amended=true`, `amendment_type="modification"`, `marking="both"` |

Red text is detected by inspecting character-level RGB values from the PDF (`r > 0.7, g < 0.3, b < 0.3`). Strikethrough is detected via PDF annotation objects overlapping the text bounding box.

---

## Setup and Installation

```bash
# Requires Python 3.11+
python3 -m venv venv
source venv/bin/activate        # (venv) appears in your prompt

pip install -r requirements.txt
```

**requirements.txt**
```
anthropic>=0.40.0
pdfplumber>=0.11.0
pydantic>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

---

## Configuration

Set your Anthropic API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

### Basic extraction

```bash
python main.py path/to/credit_agreement.pdf
```

Output is written to `credit_agreement_covenants.json` in the same directory as the PDF.

### Custom output path

```bash
python main.py path/to/credit_agreement.pdf --output results/output.json
```

### Save as golden fixture for determinism tests

```bash
python main.py path/to/credit_agreement.pdf --save-fixture
```

This writes the result to `tests/fixtures/expected_output.json`. Subsequent runs of `pytest tests/test_determinism.py` will compare new output against this golden file to verify determinism.

---

## Testing

```bash
pytest tests/ -v
```

| Test file | What it covers |
|-----------|----------------|
| `test_schema.py` | Pydantic model validation, field constraints, `make_covenant_id` determinism |
| `test_validation_tools.py` | `validate_covenants` tool: valid/invalid inputs, error reporting |
| `test_pdf_tools.py` | PDF tool functions with fixture PDFs |
| `test_determinism.py` | End-to-end: two runs on the same PDF produce identical JSON (excluding `extraction_date`) |

---

## Determinism Guarantee

The same PDF input produces identical JSON output on every run. This is ensured by:

- `temperature=0` on all Claude API calls
- Covenant `id` values derived from `sha256(source_section + "||" + obligation_text)`, not random UUIDs
- Output `covenants` list sorted by `(source_page ASC, source_section ASC)` before writing
- No run-time-generated values in covenant fields (`extraction_date` in the wrapper is the only date that changes between runs)

---

## Project Structure

```
covenant-extractor-agent/
├── main.py                        # CLI entry point
├── agent.py                       # Anthropic SDK tool-use loop
├── requirements.txt
├── schema/
│   ├── __init__.py
│   └── covenant.py                # Pydantic models
├── tools/
│   ├── __init__.py
│   ├── pdf_tools.py               # PDF inspection tools (pdfplumber)
│   └── validation_tools.py        # Schema validation tool
├── prompts/
│   ├── __init__.py
│   └── system.py                  # Agent system prompt
└── tests/
    ├── conftest.py
    ├── fixtures/                  # Golden output files for determinism tests
    ├── test_schema.py
    ├── test_validation_tools.py
    ├── test_pdf_tools.py
    └── test_determinism.py
```
