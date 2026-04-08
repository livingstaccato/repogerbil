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


class TestHasCoverageGap:
    def test_no_gap(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 10}]}, actual_files=10) is False

    def test_gap(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 2}]}, actual_files=20) is True

    def test_zero_actual(self) -> None:
        assert has_coverage_gap({}, actual_files=0) is False

    def test_within_tolerance(self) -> None:
        assert has_coverage_gap({"bulk": [{"files": 8}]}, actual_files=10, tolerance=30) is False


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
