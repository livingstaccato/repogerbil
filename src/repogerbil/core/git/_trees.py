# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tree resolution, ref-range commit collection, and deduplication."""

from __future__ import annotations

from pathlib import Path

from repogerbil.core.errors import GitCommandError

from ._runner import _run_git
from ._types import CommitInfo


def resolve_commit_trees(
    repo_path: str | Path,
    commits: list[CommitInfo],
    source_subdir: str | None = None,
) -> dict[str, str]:
    """Resolve tree SHA for each commit (monorepo subdir or full tree).

    Returns dict mapping commit hash → tree SHA.
    Falls back to full tree if subdir doesn't exist in commit.

    Args:
        repo_path: Path to git repository with all commits fetched.
        commits: List of commits to resolve trees for.
        source_subdir: Optional subdirectory for monorepo filtering.
    """
    tree_map: dict[str, str] = {}
    for commit in commits:
        try:
            if source_subdir:
                # Try subdir first (monorepo)
                tree_sha = _run_git(
                    repo_path, "rev-parse", f"{commit.hash}:{source_subdir}", timeout=10
                ).strip()
            else:
                # Full tree (standalone)
                tree_sha = _run_git(repo_path, "rev-parse", f"{commit.hash}^{{tree}}", timeout=10).strip()
        except GitCommandError:
            # Fall back to full tree if subdir doesn't exist
            tree_sha = _run_git(repo_path, "rev-parse", f"{commit.hash}^{{tree}}", timeout=10).strip()
        tree_map[commit.hash] = tree_sha
    return tree_map


def get_commits_for_range(
    repo_path: str | Path,
    from_ref: str,
    to_ref: str,
    include_files: bool = False,
) -> list[CommitInfo]:
    """Get commits in a ref range (exclusive of from_ref, inclusive of to_ref).

    Equivalent to ``git log from_ref..to_ref`` in oldest-first order.

    Args:
        repo_path: Path to the git repository.
        from_ref: Exclusive lower bound (tag, branch, or SHA).
        to_ref: Inclusive upper bound (tag, branch, or SHA).
        include_files: Attach per-commit file lists.
    """
    output = _run_git(
        repo_path,
        "log",
        "--no-merges",
        "--format=%H\t%as\t%at\t%s",
        f"{from_ref}..{to_ref}",
    )
    commits: list[CommitInfo] = []
    for line in output.strip().splitlines():
        parts = line.split("\t", 3)
        if len(parts) >= 3:
            commits.append(
                CommitInfo(
                    hash=parts[0],
                    date=parts[1],
                    subject=parts[3] if len(parts) > 3 else "",
                    timestamp=int(parts[2]),
                )
            )
    commits.reverse()
    if include_files and commits:
        commits = _attach_commit_files_from_range(repo_path, commits, from_ref, to_ref)
    return commits


def _attach_commit_files_from_range(
    repo_path: str | Path,
    commits: list[CommitInfo],
    from_ref: str,
    to_ref: str,
) -> list[CommitInfo]:
    """Attach per-commit file lists for a ref range.

    Uses a NUL-prefixed ``--format`` sentinel so hash lines are unambiguous
    regardless of hash length (SHA-1 vs SHA-256) and even when a file path
    happens to look like a hex digest.
    """
    output = _run_git(
        repo_path,
        "log",
        "--no-merges",
        "--format=%x00%H",
        "--name-only",
        f"{from_ref}..{to_ref}",
    )
    hash_files: dict[str, list[str]] = {}
    current_hash: str | None = None
    for line in output.splitlines():
        if line.startswith("\x00"):
            current_hash = line[1:].strip()
            hash_files[current_hash] = []
            continue
        if current_hash is None:
            continue
        stripped = line.strip()
        if stripped:
            hash_files[current_hash].append(stripped)
    return [
        CommitInfo(
            hash=c.hash,
            date=c.date,
            subject=c.subject,
            timestamp=c.timestamp,
            files=hash_files.get(c.hash, []),
        )
        for c in commits
    ]


def deduplicate_by_tree(
    commits: list[CommitInfo],
    tree_map: dict[str, str],
) -> list[CommitInfo]:
    """Deduplicate commits by tree SHA, keeping earliest of each unique state.

    Returns commits in chronological order with unique tree states only.

    Args:
        commits: List of commits (should be sorted chronologically).
        tree_map: Dict mapping commit hash → tree SHA.
    """
    # Map tree SHA → earliest commit with that state
    tree_to_commit: dict[str, CommitInfo] = {}
    for commit in commits:
        tree_sha = tree_map.get(commit.hash)
        if tree_sha and tree_sha not in tree_to_commit:
            tree_to_commit[tree_sha] = commit

    # Return unique commits in chronological order
    unique_commits = list(tree_to_commit.values())
    unique_commits.sort(key=lambda c: c.timestamp if c.timestamp else 0)
    return unique_commits
