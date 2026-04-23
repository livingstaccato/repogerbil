# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Diff statistics computation."""

from __future__ import annotations

from pathlib import Path

from repogerbil.core.errors import GitCommandError

from ._runner import _run_git, parse_shortstat
from ._types import DiffStats


def _shortstat_with_parent_fallback(repo_path: str | Path, commit_hash: str) -> str:
    """Return shortstat text for a single commit.

    Tries ``HASH^..HASH`` first; if that fails (root commit has no parent)
    falls back to ``git diff-tree --shortstat --root HASH``, which works
    for both root and non-root commits and always produces a stat line when
    the commit has content.  Returns an empty string only when the commit
    contains no file changes (e.g. an empty commit created with
    ``--allow-empty``).
    """
    try:
        output = _run_git(repo_path, "diff", "--shortstat", f"{commit_hash}^..{commit_hash}", timeout=30)
    except GitCommandError:
        output = ""

    stat_line = output.strip()
    if not stat_line:
        # diff-tree --root works for both root and non-root commits; the
        # first line of its output is the commit hash — parse_shortstat's
        # regexes ignore that line automatically.
        output = _run_git(repo_path, "diff-tree", "--shortstat", "--root", commit_hash, timeout=30)
        stat_line = output.strip()
    return stat_line


def get_diff_stats(repo_path: str | Path, first_hash: str, last_hash: str) -> DiffStats:
    """Get aggregate diff stats between two commits.

    Uses ``first^..last`` to capture all changes in the range.  When
    ``first`` is the initial commit (no parent) git returns a non-zero exit
    code; in that case the function falls back to ``--root last``.
    When both hashes are identical, computes the single-commit diff so that
    one-commit-per-day resolutions report accurate file and line counts.
    """
    if first_hash == last_hash:
        stat_line = _shortstat_with_parent_fallback(repo_path, first_hash)
        if not stat_line:
            return DiffStats(commits=0, files_changed=0, insertions=0, deletions=0)
        parsed = parse_shortstat(stat_line)
        return DiffStats(commits=0, **parsed)

    try:
        output = _run_git(repo_path, "diff", "--shortstat", f"{first_hash}^..{last_hash}", timeout=30)
    except GitCommandError:
        output = ""

    stat_line = output.strip()
    if not stat_line:  # pragma: no branch — first-commit fallback
        output = _run_git(repo_path, "diff", "--shortstat", "--root", last_hash, timeout=30)
        stat_line = output.strip()
    if not stat_line:
        return DiffStats(commits=0, files_changed=0, insertions=0, deletions=0)
    parsed = parse_shortstat(stat_line)
    return DiffStats(commits=0, **parsed)
