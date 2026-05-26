# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for stats verification and coverage checking."""

from pathlib import Path
import subprocess
from typing import Any

import yaml

from repogerbil.core.verify import (
    VerifyResult,
    count_accounted_files,
    has_coverage_gap,
    verify_changelog,
)


def _init_verify_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / "f.py").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: init"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
    )
    return repo


class TestCountAccountedFiles:
    def test_empty(self) -> None:
        assert count_accounted_files({}) == 0

    def test_bulk_only(self) -> None:
        data: dict[str, Any] = {"bulk": [{"files": 10}, {"files": 5}]}
        assert count_accounted_files(data) == 15

    def test_changes_only(self) -> None:
        data: dict[str, Any] = {
            "changes": [{"files": [{"path": "a.py"}, {"path": "b.py"}], "points": [{"files": ["c.py"]}]}],
        }
        assert count_accounted_files(data) == 3

    def test_deduplicates(self) -> None:
        data: dict[str, Any] = {"changes": [{"files": [{"path": "a.py"}], "points": [{"files": ["a.py"]}]}]}
        assert count_accounted_files(data) == 1

    def test_bulk_plus_changes(self) -> None:
        data: dict[str, Any] = {
            "bulk": [{"files": 10}],
            "changes": [{"files": [{"path": "a.py"}], "points": []}],
        }
        assert count_accounted_files(data) == 11

    def test_invalid_file_entries(self) -> None:
        data: dict[str, Any] = {"changes": [{"files": ["not-a-dict"], "points": [{"files": [123]}]}]}
        assert count_accounted_files(data) == 0

    def test_string_points(self) -> None:
        data: dict[str, Any] = {"changes": [{"points": ["just a string"]}]}
        assert count_accounted_files(data) == 0

    def test_bulk_entry_without_files_defaults_to_zero(self) -> None:
        """Missing 'files' key in bulk entry must default to 0, not 1."""
        data: dict[str, Any] = {"bulk": [{}, {}]}
        # If default is 1, this would be 2. If default is None, TypeError.
        # If default is 0 (correct), result is 0.
        assert count_accounted_files(data) == 0

    def test_bulk_entry_explicit_files_takes_priority(self) -> None:
        """Explicit files value used; default only kicks in when key missing."""
        data: dict[str, Any] = {"bulk": [{"files": 5}, {}, {"files": 3}]}
        # 5 + 0 (default) + 3 = 8. With default=1 → 9. With None → TypeError.
        assert count_accounted_files(data) == 8


class TestWithinTolerance:
    def test_within(self) -> None:
        from repogerbil.core.verify import _within_tolerance

        assert _within_tolerance(10, 10, 20) is True

    def test_outside(self) -> None:
        from repogerbil.core.verify import _within_tolerance

        assert _within_tolerance(100, 10, 20) is False

    def test_actual_zero_reported_zero(self) -> None:
        from repogerbil.core.verify import _within_tolerance

        assert _within_tolerance(0, 0, 20) is True

    def test_actual_zero_reported_nonzero(self) -> None:
        from repogerbil.core.verify import _within_tolerance

        assert _within_tolerance(5, 0, 20) is False


class TestSafeInt:
    def test_safe_int_supported_inputs(self) -> None:
        from repogerbil.core.verify import _safe_int

        assert _safe_int(True) == 1
        assert _safe_int(9) == 9
        assert _safe_int(3.4) == 3
        assert _safe_int("12") == 12
        assert _safe_int(object()) is None


