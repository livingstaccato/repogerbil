# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git operation helpers for multi-repo snapshot — repo init, tree ops, commit creation."""

from __future__ import annotations

import contextlib
from datetime import date
import os
from pathlib import Path
import subprocess
import tempfile

from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git
from repogerbil.core.tree_filter import filter_tree


def _init_dest_repo(dest_path: Path, source_repos: dict[str, Path]) -> None:
    """Initialize the destination repo and add source remotes."""
    dest_path.mkdir(parents=True, exist_ok=True)
    _run_git(dest_path, "init")
    _run_git(dest_path, "config", "user.email", "repogerbil@localhost")
    _run_git(dest_path, "config", "user.name", "repogerbil")

    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        source_uri = path.resolve().as_uri()
        _run_git(dest_path, "remote", "add", f"source-{name}", source_uri)
        with contextlib.suppress(GitCommandError):
            _run_git(dest_path, "fetch", f"source-{name}", "--tags", timeout=120)


def _commit_tree(dest_path: Path, tree_sha: str, message: str, timestamp: str) -> str:
    """Create a commit on the tree with the given timestamp. Returns the commit hash."""
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

    result = subprocess.run(  # noqa: S603
        ["git", *cmd],  # noqa: S607
        cwd=str(dest_path),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    new_commit = result.stdout.strip()
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
    """Build a combined tree with each repo as a subdirectory."""
    with tempfile.NamedTemporaryFile(prefix="multi-snap-idx-", delete=False) as tmp:
        index_file = tmp.name

    try:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = index_file

        subprocess.run(
            ["git", "read-tree", "--empty"],  # noqa: S607
            cwd=str(dest_path),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        for name, tree_sha in sorted(repo_trees.items()):
            subprocess.run(  # noqa: S603
                ["git", "read-tree", f"--prefix={name}/", tree_sha],  # noqa: S607
                cwd=str(dest_path),
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )

        result = subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=str(dest_path),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        return result.stdout.strip()
    finally:
        Path(index_file).unlink(missing_ok=True)


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
