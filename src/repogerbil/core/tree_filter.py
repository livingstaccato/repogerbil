# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tree filtering utilities — shared by snapshot and multi_snapshot."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile


def filter_tree(dest_path: Path, tree_sha: str, exclude_paths: list[str] | None) -> str:
    """Return a new tree SHA with files matching any exclude regex removed.

    Uses a temporary index so the real index and working tree are untouched.
    Returns the original ``tree_sha`` unchanged when ``exclude_paths`` is empty.

    Args:
        dest_path: Repository where the tree object lives.
        tree_sha: SHA of the tree to filter.
        exclude_paths: Regex patterns to match against file paths (via re.search).
                      E.g. ["^\\.claude(/|$)", ".*\\.lock$"].

    Returns:
        SHA of the filtered tree, or the original SHA if nothing to exclude.
    """
    if not exclude_paths:
        return tree_sha

    compiled = [re.compile(p) for p in exclude_paths]

    with tempfile.NamedTemporaryFile(dir=str(dest_path / ".git"), delete=True) as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": tmp.name}
        subprocess.run(  # noqa: S603
            ["git", "read-tree", tree_sha],  # noqa: S607
            cwd=str(dest_path),
            env=env,
            capture_output=True,
            check=True,
        )
        ls = subprocess.run(
            ["git", "ls-files"],  # noqa: S607
            cwd=str(dest_path),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        to_remove = [f for f in ls.stdout.splitlines() if f and any(pat.search(f) for pat in compiled)]
        for f in to_remove:
            subprocess.run(  # noqa: S603
                ["git", "rm", "--cached", "--quiet", f],  # noqa: S607
                cwd=str(dest_path),
                env=env,
                capture_output=True,
            )
        result = subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=str(dest_path),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    return result.stdout.strip()


def exclude_files(files: set[str], exclude_paths: list[str] | None) -> set[str]:
    """Remove files whose path matches any of the exclude regex patterns.

    Args:
        files: Set of file paths to filter.
        exclude_paths: Regex patterns to match against file paths (via re.search).
                      E.g. ["^\\.claude(/|$)", ".*\\.lock$"].

    Returns:
        Filtered set with matched paths removed.
    """
    if not exclude_paths:
        return files
    compiled = [re.compile(p) for p in exclude_paths]
    return {f for f in files if not any(pat.search(f) for pat in compiled)}
