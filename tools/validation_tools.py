"""Schema validation tool exposed to the agent."""

import json
import logging
from pydantic import ValidationError
from schema.covenant import Covenant

logger = logging.getLogger("tools.validation")


def validate_covenants(covenants_json: list[dict]) -> str:
    """
    Validate a list of covenant dicts against the Covenant Pydantic model.

    Returns JSON with either {"status": "valid", "count": N} or a list of
    per-covenant errors so the agent can fix them before finalising output.
    """
    logger.debug("validate_covenants: checking %d covenant(s)", len(covenants_json))
    errors: list[dict] = []
    for i, cov in enumerate(covenants_json):
        try:
            Covenant.model_validate(cov)
        except ValidationError as exc:
            cov_id = cov.get("id", f"item_{i}")
            logger.debug(
                "Covenant %s (index %d) failed validation: %s",
                cov_id, i,
                [f"{e['loc']} — {e['msg']}" for e in exc.errors(include_url=False)],
            )
            errors.append({
                "index": i,
                "id": cov_id,
                "errors": exc.errors(include_url=False),
            })

    if errors:
        logger.info("Validation result: INVALID — %d error(s) across %d covenant(s)",
                    len(errors), len(covenants_json))
        return json.dumps({"status": "invalid", "error_count": len(errors), "errors": errors}, indent=2)

    logger.info("Validation result: valid — %d covenant(s)", len(covenants_json))
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
