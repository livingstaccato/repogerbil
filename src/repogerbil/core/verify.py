# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Stats verification and file coverage checking for changelogs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.git import get_commits_for_date, get_diff_stats


@dataclass(frozen=True)
class VerifyResult:
    """Result of verifying a single changelog file."""

    repo: str
    date: str
    stats_match: bool
    reported_files: int
    actual_files: int
    accounted_files: int
    actual_insertions: int
    actual_deletions: int
    reported_insertions: int
    reported_deletions: int


def verify_changelog(
    yaml_path: Path,
    repo_path: str | Path,
    tolerance: int = 20,
) -> VerifyResult | None:
    """Verify a changelog's stats against git truth.

    Returns None if the file can't be verified (missing data, no commits).
    """
    data = _load_yaml(yaml_path)
    if not data:
        return None

    stats = data.get("stats")
    if not isinstance(stats, dict) or "files_changed" not in stats:
        return None

    repo = data.get("repo", "")
    date_str = data.get("date", "")
    if not date_str:
        return None
    # Normalize date (yaml may parse as datetime)
    date_str = str(date_str)[:10]

    commits = get_commits_for_date(repo_path, date_str)
    if not commits:
        return None

    git_stats = get_diff_stats(repo_path, commits[0].hash, commits[-1].hash)
    accounted = count_accounted_files(data)

    return VerifyResult(
        repo=repo,
        date=date_str,
        stats_match=_within_tolerance(stats["files_changed"], git_stats.files_changed, tolerance),
        reported_files=stats["files_changed"],
        actual_files=git_stats.files_changed,
        accounted_files=accounted,
        actual_insertions=git_stats.insertions,
        actual_deletions=git_stats.deletions,
        reported_insertions=stats.get("insertions", 0),
        reported_deletions=stats.get("deletions", 0),
    )


def count_accounted_files(data: dict[str, Any]) -> int:
    """Count files accounted for by bulk entries + change files."""
    bulk_files = 0
    for entry in data.get("bulk") or []:
        bulk_files += entry.get("files", 0)

    change_files: set[str] = set()
    for change in data.get("changes") or []:
        for f in change.get("files") or []:
            if isinstance(f, dict) and f.get("path"):
                change_files.add(f["path"])
        for point in change.get("points") or []:
            if isinstance(point, dict):
                for pf in point.get("files") or []:
                    if isinstance(pf, str):
                        change_files.add(pf)

    return bulk_files + len(change_files)


def has_coverage_gap(data: dict[str, Any], actual_files: int, tolerance: int = 20) -> bool:
    """Check if bulk + changes account for the files within tolerance."""
    accounted = count_accounted_files(data)
    if actual_files == 0:
        return False
    coverage_pct = accounted / actual_files * 100
    return coverage_pct < (100 - tolerance)


def _within_tolerance(reported: int, actual: int, tolerance: int) -> bool:
    if actual == 0:
        return reported == 0
    pct_diff = abs(reported - actual) / actual * 100
    return pct_diff <= tolerance


def _load_yaml(path: Path) -> dict[str, Any] | None:
    try:
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None
