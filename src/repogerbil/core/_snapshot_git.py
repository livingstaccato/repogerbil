# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git helpers for snapshot — reading commit bodies and changed file lists."""

from __future__ import annotations

from pathlib import Path

from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git


def _get_commit_body(dest_path: Path, commit_hash: str) -> str:
    """Return the full commit message (subject + body) for a source commit.

    Args:
        dest_path: Destination repo with all sources already fetched.
        commit_hash: The commit hash to inspect.

    Returns:
        Full commit message, stripped. Returns ``""`` if the commit cannot be read.
    """
    try:
        return _run_git(dest_path, "log", "-1", "--format=%B", commit_hash, timeout=10).strip()
    except GitCommandError:
        return ""


def _get_files_for_commit(dest_path: Path, commit_hash: str) -> list[str]:
    """Return the list of files changed in a commit, resolved from the fetched repo.

    Args:
        dest_path: Destination repo with all sources already fetched.
        commit_hash: The commit hash to inspect.

    Returns:
        Sorted list of file paths changed in that commit.
        Returns an empty list if the commit cannot be inspected (e.g. initial commit).
    """
    try:
        output = _run_git(
            dest_path,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--no-renames",
            "--no-ext-diff",
            commit_hash,
            timeout=20,
        )
        return sorted(line.strip() for line in output.splitlines() if line.strip())
    except GitCommandError:
        return []
