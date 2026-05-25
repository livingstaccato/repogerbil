# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Commit consolidation — distill daily commits with changelog-based messages.

.. warning::
    **This module writes to the SOURCE repository.** ``consolidate()`` creates
    branches and tags directly on ``repo_path`` (the source repo) — it is *not*
    a read-only operation. Specifically it will:

    * create a backup branch (``<source>-backup-<timestamp>``) on the source repo
    * create a backup tag (``repogerbil/pre-distill/<timestamp>``) on the source repo
    * create / check out a new target branch on the source repo
    * cherry-pick and commit onto that target branch

    This predates the read-only ``read-tree`` approach implemented in
    :mod:`repogerbil.core.snapshot`. **For new code, prefer ``gerbil snapshot``**
    (and the ``snapshot`` / ``multi-snapshot`` CLI commands) — those operate on
    the source repo strictly read-only and emit a fresh, distilled destination
    repository instead of mutating the source.

    ``consolidate()`` is retained because the ``gerbil distill`` CLI command
    still routes through it and external callers may rely on its behavior. New
    callers should treat invocation of this function as an explicit opt-in to a
    destructive operation on the source repository.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.git import _run_git


@dataclass(frozen=True)
class ConsolidationResult:
    """Result of a consolidation operation."""

    target_branch: str
    backup_branch: str
    backup_tag: str
    groups_consolidated: int
    commits_consolidated: int


def consolidate(
    repo_path: Path,
    groups: list[TimeGroup],
    target_branch: str = "repogerbil-consolidated",
    source_branch: str = "main",
    changelog_messages: dict[str, str] | None = None,
    preserve_timestamps: bool = True,
    create_backup: bool = True,
    dry_run: bool = False,
) -> ConsolidationResult:
    """Consolidate commit groups into a new branch.

    Each TimeGroup becomes one commit on the target branch.
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_branch = f"{source_branch}-backup-{timestamp}"
    backup_tag = f"repogerbil/pre-distill/{timestamp}"
    total_commits = sum(len(g.commits) for g in groups)

    if dry_run:
        return ConsolidationResult(
            target_branch=target_branch,
            backup_branch=backup_branch,
            backup_tag=backup_tag,
            groups_consolidated=len(groups),
            commits_consolidated=total_commits,
        )

    original_branch = _run_git(repo_path, "symbolic-ref", "--short", "HEAD", timeout=10).strip()
    target_created = False
    if create_backup:
        _run_git(repo_path, "branch", backup_branch, source_branch)
        _run_git(repo_path, "tag", backup_tag, source_branch)

    try:
        # Find base: parent of first commit, or root if first commit
        first_hash = groups[0].commits[0].hash
        parent_check = _run_git(repo_path, "rev-list", "--parents", "-n", "1", first_hash, timeout=10).strip()
        parents = parent_check.split()

        if len(parents) > 1:
            base = parents[1]  # Parent hash
            _run_git(repo_path, "checkout", "-b", target_branch, base)
        else:
            # Root commit — create orphan branch
            _run_git(repo_path, "checkout", "--orphan", target_branch)
            _run_git(repo_path, "rm", "-rf", ".", timeout=10)
        target_created = True

        for group in groups:
            _consolidate_group(repo_path, group, changelog_messages, preserve_timestamps)
    except Exception:
        with contextlib.suppress(Exception):
            _run_git(repo_path, "cherry-pick", "--abort", timeout=10)
        with contextlib.suppress(Exception):
            _run_git(repo_path, "checkout", original_branch, timeout=10)
        if target_created:
            with contextlib.suppress(Exception):
                _run_git(repo_path, "branch", "-D", target_branch, timeout=10)
        raise
    else:
        _run_git(repo_path, "checkout", source_branch)

    return ConsolidationResult(
        target_branch=target_branch,
        backup_branch=backup_branch if create_backup else "",
        backup_tag=backup_tag if create_backup else "",
        groups_consolidated=len(groups),
        commits_consolidated=total_commits,
    )


def _consolidate_group(
    repo_path: Path,
    group: TimeGroup,
    changelog_messages: dict[str, str] | None,
    preserve_timestamps: bool,
) -> None:
    """Cherry-pick and distill a single group into one commit."""
    for commit in group.commits:
        parents = _run_git(
            repo_path,
            "rev-list",
            "--parents",
            "-n",
            "1",
            commit.hash,
            timeout=10,
        ).split()
        if len(parents) > 2:  # pragma: no cover — merge commit path, tested in integration
            _run_git(repo_path, "cherry-pick", "--no-commit", "-m", "1", commit.hash)
        else:
            _run_git(repo_path, "cherry-pick", "--no-commit", commit.hash)

    message = _build_commit_message(group, changelog_messages)

    # Build git commit command with optional timestamp flags
    if preserve_timestamps:
        ts = group.period_end.strftime("%Y-%m-%d %H:%M:%S")
        _run_git(
            repo_path,
            "-c",
            f"user.date={ts}",
            "commit",
            "-m",
            message,
            f"--date={ts}",
            timeout=30,
        )
    else:
        _run_git(repo_path, "commit", "-m", message, timeout=30)


def _build_commit_message(
    group: TimeGroup,
    changelog_messages: dict[str, str] | None,
) -> str:
    """Build commit message from changelog or auto-generate."""
    date_str = group.period_start.strftime("%Y-%m-%d")

    if changelog_messages and date_str in changelog_messages:
        return changelog_messages[date_str]

    subjects = [c.subject for c in group.commits]
    if len(subjects) == 1:
        return subjects[0]

    n = len(subjects)
    lines = [
        f"{subjects[0]}, and {n - 1} more change{'s' if n > 2 else ''}",
        "",
        f"Consolidates {n} commits from {date_str}:",
    ]
    for s in subjects:
        lines.append(f"- {s}")
    return "\n".join(lines)


def generate_consolidation_preview(groups: list[TimeGroup]) -> list[dict[str, Any]]:
    """Generate a preview of what consolidation would produce."""
    return [
        {
            "date": group.period_start.strftime("%Y-%m-%d"),
            "commit_count": len(group.commits),
            "files_affected": len(group.files_affected),
            "subjects": [c.subject for c in group.commits],
        }
        for group in groups
    ]
