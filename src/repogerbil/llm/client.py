# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Ollama LLM client — Protocol, deterministic fake, and HTTP implementations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OllamaClient(Protocol):
    """Protocol for Ollama LLM clients.

    Both ``FakeOllamaClient`` (for tests) and ``HTTPOllamaClient`` (for
    production) implement this interface.
    """

    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]: ...


class FakeOllamaClient:
    """Deterministic test client that returns preset responses in order.

    Usage::

        client = FakeOllamaClient([response_dict_1, response_dict_2])
        out = client.generate(...)  # returns response_dict_1
        out = client.generate(...)  # returns response_dict_2
    """

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self._index = 0

    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Return the next preset response; raise if all responses have been consumed."""
        if self._index >= len(self._responses):
            msg = f"FakeOllamaClient ran out of responses at call {self._index}"
            raise ValueError(msg)
        response = self._responses[self._index]
        self._index += 1
        return response


class HTTPOllamaClient:
    """Production Ollama HTTP client using stdlib ``urllib.request`` (no extra deps).

    Sends a ``POST /api/generate`` request with structured-output JSON schema
    constraint (``format`` field) and returns the parsed response object.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Call Ollama generate API with structured output schema.

        Args:
            prompt: The full prompt string.
            schema: JSON schema dict passed to Ollama's ``format`` field.
            model: Ollama model name (e.g. ``"gemma4"``).
            temperature: Sampling temperature (0.0 = deterministic).
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON object from Ollama's ``response`` field.

        Raises:
            OSError: If the Ollama server is unreachable.
            ValueError: If the response cannot be decoded as JSON.
        """
        import json
        import urllib.request

        payload = {
            "model": model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec: B310 — base_url is config-controlled, not user input
            body = json.loads(resp.read())
        return json.loads(body["response"])  # type: ignore[no-any-return]
