"""Strict validation of the LLM's structured output.

The Tier-2 LLM pass must return JSON of a fixed shape. This module validates
that shape with stdlib only (no jsonschema dependency) so a malformed response
is caught deterministically and mapped to the ANALYSIS_FAILED state after one
retry, rather than throwing mid-batch or silently producing a bad verdict.

Expected LLM payload:

    {
      "findings": [
        {
          "tell_id": "T1",
          "quote": "verbatim text from the report",
          "rationale": "one sentence"
        },
        ...
      ]
    }

We deliberately do NOT trust the LLM to assign severity or tier — those come
from the rubric (the source of truth), keyed by tell_id. The LLM only proposes
which tell fired and supplies the quote + rationale. Code decides everything
that affects the label.
"""

from __future__ import annotations

from typing import Any


class SchemaError(ValueError):
    """Raised when LLM output does not conform to the expected shape."""


# Only these keys are meaningful on a finding; extras are ignored (forward-compat),
# but the required ones must be present, of the right type, and non-empty where noted.
_REQUIRED_FINDING_FIELDS = ("tell_id", "quote", "rationale")


def validate_llm_payload(payload: Any) -> list[dict[str, str]]:
    """Validate and normalize the raw LLM payload.

    Returns a list of normalized finding dicts with exactly the keys
    tell_id / quote / rationale (all str). Raises SchemaError on any
    non-conformance so the caller can retry once, then fail the analysis.
    """
    if not isinstance(payload, dict):
        raise SchemaError(f"payload must be an object, got {type(payload).__name__}")

    if "findings" not in payload:
        raise SchemaError("payload missing required key 'findings'")

    findings = payload["findings"]
    if not isinstance(findings, list):
        raise SchemaError(
            f"'findings' must be a list, got {type(findings).__name__}"
        )

    normalized: list[dict[str, str]] = []
    for i, raw in enumerate(findings):
        if not isinstance(raw, dict):
            raise SchemaError(f"findings[{i}] must be an object, got {type(raw).__name__}")

        for key in _REQUIRED_FINDING_FIELDS:
            if key not in raw:
                raise SchemaError(f"findings[{i}] missing required key '{key}'")
            if not isinstance(raw[key], str):
                raise SchemaError(
                    f"findings[{i}]['{key}'] must be a string, "
                    f"got {type(raw[key]).__name__}"
                )

        tell_id = raw["tell_id"].strip()
        quote = raw["quote"]  # exact-match verified later; do NOT strip interior
        rationale = raw["rationale"].strip()

        if not tell_id:
            raise SchemaError(f"findings[{i}]['tell_id'] is empty")
        if not quote.strip():
            raise SchemaError(f"findings[{i}]['quote'] is empty")
        if not rationale:
            raise SchemaError(f"findings[{i}]['rationale'] is empty")

        normalized.append(
            {"tell_id": tell_id, "quote": quote, "rationale": rationale}
        )

    return normalized
