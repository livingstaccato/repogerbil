# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Snapshot engine — create independent repo with distilled daily commits via git read-tree."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date as date_type
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import TYPE_CHECKING

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git
from repogerbil.core.multi_snapshot import _make_timestamp

if TYPE_CHECKING:
    from repogerbil.llm.generator import MessageGenerator


@dataclass(frozen=True)
class SnapshotResult:
    """Result of a snapshot operation."""

    dest_path: str
    groups_created: int
    commits_created: int
    groups_skipped: int = 0  # Duplicates removed during deduplication


def create_snapshot(
    source_path: Path,
    dest_path: Path,
    groups: list[TimeGroup],
    source_branch: str = "main",
    changelog_messages: dict[str, str] | None = None,
    preserve_timestamps: bool = True,
    commit_time: str | None = None,
    timezone: str | None = None,
    extra_sources: list[Path] | None = None,
    source_subdir: str | None = None,
    llm_generator: MessageGenerator | None = None,
    progress: bool = False,
) -> SnapshotResult:
    """Create an independent repo with one commit per TimeGroup.

    Uses git read-tree for fast, working-directory-free operations.
    Source repos are never written to — only the destination receives writes.

    Args:
        source_subdir: When set, filter primary source commits to this subdirectory
                      and use its tree state (for monorepo sources).
    """
    if dest_path.exists() and any(dest_path.iterdir()):
        msg = f"Destination already exists and is not empty: {dest_path}"
        raise RuntimeError(msg)

    remote_names = _init_and_fetch(dest_path, source_path, extra_sources)

    # Deduplicate groups by tree state BEFORE creating commits
    dedup_groups, groups_skipped = _deduplicate_groups(dest_path, groups, source_subdir)

    commits_created = _create_commits(
        dest_path,
        dedup_groups,
        changelog_messages,
        preserve_timestamps,
        commit_time,
        timezone,
        source_subdir,
        llm_generator,
        progress,
    )

    for rname in remote_names:
        with contextlib.suppress(GitCommandError):
            _run_git(dest_path, "remote", "remove", rname)

    _run_git(dest_path, "checkout", "main", timeout=30)

    return SnapshotResult(
        dest_path=str(dest_path),
        groups_created=len(groups),
        commits_created=commits_created,
        groups_skipped=groups_skipped,
    )


def _init_and_fetch(
    dest_path: Path,
    source_path: Path,
    extra_sources: list[Path] | None,
) -> list[str]:
    """Initialize destination repo and fetch all source remotes."""
    dest_path.mkdir(parents=True, exist_ok=True)
    _run_git(dest_path, "init")

    _fetch_source(dest_path, "source", source_path)
    remote_names = ["source"]
    for i, extra in enumerate(extra_sources or []):
        if extra.exists():  # pragma: no branch
            name = f"extra-{i}"
            _fetch_source(dest_path, name, extra)
            remote_names.append(name)
    return remote_names


def _deduplicate_groups(
    dest_path: Path,
    groups: list[TimeGroup],
    source_subdir: str | None = None,
) -> tuple[list[TimeGroup], int]:
    """Deduplicate groups by their tree state, keeping only unique code states.

    Returns tuple of (deduplicated_groups, number_skipped).

    Args:
        dest_path: Path to destination repo with all sources fetched.
        groups: Groups to deduplicate.
        source_subdir: Optional subdirectory for monorepo filtering.
    """
    seen_trees: set[str] = set()
    unique_groups: list[TimeGroup] = []
    skipped = 0

    for group in groups:
        if not group.commits:
            continue  # pragma: no cover — empty group

        last_commit = group.commits[-1]
        try:
            if source_subdir:
                # Try subdir first (for monorepo sources)
                tree_sha = _run_git(
                    dest_path, "rev-parse", f"{last_commit.hash}:{source_subdir}", timeout=10
                ).strip()
            else:
                # Full tree (for standalone repos)
                tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()
        except GitCommandError:
            # Fall back to full tree if subdir doesn't exist
            tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()

        # Skip if we've already seen this tree state
        if tree_sha in seen_trees:
            skipped += 1
            continue

        seen_trees.add(tree_sha)
        unique_groups.append(group)

    return unique_groups, skipped


