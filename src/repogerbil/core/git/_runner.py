# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Low-level git subprocess runner and shortstat parser."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess

from repogerbil.core.errors import GitCommandError, NotAGitRepositoryError

_SHORTSTAT_FILE_RE = re.compile(r"(\d+)\s+file")
_SHORTSTAT_INS_RE = re.compile(r"(\d+)\s+insertion")
_SHORTSTAT_DEL_RE = re.compile(r"(\d+)\s+deletion")


def _run_git(
    repo_path: str | Path,
    *args: str,
    timeout: int = 60,
    env: dict[str, str] | None = None,
) -> str:
    """Run a git command and return stdout.

    Args:
        env: Optional environment override. When provided, passed as-is to
             subprocess (caller is responsible for including PATH etc.).

    Raises:
        NotAGitRepositoryError: If the path is not a git repository.
        GitCommandError: If the git command fails.
    """
    result = subprocess.run(  # noqa: S603 — git is a trusted binary
        ["git", *args],  # noqa: S607 — partial path is intentional
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            raise NotAGitRepositoryError(repo_path)
        raise GitCommandError(
            f"Git command failed: git {' '.join(args)}\n{stderr}",
            returncode=result.returncode,
            stderr=stderr,
        )

    return result.stdout


def parse_shortstat(stat_line: str) -> dict[str, int]:
    """Parse a git diff --shortstat line into files/insertions/deletions."""
    stats: dict[str, int] = {"files_changed": 0, "insertions": 0, "deletions": 0}
    m = _SHORTSTAT_FILE_RE.search(stat_line)
    if m:
        stats["files_changed"] = int(m.group(1))
    m = _SHORTSTAT_INS_RE.search(stat_line)
    if m:
        stats["insertions"] = int(m.group(1))
    m = _SHORTSTAT_DEL_RE.search(stat_line)
    if m:
        stats["deletions"] = int(m.group(1))
    return stats
