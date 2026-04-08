# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for stats verification and coverage checking."""

from typing import Any

from repogerbil.core.verify import count_accounted_files, has_coverage_gap


class TestCountAccountedFiles:
    def test_empty(self) -> None:
        assert count_accounted_files({}) == 0

    def test_bulk_only(self) -> None:
        data: dict[str, Any] = {"bulk": [{"files": 10}, {"files": 5}]}
        assert count_accounted_files(data) == 15

    def test_changes_only(self) -> None:
        data: dict[str, Any] = {
            "changes": [
                {
                    "files": [{"path": "a.py"}, {"path": "b.py"}],
                    "points": [{"files": ["c.py"]}],
                },
            ],
        }
        assert count_accounted_files(data) == 3

    def test_deduplicates(self) -> None:
        data: dict[str, Any] = {
            "changes": [
                {
                    "files": [{"path": "a.py"}],
                    "points": [{"files": ["a.py"]}],
                },
            ],
        }
        assert count_accounted_files(data) == 1

    def test_bulk_plus_changes(self) -> None:
        data: dict[str, Any] = {
            "bulk": [{"files": 10}],
            "changes": [{"files": [{"path": "a.py"}], "points": []}],
        }
        assert count_accounted_files(data) == 11

    def test_invalid_file_entries(self) -> None:
        data: dict[str, Any] = {
            "changes": [
                {"files": ["not-a-dict"], "points": [{"files": [123]}]},
            ],
        }
        assert count_accounted_files(data) == 0

    def test_string_points(self) -> None:
        data: dict[str, Any] = {
            "changes": [{"points": ["just a string"]}],
        }
        assert count_accounted_files(data) == 0


class TestHasCoverageGap:
    def test_no_gap(self) -> None:
        data: dict[str, Any] = {"bulk": [{"files": 10}]}
        assert has_coverage_gap(data, actual_files=10) is False

    def test_gap(self) -> None:
        data: dict[str, Any] = {"bulk": [{"files": 2}]}
        assert has_coverage_gap(data, actual_files=20) is True

    def test_zero_actual(self) -> None:
        assert has_coverage_gap({}, actual_files=0) is False

    def test_within_tolerance(self) -> None:
        data: dict[str, Any] = {"bulk": [{"files": 8}]}
        assert has_coverage_gap(data, actual_files=10, tolerance=30) is False
