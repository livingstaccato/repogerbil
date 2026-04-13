# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""MessageGenerator — orchestrates client + prompt + schema into a refined commit message."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from repogerbil.core.vocabulary import allowed_verbs as _allowed_verbs
from repogerbil.llm.client import OllamaClient
from repogerbil.llm.prompt import PROMPT_VERSION, build_prompt
from repogerbil.llm.schema import build_schema, compose_message, extract_body, extract_changes


class RefinementError(Exception):
    """Raised when the LLM returns invalid or unrecoverable output."""


@dataclass(frozen=True)
class GeneratedMessage:
    """Result of a single LLM refinement call.

    Attributes:
        message: Commit message headers only — one ``verb(scope): description``
                 line per entry. Suitable for use as a git commit message.
        body: Narrative paragraph explaining why the change exists. Stored in
              a sidecar file rather than in the commit message itself.
        changes: Per-file change descriptions — list of
                 ``{"file": str, "description": str}`` dicts. Stored in sidecar.
    """

    message: str
    body: str
    changes: list[dict[str, str]] = field(default_factory=list)


class MessageGenerator:
    """Generates refined commit messages using a local Ollama LLM.

    Holds the allowed-verb list and JSON schema as instance state so they
    are built once and reused across many ``generate()`` calls.
    """

    def __init__(
        self,
        client: OllamaClient,
        model: str = "gemma4",
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._verbs = _allowed_verbs()
        self._schema = build_schema(self._verbs)

    @property
    def prompt_version(self) -> str:
        """Current prompt template version (from ``llm.prompt.PROMPT_VERSION``)."""
        return PROMPT_VERSION

    def generate(
        self,
        date_str: str,
        files: list[str],
        commit_count: int,
        original_subjects: list[str],
        original_bodies: list[str] | None = None,
    ) -> GeneratedMessage:
        """Generate a refined commit message for a group of source commits.

        Args:
            date_str: YYYY-MM-DD string for the group's period start.
            files: Sorted union of file paths touched by all commits in the group.
            commit_count: Total number of source commits in the group.
            original_subjects: Raw source commit subjects (may be empty or noisy).
            original_bodies: Full commit message bodies from source (may be empty
                             strings for commits with no body). When provided, the
                             LLM uses them as source material to extract intent.

        Returns:
            ``GeneratedMessage`` with ``.message`` (header lines only, suitable
            for git commit), ``.body`` (narrative paragraph), and ``.changes``
            (per-file descriptions) for sidecar storage.

        Raises:
            RefinementError: If the LLM response fails validation.
        """
        prompt = build_prompt(
            date_str=date_str,
            files=files,
            commit_count=commit_count,
            original_subjects=original_subjects,
            allowed_verbs=self._verbs,
            original_bodies=original_bodies,
        )
        response = self._client.generate(
            prompt=prompt,
            schema=self._schema,
            model=self._model,
            temperature=self._temperature,
            timeout=self._timeout,
        )
        self._validate(response)
        return GeneratedMessage(
            message=compose_message(response),
            body=extract_body(response),
            changes=extract_changes(response),
        )

    def _validate(self, response: dict[str, Any]) -> None:
        """Validate LLM response structure and verb choices.

        Raises:
            RefinementError: If required fields are missing or verb is not in the allowed set.
        """
        missing = [k for k in ("entries", "body", "changes") if k not in response]
        if missing:
            msg = f"LLM response missing required fields: {missing}"
            raise RefinementError(msg)
        for entry in response["entries"]:
            verb = entry["verb"]
            if verb not in self._verbs:
                msg = f"LLM returned invalid verb '{verb}'; allowed: {self._verbs}"
                raise RefinementError(msg)
