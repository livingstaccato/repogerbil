# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

from repogerbil.llm.prompt import PROMPT_VERSION, VERB_HINTS, WELL_FORMED_RE, build_prompt


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


def test_build_prompt_includes_original_bodies() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=1,
        original_subjects=["feat: add x"],
        allowed_verbs=["instantiate"],
        original_bodies=["feat: add x\n\nDetailed explanation of the change."],
    )
    assert "Detailed explanation" in prompt
    assert "Original commit messages" in prompt


def test_verb_hints_is_public_dict() -> None:
    assert isinstance(VERB_HINTS, dict)
    assert "feat" in VERB_HINTS
    assert "scaffold" in VERB_HINTS
    assert "harden" in VERB_HINTS


class TestWellFormedRe:
    def test_standard_verb_no_scope(self) -> None:
        assert WELL_FORMED_RE.match("feat: add login endpoint")

    def test_standard_verb_with_scope(self) -> None:
        assert WELL_FORMED_RE.match("fix(auth): handle missing token")

    def test_extended_verb_scaffold(self) -> None:
        assert WELL_FORMED_RE.match("scaffold(cli): create command skeleton")

    def test_extended_verb_harden(self) -> None:
        assert WELL_FORMED_RE.match("harden(core): add error boundary checks")

    def test_extended_verb_decouple(self) -> None:
        assert WELL_FORMED_RE.match("decouple(schema): extract validation logic")

    def test_all_verbs_match(self) -> None:
        for verb in VERB_HINTS:
            assert WELL_FORMED_RE.match(f"{verb}: do something"), f"{verb}: failed"

    def test_rejects_no_description(self) -> None:
        assert not WELL_FORMED_RE.match("feat: ")

    def test_rejects_unknown_verb(self) -> None:
        assert not WELL_FORMED_RE.match("update: change something")

    def test_rejects_plain_message(self) -> None:
        assert not WELL_FORMED_RE.match("add new login endpoint")

    def test_rejects_wip(self) -> None:
        assert not WELL_FORMED_RE.match("WIP: not done")


def test_build_prompt_skips_all_empty_bodies() -> None:
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=1,
        original_subjects=["lots of changes"],
        allowed_verbs=["instantiate"],
        original_bodies=["", "  "],
    )
    assert "Original commit messages" not in prompt
