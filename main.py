"""
CLI entry point for the covenant extractor agent.

Usage:
    python main.py <file_path> [--output <output_json>] [--save-fixture]

Accepts PDF (.pdf) and plain-text (.txt) credit agreements.

--save-fixture writes the result to tests/fixtures/expected_output.json,
used as the golden file for determinism tests.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from logging_config import setup_logging

setup_logging()

logger = logging.getLogger("main")

from agent import run_extraction

_SUPPORTED_EXTENSIONS = {".pdf", ".txt"}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract credit covenants from a credit agreement (PDF or plain-text .txt)."
    )
    parser.add_argument(
        "file_path",
        help="Path to the credit agreement file (.pdf or .txt)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path for the output JSON file (default: <stem>_covenants.json)",
    )
    parser.add_argument(
        "--save-fixture",
        action="store_true",
        help="Also save the result to tests/fixtures/expected_output.json as the golden test file",
    )
    args = parser.parse_args()

    path = Path(args.file_path)
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        logger.error(
            "Unsupported file type '%s'. Supported formats: %s",
            path.suffix,
            ", ".join(sorted(_SUPPORTED_EXTENSIONS)),
        )
        sys.exit(1)

    output_path = Path(args.output) if args.output else path.with_name(f"{path.stem}_covenants.json")
    logger.info("Input : %s", path)
    logger.info("Output: %s", output_path)

    result = run_extraction(str(path))

    output_json = result.model_dump_json(indent=2)
    output_path.write_text(output_json, encoding="utf-8")
    logger.info(
        "Done — %d covenant(s) extracted (%d amended), written to %s",
        result.total_count, result.amended_count, output_path,
    )

    if args.save_fixture:
        fixture_path = Path(__file__).parent / "tests" / "fixtures" / "expected_output.json"
        fixture_path.write_text(output_json, encoding="utf-8")
        logger.info("Golden fixture saved to: %s", fixture_path)


if __name__ == "__main__":
    main()