def _create_commits(
    dest_path: Path,
    groups: list[TimeGroup],
    changelog_messages: dict[str, str] | None,
    preserve_timestamps: bool,
    commit_time: str | None,
    timezone: str | None,
    source_subdir: str | None = None,
    llm_generator: MessageGenerator | None = None,
    progress: bool = False,
) -> int:
    """Create one commit per TimeGroup in the destination repo.

    Args:
        source_subdir: When set, use the tree state of this subdirectory
                      within each commit (for monorepo sources).
    """
    commits_created = 0
    used_changelog_keys: set[str] = set()
    total = len(groups)
    width = len(str(total))

    for idx, group in enumerate(groups, 1):
        if not group.commits:
            continue  # pragma: no cover — empty group

        last_commit = group.commits[-1]
        try:
            if source_subdir:
                # Try subdir first (for monorepo sources)
                tree_sha = _run_git(
                    dest_path, "rev-parse", f"{last_commit.hash}:{source_subdir}", timeout=10
                ).strip()
            else:
                # Full tree (for standalone repos)
                tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()
        except GitCommandError:
            # Fall back to full tree if subdir doesn't exist
            tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()

        _run_git(dest_path, "read-tree", tree_sha)

        if llm_generator is not None:
            all_files: set[str] = set()
            for commit in group.commits:
                all_files.update(_get_files_for_commit(dest_path, commit.hash))
            message = llm_generator.generate(
                date_str=group.period_start.strftime("%Y-%m-%d"),
                files=sorted(all_files),
                commit_count=len(group.commits),
                original_subjects=[c.subject for c in group.commits],
            )
        else:
            message = _build_snapshot_message(group, changelog_messages, used_changelog_keys)
        date_str = _resolve_timestamp(group, commit_time, timezone)

        if progress:
            first_line = message.splitlines()[0][:72]
            ts = group.period_start.strftime("%Y-%m-%d %H:%M")
            print(f"[{idx:{width}}/{total}] {ts}  {first_line}", file=sys.stderr, flush=True)

        _commit_with_timestamp(dest_path, tree_sha, message, date_str, preserve_timestamps)
        commits_created += 1

    return commits_created


def _resolve_timestamp(
    group: TimeGroup,
    commit_time: str | None,
    timezone: str | None,
) -> str:
    """Resolve the timestamp for a commit."""
    if commit_time and timezone:
        day = date_type(group.period_start.year, group.period_start.month, group.period_start.day)
        return _make_timestamp(day, commit_time, timezone)
    return group.period_end.strftime("%Y-%m-%dT%H:%M:%S")


def _commit_with_timestamp(
    dest_path: Path,
    tree_sha: str,
    message: str,
    date_str: str,
    preserve: bool,
) -> None:
    """Create a commit-tree with optional timestamp override."""
    cmd = ["commit-tree", tree_sha, "-m", message]

    try:
        head = _run_git(dest_path, "rev-parse", "--verify", "HEAD", timeout=5).strip()
    except GitCommandError:
        head = ""
    if head:
        cmd.extend(["-p", head])

    if preserve:
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        result = subprocess.run(  # noqa: S603
            ["git", *cmd],  # noqa: S607
            cwd=str(dest_path),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )
        new_commit = result.stdout.strip()
    else:
        new_commit = _run_git(dest_path, *cmd, timeout=30).strip()

    _run_git(dest_path, "update-ref", "refs/heads/main", new_commit)


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


def _fetch_source(dest_path: Path, remote_name: str, source_path: Path) -> None:
    """Add a source repo as a remote and fetch all refs."""
    source_uri = source_path.resolve().as_uri()
    _run_git(dest_path, "remote", "add", remote_name, source_uri)
    subprocess.run(  # noqa: S603
        ["git", "fetch", remote_name, f"+refs/*:refs/fetch-{remote_name}/*"],  # noqa: S607
        cwd=str(dest_path),
        capture_output=True,
        timeout=300,
    )


_CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|refactor|chore|test|docs|ci|perf|build|style|release"
    r"|standardize|revert|Merge )(\(.*?\))?:?"
)


def _build_snapshot_message(
    group: TimeGroup,
    changelog_messages: dict[str, str] | None,
    used_keys: set[str] | None = None,
) -> str:
    """Build commit message from changelog or conventional commits only.

    For gap-based cadence, tracks which changelog keys have been used to avoid
    multiple same-day groups getting the same YAML message.
    """
    date_str = group.period_start.strftime("%Y-%m-%d")

    # Changelog is authoritative — use it directly if not already consumed
    if (
        changelog_messages
        and date_str in changelog_messages
        and (used_keys is None or date_str not in used_keys)
    ):
        if used_keys is not None:
            used_keys.add(date_str)
        return changelog_messages[date_str]

    # No changelog (or already used): only list conventional commits, suppress garbage
    n = len(group.commits)
    conventional = [c.subject for c in group.commits if _CONVENTIONAL_RE.match(c.subject)]

    if len(conventional) == 1:
        return conventional[0]

    if conventional:
        lines = [f"{date_str}: {n} commits", ""]
        for s in conventional:
            lines.append(f"- {s}")
        other = n - len(conventional)
        if other:  # pragma: no cover — test repos use conventional commits
            lines.append(f"- ({other} commits)")
        return "\n".join(lines)

    return f"{date_str}: {n} commits"
