# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tree filtering utilities — shared by snapshot and multi_snapshot."""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

# Batch size for ``git update-index --force-remove`` calls. Keeps argv length
# well under typical OS limits (Linux ~128 KB, macOS ~256 KB) even with very
# long repo-relative paths.
_REMOVE_BATCH_SIZE = 1000


def _cleanup_index_files(tmp_path: Path) -> None:
    """Remove an index temp file and its sibling ``.lock`` if either exists.

    ``git`` can leave an orphan ``<index>.lock`` if it is interrupted mid-write;
    ``NamedTemporaryFile(delete=True)`` would not clean that up because the
    lock lives at a different path. We suppress missing-file errors so this is
    safe to call from a ``finally`` block regardless of how far the operation
    got.
    """
    with contextlib.suppress(FileNotFoundError):
        tmp_path.unlink()
    with contextlib.suppress(FileNotFoundError):
        Path(f"{tmp_path}.lock").unlink()


def filter_tree(dest_path: Path, tree_sha: str, exclude_paths: list[str] | None) -> str:
    """Return a new tree SHA with files matching any exclude regex removed.

    Uses a temporary index (via ``mkstemp`` for a unique name) so the real
    index and working tree are untouched. The temp index AND any orphan
    ``.lock`` are cleaned up in a ``finally`` block. Returns the original
    ``tree_sha`` unchanged when ``exclude_paths`` is empty.

    Excluded files are removed in a single ``git update-index --force-remove``
    call per chunk of ``_REMOVE_BATCH_SIZE`` paths — orders of magnitude
    fewer subprocess spawns than the previous one-call-per-file approach.

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

    fd, tmp_name = tempfile.mkstemp(dir=str(dest_path / ".git"), prefix="filter-tree-idx-", suffix=".idx")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        env = {**os.environ, "GIT_INDEX_FILE": tmp_name}
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
        # Batch removals to dodge OS argv length limits on huge file lists.
        for start in range(0, len(to_remove), _REMOVE_BATCH_SIZE):
            chunk = to_remove[start : start + _REMOVE_BATCH_SIZE]
            subprocess.run(  # noqa: S603
                ["git", "update-index", "--force-remove", "--", *chunk],  # noqa: S607
                cwd=str(dest_path),
                env=env,
                capture_output=True,
                check=True,
            )
        result = subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=str(dest_path),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    finally:
        _cleanup_index_files(tmp_path)
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
