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
