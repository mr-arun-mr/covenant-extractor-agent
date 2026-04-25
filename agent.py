"""
Covenant extraction agent using the Anthropic SDK tool-use loop.

The agent calls PDF inspection tools, structures the covenants, validates
them against the Pydantic schema, and returns a CovenantExtractionResult.

temperature=0 on every API call ensures deterministic output for a given input.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import anthropic

from prompts.system import SYSTEM_PROMPT
from schema.covenant import CovenantExtractionResult
from tools.pdf_tools import PDF_TOOL_DEFINITIONS, extract_pdf_pages, get_pdf_structure, lookup_source_clause
from tools.validation_tools import VALIDATION_TOOL_DEFINITIONS, validate_covenants

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 8192
MAX_TOOL_ROUNDS = 30  # hard cap to prevent infinite loops

ALL_TOOL_DEFINITIONS = PDF_TOOL_DEFINITIONS + VALIDATION_TOOL_DEFINITIONS


def _dispatch_tool(tool_name: str, tool_input: dict, pdf_path: str) -> str:
    """Route a tool call to its Python implementation."""
    if tool_name == "get_pdf_structure":
        return get_pdf_structure(pdf_path)
    elif tool_name == "extract_pdf_pages":
        return extract_pdf_pages(
            pdf_path,
            tool_input["page_numbers"],
            tool_input.get("detect_amendments", True),
        )
    elif tool_name == "lookup_source_clause":
        return lookup_source_clause(
            pdf_path,
            tool_input["search_text"],
            tool_input.get("page_hint"),
        )
    elif tool_name == "validate_covenants":
        return validate_covenants(tool_input["covenants_json"])
    else:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})


def run_extraction(pdf_path: str) -> CovenantExtractionResult:
    """
    Run the covenant extraction agent on a PDF file.

    Returns a validated CovenantExtractionResult. Raises ValueError if the
    agent does not produce parseable output within MAX_TOOL_ROUNDS turns.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

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

            try:
                raw = json.loads(final_text)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Agent returned non-JSON output after {round_num + 1} rounds: {exc}\n\nOutput:\n{final_text}"
                )

            result = CovenantExtractionResult.model_validate(raw)
            # Ensure covenants are sorted for determinism (agent should do this, but enforce it here too)
            result.covenants.sort(key=lambda c: (c.source_page, c.source_section))
            return result

        if response.stop_reason == "tool_use":
            # Execute every tool the agent requested
            tool_results: list[dict] = []
            for block in response.content:
                if block.type == "tool_use":
                    output = _dispatch_tool(block.name, block.input, str(path.resolve()))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # Unexpected stop reason
        raise ValueError(f"Unexpected stop_reason: {response.stop_reason}")

    raise ValueError(f"Agent did not finish within {MAX_TOOL_ROUNDS} tool rounds.")