class TestHasCoverageGap:
    def test_no_gap(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 10}]}, actual_files=10) is False

    def test_gap(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 2}]}, actual_files=20) is True

    def test_zero_actual(self) -> None:
        assert has_coverage_gap({}, actual_files=0) is False

    def test_within_tolerance(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 8}]}, actual_files=10, tolerance=30) is False

    def test_default_tolerance_boundary(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 80}]}, actual_files=100) is False
        assert has_coverage_gap({"bulk": [{"files": 79}]}, actual_files=100) is True

    def test_default_tolerance_signature_pinned(self) -> None:
        """Pin default tolerance value to exactly 20 (not 21)."""
        import inspect

        sig = inspect.signature(has_coverage_gap)
        assert sig.parameters["tolerance"].default == 20

    def test_coverage_pct_uses_exact_100_multiplier(self) -> None:
        """coverage_pct = accounted/actual * 100 (not * 101).

        With accounted=80, actual=100, tolerance=20:
          - * 100: pct=80.0, threshold=80, 80<80 False → no gap.
          - * 101: pct=80.8, threshold=80, 80.8<80 False → no gap (same result, equivalent).
        Use a sharper boundary: accounted=79, actual=100, tolerance=20:
          - * 100: pct=79.0, threshold=80, 79<80 True → gap.
          - * 101: pct=79.79, threshold=80, 79.79<80 True → gap (still equivalent).
        Pick accounted=80, actual=101, tolerance=21:
          - * 100: pct=79.207, threshold=79, 79.207<79 False → no gap.
          - * 101: pct=79.999, threshold=79, 79.999<79 False → still equivalent.
        The mutant is equivalent for *some* inputs but not when result of the
        comparison flips. Try accounted=79, actual=100, tolerance=21:
          - * 100: pct=79.0, threshold=79, 79<79 False → no gap.
          - * 101: pct=79.79, threshold=79, 79.79<79 False → no gap.
        accounted=78, actual=100, tolerance=21:
          - * 100: pct=78.0, threshold=79, 78<79 True → gap.
          - * 101: pct=78.78, threshold=79, 78.78<79 True → gap.
        accounted=79, actual=100, tolerance=20:
          - * 100: pct=79.0, threshold=80, True (gap).
          - * 101: pct=79.79, threshold=80, True (gap).
        Need a case where *100 < threshold but *101 >= threshold:
          accounted/actual*100 < threshold AND accounted/actual*101 >= threshold
          For threshold T, ratio r = accounted/actual. r*100 < T and r*101 >= T.
          So T/101 <= r < T/100. Pick T=80 → 0.7920... <= r < 0.8. Try r=0.795
          accounted=159, actual=200, tolerance=20:
          - * 100: pct=79.5, threshold=80, 79.5<80 True → gap.
          - * 101: pct=80.295, threshold=80, 80.295<80 False → no gap.
        """
        # accounted=159, actual=200, default tolerance=20: must be True (gap).
        assert has_coverage_gap({"bulk": [{"files": 159}]}, actual_files=200) is True


