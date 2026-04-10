# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for snapshot/distill CLI commands."""

from __future__ import annotations

from pathlib import Path
import subprocess

from click.testing import CliRunner
import yaml

from repogerbil.cli.main import cli


def _init_test_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with two commits on the same date."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / "f.py").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
    )
    (repo / "g.py").write_text("y\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: second"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
    )
    return repo


class TestSnapshot:
    def test_basic_snapshot(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest)])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output

    def test_snapshot_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest)])
        assert "No commits" in result.output

    def test_snapshot_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest), "--since", "2026-04-07"])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output

    def test_snapshot_with_changelog_dir(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl" / "repo"
        cl_dir.mkdir(parents=True)
        changelog = {
            "date": "2026-04-07",
            "repo": "repo",
            "title": "Daily update",
            "summary": "Two changes.",
            "stats": {"commits": 2, "files_changed": 2, "insertions": 2, "deletions": 0},
            "changes": [],
        }
        (cl_dir / "2026-04-07-repo-changelog.yaml").write_text(yaml.dump(changelog))
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest), "--changelog-dir", str(cl_dir)])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output


class TestExportCadence:
    def test_export_to_stdout(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo)])
        assert result.exit_code == 0
        assert "date" in result.output  # JSON contains date fields

    def test_export_to_file(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out_file = tmp_path / "cadence.json"
        result = CliRunner().invoke(cli, ["export-cadence", str(repo), "--output", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        assert "Exported" in result.output

    def test_export_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo)])
        assert "No commits" in result.output

    def test_export_with_cadence(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo), "--cadence", "weekly"])
        assert result.exit_code == 0

    def test_export_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0


class TestPreview:
    def _init_many_commits(self, tmp_path: Path) -> Path:
        """Create a repo with 4 commits on the same day to exercise the overflow line."""
        repo = tmp_path / "many"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        for i in range(4):
            (repo / f"f{i}.py").write_text(f"x{i}\n")
            subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: change {i}"],
                cwd=repo,
                capture_output=True,
                check=True,
                env={
                    **env,
                    "GIT_AUTHOR_DATE": f"2026-04-07T1{i}:00:00",
                    "GIT_COMMITTER_DATE": f"2026-04-07T1{i}:00:00",
                },
            )
        return repo

    def test_preview_output(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo)])
        assert result.exit_code == 0
        assert "commits" in result.output
        assert "groups" in result.output

    def test_preview_many_commits_shows_overflow(self, tmp_path: Path) -> None:
        repo = self._init_many_commits(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo)])
        assert result.exit_code == 0
        assert "more" in result.output

    def test_preview_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["preview", str(repo)])
        assert "No commits" in result.output

    def test_preview_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0

    def test_preview_with_cadence(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo), "--cadence", "weekly"])
        assert result.exit_code == 0
        assert "groups" in result.output
