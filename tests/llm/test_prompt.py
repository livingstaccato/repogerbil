# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

from repogerbil.llm.prompt import PROMPT_VERSION, build_prompt


def test_prompt_version_is_string() -> None:
    assert isinstance(PROMPT_VERSION, str)
    assert len(PROMPT_VERSION) > 0


def test_build_prompt_contains_verbs() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/core/api.py"],
        commit_count=2,
        original_subjects=["feat: add api"],
        allowed_verbs=["instantiate", "qualify"],
    )
    assert "instantiate" in prompt
    assert "qualify" in prompt


def test_build_prompt_contains_files() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/core/api.py", "tests/test_api.py"],
        commit_count=2,
        original_subjects=[],
        allowed_verbs=["instantiate"],
    )
    assert "src/core/api.py" in prompt
    assert "tests/test_api.py" in prompt


def test_build_prompt_contains_date_and_count() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=5,
        original_subjects=[],
        allowed_verbs=["baseline"],
    )
    assert "2026-04-07" in prompt
    assert "5" in prompt


def test_build_prompt_handles_empty_subjects() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=1,
        original_subjects=[],
        allowed_verbs=["baseline"],
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_build_prompt_contains_original_subjects() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=1,
        original_subjects=["feat: add x"],
        allowed_verbs=["instantiate"],
    )
    assert "feat: add x" in prompt
