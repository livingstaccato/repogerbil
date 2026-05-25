# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Smoke test for the shared ``git_repo`` fixture in :mod:`tests.conftest`.

This exists so the conftest helper code is covered by the test suite (the
project enforces 100% coverage). Real tests should adopt the fixture in a
follow-up; see the TODO in ``tests/conftest.py``.
"""

from __future__ import annotations

from pathlib import Path
import subprocess


def test_git_repo_fixture_yields_initialised_repo(git_repo: Path) -> None:
    """The fixture should produce a usable git working tree with our defaults."""
    assert git_repo.is_dir()
    assert (git_repo / ".git").is_dir()

    # Defaults set by the fixture must be readable from the local config.
    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert email == "test@example.com"

    gpgsign = subprocess.run(
        ["git", "config", "commit.gpgsign"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert gpgsign == "false"


def test_git_repo_fixture_supports_a_commit(git_repo: Path) -> None:
    """A bare commit should succeed using only the fixture's defaults."""
    (git_repo / "file.txt").write_text("hello\n")
    subprocess.run(["git", "add", "file.txt"], cwd=git_repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=git_repo,
        capture_output=True,
        check=True,
    )
    log = subprocess.run(
        ["git", "log", "--format=%s"],
        cwd=git_repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert log == "initial"
