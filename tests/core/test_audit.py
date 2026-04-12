# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for missing changelog audit."""

from pathlib import Path
import subprocess

import yaml

from repogerbil.core.audit import MissingDate, find_missing
from repogerbil.core.config import RepoOverride


def _init_repo(tmp_path: Path, name: str, dates: list[str]) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    for d in dates:
        (repo / f"{d}.txt").write_text(d)
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat: work on {d}"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": f"{d}T10:00:00", "GIT_COMMITTER_DATE": f"{d}T10:00:00"},
        )
    return repo


def _write_changelog(cl_dir: Path, repo_name: str, date: str) -> None:
    d = cl_dir / repo_name
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{date}-{repo_name}-changelog.yaml").write_text(yaml.dump({"date": date, "repo": repo_name}))


class TestFindMissing:
    def test_finds_missing_dates(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07", "2026-04-08"])
        cl_dir = tmp_path / "changelogs"
        _write_changelog(cl_dir, "myrepo", "2026-04-07")

        tracked = {"myrepo": str(repo)}
        result = find_missing(tracked, cl_dir)
        assert len(result) == 1
        assert result[0] == MissingDate(repo="myrepo", date="2026-04-08")

    def test_all_up_to_date(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07"])
        cl_dir = tmp_path / "changelogs"
        _write_changelog(cl_dir, "myrepo", "2026-04-07")

        result = find_missing({"myrepo": str(repo)}, cl_dir)
        assert result == []

    def test_nonexistent_repo_path(self, tmp_path: Path) -> None:
        result = find_missing({"gone": "/nonexistent/path"}, tmp_path / "changelogs")
        assert result == []

    def test_no_changelog_dir(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07"])
        result = find_missing({"myrepo": str(repo)}, tmp_path / "changelogs")
        assert len(result) == 1

    def test_multiple_repos(self, tmp_path: Path) -> None:
        repo_a = _init_repo(tmp_path, "repo-a", ["2026-04-07"])
        repo_b = _init_repo(tmp_path, "repo-b", ["2026-04-07", "2026-04-08"])
        tracked = {"repo-a": str(repo_a), "repo-b": str(repo_b)}
        result = find_missing(tracked, tmp_path / "changelogs")
        repos = {m.repo for m in result}
        assert "repo-a" in repos
        assert "repo-b" in repos


class TestSkipDates:
    def test_skip_dates_filters_results(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07", "2026-04-08"])
        cl_dir = tmp_path / "changelogs"
        # No changelogs at all — both dates missing

        overrides = {"myrepo": RepoOverride(skip_dates=["2026-04-07"])}
        result = find_missing({"myrepo": str(repo)}, cl_dir, repo_overrides=overrides)
        assert len(result) == 1
        assert result[0].date == "2026-04-08"

    def test_skip_dates_empty_list(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07"])
        overrides = {"myrepo": RepoOverride(skip_dates=[])}
        result = find_missing({"myrepo": str(repo)}, tmp_path / "changelogs", repo_overrides=overrides)
        assert len(result) == 1

    def test_skip_dates_no_override_for_repo(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07"])
        overrides = {"other": RepoOverride(skip_dates=["2026-04-07"])}
        result = find_missing({"myrepo": str(repo)}, tmp_path / "changelogs", repo_overrides=overrides)
        assert len(result) == 1


class TestArchivedRepos:
    def test_empty_path_triggers_gap_detection(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        # Changelogs for day 1 and day 3 — gap on day 2
        _write_changelog(cl_dir, "archived", "2026-04-01")
        _write_changelog(cl_dir, "archived", "2026-04-03")

        result = find_missing({"archived": ""}, cl_dir)
        assert MissingDate(repo="archived", date="2026-04-02") in result

    def test_no_changelogs_no_gaps(self, tmp_path: Path) -> None:
        result = find_missing({"archived": ""}, tmp_path / "changelogs")
        assert result == []

    def test_contiguous_changelogs_no_gaps(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(cl_dir, "archived", "2026-04-01")
        _write_changelog(cl_dir, "archived", "2026-04-02")
        _write_changelog(cl_dir, "archived", "2026-04-03")

        result = find_missing({"archived": ""}, cl_dir)
        assert result == []

    def test_skip_dates_with_archived(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(cl_dir, "archived", "2026-04-01")
        _write_changelog(cl_dir, "archived", "2026-04-03")

        overrides = {"archived": RepoOverride(skip_dates=["2026-04-02"])}
        result = find_missing({"archived": ""}, cl_dir, repo_overrides=overrides)
        assert result == []

    def test_nonexistent_source_path_uses_gap_detection(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(cl_dir, "gone", "2026-04-01")
        _write_changelog(cl_dir, "gone", "2026-04-03")

        result = find_missing({"gone": "/nonexistent/path"}, cl_dir)
        assert MissingDate(repo="gone", date="2026-04-02") in result

    def test_gap_detection_uses_full_existing_range(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(cl_dir, "archived", "2026-04-01")
        _write_changelog(cl_dir, "archived", "2026-04-03")
        _write_changelog(cl_dir, "archived", "2026-04-05")

        result = find_missing({"archived": ""}, cl_dir)

        assert result == [
            MissingDate(repo="archived", date="2026-04-02"),
            MissingDate(repo="archived", date="2026-04-04"),
        ]
