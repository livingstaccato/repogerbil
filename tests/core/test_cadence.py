# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for time-based cadence grouping."""

from datetime import UTC, datetime

import pytest

from repogerbil.core.cadence import TimeGroup, group_by_cadence, groups_to_json
from repogerbil.core.git import CommitInfo


def _make_commit(hash: str, date: str, subject: str = "test", files: list[str] | None = None) -> CommitInfo:
    return CommitInfo(hash=hash, date=date, subject=subject, files=files or [])


class TestGroupByDay:
    def test_single_day(self) -> None:
        commits = [
            _make_commit("a1", "2026-04-07", "first"),
            _make_commit("a2", "2026-04-07", "second"),
        ]
        groups = group_by_cadence(commits, "daily")
        assert len(groups) == 1
        assert len(groups[0].commits) == 2

    def test_two_days(self) -> None:
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-08"),
        ]
        groups = group_by_cadence(commits, "daily")
        assert len(groups) == 2
        assert groups[0].period_start.date().isoformat() == "2026-04-07"
        assert groups[1].period_start.date().isoformat() == "2026-04-08"

    def test_empty_commits(self) -> None:
        groups = group_by_cadence([], "daily")
        assert groups == []

    def test_preserves_files(self) -> None:
        commits = [
            _make_commit("a1", "2026-04-07", files=["src/a.py"]),
            _make_commit("a2", "2026-04-07", files=["src/b.py"]),
        ]
        groups = group_by_cadence(commits, "daily")
        assert set(groups[0].files_affected) == {"src/a.py", "src/b.py"}

    def test_deduplicates_files(self) -> None:
        commits = [
            _make_commit("a1", "2026-04-07", files=["src/a.py"]),
            _make_commit("a2", "2026-04-07", files=["src/a.py"]),
        ]
        groups = group_by_cadence(commits, "daily")
        assert groups[0].files_affected == ["src/a.py"]

    def test_with_explicit_timestamps(self) -> None:
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
        ]
        ts = {
            "a1": int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp()),
            "a2": int(datetime(2026, 4, 7, 14, 0, tzinfo=UTC).timestamp()),
        }
        groups = group_by_cadence(commits, "daily", timestamps=ts)
        assert len(groups) == 1

    def test_with_commit_timestamp_field(self) -> None:
        """Test that CommitInfo.timestamp field is used when set and no timestamps dict provided."""
        from repogerbil.core.git import CommitInfo

        ts1 = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts2 = int(datetime(2026, 4, 7, 14, 0, tzinfo=UTC).timestamp())
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="first", timestamp=ts1),
            CommitInfo(hash="a2", date="2026-04-07", subject="second", timestamp=ts2),
        ]
        groups = group_by_cadence(commits, "daily")
        assert len(groups) == 1
        assert len(groups[0].commits) == 2


class TestGroupByHour:
    def test_two_hours(self) -> None:
        commits = [_make_commit("a1", "2026-04-07"), _make_commit("a2", "2026-04-07")]
        ts = {
            "a1": int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp()),
            "a2": int(datetime(2026, 4, 7, 11, 0, tzinfo=UTC).timestamp()),
        }
        groups = group_by_cadence(commits, "hourly", timestamps=ts)
        assert len(groups) == 2

    def test_same_hour(self) -> None:
        commits = [_make_commit("a1", "2026-04-07"), _make_commit("a2", "2026-04-07")]
        ts = {
            "a1": int(datetime(2026, 4, 7, 10, 15, tzinfo=UTC).timestamp()),
            "a2": int(datetime(2026, 4, 7, 10, 45, tzinfo=UTC).timestamp()),
        }
        groups = group_by_cadence(commits, "hourly", timestamps=ts)
        assert len(groups) == 1
        assert len(groups[0].commits) == 2

    def test_hour_group_preserves_utc_boundary(self) -> None:
        commits = [_make_commit("a1", "2026-04-07")]
        ts = {"a1": int(datetime(2026, 4, 7, 10, 15, tzinfo=UTC).timestamp())}

        groups = group_by_cadence(commits, "hourly", timestamps=ts)

        assert groups[0].period_start == datetime(2026, 4, 7, 10, 0, tzinfo=UTC)
        assert groups[0].period_end == datetime(2026, 4, 7, 10, 59, 59, tzinfo=UTC)

    def test_hour_group_files_affected_populated(self) -> None:
        """files_affected must contain commit files, not be empty/missing."""
        commits = [_make_commit("a1", "2026-04-07", files=["x.py", "y.py"])]
        ts = {"a1": int(datetime(2026, 4, 7, 10, 15, tzinfo=UTC).timestamp())}
        groups = group_by_cadence(commits, "hourly", timestamps=ts)
        assert len(groups) == 1
        assert set(groups[0].files_affected) == {"x.py", "y.py"}


