# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

from repogerbil.llm.schema import build_schema, compose_message, extract_body, extract_changes


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
    assert "body" in schema["required"]
    assert "changes" in schema["required"]


def test_compose_message_single_entry() -> None:
    response = {
        "entries": [
            {"verb": "instantiate", "scope": "core", "description": "base type definitions introduced"}
        ],
        "body": "Added the foundational type layer.",
        "changes": [{"file": "src/core/api.py", "description": "introduce base types"}],
    }
    msg = compose_message(response)
    assert msg == "instantiate(core): base type definitions introduced"


def test_compose_message_multi_entry() -> None:
    response = {
        "entries": [
            {"verb": "instantiate", "scope": "core", "description": "primary api built"},
            {"verb": "qualify", "scope": "primitives", "description": "first unit tests"},
        ],
        "body": "Expanded the api surface and added tests.",
        "changes": [{"file": "src/core/api.py", "description": "build api"}],
    }
    msg = compose_message(response)
    lines = msg.splitlines()
    assert lines[0] == "instantiate(core): primary api built"
    assert lines[1] == "qualify(primitives): first unit tests"
    assert len(lines) == 2
    assert "Expanded the api surface" not in msg


def test_compose_message_excludes_body() -> None:
    response = {
        "entries": [{"verb": "baseline", "scope": "deps", "description": "bump ruff"}],
        "body": "Updated ruff to latest version.",
        "changes": [{"file": "pyproject.toml", "description": "bump ruff version"}],
    }
    msg = compose_message(response)
    assert msg == "baseline(deps): bump ruff"
    assert "Updated ruff" not in msg


def test_compose_message_omits_empty_scope() -> None:
    response = {
        "entries": [{"verb": "docs", "scope": "", "description": "add readme"}],
        "body": "Added readme.",
        "changes": [{"file": "README.md", "description": "add project readme"}],
    }
    msg = compose_message(response)
    assert msg == "docs: add readme"


def test_compose_message_omits_missing_scope() -> None:
    response = {
        "entries": [{"verb": "test", "description": "add coverage for parser"}],
        "body": "Added parser tests.",
        "changes": [{"file": "tests/test_parser.py", "description": "add parser coverage"}],
    }
    msg = compose_message(response)
    assert msg == "test: add coverage for parser"


def test_extract_body_strips_whitespace() -> None:
    response = {
        "entries": [{"verb": "baseline", "scope": "deps", "description": "bump ruff"}],
        "body": "  Updated ruff.  ",
        "changes": [{"file": "pyproject.toml", "description": "bump ruff"}],
    }
    body = extract_body(response)
    assert body == "Updated ruff."


def test_extract_body_returns_content() -> None:
    response = {
        "entries": [{"verb": "instantiate", "scope": "core", "description": "init"}],
        "body": "The core module now initialises all type definitions.",
        "changes": [{"file": "src/core/__init__.py", "description": "init module"}],
    }
    assert extract_body(response) == "The core module now initialises all type definitions."


def test_extract_changes_returns_list() -> None:
    response = {
        "entries": [{"verb": "feat", "scope": "auth", "description": "add login"}],
        "body": "Login is now supported.",
        "changes": [
            {"file": "src/auth.py", "description": "implement login handler"},
            {"file": "tests/test_auth.py", "description": "add login tests"},
        ],
    }
    changes = extract_changes(response)
    assert len(changes) == 2
    assert changes[0]["file"] == "src/auth.py"
    assert changes[1]["file"] == "tests/test_auth.py"


def test_extract_changes_returns_copy() -> None:
    original = [{"file": "src/x.py", "description": "do something"}]
    response = {
        "entries": [{"verb": "feat", "scope": "x", "description": "add x"}],
        "body": "X is added.",
        "changes": original,
    }
    result = extract_changes(response)
    result.append({"file": "extra.py", "description": "extra"})
    assert len(extract_changes(response)) == 1  # original unchanged