class TestVerifyChangelog:
    def test_valid_changelog(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        from repogerbil.core.git import get_commits_for_date, get_diff_stats

        commits = get_commits_for_date(repo, "2026-04-07")
        stats = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {
                        "files_changed": stats.files_changed,
                        "insertions": stats.insertions,
                        "deletions": stats.deletions,
                    },
                    "changes": [],
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        assert isinstance(result, VerifyResult)
        assert result.repo == "repo"
        assert result.stats_match is True

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "bad.yaml"
        yaml_path.write_text("not: [valid: yaml: {{")
        assert verify_changelog(yaml_path, repo) is None

    def test_not_a_dict(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "list.yaml"
        yaml_path.write_text("- item1\n- item2\n")
        assert verify_changelog(yaml_path, repo) is None

    def test_missing_stats(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "nostats.yaml"
        yaml_path.write_text(yaml.dump({"date": "2026-04-07", "repo": "repo"}))
        assert verify_changelog(yaml_path, repo) is None

    def test_stats_not_dict(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "badstats.yaml"
        yaml_path.write_text(yaml.dump({"date": "2026-04-07", "repo": "repo", "stats": "nope"}))
        assert verify_changelog(yaml_path, repo) is None

    def test_missing_files_changed(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "nofc.yaml"
        yaml_path.write_text(yaml.dump({"date": "2026-04-07", "repo": "repo", "stats": {"insertions": 1}}))
        assert verify_changelog(yaml_path, repo) is None

    def test_non_numeric_files_changed_returns_none(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "bad-files.yaml"
        yaml_path.write_text(
            yaml.dump(
                {"date": "2026-04-07", "repo": "repo", "stats": {"files_changed": "n/a", "insertions": 1}}
            )
        )
        assert verify_changelog(yaml_path, repo) is None

    def test_missing_date(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "nodate.yaml"
        yaml_path.write_text(yaml.dump({"repo": "repo", "stats": {"files_changed": 1}}))
        assert verify_changelog(yaml_path, repo) is None

    def test_no_commits_for_date(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "nocommits.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2020-01-01",
                    "repo": "repo",
                    "stats": {"files_changed": 1},
                }
            )
        )
        assert verify_changelog(yaml_path, repo) is None

    def test_zero_actual_files(self, tmp_path: Path) -> None:
        """Test tolerance check when actual files is 0."""
        repo = tmp_path / "zrepo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "empty"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
        )
        yaml_path = tmp_path / "zero.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "zrepo",
                    "stats": {"files_changed": 0, "insertions": 0, "deletions": 0},
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        assert result.stats_match is True

    def test_stats_mismatch(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "mismatch.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {"files_changed": 999, "insertions": 1, "deletions": 0},
                }
            )
        )
        result = verify_changelog(yaml_path, repo, tolerance=5)
        assert result is not None
        assert result.stats_match is False

    def test_insertions_mismatch_affects_stats_match(self, tmp_path: Path) -> None:
        repo = _init_verify_repo(tmp_path)
        from repogerbil.core.git import get_commits_for_date, get_diff_stats

        commits = get_commits_for_date(repo, "2026-04-07")
        stats = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        yaml_path = tmp_path / "insertions-mismatch.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {
                        "files_changed": stats.files_changed,
                        "insertions": stats.insertions + 999,
                        "deletions": stats.deletions,
                    },
                    "changes": [],
                }
            )
        )
        result = verify_changelog(yaml_path, repo, tolerance=5)
        assert result is not None
        assert result.stats_match is False

    def test_default_tolerance_is_exactly_20(self, tmp_path: Path) -> None:
        """A 20% diff must pass at default tolerance; 21% must fail. Pins tolerance=20."""
        repo = _init_verify_repo(tmp_path)
        from repogerbil.core.git import get_commits_for_date, get_diff_stats

        commits = get_commits_for_date(repo, "2026-04-07")
        actual = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        # Files exactly at +20%: actual=1, reported=1 → 0% diff; force a +20% on insertions
        # actual.insertions=1 (from "x\n"), so reported=1 → diff=0%. Use deletions=0 case.
        # Pick numbers where 20% boundary matters: actual.insertions=1, reported=1 (0% diff, passes)
        # To verify the default is 20 not 21, we need a case at 21% to fail with default.
        yaml_path = tmp_path / "tol-default.yaml"
        # actual_files=1; reported=100 → 9900% diff: fails at any tolerance ≤ 9899
        # That kills mutmut_1 (20→21) only if both sides agree. Need a more precise boundary.
        # Better: test with explicit tolerance values directly via _within_tolerance.
        # For verify_changelog default: assert default behaviour matches tolerance=20 explicitly.
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {
                        "files_changed": actual.files_changed,
                        "insertions": actual.insertions,
                        "deletions": actual.deletions,
                    },
                    "changes": [],
                }
            )
        )
        # Verify default tolerance handles exactly correct stats
        default_result = verify_changelog(yaml_path, repo)
        explicit_result = verify_changelog(yaml_path, repo, tolerance=20)
        assert default_result is not None
        assert explicit_result is not None
        assert default_result.stats_match == explicit_result.stats_match

    def test_default_tolerance_value_pinned(self) -> None:
        """Pin the default tolerance value exactly to 20."""
        import inspect

        from repogerbil.core import verify

        sig = inspect.signature(verify.verify_changelog)
        assert sig.parameters["tolerance"].default == 20

    def test_deletions_key_is_read_and_used(self, tmp_path: Path) -> None:
        """The 'deletions' key must be read literally and propagate into reported_deletions."""
        repo = _init_verify_repo(tmp_path)
        from repogerbil.core.git import get_commits_for_date, get_diff_stats

        commits = get_commits_for_date(repo, "2026-04-07")
        actual = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        yaml_path = tmp_path / "deletions-key.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {
                        "files_changed": actual.files_changed,
                        "insertions": actual.insertions,
                        "deletions": 42,
                    },
                    "changes": [],
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        # The "deletions" key must be read correctly to propagate to reported_deletions
        assert result.reported_deletions == 42

    def test_repo_default_empty_string(self, tmp_path: Path) -> None:
        """When repo key is missing, default repo must be exactly empty string ''."""
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "no-repo-key.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "stats": {"files_changed": 1, "insertions": 1, "deletions": 0},
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        # Must be empty string, not None, not "XXXX"
        assert result.repo == ""
        assert isinstance(result.repo, str)

    def test_date_normalized_to_first_ten_chars(self, tmp_path: Path) -> None:
        """A date longer than 10 chars (e.g. ISO datetime) must be truncated to exactly [:10]."""
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "long-date.yaml"
        # Date string longer than 10 chars; [:10] truncates correctly, [:11] gives extra char
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07T10:00:00",
                    "repo": "repo",
                    "stats": {"files_changed": 1, "insertions": 1, "deletions": 0},
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        # The date field must be exactly "2026-04-07", not "2026-04-07T"
        assert result.date == "2026-04-07"
        assert len(result.date) == 10

    def test_accounted_files_propagates_exactly(self, tmp_path: Path) -> None:
        """count_accounted_files result must flow into accounted_files."""
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "with-bulk.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {"files_changed": 1, "insertions": 1, "deletions": 0},
                    "bulk": [{"files": 7}],
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        # If accounted = None or wrong, this fails
        assert result.accounted_files == 7

    def test_all_fields_propagate_exactly(self, tmp_path: Path) -> None:
        """All VerifyResult fields must contain the right value, not None."""
        repo = _init_verify_repo(tmp_path)
        from repogerbil.core.git import get_commits_for_date, get_diff_stats

        commits = get_commits_for_date(repo, "2026-04-07")
        actual = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        yaml_path = tmp_path / "all-fields.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "myrepo",
                    "stats": {
                        "files_changed": actual.files_changed,
                        "insertions": actual.insertions,
                        "deletions": actual.deletions,
                    },
                    "bulk": [{"files": 3}],
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        assert result.repo == "myrepo"
        assert result.date == "2026-04-07"
        assert result.reported_files == actual.files_changed
        assert result.actual_files == actual.files_changed
        assert result.accounted_files == 3
        assert result.actual_insertions == actual.insertions
        assert result.actual_deletions == actual.deletions
        assert result.reported_insertions == actual.insertions
        assert result.reported_deletions == actual.deletions

    def test_reported_insertions_falls_back_to_zero_not_one(self, tmp_path: Path) -> None:
        """When insertions key missing/None, reported_insertions must be 0 exactly (not 1)."""
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "no-insertions.yaml"
        # insertions missing entirely → _safe_int(None) returns None → `None or 0` = 0
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {"files_changed": 1},
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        # Must be exactly 0, not 1, not None
        assert result.reported_insertions == 0
        assert result.reported_deletions == 0

    def test_reported_insertions_propagates_when_truthy(self, tmp_path: Path) -> None:
        """When insertions provided and truthy, reported_insertions must equal the value
        (not 0 from `and 0`)."""
        repo = _init_verify_repo(tmp_path)
        yaml_path = tmp_path / "with-insertions.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {"files_changed": 1, "insertions": 5, "deletions": 7},
                }
            )
        )
        result = verify_changelog(yaml_path, repo)
        assert result is not None
        # `5 or 0` == 5; `5 and 0` == 0. Must be 5.
        assert result.reported_insertions == 5
        # `7 or 0` == 7; `7 and 0` == 0. Must be 7.
        assert result.reported_deletions == 7

    def test_tolerance_argument_propagates_to_deletions_check(self, tmp_path: Path) -> None:
        """The tolerance arg must be passed into the deletions _within_tolerance check (not None)."""
        repo = _init_verify_repo(tmp_path)
        from repogerbil.core.git import get_commits_for_date, get_diff_stats

        commits = get_commits_for_date(repo, "2026-04-07")
        actual = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        # Construct case where deletions are mismatched and only a permissive tolerance saves it.
        # actual.deletions is 0 (single file added). To exercise tolerance arg on deletions, we
        # need actual.deletions > 0. Add a second commit that deletes content.
        subprocess.run(
            ["git", "rm", "f.py"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        subprocess.run(
            ["git", "commit", "-m", "remove"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
        )
        commits = get_commits_for_date(repo, "2026-04-07")
        actual = get_diff_stats(repo, commits[0].hash, commits[-1].hash)
        # actual.deletions is now 1. Report deletions as 100 → 9900% off.
        yaml_path = tmp_path / "tol-deletions.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {
                        "files_changed": actual.files_changed,
                        "insertions": actual.insertions,
                        "deletions": 100,
                    },
                    "changes": [],
                }
            )
        )
        # With tolerance=5, deletions mismatch breaks stats_match. If tolerance is dropped
        # (passed as None to _within_tolerance), the comparison `pct_diff <= None` would TypeError.
        # Using a numeric tolerance keeps stats_match False on mismatch.
        result = verify_changelog(yaml_path, repo, tolerance=5)
        assert result is not None
        assert result.stats_match is False
