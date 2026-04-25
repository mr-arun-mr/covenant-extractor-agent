"""Schema validation tool exposed to the agent."""

import json
from pydantic import ValidationError
from schema.covenant import Covenant


def validate_covenants(covenants_json: list[dict]) -> str:
    """
    Validate a list of covenant dicts against the Covenant Pydantic model.

    Returns JSON with either {"status": "valid", "count": N} or a list of
    per-covenant errors so the agent can fix them before finalising output.
    """
    errors: list[dict] = []
    for i, cov in enumerate(covenants_json):
        try:
            Covenant.model_validate(cov)
        except ValidationError as exc:
            errors.append({
                "index": i,
                "id": cov.get("id", f"item_{i}"),
                "errors": exc.errors(include_url=False),
            })

    if errors:
        return json.dumps({"status": "invalid", "error_count": len(errors), "errors": errors}, indent=2)
    return json.dumps({"status": "valid", "count": len(covenants_json)})


VALIDATION_TOOL_DEFINITIONS = [
    {
        "name": "validate_covenants",
        "description": (
            "Validate a list of covenant JSON objects against the Covenant schema. "
            "Returns 'valid' with a count, or a list of field-level errors to fix. "
            "Call this after structuring all covenants and again after any corrections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "covenants_json": {
                    "type": "array",
                    "description": "List of covenant objects to validate.",
                    "items": {"type": "object"},
                },
            },
            "required": ["covenants_json"],
        },
    },
]
