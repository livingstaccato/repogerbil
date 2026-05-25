# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Time-window timestamp helpers for snapshot — internal to snapshot.py."""

from __future__ import annotations

from collections import defaultdict
from datetime import date as date_type, datetime, timedelta
import hashlib
import random
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from repogerbil.core.cadence import TimeGroup


def _spread_timestamps_for_day(
    day_groups: list[TimeGroup],
    start_dt: datetime,
    end_dt: datetime,
    rng: random.Random,
) -> list[str]:
    """Spread N groups across [start_dt, end_dt] with weight-proportional spacing.

    Each group occupies a proportional slot sized by its ``files_affected`` count.
    A random position is chosen within the middle 80% of each slot, ensuring
    strictly increasing timestamps by construction.

    Args:
        day_groups: Groups to spread (all from the same calendar day).
        start_dt: Window start (timezone-aware).
        end_dt: Window end (timezone-aware, may be next day for midnight-crossing windows).
        rng: Random number generator for reproducible tests.

    Returns:
        List of ISO8601 timestamp strings, one per group, strictly increasing.
    """
    total_seconds = (end_dt - start_dt).total_seconds()
    if len(day_groups) == 1:
        offset = rng.uniform(0, total_seconds)
        return [(start_dt + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S%z")]

    weights = [max(1, len(g.files_affected)) for g in day_groups]
    total_weight = sum(weights)
    cumulative = 0.0
    results = []
    for w in weights:
        slot_start = cumulative / total_weight
        slot_end = (cumulative + w) / total_weight
        # Random position in middle 80% of slot (10% margin each side)
        lo = slot_start + 0.1 * (slot_end - slot_start)
        hi = slot_end - 0.1 * (slot_end - slot_start)
        pos = rng.uniform(lo, hi)
        ts = start_dt + timedelta(seconds=pos * total_seconds)
        results.append(ts.strftime("%Y-%m-%dT%H:%M:%S%z"))
        cumulative += w
    return results


def _compute_window_timestamps(
    groups: list[TimeGroup],
    window_start_hm: str,
    window_end_hm: str,
    timezone: str,
    seed: int | None = None,
) -> list[str]:
    """Distribute groups across a daily time window, one timestamp per group.

    Groups are bucketed by calendar day. Each day's groups are spread across
    [window_start_hm, window_end_hm] using weighted random spacing. Timestamps
    are strictly increasing within each day's window.

    Args:
        groups: All groups to timestamp (may span multiple calendar days).
        window_start_hm: Window start as ``HH:MM``.
        window_end_hm: Window end as ``HH:MM``. If end <= start, the window
                      crosses midnight (end is on the next calendar day).
        timezone: IANA timezone name (e.g. ``"America/Los_Angeles"``).
        seed: Optional RNG seed for deterministic output (useful in tests).

    Returns:
        List of ISO8601 timestamp strings, one per input group, in input order.
    """
    if seed is None:
        seed = _default_window_seed(groups, window_start_hm, window_end_hm, timezone)
    rng = random.Random(seed)  # noqa: S311 — not security-sensitive, used for commit timestamp jitter
    tz = ZoneInfo(timezone)
    sh, sm = map(int, window_start_hm.split(":"))
    eh, em = map(int, window_end_hm.split(":"))

    day_to_indices: dict[date_type, list[int]] = defaultdict(list)
    for i, g in enumerate(groups):
        day_to_indices[g.period_start.date()].append(i)

    timestamps: list[str | None] = [None] * len(groups)

    for day, indices in sorted(day_to_indices.items()):
        start_dt = datetime(day.year, day.month, day.day, sh, sm, 0, tzinfo=tz)
        end_day = day
        if eh < sh or (eh == sh and em <= sm):
            # Window crosses midnight — end is on the following calendar day
            end_day = day + timedelta(days=1)
        end_dt = datetime(end_day.year, end_day.month, end_day.day, eh, em, 0, tzinfo=tz)

        day_groups = [groups[i] for i in indices]
        day_ts = _spread_timestamps_for_day(day_groups, start_dt, end_dt, rng)
        for idx, ts in zip(indices, day_ts, strict=True):
            timestamps[idx] = ts

    return timestamps  # type: ignore[return-value]  # all slots filled by construction


def _default_window_seed(
    groups: list[TimeGroup],
    window_start_hm: str,
    window_end_hm: str,
    timezone: str,
) -> int:
    """Build a deterministic RNG seed from stable snapshot inputs."""
    chunks = [window_start_hm, window_end_hm, timezone]
    for group in groups:
        chunks.append(group.period_start.isoformat())
        chunks.append(group.period_end.isoformat())
        chunks.append(str(len(group.files_affected)))
        for commit in group.commits:
            chunks.append(commit.hash)
    digest = hashlib.sha256("|".join(chunks).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)
