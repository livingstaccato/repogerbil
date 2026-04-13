# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path
from typing import Any

import pytest

from repogerbil.llm.client import FakeOllamaClient
from repogerbil.llm.generator import MessageGenerator, RefinementError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ollama_responses"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())  # type: ignore[no-any-return]


def _make_generator(responses: list[dict[str, Any]]) -> MessageGenerator:
    client = FakeOllamaClient(responses)
    return MessageGenerator(client=client, model="gemma4")


def test_generate_returns_generated_message() -> None:
    from repogerbil.llm.generator import GeneratedMessage

    gen = _make_generator([_load("valid_single.json")])
    result = gen.generate(
        date_str="2026-04-07",
        files=["src/core/api.py"],
        commit_count=1,
        original_subjects=["feat: add api"],
    )
    assert isinstance(result, GeneratedMessage)
    assert len(result.message) > 10
    assert len(result.summary) > 10


def test_generate_single_entry_format() -> None:
    gen = _make_generator([_load("valid_single.json")])
    result = gen.generate("2026-04-07", ["src/core/api.py"], 1, [])
    first_line = result.message.splitlines()[0]
    assert first_line == "instantiate(core): base type definitions introduced"


def test_generate_single_entry_summary_not_in_message() -> None:
    gen = _make_generator([_load("valid_single.json")])
    result = gen.generate("2026-04-07", ["src/core/api.py"], 1, [])
    assert result.summary != ""
    assert result.summary not in result.message


def test_generate_multi_entry_format() -> None:
    gen = _make_generator([_load("valid_multi.json")])
    result = gen.generate("2026-04-08", ["src/core/api.py", "tests/test_api.py"], 2, [])
    lines = result.message.splitlines()
    assert lines[0] == "instantiate(core-api): primary api module built over the type layer"
    assert lines[1] == "qualify(primitives): first unit tests for conversions and equality"
    assert len(lines) == 2


def test_generate_raises_on_invalid_verb() -> None:
    bad_response = {
        "entries": [{"verb": "notaverb", "scope": "core", "description": "something"}],
        "summary": "Summary text here that is long enough to pass validation.",
    }
    gen = _make_generator([bad_response])
    with pytest.raises(RefinementError, match="invalid verb"):
        gen.generate("2026-04-07", ["src/x.py"], 1, [])


def test_generate_raises_on_missing_entries() -> None:
    bad_response: dict[str, Any] = {"summary": "No entries here at all."}
    gen = _make_generator([bad_response])
    with pytest.raises(RefinementError, match="missing required fields"):
        gen.generate("2026-04-07", ["src/x.py"], 1, [])


def test_prompt_version_accessible() -> None:
    from repogerbil.llm.prompt import PROMPT_VERSION

    gen = _make_generator([])
    assert gen.prompt_version == PROMPT_VERSION
