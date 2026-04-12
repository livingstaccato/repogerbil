# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Audit missing changelog dates across tracked repos."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from repogerbil.core.config import RepoOverride
from repogerbil.core.provenance import collect_effective_dates


@dataclass(frozen=True)
class MissingDate:
    """A repo+date combination that has commits but no changelog."""

    repo: str
    date: str


def find_missing(
    tracked: dict[str, str],
    changelog_dir: Path,
    repo_overrides: dict[str, RepoOverride] | None = None,
    extra_sources: list[Path] | None = None,
) -> list[MissingDate]:
    """Find dates with commits but no changelog file.

    Args:
        tracked: {repo_name: repo_path} registry. Empty string = archived (no source).
        changelog_dir: Root directory containing per-repo changelog subdirectories.
        repo_overrides: Optional per-repo overrides (for skip_dates).

    Returns:
        List of MissingDate sorted by repo then date.
    """
    missing: list[MissingDate] = []
    overrides = repo_overrides or {}
    today = date.today().isoformat()

    for repo_name, repo_path in sorted(tracked.items()):
        skip = set((overrides.get(repo_name) or RepoOverride()).skip_dates)
        path = Path(repo_path) if repo_path else None

        if path and path.is_dir():
            # Active repo: compare git dates against changelogs
            commit_dates = collect_effective_dates(path, extra_sources=extra_sources)
            existing = _get_changelog_dates(changelog_dir / repo_name, repo_name)
            expected = {d for d in commit_dates if d <= today}

            for d in sorted(expected - existing - skip):
                missing.append(MissingDate(repo=repo_name, date=d))
        else:
            # Archived repo (no source): check for gaps in existing range
            gap_dates = _find_date_gaps(changelog_dir / repo_name, repo_name)
            for d in sorted(gap_dates - skip):
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


def _find_date_gaps(repo_cl_dir: Path, repo_name: str) -> set[str]:
    """Find date gaps within the existing changelog range for archived repos."""
    existing = _get_changelog_dates(repo_cl_dir, repo_name)
    if not existing:
        return set()

    sorted_dates = sorted(existing)
    start = date.fromisoformat(sorted_dates[0])
    end = date.fromisoformat(sorted_dates[-1])
    today = date.today()
    if end > today:  # pragma: no cover
        end = today

    gaps: set[str] = set()
    current = start
    while current <= end:
        d_str = current.isoformat()
        if d_str not in existing:
            gaps.add(d_str)
        current += timedelta(days=1)

    return gaps
