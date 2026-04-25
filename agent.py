"""
Covenant extraction agent using the Anthropic SDK tool-use loop.

The agent calls PDF inspection tools, structures the covenants, validates
them against the Pydantic schema, and returns a CovenantExtractionResult.

temperature=0 on every API call ensures deterministic output for a given input.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import anthropic

from prompts.system import SYSTEM_PROMPT
from schema.covenant import CovenantExtractionResult
from tools.pdf_tools import PDF_TOOL_DEFINITIONS, extract_pdf_pages, get_pdf_structure, lookup_source_clause
from tools.validation_tools import VALIDATION_TOOL_DEFINITIONS, validate_covenants

logger = logging.getLogger("agent")

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_TOOL_ROUNDS = 30  # hard cap to prevent infinite loops

_TRUNCATE = 1500  # max chars of tool content to show at DEBUG level


def _trunc(text: str, limit: int = _TRUNCATE) -> str:
    """Truncate long strings for debug output."""
    return text if len(text) <= limit else text[:limit] + f"… [{len(text) - limit} chars truncated]"

ALL_TOOL_DEFINITIONS = PDF_TOOL_DEFINITIONS + VALIDATION_TOOL_DEFINITIONS


def _dispatch_tool(tool_name: str, tool_input: dict, pdf_path: str) -> str:
    """Route a tool call to its Python implementation."""
    logger.debug("Tool input for %s: %s", tool_name, _trunc(json.dumps(tool_input)))
    if tool_name == "get_pdf_structure":
        result = get_pdf_structure(pdf_path)
    elif tool_name == "extract_pdf_pages":
        result = extract_pdf_pages(
            pdf_path,
            tool_input["page_numbers"],
            tool_input.get("detect_amendments", True),
        )
    elif tool_name == "lookup_source_clause":
        result = lookup_source_clause(
            pdf_path,
            tool_input["search_text"],
            tool_input.get("page_hint"),
        )
    elif tool_name == "validate_covenants":
        result = validate_covenants(tool_input["covenants_json"])
    else:
        result = json.dumps({"error": f"Unknown tool: {tool_name}"})
        logger.warning("Unknown tool requested: %s", tool_name)

    logger.debug("Tool result for %s: %s", tool_name, _trunc(result))
    return result


def run_extraction(pdf_path: str) -> CovenantExtractionResult:
    """
    Run the covenant extraction agent on a PDF file.

    Returns a validated CovenantExtractionResult. Raises ValueError if the
    agent does not produce parseable output within MAX_TOOL_ROUNDS turns.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    logger.info("Starting extraction: %s", path.name)
    logger.debug(
        "Agent config — model: %s, max_tokens: %d, max_rounds: %d",
        MODEL, MAX_TOKENS, MAX_TOOL_ROUNDS,
    )

    # api_key defaults to ANTHROPIC_API_KEY env var if not explicitly provided
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    # Initial user message — just the filename; the agent uses tools to read it
    messages: list[dict] = [
        {
            "role": "user",
            "content": (
                f"Extract all credit covenants from the credit agreement PDF: {path.name}\n"
                f"Full path for tool calls: {str(path.resolve())}"
            ),
        }
    ]

    for round_num in range(MAX_TOOL_ROUNDS):
        logger.debug("Round %d — sending %d message(s) to Claude", round_num + 1, len(messages))

        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=0,  # determinism
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},  # prompt caching
                }
            ],
            tools=ALL_TOOL_DEFINITIONS,
            messages=messages,
        )

        logger.debug(
            "Round %d response — stop_reason: %s, content blocks: %d",
            round_num + 1, response.stop_reason, len(response.content),
        )
        if hasattr(response, "usage"):
            logger.debug(
                "Token usage — input: %s, output: %s",
                getattr(response.usage, "input_tokens", "?"),
                getattr(response.usage, "output_tokens", "?"),
            )

        # Append the assistant's response to the conversation
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            # Agent finished — extract the JSON from the final text block
            final_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    final_text += block.text

            final_text = final_text.strip()

            # Strip markdown code fences if present
            if final_text.startswith("```"):
                lines = final_text.splitlines()
                final_text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            logger.debug("Final output (%d chars): %s", len(final_text), _trunc(final_text))

            try:
                raw = json.loads(final_text)
            except json.JSONDecodeError as exc:
                logger.error("Agent returned non-JSON output after %d round(s): %s", round_num + 1, exc)
                raise ValueError(
                    f"Agent returned non-JSON output after {round_num + 1} rounds: {exc}\n\nOutput:\n{final_text}"
                )

            result = CovenantExtractionResult.model_validate(raw)
            # Ensure covenants are sorted for determinism (agent should do this, but enforce it here too)
            result.covenants.sort(key=lambda c: (c.source_page, c.source_section))

            logger.info(
                "Extraction complete in %d round(s) — %d covenant(s), %d amended",
                round_num + 1, result.total_count, result.amended_count,
            )
            if result.validation_notes:
                logger.info("Validation notes: %s", result.validation_notes)
            return result

        if response.stop_reason == "tool_use":
            # Execute every tool the agent requested
            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Round %d — tool call: %s", round_num + 1, block.name)
                    output = _dispatch_tool(block.name, block.input, str(path.resolve()))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        logger.error("Unexpected stop_reason: %s", response.stop_reason)
        raise ValueError(f"Unexpected stop_reason: {response.stop_reason}")

    logger.error("Agent did not finish within %d tool rounds", MAX_TOOL_ROUNDS)
    raise ValueError(f"Agent did not finish within {MAX_TOOL_ROUNDS} tool rounds.")