class TestGroupByWeek:
    def test_same_week(self) -> None:
        # Mon Apr 6 and Fri Apr 10 are same ISO week
        commits = [
            _make_commit("a1", "2026-04-06"),
            _make_commit("a2", "2026-04-10"),
        ]
        groups = group_by_cadence(commits, "weekly")
        assert len(groups) == 1

    def test_different_weeks(self) -> None:
        # Apr 5 (Sun) and Apr 6 (Mon) span a week boundary
        commits = [
            _make_commit("a1", "2026-04-05"),
            _make_commit("a2", "2026-04-06"),
        ]
        groups = group_by_cadence(commits, "weekly")
        assert len(groups) == 2

    def test_week_boundaries_are_monday_to_sunday(self) -> None:
        commits = [_make_commit("a1", "2026-04-10")]

        groups = group_by_cadence(commits, "weekly")

        assert groups[0].period_start == datetime(2026, 4, 6, 0, 0, tzinfo=UTC)
        assert groups[0].period_end == datetime(2026, 4, 12, 23, 59, 59, tzinfo=UTC)

    def test_week_uses_provided_timestamps(self) -> None:
        """The weekly bucketing must pass timestamps dict (not None) to _get_timestamp.

        Two commits with same date='2026-04-10' (Friday) but explicit timestamps
        spanning a week boundary: midnight Mon Apr 13 vs Sat Apr 11.
        With timestamps used: end up in two separate weeks.
        With timestamps ignored: both use date='2026-04-10' → same week.
        """
        commits = [
            _make_commit("a1", "2026-04-10"),
            _make_commit("a2", "2026-04-10"),
        ]
        ts = {
            "a1": int(datetime(2026, 4, 11, 12, 0, tzinfo=UTC).timestamp()),  # Sat (week of Apr 6)
            "a2": int(datetime(2026, 4, 13, 12, 0, tzinfo=UTC).timestamp()),  # Mon (week of Apr 13)
        }
        groups = group_by_cadence(commits, "weekly", timestamps=ts)
        assert len(groups) == 2

    def test_week_files_affected_populated(self) -> None:
        """files_affected must contain commit files for weekly grouping."""
        commits = [_make_commit("a1", "2026-04-10", files=["w.py", "v.py"])]
        groups = group_by_cadence(commits, "weekly")
        assert len(groups) == 1
        assert set(groups[0].files_affected) == {"w.py", "v.py"}


class TestGroupByInvalidCadence:
    def test_raises_on_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unsupported cadence"):
            group_by_cadence([], "monthly")


