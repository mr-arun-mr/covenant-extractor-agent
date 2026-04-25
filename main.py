"""
CLI entry point for the covenant extractor agent.

Usage:
    python main.py <pdf_path> [--output <output_json>] [--save-fixture]

--save-fixture writes the result to tests/fixtures/expected_output.json,
used as the golden file for determinism tests.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from agent import run_extraction


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract credit covenants from a PDF credit agreement.")
    parser.add_argument("pdf_path", help="Path to the credit agreement PDF")
    parser.add_argument(
        "--output",
        default=None,
        help="Path for the output JSON file (default: <pdf_stem>_covenants.json)",
    )
    parser.add_argument(
        "--save-fixture",
        action="store_true",
        help="Also save the result to tests/fixtures/expected_output.json as the golden test file",
    )
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: file not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Extracting covenants from: {pdf_path.name}")
    result = run_extraction(str(pdf_path))

    output_path = Path(args.output) if args.output else pdf_path.with_name(f"{pdf_path.stem}_covenants.json")
    output_json = result.model_dump_json(indent=2)
    output_path.write_text(output_json, encoding="utf-8")
    print(f"Output written to: {output_path}")
    print(f"  Total covenants : {result.total_count}")
    print(f"  Amended         : {result.amended_count}")

    if args.save_fixture:
        fixture_path = Path(__file__).parent / "tests" / "fixtures" / "expected_output.json"
        fixture_path.write_text(output_json, encoding="utf-8")
        print(f"Golden fixture saved to: {fixture_path}")


if __name__ == "__main__":
    main()
