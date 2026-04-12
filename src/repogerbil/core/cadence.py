# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Time-based commit grouping by calendar boundaries."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from repogerbil.core.git import CommitInfo

_SECONDS_PER_HOUR = 3600
_SECONDS_PER_DAY = 86400
_SECONDS_PER_WEEK = 7 * _SECONDS_PER_DAY
_EPOCH_MONDAY_OFFSET = 3 * _SECONDS_PER_DAY  # 1970-01-01 was Thursday


@dataclass(frozen=True)
class TimeGroup:
    """A group of commits within a time period."""

    period_start: datetime
    period_end: datetime
    commits: list[CommitInfo]
    files_affected: list[str] = field(default_factory=list)


def group_by_cadence(
    commits: list[CommitInfo],
    cadence: str,
    timestamps: dict[str, int] | None = None,
) -> list[TimeGroup]:
    """Group commits by time cadence.

    Args:
        commits: List of commits to group (must have date field as YYYY-MM-DD).
        cadence: "hourly", "daily", "weekly", or "gap:NNm"/"gap:NNh"
                 (e.g. "gap:30m" = group commits within 30 minute gaps).
        timestamps: Optional {hash: unix_timestamp} for sub-day precision.
                    If not provided, uses midnight of the commit date.

    Returns:
        Chronologically sorted list of TimeGroups.
    """
    if cadence == "daily":
        return _group_by_day(commits, timestamps)
    if cadence == "hourly":
        return _group_by_hour(commits, timestamps)
    if cadence == "weekly":
        return _group_by_week(commits, timestamps)
    if cadence.startswith("gap:"):
        return _group_by_gap(commits, cadence[4:], timestamps)
    msg = f"Unsupported cadence: {cadence}"
    raise ValueError(msg)


def _get_timestamp(commit: CommitInfo, timestamps: dict[str, int] | None) -> int:
    """Get unix timestamp for a commit.

    Uses (in order of preference):
    1. Provided timestamps dict
    2. CommitInfo.timestamp field (if non-zero)
    3. Midnight UTC of commit date field
    """
    if timestamps and commit.hash in timestamps:
        return timestamps[commit.hash]
    if commit.timestamp != 0:
        return commit.timestamp
    # Fall back to parsing the date field (midnight UTC)
    dt = datetime.strptime(commit.date, "%Y-%m-%d").replace(tzinfo=UTC)
    return int(dt.timestamp())


def _collect_files(commits: list[CommitInfo]) -> list[str]:
    """Collect unique files from all commits."""
    seen: set[str] = set()
    result: list[str] = []
    for c in commits:
        for f in c.files:
            if f not in seen:
                seen.add(f)
                result.append(f)
    return result


def _group_by_day(
    commits: list[CommitInfo],
    timestamps: dict[str, int] | None,
) -> list[TimeGroup]:
    """Group commits by calendar day using integer division."""
    buckets: dict[int, list[CommitInfo]] = defaultdict(list)
    for commit in commits:
        ts = _get_timestamp(commit, timestamps)
        bucket = ts // _SECONDS_PER_DAY
        buckets[bucket].append(commit)

    groups: list[TimeGroup] = []
    for bucket, bucket_commits in sorted(buckets.items()):
        day_start = datetime.fromtimestamp(bucket * _SECONDS_PER_DAY, tz=UTC)
        day_end = day_start.replace(hour=23, minute=59, second=59)  # pragma: no mutate
        groups.append(
            TimeGroup(
                period_start=day_start,
                period_end=day_end,
                commits=bucket_commits,
                files_affected=_collect_files(bucket_commits),
            )
        )
    return groups


def _group_by_hour(
    commits: list[CommitInfo],
    timestamps: dict[str, int] | None,
) -> list[TimeGroup]:
    """Group commits by calendar hour using integer division."""
    buckets: dict[int, list[CommitInfo]] = defaultdict(list)
    for commit in commits:
        ts = _get_timestamp(commit, timestamps)
        bucket = ts // _SECONDS_PER_HOUR
        buckets[bucket].append(commit)

    groups: list[TimeGroup] = []
    for bucket, bucket_commits in sorted(buckets.items()):
        hour_start = datetime.fromtimestamp(bucket * _SECONDS_PER_HOUR, tz=UTC)
        hour_end = hour_start.replace(minute=59, second=59)  # pragma: no mutate
        groups.append(
            TimeGroup(
                period_start=hour_start,
                period_end=hour_end,
                commits=bucket_commits,
                files_affected=_collect_files(bucket_commits),
            )
        )
    return groups