class TestTimeGroup:
    def test_frozen(self) -> None:
        group = TimeGroup(
            period_start=datetime(2026, 4, 7, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
            commits=[],
        )
        with pytest.raises(AttributeError):
            group.commits = []  # type: ignore[misc]


class TestGroupsToJson:
    def test_exports_json(self) -> None:
        import json

        from repogerbil.core.cadence import groups_to_json

        commits = [_make_commit("a1", "2026-04-07", "first")]
        groups = group_by_cadence(commits, "daily")
        result = groups_to_json(groups, "daily")
        data = json.loads(result)
        assert data["cadence"] == "daily"
        assert data["group_count"] == 1
        assert data["groups"][0]["commit_count"] == 1

    def test_exports_with_exact_two_space_indent(self) -> None:
        """JSON output must use exactly indent=2 (not 3)."""
        commits = [_make_commit("a1", "2026-04-07", "first")]
        groups = group_by_cadence(commits, "daily")
        result = groups_to_json(groups, "daily")
        # With indent=2, top-level keys are indented by exactly 2 spaces.
        # With indent=3, they would be indented by 3 spaces.
        assert '\n  "cadence":' in result  # exactly 2 spaces
        assert '\n   "cadence":' not in result  # NOT 3 spaces

    def test_exports_exact_group_payload(self) -> None:
        import json

        commits = [_make_commit("a1", "2026-04-07", "first", files=["src/a.py"])]
        groups = group_by_cadence(commits, "daily")

        data = json.loads(group_to_json := groups_to_json(groups, "daily"))

        assert "\n  " in group_to_json
        assert data == {
            "cadence": "daily",
            "group_count": 1,
            "groups": [
                {
                    "period_start": "2026-04-07T00:00:00+00:00",
                    "period_end": "2026-04-07T23:59:59+00:00",
                    "commit_count": 1,
                    "commits": [{"hash": "a1", "date": "2026-04-07", "subject": "first"}],
                    "files_affected": ["src/a.py"],
                }
            ],
        }


class TestGroupByGap:
    def test_gap_splits_on_threshold(self) -> None:
        """Three commits: t=0, t=30m, t=2h → two groups (0+30m together, 2h separate)."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
            _make_commit("a3", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 1800,  # +30 minutes
            "a3": base_time + 7200,  # +2 hours
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert len(groups) == 2
        assert len(groups[0].commits) == 2
        assert groups[0].commits[0].hash == "a1"
        assert groups[0].commits[1].hash == "a2"
        assert len(groups[1].commits) == 1
        assert groups[1].commits[0].hash == "a3"

    def test_gap_single_commit_per_group(self) -> None:
        """All commits > threshold apart → one group each."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
            _make_commit("a3", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 3600,  # +1 hour
            "a3": base_time + 7200,  # +2 hours
        }
        groups = group_by_cadence(commits, "gap:30m", timestamps=ts)
        assert len(groups) == 3
        assert all(len(group.commits) == 1 for group in groups)

    def test_gap_all_in_one_group(self) -> None:
        """All commits within threshold → one group."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
            _make_commit("a3", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 600,  # +10 minutes
            "a3": base_time + 1200,  # +20 minutes
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert len(groups) == 1
        assert len(groups[0].commits) == 3

    def test_gap_parses_minutes(self) -> None:
        """Parsing 'gap:30m' format."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 1800,  # +30 minutes
        }
        groups = group_by_cadence(commits, "gap:30m", timestamps=ts)
        assert len(groups) == 1  # Within threshold

    def test_gap_parses_hours(self) -> None:
        """Parsing 'gap:2h' format."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 3600,  # +1 hour
        }
        groups = group_by_cadence(commits, "gap:2h", timestamps=ts)
        assert len(groups) == 1  # Within threshold

    def test_gap_invalid_format(self) -> None:
        """Invalid gap formats raise ValueError."""
        commits = [_make_commit("a1", "2026-04-07")]
        with pytest.raises(ValueError, match="Invalid gap format"):
            group_by_cadence(commits, "gap:invalid", timestamps={})

    def test_gap_invalid_unit(self) -> None:
        """Invalid gap units raise ValueError."""
        commits = [_make_commit("a1", "2026-04-07")]
        with pytest.raises(ValueError, match="Invalid gap format"):
            group_by_cadence(commits, "gap:30s", timestamps={})

    def test_gap_preserves_chronological_order(self) -> None:
        """Groups remain chronologically sorted even with gaps."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
            _make_commit("a3", "2026-04-07"),
            _make_commit("a4", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 1800,  # +30m (together with a1)
            "a3": base_time + 7260,  # +121m (separate from a1-a2, together with a4)
            "a4": base_time + 9000,  # +150m (together with a3)
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert len(groups) == 2
        assert [c.hash for c in groups[0].commits] == ["a1", "a2"]
        assert [c.hash for c in groups[1].commits] == ["a3", "a4"]

    def test_gap_collects_files(self) -> None:
        """Files from all commits in gap group are collected."""
        commits = [
            _make_commit("a1", "2026-04-07", files=["src/a.py"]),
            _make_commit("a2", "2026-04-07", files=["src/b.py"]),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 1800,
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert set(groups[0].files_affected) == {"src/a.py", "src/b.py"}

    def test_gap_empty_commits(self) -> None:
        """Empty commits list returns empty groups."""
        groups = group_by_cadence([], "gap:1h")
        assert groups == []

    def test_gap_minute_unit_uses_60_seconds_exactly(self) -> None:
        """'30m' must mean exactly 30*60=1800 sec threshold (not 30*61=1830)."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        # Gap is exactly 1801 sec. With threshold=1800: 1801 > 1800 → split.
        # With threshold=1830 (mutant 30*61): 1801 > 1830 False → no split.
        ts = {
            "a1": base_time,
            "a2": base_time + 1801,
        }
        groups = group_by_cadence(commits, "gap:30m", timestamps=ts)
        # Must be 2 groups (threshold is 1800, not 1830)
        assert len(groups) == 2

    def test_gap_hour_unit_uses_3600_seconds_exactly(self) -> None:
        """'1h' must mean exactly 1*3600=3600 sec threshold (not 1*3601=3601)."""
        commits = [
            _make_commit("a1", "2026-04-07"),
            _make_commit("a2", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        # Gap is exactly 3601 sec. With threshold=3600: 3601 > 3600 → split.
        # With threshold=3601 (mutant 1*3601): 3601 > 3601 False → no split.
        ts = {
            "a1": base_time,
            "a2": base_time + 3601,
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        # Must be 2 groups (threshold is 3600, not 3601)
        assert len(groups) == 2

    def test_gap_sort_uses_timestamps_dict_not_none(self) -> None:
        """The sort key must use the provided timestamps dict, not pass None.

        If timestamps were passed as None to _get_timestamp, the function would fall
        back to commit.timestamp/date. With all commits having date='2026-04-07' and
        no .timestamp field, sort order would not match the timestamps dict.
        """
        # All commits have same date and no .timestamp; use timestamps dict to set order.
        commits = [
            _make_commit("third", "2026-04-07"),
            _make_commit("first", "2026-04-07"),
            _make_commit("second", "2026-04-07"),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "first": base_time,
            "second": base_time + 600,
            "third": base_time + 1200,
        }
        # All within 30m → one group, sorted by timestamps dict.
        groups = group_by_cadence(commits, "gap:30m", timestamps=ts)
        assert len(groups) == 1
        # Order must match timestamps dict, not input order.
        assert [c.hash for c in groups[0].commits] == ["first", "second", "third"]

    def test_gap_mid_loop_group_uses_correct_start_end_and_files(self) -> None:
        """First (non-final) group's period_start/end and files_affected must be
        derived from current_group's first/last commit (not None)."""
        commits = [
            _make_commit("a1", "2026-04-07", files=["a.py"]),
            _make_commit("a2", "2026-04-07", files=["b.py"]),
            _make_commit("a3", "2026-04-07", files=["c.py"]),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 600,  # +10m (same group as a1)
            "a3": base_time + 7200,  # +2h (splits → new group)
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert len(groups) == 2
        # First group: starts at a1 timestamp, ends at a2 timestamp.
        first = groups[0]
        assert first.period_start == datetime.fromtimestamp(ts["a1"], tz=UTC)
        assert first.period_end == datetime.fromtimestamp(ts["a2"], tz=UTC)
        assert first.period_start.tzinfo == UTC
        assert first.period_end.tzinfo == UTC
        assert set(first.files_affected) == {"a.py", "b.py"}

    def test_gap_final_group_uses_correct_start_end_and_files(self) -> None:
        """Final group's period_start/end and files_affected must be derived from
        current_group's first/last commit (not None)."""
        commits = [
            _make_commit("a1", "2026-04-07", files=["a.py"]),
            _make_commit("a2", "2026-04-07", files=["b.py"]),
            _make_commit("a3", "2026-04-07", files=["c.py"]),
            _make_commit("a4", "2026-04-07", files=["d.py"]),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 600,  # +10m (same group as a1)
            "a3": base_time + 7200,  # +2h (splits → new group with a3+a4)
            "a4": base_time + 7800,  # +130m (same group as a3)
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert len(groups) == 2
        # Final group: starts at a3 timestamp, ends at a4 timestamp.
        final = groups[1]
        assert final.period_start == datetime.fromtimestamp(ts["a3"], tz=UTC)
        assert final.period_end == datetime.fromtimestamp(ts["a4"], tz=UTC)
        assert final.period_start.tzinfo == UTC
        assert final.period_end.tzinfo == UTC
        assert set(final.files_affected) == {"c.py", "d.py"}

    def test_gap_single_group_final_uses_correct_values(self) -> None:
        """When only the final group exists (no mid-loop splits), it must still
        produce the right period boundaries and files."""
        commits = [
            _make_commit("a1", "2026-04-07", files=["a.py"]),
            _make_commit("a2", "2026-04-07", files=["b.py"]),
        ]
        base_time = int(datetime(2026, 4, 7, 10, 0, tzinfo=UTC).timestamp())
        ts = {
            "a1": base_time,
            "a2": base_time + 600,
        }
        groups = group_by_cadence(commits, "gap:1h", timestamps=ts)
        assert len(groups) == 1
        g = groups[0]
        assert g.period_start == datetime.fromtimestamp(ts["a1"], tz=UTC)
        assert g.period_end == datetime.fromtimestamp(ts["a2"], tz=UTC)
        assert g.period_start.tzinfo == UTC
        assert g.period_end.tzinfo == UTC
        assert set(g.files_affected) == {"a.py", "b.py"}
