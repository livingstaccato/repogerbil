# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

from repogerbil.llm.schema import build_schema, compose_message


def test_build_schema_populates_verb_enum() -> None:
    verbs = ["baseline", "instantiate", "qualify"]
    schema = build_schema(verbs)
    items = schema["properties"]["entries"]["items"]
    assert items["properties"]["verb"]["enum"] == sorted(verbs)


def test_build_schema_does_not_mutate_input() -> None:
    verbs = ["instantiate", "qualify"]
    build_schema(verbs)
    assert verbs == ["instantiate", "qualify"]


def test_build_schema_required_fields_present() -> None:
    schema = build_schema(["instantiate"])
    assert "entries" in schema["required"]
    assert "summary" in schema["required"]


def test_compose_message_single_entry() -> None:
    response = {
        "entries": [
            {"verb": "instantiate", "scope": "core", "description": "base type definitions introduced"}
        ],
        "summary": "Added the foundational type layer.",
    }
    msg = compose_message(response)
    assert msg.startswith("instantiate(core): base type definitions introduced")
    assert "\n\nAdded the foundational type layer." in msg


def test_compose_message_multi_entry() -> None:
    response = {
        "entries": [
            {"verb": "instantiate", "scope": "core", "description": "primary api built"},
            {"verb": "qualify", "scope": "primitives", "description": "first unit tests"},
        ],
        "summary": "Expanded the api surface and added tests.",
    }
    msg = compose_message(response)
    lines = msg.splitlines()
    assert lines[0] == "instantiate(core): primary api built"
    assert lines[1] == "qualify(primitives): first unit tests"
    assert lines[2] == ""
    assert "Expanded the api surface" in msg


def test_compose_message_strips_summary_whitespace() -> None:
    response = {
        "entries": [{"verb": "baseline", "scope": "deps", "description": "bump ruff"}],
        "summary": "  Updated ruff.  ",
    }
    msg = compose_message(response)
    assert msg.endswith("Updated ruff.")