def _group_by_week(
    commits: list[CommitInfo],
    timestamps: dict[str, int] | None,
) -> list[TimeGroup]:
    """Group commits by ISO week (Monday-Sunday) using integer division."""
    buckets: dict[int, list[CommitInfo]] = defaultdict(list)
    for commit in commits:
        ts = _get_timestamp(commit, timestamps)
        bucket = (ts + _EPOCH_MONDAY_OFFSET) // _SECONDS_PER_WEEK
        buckets[bucket].append(commit)

    groups: list[TimeGroup] = []
    for bucket, bucket_commits in sorted(buckets.items()):
        week_start_ts = bucket * _SECONDS_PER_WEEK - _EPOCH_MONDAY_OFFSET
        week_start = datetime.fromtimestamp(week_start_ts, tz=UTC)
        week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)  # pragma: no mutate
        groups.append(
            TimeGroup(
                period_start=week_start,
                period_end=week_end,
                commits=bucket_commits,
                files_affected=_collect_files(bucket_commits),
            )
        )
    return groups


def _group_by_gap(
    commits: list[CommitInfo],
    gap_spec: str,
    timestamps: dict[str, int] | None,
) -> list[TimeGroup]:
    """Group commits by time gap between consecutive commits.

    Args:
        commits: List of commits (will be sorted by timestamp).
        gap_spec: Time threshold like "30m" or "2h".
        timestamps: Optional {hash: unix_timestamp} for sub-day precision.

    Returns:
        Chronologically sorted list of TimeGroups, each containing commits
        within the gap threshold of each other.
    """
    import re

    # Parse gap specification
    match = re.match(r"^(\d+)([mh])$", gap_spec)
    if not match:
        msg = f"Invalid gap format: {gap_spec} (use '30m' or '2h')"
        raise ValueError(msg)

    value, unit = int(match.group(1)), match.group(2)
    threshold_seconds = value * (60 if unit == "m" else 3600)

    # Sort commits by timestamp
    sorted_commits = sorted(commits, key=lambda c: _get_timestamp(c, timestamps))

    # Group by gap
    groups: list[TimeGroup] = []
    current_group: list[CommitInfo] = []
    last_ts = -threshold_seconds - 1  # Ensure first commit starts a group

    for commit in sorted_commits:
        ts = _get_timestamp(commit, timestamps)
        if ts - last_ts > threshold_seconds and current_group:
            # Start a new group
            group_start = datetime.fromtimestamp(_get_timestamp(current_group[0], timestamps), tz=UTC)
            group_end = datetime.fromtimestamp(_get_timestamp(current_group[-1], timestamps), tz=UTC)
            groups.append(
                TimeGroup(
                    period_start=group_start,
                    period_end=group_end,
                    commits=current_group,
                    files_affected=_collect_files(current_group),
                )
            )
            current_group = []

        current_group.append(commit)
        last_ts = ts

    # Add final group
    if current_group:
        group_start = datetime.fromtimestamp(_get_timestamp(current_group[0], timestamps), tz=UTC)
        group_end = datetime.fromtimestamp(_get_timestamp(current_group[-1], timestamps), tz=UTC)
        groups.append(
            TimeGroup(
                period_start=group_start,
                period_end=group_end,
                commits=current_group,
                files_affected=_collect_files(current_group),
            )
        )

    return groups


def groups_to_json(groups: list[TimeGroup], cadence: str) -> str:
    """Export time groups as JSON for external analysis."""
    import json

    data = {
        "cadence": cadence,
        "group_count": len(groups),
        "groups": [
            {
                "period_start": g.period_start.isoformat(),
                "period_end": g.period_end.isoformat(),
                "commit_count": len(g.commits),
                "commits": [{"hash": c.hash, "date": c.date, "subject": c.subject} for c in g.commits],
                "files_affected": g.files_affected,
            }
            for g in groups
        ],
    }
    return json.dumps(data, indent=2)
