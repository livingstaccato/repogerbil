# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for missing changelog audit."""

from pathlib import Path
import subprocess

import yaml

from repogerbil.core.audit import MissingDate, find_missing


def _init_repo(tmp_path: Path, name: str, dates: list[str]) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
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


class TestFindMissing:
    def test_finds_missing_dates(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07", "2026-04-08"])
        cl_dir = tmp_path / "changelogs" / "myrepo"
        cl_dir.mkdir(parents=True)
        # Only create changelog for one date
        (cl_dir / "2026-04-07-myrepo-changelog.yaml").write_text(
            yaml.dump({"date": "2026-04-07", "repo": "myrepo"})
        )

        tracked = {"myrepo": str(repo)}
        result = find_missing(tracked, tmp_path / "changelogs")
        assert len(result) == 1
        assert result[0] == MissingDate(repo="myrepo", date="2026-04-08")

    def test_all_up_to_date(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path, "myrepo", ["2026-04-07"])
        cl_dir = tmp_path / "changelogs" / "myrepo"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-04-07-myrepo-changelog.yaml").write_text(
            yaml.dump({"date": "2026-04-07", "repo": "myrepo"})
        )

        result = find_missing({"myrepo": str(repo)}, tmp_path / "changelogs")
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
