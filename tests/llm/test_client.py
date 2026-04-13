# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any

import pytest

from repogerbil.llm.client import FakeOllamaClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ollama_responses"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


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
