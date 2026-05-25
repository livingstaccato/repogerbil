# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for Ollama LLM clients — Protocol conformance, fake, and HTTP."""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch
import urllib.error

import pytest

from repogerbil.llm.client import FakeOllamaClient, HTTPOllamaClient, OllamaClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ollama_responses"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# FakeOllamaClient
# ---------------------------------------------------------------------------


def test_fake_client_returns_responses_in_order() -> None:
    r1 = _load("valid_single.json")
    r2 = _load("valid_multi.json")
    client = FakeOllamaClient([r1, r2])

    out1 = client.generate("p1", {}, "gemma4")
    out2 = client.generate("p2", {}, "gemma4")

    assert out1 == r1
    assert out2 == r2


def test_fake_client_raises_when_exhausted() -> None:
    client = FakeOllamaClient([_load("valid_single.json")])
    client.generate("p1", {}, "gemma4")

    with pytest.raises(ValueError, match="ran out of responses"):
        client.generate("p2", {}, "gemma4")


def test_fake_client_accepts_kwargs() -> None:
    r = _load("valid_single.json")
    client = FakeOllamaClient([r])
    out = client.generate("prompt", {"type": "object"}, "gemma4", temperature=0.0, timeout=30.0)
    assert out == r


def test_fixture_valid_single_parses() -> None:
    r = _load("valid_single.json")
    assert "entries" in r
    assert "body" in r
    assert "changes" in r
    entries = r["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 1
    first = entries[0]
    assert isinstance(first, dict)
    assert all(k in first for k in ("verb", "scope", "description"))


def test_fixture_valid_multi_parses() -> None:
    r = _load("valid_multi.json")
    entries = r["entries"]
    assert isinstance(entries, list)
    assert len(entries) == 2


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_http_client_implements_ollama_client_protocol() -> None:
    """``runtime_checkable`` Protocol — both production and fake implement it."""
    assert isinstance(HTTPOllamaClient("http://localhost:11434"), OllamaClient)
    assert isinstance(FakeOllamaClient([]), OllamaClient)


def test_ollama_client_protocol_stub_body_is_executable() -> None:
    """Execute the Protocol method stub itself so its body line is covered."""
    # Calling the Protocol's unbound method runs the ``...`` body (returns None).
    # We pass a concrete implementation as ``self`` solely to satisfy the
    # signature; we are not invoking the implementation's body.
    result = OllamaClient.generate(FakeOllamaClient([]), "p", {}, "m")
    assert result is None


# ---------------------------------------------------------------------------
# HTTPOllamaClient — request construction & response decoding
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal urlopen-style response context manager returning preset bytes."""

    def __init__(self, body: bytes) -> None:
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@contextmanager
def _patched_urlopen(body: bytes, captured: dict[str, Any]):  # type: ignore[no-untyped-def]
    """Patch urllib.request.urlopen, capturing the Request object and timeout."""

    def fake_urlopen(req: Any, timeout: float | None = None) -> _FakeResponse:
        captured["request"] = req
        captured["timeout"] = timeout
        return _FakeResponse(body)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        yield


def _ollama_envelope(response_obj: dict[str, Any]) -> bytes:
    """Build an Ollama API response envelope wrapping a structured JSON object."""
    return json.dumps({"response": json.dumps(response_obj)}).encode()


def test_http_client_strips_trailing_slash_from_base_url() -> None:
    client = HTTPOllamaClient("http://localhost:11434/")
    assert client._base_url == "http://localhost:11434"


def test_http_client_constructs_generate_url_and_post() -> None:
    expected = _load("valid_single.json")
    captured: dict[str, Any] = {}

    with _patched_urlopen(_ollama_envelope(expected), captured):
        client = HTTPOllamaClient("http://localhost:11434")
        out = client.generate(
            prompt="hello world",
            schema={"type": "object"},
            model="gemma4",
            temperature=0.0,
            timeout=42.0,
        )

    assert out == expected
    req = captured["request"]
    assert req.full_url == "http://localhost:11434/api/generate"
    assert req.get_method() == "POST"
    assert req.headers.get("Content-type") == "application/json"
    assert captured["timeout"] == 42.0


def test_http_client_serializes_expected_payload_fields() -> None:
    expected = _load("valid_multi.json")
    captured: dict[str, Any] = {}
    schema = {"type": "object", "properties": {"entries": {"type": "array"}}}

    with _patched_urlopen(_ollama_envelope(expected), captured):
        client = HTTPOllamaClient("http://localhost:11434")
        out = client.generate(
            prompt="my prompt",
            schema=schema,
            model="gemma4",
            temperature=0.7,
        )

    assert out == expected
    payload = json.loads(captured["request"].data.decode())
    assert payload["model"] == "gemma4"
    assert payload["prompt"] == "my prompt"
    assert payload["format"] == schema
    assert payload["stream"] is False
    assert payload["options"] == {"temperature": 0.7}


def test_http_client_decodes_structured_json_response() -> None:
    """The Ollama ``response`` field is a JSON-encoded string; verify it parses."""
    expected = {"entries": [{"verb": "fix", "scope": "x", "description": "y"}]}
    captured: dict[str, Any] = {}

    with _patched_urlopen(_ollama_envelope(expected), captured):
        client = HTTPOllamaClient("http://localhost:11434")
        out = client.generate("p", {}, "gemma4")

    assert out == expected


def test_http_client_propagates_url_error() -> None:
    """A URLError from the transport should propagate (subclass of OSError)."""

    def boom(req: Any, timeout: float | None = None) -> _FakeResponse:
        raise urllib.error.URLError("connection refused")

    with patch("urllib.request.urlopen", side_effect=boom):
        client = HTTPOllamaClient("http://localhost:11434")
        with pytest.raises(urllib.error.URLError, match="connection refused"):
            client.generate("p", {}, "gemma4")


def test_http_client_propagates_timeout_error() -> None:
    """A TimeoutError from the transport should propagate to the caller."""

    def slow(req: Any, timeout: float | None = None) -> _FakeResponse:
        raise TimeoutError("request timed out")

    with patch("urllib.request.urlopen", side_effect=slow):
        client = HTTPOllamaClient("http://localhost:11434")
        with pytest.raises(TimeoutError, match="timed out"):
            client.generate("p", {}, "gemma4", timeout=0.001)


def test_http_client_propagates_http_error() -> None:
    """An HTTPError (4xx/5xx from Ollama) should propagate unchanged.

    Current ``HTTPOllamaClient.generate`` does not catch transport errors —
    this test pins that contract so a future "wrap as LlmRunnerError" change
    is an explicit decision rather than an accident.
    """
    http_error = urllib.error.HTTPError(
        url="http://localhost:11434/api/generate",
        code=500,
        msg="Internal Server Error",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )

    def boom(req: Any, timeout: float | None = None) -> _FakeResponse:
        raise http_error

    with patch("urllib.request.urlopen", side_effect=boom):
        client = HTTPOllamaClient("http://localhost:11434")
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            client.generate("p", {}, "gemma4")
        assert exc_info.value.code == 500


def test_http_client_raises_on_invalid_json_response_body() -> None:
    """A non-JSON outer envelope should raise ``json.JSONDecodeError`` (ValueError subclass)."""
    captured: dict[str, Any] = {}

    with _patched_urlopen(b"not json at all", captured), pytest.raises(ValueError):
        client = HTTPOllamaClient("http://localhost:11434")
        client.generate("p", {}, "gemma4")


def test_http_client_raises_on_invalid_json_in_response_field() -> None:
    """The inner ``response`` field must be JSON-parseable."""
    body = json.dumps({"response": "this is not json"}).encode()
    captured: dict[str, Any] = {}

    with _patched_urlopen(body, captured), pytest.raises(ValueError):
        client = HTTPOllamaClient("http://localhost:11434")
        client.generate("p", {}, "gemma4")
