# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for ecosystem snapshot helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from repogerbil.core.ecosystem_snapshot import _count_prefixed_commits


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
