"""
Shared fixtures for the covenant extractor test suite.

The synthetic PDF fixture is generated programmatically so tests can run
without a real credit agreement on disk.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers to build a minimal synthetic PDF without external dependencies
# ---------------------------------------------------------------------------

def _minimal_pdf_bytes(pages: list[str]) -> bytes:
    """
    Build a bare-minimum PDF from plain text pages.
    Each string in `pages` becomes one page of text.
    Uses only Python stdlib — no reportlab or fpdf dependency.
    """
    objects: list[bytes] = []
    offsets: list[int] = []

    def add_obj(content: bytes) -> int:
        idx = len(objects) + 1
        objects.append(content)
        return idx

    # We'll build the PDF in memory
    buf = io.BytesIO()

    def write(data: bytes) -> int:
        pos = buf.tell()
        buf.write(data)
        return pos

    write(b"%PDF-1.4\n")

    # Font object
    font_obj_num = 1
    page_obj_nums: list[int] = []
    content_obj_nums: list[int] = []

    # We build objects linearly; track byte offsets for xref
    raw_objects: list[tuple[int, bytes]] = []  # (obj_num, content_bytes)

    obj_num = 1

    # Font
    font_content = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    raw_objects.append((obj_num, font_content))
    font_obj_num = obj_num
    obj_num += 1

    for page_text in pages:
        # Content stream
        escaped = page_text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream_data = (
            f"BT /F1 10 Tf 50 750 Td ({escaped}) Tj ET"
        ).encode("latin-1", errors="replace")
        stream_obj = (
            f"<< /Length {len(stream_data)} >>\nstream\n".encode()
            + stream_data
            + b"\nendstream"
        )
        raw_objects.append((obj_num, stream_obj))
        content_obj_num = obj_num
        obj_num += 1

        # Page object
        page_obj = (
            f"<< /Type /Page /Parent {obj_num + len(pages) * 2 + 1} 0 R "
            f"/MediaBox [0 0 612 792] "
            f"/Contents {content_obj_num} 0 R "
            f"/Resources << /Font << /F1 {font_obj_num} 0 R >> >> >>"
        ).encode()
        raw_objects.append((obj_num, page_obj))
        page_obj_nums.append(obj_num)
        obj_num += 1

    # Pages dict
    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    pages_obj = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    raw_objects.append((obj_num, pages_obj))
    pages_obj_num = obj_num
    obj_num += 1

    # Catalog
    catalog_obj = f"<< /Type /Catalog /Pages {pages_obj_num} 0 R >>".encode()
    raw_objects.append((obj_num, catalog_obj))
    catalog_obj_num = obj_num
    obj_num += 1

    # Fix up page parent references — rebuild pages_obj with correct num
    # (already correct since pages_obj_num is set before page objects reference it via obj_num + len(pages)*2+1 — this simple builder works for small docs)

    # Write all objects and record offsets
    xref_offsets: dict[int, int] = {}
    buf2 = io.BytesIO()
    buf2.write(b"%PDF-1.4\n")

    for num, content in raw_objects:
        xref_offsets[num] = buf2.tell()
        buf2.write(f"{num} 0 obj\n".encode())
        buf2.write(content)
        buf2.write(b"\nendobj\n")

    xref_pos = buf2.tell()
    total_objs = len(raw_objects) + 1  # +1 for free entry

    buf2.write(b"xref\n")
    buf2.write(f"0 {total_objs}\n".encode())
    buf2.write(b"0000000000 65535 f \n")
    for i in range(1, total_objs):
        buf2.write(f"{xref_offsets.get(i, 0):010d} 00000 n \n".encode())

    buf2.write(b"trailer\n")
    buf2.write(f"<< /Size {total_objs} /Root {catalog_obj_num} 0 R >>\n".encode())
    buf2.write(b"startxref\n")
    buf2.write(f"{xref_pos}\n".encode())
    buf2.write(b"%%EOF\n")

    return buf2.getvalue()


@pytest.fixture(scope="session")
def sample_pdf_path(tmp_path_factory) -> Path:
    """A synthetic single-page credit agreement PDF for unit tests."""
    tmp = tmp_path_factory.mktemp("pdfs")
    pdf_path = tmp / "sample_credit_agreement.pdf"

    page1 = (
        "CREDIT AGREEMENT\n\n"
        "Section 7.1 Financial Covenants\n"
        "(a) Leverage Ratio. The Borrower shall not permit the Consolidated Leverage Ratio, "
        "as of the last day of any fiscal quarter, to exceed 4.00x.\n\n"
        "(b) Interest Coverage Ratio. The Borrower shall maintain an Interest Coverage Ratio "
        "of not less than 2.50x for any trailing 12-month period.\n\n"
        "Section 7.2 Negative Covenants\n"
        "(a) Indebtedness. The Borrower shall not incur any additional Indebtedness "
        "in excess of $50,000,000 without prior written consent of the Agent.\n\n"
        "Section 7.3 Affirmative Covenants\n"
        "(a) Financial Statements. The Borrower shall deliver audited annual financial statements "
        "within 90 days of each fiscal year end.\n"
    )

    pdf_path.write_bytes(_minimal_pdf_bytes([page1]))
    return pdf_path


@pytest.fixture(scope="session")
def expected_output_path() -> Path:
    return FIXTURE_DIR / "expected_output.json"


@pytest.fixture(scope="session")
def amended_pdf_path() -> Path:
    """
    Multi-page credit agreement with red text and strikethrough amendments.
    Generated by: python scripts/create_sample_pdf.py
    """
    path = FIXTURE_DIR / "sample_credit_agreement.pdf"
    if not path.exists():
        pytest.skip(
            "Run 'python scripts/create_sample_pdf.py' to generate the sample PDF fixture"
        )
    return path
