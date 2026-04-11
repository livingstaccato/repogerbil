# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Snapshot engine — create independent repo with distilled daily commits via git read-tree."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git
from repogerbil.core.multi_snapshot import _make_timestamp


@dataclass(frozen=True)
class SnapshotResult:
    """Result of a snapshot operation."""

    dest_path: str
    groups_created: int
    commits_created: int


def create_snapshot(
    source_path: Path,
    dest_path: Path,
    groups: list[TimeGroup],
    source_branch: str = "main",
    changelog_messages: dict[str, str] | None = None,
    preserve_timestamps: bool = True,
    commit_time: str | None = None,
    timezone: str | None = None,
) -> SnapshotResult:
    """Create an independent repo with one commit per TimeGroup.

    Uses git read-tree for fast, working-directory-free operations.

    Args:
        source_path: Path to the source git repository.
        dest_path: Path for the new snapshot repository (must not exist or be empty).
        groups: TimeGroups from cadence grouping.
        source_branch: Branch to read from in the source repo.
        changelog_messages: Optional {YYYY-MM-DD: message} for commit messages.
        preserve_timestamps: Keep original author dates.
        commit_time: Optional HH:MM to override commit timestamp (e.g. "20:00").
        timezone: IANA timezone for commit_time (e.g. "America/Los_Angeles").

    Returns:
        SnapshotResult with path and counts.
    """
    if dest_path.exists() and any(dest_path.iterdir()):
        msg = f"Destination already exists and is not empty: {dest_path}"
        raise RuntimeError(msg)

    # Initialize destination repo
    dest_path.mkdir(parents=True, exist_ok=True)
    _run_git(dest_path, "init")
    _run_git(dest_path, "config", "user.email", "repogerbil@localhost")
    _run_git(dest_path, "config", "user.name", "repogerbil")

    # Add source as temporary remote and fetch all refs
    source_uri = source_path.resolve().as_uri()
    _run_git(dest_path, "remote", "add", "source", source_uri)
    _run_git(dest_path, "fetch", "source", "--tags", timeout=120)

    commits_created = 0
    for group in groups:
        if not group.commits:
            continue  # pragma: no cover — empty group

        last_commit = group.commits[-1]
        tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()

        # Read tree into index (no working directory I/O)
        _run_git(dest_path, "read-tree", tree_sha)

        message = _build_snapshot_message(group, changelog_messages)
        if commit_time and timezone:
            from datetime import date as date_type

            day = date_type(group.period_start.year, group.period_start.month, group.period_start.day)
            date_str = _make_timestamp(day, commit_time, timezone)
        else:
            date_str = group.period_end.strftime("%Y-%m-%dT%H:%M:%S")

        # Build commit command with timestamp
        cmd = ["commit-tree", tree_sha, "-m", message]

        # Parent: previous commit on main (if any — empty repo raises GitCommandError)
        try:
            head = _run_git(dest_path, "rev-parse", "--verify", "HEAD", timeout=5).strip()
        except GitCommandError:
            head = ""
        if head:
            cmd.extend(["-p", head])

        # Set timestamp via environment
        if preserve_timestamps:
            import os

            env = dict(os.environ)
            env["GIT_AUTHOR_DATE"] = date_str
            env["GIT_COMMITTER_DATE"] = date_str

            import subprocess

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

        # commit-tree always returns a hash; update-ref to advance main
        _run_git(dest_path, "update-ref", "refs/heads/main", new_commit)
        commits_created += 1

    # Cleanup: remove temporary remote
    _run_git(dest_path, "remote", "remove", "source")

    # Checkout main so working directory has files
    _run_git(dest_path, "checkout", "main", timeout=30)

    return SnapshotResult(
        dest_path=str(dest_path),
        groups_created=len(groups),
        commits_created=commits_created,
    )


def _build_snapshot_message(
    group: TimeGroup,
    changelog_messages: dict[str, str] | None,
) -> str:
    """Build commit message from changelog or auto-generate."""
    date_str = group.period_start.strftime("%Y-%m-%d")

    if changelog_messages and date_str in changelog_messages:
        return changelog_messages[date_str]

    n = len(group.commits)
    subjects = [c.subject for c in group.commits]

    if n == 1:
        return subjects[0]

    lines = [
        f"Daily distill: {date_str} ({n} commits)",
        "",
    ]
    for s in subjects:
        lines.append(f"- {s}")
    return "\n".join(lines)
