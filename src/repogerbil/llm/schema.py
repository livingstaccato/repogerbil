# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""JSON schema for Ollama structured output — constrains LLM verb and scope choices."""

from __future__ import annotations

import copy
from typing import Any

_BASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["entries", "summary"],
    "properties": {
        "entries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": ["verb", "scope", "description"],
                "properties": {
                    "verb": {
                        "type": "string",
                        "enum": [],  # populated by build_schema()
                    },
                    "scope": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 40,
                    },
                    "description": {
                        "type": "string",
                        "minLength": 5,
                        "maxLength": 120,
                    },
                },
            },
        },
        "summary": {
            "type": "string",
            "minLength": 20,
            "maxLength": 600,
        },
    },
}


def build_schema(allowed_verbs: list[str]) -> dict[str, Any]:
    """Build the Ollama JSON schema with the allowed verb enum populated.

    Args:
        allowed_verbs: List of valid verb strings (from ``vocabulary.allowed_verbs()``).

    Returns:
        Deep-copied schema dict with ``verb.enum`` set to ``sorted(allowed_verbs)``.
    """
    schema = copy.deepcopy(_BASE_SCHEMA)
    schema["properties"]["entries"]["items"]["properties"]["verb"]["enum"] = sorted(allowed_verbs)
    return schema


def compose_message(response: dict[str, Any]) -> str:
    """Compose a commit message (headers only) from a validated LLM response dict.

    Args:
        response: Dict with ``entries`` list and ``summary`` string,
                  as returned by the Ollama structured-output call.

    Returns:
        Commit message string: one ``verb(scope): description`` line per entry.
        The summary is intentionally excluded — callers retrieve it via
        ``extract_summary()`` and store it in a sidecar file.
    """
    entries: list[dict[str, str]] = response["entries"]
    header_lines = [f"{e['verb']}({e['scope']}): {e['description']}" for e in entries]
    return "\n".join(header_lines)


def extract_summary(response: dict[str, Any]) -> str:
    """Extract the narrative summary from a validated LLM response dict.

    Args:
        response: Dict with ``entries`` list and ``summary`` string.

    Returns:
        The summary string, stripped of leading/trailing whitespace.
    """
    return str(response["summary"]).strip()
