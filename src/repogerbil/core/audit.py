# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Audit missing changelog dates across tracked repos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repogerbil.core.git import get_active_dates


@dataclass(frozen=True)
class MissingDate:
    """A repo+date combination that has commits but no changelog."""

    repo: str
    date: str


def find_missing(
    tracked: dict[str, str],
    changelog_dir: Path,
) -> list[MissingDate]:
    """Find dates with commits but no changelog file.

    Args:
        tracked: {repo_name: repo_path} registry.
        changelog_dir: Root directory containing per-repo changelog subdirectories.

    Returns:
        List of MissingDate sorted by repo then date.
    """
    missing: list[MissingDate] = []

    for repo_name, repo_path in sorted(tracked.items()):
        path = Path(repo_path)
        if not path.is_dir():
            continue

        commit_dates = get_active_dates(path)
        existing = _get_changelog_dates(changelog_dir / repo_name, repo_name)

        for d in sorted(commit_dates - existing):
            missing.append(MissingDate(repo=repo_name, date=d))

    return missing


def _get_changelog_dates(repo_cl_dir: Path, repo_name: str) -> set[str]:
    """Get dates that have changelog files."""
    if not repo_cl_dir.is_dir():
        return set()

    dates: set[str] = set()
    for f in repo_cl_dir.glob(f"*-{repo_name}-changelog.yaml"):
        parts = f.name.split("-")
        if len(parts) >= 3:  # pragma: no branch — filenames always have 3+ parts
            dates.add(f"{parts[0]}-{parts[1]}-{parts[2]}")
    return dates
