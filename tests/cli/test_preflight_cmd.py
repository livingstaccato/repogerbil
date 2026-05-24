# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the preflight CLI command."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from click.testing import CliRunner
import pytest

from repogerbil.cli.main import cli, main
from repogerbil.core.errors import (
    PreflightGitLogCommandFailedError,
    PreflightInvalidRevisionOrDateError,
    PreflightNotAGitRepositoryError,
)


def _make_repo(tmp_path: Path, with_lock: bool = True) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
    ]:
        subprocess.run(cmd, cwd=repo, capture_output=True, check=False)
    (repo / "main.py").write_text("x = 1\n")
    if with_lock:
        (repo / "poetry.lock").write_text("lock\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


class TestPreflightCmd:
    def test_basic_run_exits_zero(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo)])
        assert result.exit_code == 0, result.output

    def test_artifacts_section_present(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo)])
        assert "ARTIFACTS" in result.output

    def test_lock_file_flagged(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo)])
        assert "lock file" in result.output

    def test_emit_flags_outputs_only_flags(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo), "--emit-flags"])
        assert result.exit_code == 0
        lines = [line for line in result.output.splitlines() if line.strip()]
        assert all(line.startswith("--exclude-path") for line in lines)

    def test_unknown_section_for_mystery_file(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "mystery.bin").write_bytes(b"\xde\xad")
        subprocess.run(["git", "add", "mystery.bin"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "mystery"], cwd=repo, capture_output=True, check=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo)])
        assert "UNKNOWN" in result.output
        assert "mystery.bin" in result.output

    def test_verbose_shows_source(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo), "--verbose"])
        assert "SOURCE" in result.output
        assert "main.py" in result.output

    def test_no_artifacts_shows_none_message(self, tmp_path: Path) -> None:
        clean_dir = tmp_path / "clean"
        clean_dir.mkdir()
        repo2 = _make_repo(clean_dir, with_lock=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo2)])
        assert result.exit_code == 0
        assert "ARTIFACTS: none found" in result.output

    def test_since_option_accepted(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo), "--since", "2020-01-01"])
        assert result.exit_code == 0

    def test_until_option_accepted(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo), "--until", "2099-12-31"])
        assert result.exit_code == 0

    def test_no_suggested_flags_message(self, tmp_path: Path) -> None:
        clean_dir = tmp_path / "clean2"
        clean_dir.mkdir()
        repo2 = _make_repo(clean_dir, with_lock=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo2)])
        assert result.exit_code == 0
        assert "No exclude flags suggested." in result.output

    def test_suggested_flags_section_shown(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo)])
        assert "Suggested flags" in result.output

    def test_verbose_no_source_files(self, tmp_path: Path) -> None:
        """Verbose on a repo with only artifact files should not show SOURCE section."""
        repo2 = tmp_path / "artifacts_only"
        repo2.mkdir()
        for cmd in [
            ["git", "init"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "T"],
            ["git", "config", "commit.gpgsign", "false"],
        ]:
            subprocess.run(cmd, cwd=repo2, capture_output=True, check=False)
        (repo2 / "poetry.lock").write_text("lock\n")
        subprocess.run(["git", "add", "."], cwd=repo2, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo2, capture_output=True, check=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo2), "--verbose"])
        assert result.exit_code == 0
        assert "SOURCE" not in result.output

    def test_emit_flags_empty_repo_no_output(self, tmp_path: Path) -> None:
        clean_dir = tmp_path / "clean3"
        clean_dir.mkdir()
        repo2 = _make_repo(clean_dir, with_lock=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo2), "--emit-flags"])
        assert result.exit_code == 0
        assert result.output.strip() == ""

    def test_multiple_lock_types_both_flagged(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        # Add package-lock.json alongside poetry.lock
        (repo / "package-lock.json").write_text("{}\n")
        subprocess.run(["git", "add", "package-lock.json"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "add npm lock"], cwd=repo, capture_output=True, check=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo)])
        assert result.exit_code == 0
        # Both lock types should appear as separate rows
        assert "lock file" in result.output
        # Suggested flags section should have both
        assert "poetry" in result.output or "lock" in result.output

    def test_non_git_directory_shows_error(self, tmp_path: Path) -> None:
        non_git = tmp_path / "not_a_repo"
        non_git.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(non_git)])
        assert result.exit_code != 0

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (
                PreflightNotAGitRepositoryError(
                    repo_path="/tmp/notgit",
                    operation="collecting file history with git log",
                    command=("git", "log"),
                    returncode=128,
                    stderr="fatal: not a git repository",
                ),
                "category: not-a-git-repository",
            ),
            (
                PreflightInvalidRevisionOrDateError(
                    repo_path="/tmp/repo",
                    operation="collecting file history with git log",
                    command=("git", "log", "--since=bad"),
                    returncode=128,
                    stderr="fatal: invalid date format: bad",
                ),
                "category: invalid-revision-or-date",
            ),
            (
                PreflightGitLogCommandFailedError(
                    repo_path="/tmp/repo",
                    operation="collecting file history with git log",
                    command=("git", "log"),
                    returncode=2,
                    stderr="fatal: unexpected failure",
                ),
                "category: git-command-failed",
            ),
        ],
    )
    def test_top_level_main_surfaces_specific_preflight_errors(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        error: Exception,
        expected: str,
    ) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setattr(
            "repogerbil.cli.commands.preflight_cmd.scan_repo",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(error),
        )
        monkeypatch.setattr(sys, "argv", ["gerbil", "preflight", str(repo)])

        with pytest.raises(SystemExit) as caught:
            main()
        assert caught.value.code == 1
        stderr = capsys.readouterr().err
        assert "Error:" in stderr
        assert expected in stderr
