# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for ecosystem snapshot helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from repogerbil.core import ecosystem_snapshot as ecosystem_snapshot_module
from repogerbil.core.ecosystem_snapshot import (
    _count_prefixed_commits,
    _known_prefixes,
    _line_has_known_prefix,
)
from repogerbil.core.vocabulary import PREFIX_TO_CATEGORY


def test_count_prefixed_commits_handles_nonzero_returncode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Git failures should be treated as zero prefixed commits."""

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stdout="")

    monkeypatch.setattr("repogerbil.core.ecosystem_snapshot.subprocess.run", fake_run)

    assert _count_prefixed_commits(tmp_path) == 0


def test_count_prefixed_commits_handles_exception(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Unexpected subprocess exceptions should also collapse to zero."""

    def fake_run(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("repogerbil.core.ecosystem_snapshot.subprocess.run", fake_run)

    assert _count_prefixed_commits(tmp_path) == 0


def test_known_prefixes_matches_vocabulary_keys() -> None:
    """The prefix set the counter uses must be derived from the vocabulary."""
    assert _known_prefixes() == frozenset(PREFIX_TO_CATEGORY.keys())


def test_line_has_known_prefix_accepts_known_prefix() -> None:
    """A subject like ``feat: …`` should match because ``feat`` is in the vocab."""
    prefixes = _known_prefixes()
    assert _line_has_known_prefix("feat: add widget", prefixes) is True
    # Case-insensitive on the prefix word.
    assert _line_has_known_prefix("FIX: typo", prefixes) is True


def test_line_has_known_prefix_handles_scoped_prefix() -> None:
    """Conventional scopes like ``feat(api): …`` should still be recognised."""
    prefixes = _known_prefixes()
    assert _line_has_known_prefix("feat(api): new endpoint", prefixes) is True


def test_line_has_known_prefix_rejects_unknown_or_unprefixed() -> None:
    """Lines without a known prefix or without any colon must not count."""
    prefixes = _known_prefixes()
    assert _line_has_known_prefix("totally-unknown: stuff", prefixes) is False
    assert _line_has_known_prefix("no colon at all here", prefixes) is False


def test_count_prefixed_commits_uses_vocabulary_for_new_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Injecting a new prefix into the vocabulary should make the counter pick it up.

    This pins the contract that ``_count_prefixed_commits`` reads from the
    vocabulary rather than from a frozen tuple of strings.
    """
    fake_subject = "newprefix: did a thing\n"

    def fake_run(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout=fake_subject)

    monkeypatch.setattr("repogerbil.core.ecosystem_snapshot.subprocess.run", fake_run)

    # Replace the vocab map referenced by the module with a copy that has the
    # new prefix; the module reads via ``PREFIX_TO_CATEGORY.keys()`` at call
    # time, so this must take effect for the very next call.
    extended = dict(PREFIX_TO_CATEGORY)
    extended["newprefix"] = "baseline"
    monkeypatch.setattr(ecosystem_snapshot_module, "PREFIX_TO_CATEGORY", extended)

    assert _count_prefixed_commits(tmp_path) == 1
