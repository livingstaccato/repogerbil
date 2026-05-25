# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git operation helpers for multi-repo snapshot — repo init, tree ops, commit creation."""

from __future__ import annotations

import contextlib
from datetime import date
import os
from pathlib import Path
import tempfile

from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git
from repogerbil.core.tree_filter import _cleanup_index_files, filter_tree


def _init_dest_repo(
    dest_path: Path,
    source_repos: dict[str, Path],
    *,
    author_name: str | None = None,
    author_email: str | None = None,
) -> None:
    """Initialize the destination repo and add source remotes.

    When ``author_name`` and ``author_email`` are both ``None`` the destination
    repo inherits the user's global git identity — matching the behavior of the
    single-snapshot path. When either is set, both must be set so the resulting
    commits have a complete identity.
    """
    dest_path.mkdir(parents=True, exist_ok=True)
    _run_git(dest_path, "init")
    if author_email is not None and author_name is not None:
        _run_git(dest_path, "config", "user.email", author_email)
        _run_git(dest_path, "config", "user.name", author_name)

    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        source_uri = path.resolve().as_uri()
        _run_git(dest_path, "remote", "add", f"source-{name}", source_uri)
        with contextlib.suppress(GitCommandError):
            _run_git(dest_path, "fetch", f"source-{name}", "--tags", timeout=120)


def _commit_tree(dest_path: Path, tree_sha: str, message: str, timestamp: str) -> str:
    """Create a commit on the tree with the given timestamp. Returns the commit hash.

    Raises:
        GitCommandError: If ``git commit-tree`` or the subsequent ``update-ref`` fails.
    """
    cmd = ["commit-tree", tree_sha, "-m", message]

    try:
        head = _run_git(dest_path, "rev-parse", "--verify", "HEAD", timeout=5).strip()
    except GitCommandError:
        head = ""
    if head:
        cmd.extend(["-p", head])

    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = timestamp
    env["GIT_COMMITTER_DATE"] = timestamp

    new_commit = _run_git(dest_path, *cmd, timeout=30, env=env).strip()
    if not new_commit:  # pragma: no cover — _run_git already raises on failure
        msg = "git commit-tree produced no output"
        raise GitCommandError(msg)
    _run_git(dest_path, "update-ref", "refs/heads/main", new_commit)
    return new_commit


def _get_tree_at_date(dest_path: Path, remote_name: str, day: date) -> str | None:
    """Get the tree SHA for a repo's state at end of a given day."""
    date_str = day.isoformat()
    try:
        output = _run_git(
            dest_path,
            "log",
            f"--until={date_str}T23:59:59",
            "--format=%H",
            "-1",
            f"--remotes=source-{remote_name}",
            timeout=10,
        )
        commit_hash = output.strip()
        if not commit_hash:  # pragma: no cover — day comes from same repo's history
            return None
        tree_sha = _run_git(dest_path, "rev-parse", f"{commit_hash}^{{tree}}", timeout=10).strip()
        return tree_sha
    except GitCommandError:  # pragma: no cover — fetched objects are always resolvable
        return None


def _build_merged_tree(dest_path: Path, repo_trees: dict[str, str]) -> str:
    """Build a combined tree with each repo as a subdirectory.

    Uses a unique temporary index file (``mkstemp``) so the real index and
    working tree are untouched, and so concurrent callers never collide on a
    deterministic name. The temp index AND any sibling ``.lock`` file are
    cleaned up via the shared ``_cleanup_index_files`` helper — if git is
    interrupted mid-write it can leave an orphan lock that
    ``NamedTemporaryFile(delete=True)`` would otherwise miss.

    Raises:
        GitCommandError: If any underlying read-tree/write-tree call fails.
    """
    fd, tmp_name = tempfile.mkstemp(dir=str(dest_path / ".git"), prefix="multi-snap-idx-", suffix=".idx")
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        env = {**os.environ, "GIT_INDEX_FILE": tmp_name}

        _run_git(dest_path, "read-tree", "--empty", timeout=10, env=env)

        for name, tree_sha in sorted(repo_trees.items()):
            _run_git(dest_path, "read-tree", f"--prefix={name}/", tree_sha, timeout=10, env=env)

        tree_sha = _run_git(dest_path, "write-tree", timeout=10, env=env).strip()
    finally:
        _cleanup_index_files(tmp_path)

    if not tree_sha:  # pragma: no cover — _run_git already raises on failure
        msg = "git write-tree produced no output"
        raise GitCommandError(msg)
    return tree_sha


def _collect_repo_trees_for_day(
    dest_path: Path,
    source_repos: dict[str, Path],
    day: date,
    repo_first_dates: dict[str, date],
    repos_included: set[str],
    *,
    exclude_paths: list[str] | None = None,
) -> dict[str, str]:
    """Collect tree SHAs for all repos that should appear on this day."""
    repo_trees: dict[str, str] = {}
    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        first_date = repo_first_dates.get(name)
        if first_date is None or day < first_date:
            continue
        tree_sha = _get_tree_at_date(dest_path, name, day)
        if tree_sha:  # pragma: no branch — tree always exists for fetched commits
            tree_sha = filter_tree(dest_path, tree_sha, exclude_paths)
            repo_trees[name] = tree_sha
            repos_included.add(name)
    return repo_trees
