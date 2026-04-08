# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI commands."""

from pathlib import Path
import subprocess

from click.testing import CliRunner

from repogerbil.cli.main import cli


def _init_test_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for CLI testing."""
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
    return repo


class TestHelp:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "repogerbil" in result.output


class TestStatus:
    def test_status(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["status", str(repo)])
        assert result.exit_code == 0
        assert "Active dates" in result.output

    def test_status_invalid_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "/nonexistent"])
        assert result.exit_code != 0


class TestChangelog:
    def test_draft_mode(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        assert result.exit_code == 0
        assert "Wrote" in result.output

    def test_analyze_mode(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "changelog",
                str(repo),
                "--date",
                "2026-04-07",
                "--output-dir",
                str(out),
                "--analyze",
            ],
        )
        assert result.exit_code == 0

    def test_no_commits(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["changelog", str(repo), "--date", "2020-01-01"])
        assert "No commits" in result.output

    def test_exists_no_force(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        result = runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        assert "Exists" in result.output

    def test_force_overwrite(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        result = runner.invoke(
            cli,
            [
                "changelog",
                str(repo),
                "--date",
                "2026-04-07",
                "--output-dir",
                str(out),
                "--force",
            ],
        )
        assert "Wrote" in result.output

    def test_prompt_mode(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "changelog",
                str(repo),
                "--date",
                "2026-04-07",
                "--output-dir",
                str(out),
                "--prompt",
            ],
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output


class TestVerify:
    def test_verify_clean(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "changelog",
                str(repo),
                "--date",
                "2026-04-07",
                "--output-dir",
                str(out),
                "--analyze",
            ],
        )
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo)])
        assert result.exit_code == 0


class TestAudit:
    def test_audit(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", str(repo)])
        assert result.exit_code == 0
        assert "classifiable" in result.output

    def test_audit_show_bad(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["audit", str(repo), "--show-bad"])
        assert result.exit_code == 0


class TestSquash:
    def test_dry_run(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["squash", str(repo), "--dry-run"])
        assert result.exit_code == 0
        assert "groups" in result.output

    def test_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["squash", str(repo), "--dry-run"])
        assert "No commits" in result.output


class TestFixStats:
    def test_fix_stats(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        runner.invoke(
            cli,
            [
                "changelog",
                str(repo),
                "--date",
                "2026-04-07",
                "--output-dir",
                str(out),
                "--analyze",
            ],
        )
        result = runner.invoke(cli, ["fix-stats", str(out / repo.name), str(repo)])
        assert result.exit_code == 0
        assert "updated" in result.output
