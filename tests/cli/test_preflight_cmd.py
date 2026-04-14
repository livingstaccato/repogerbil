# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the preflight CLI command."""

from __future__ import annotations

from pathlib import Path
import subprocess

from click.testing import CliRunner

from repogerbil.cli.main import cli


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in [
        ["git", "init"],
        ["git", "config", "user.email", "t@t.com"],
        ["git", "config", "user.name", "T"],
    ]:
        subprocess.run(cmd, cwd=repo, capture_output=True, check=False)
    (repo / "main.py").write_text("x = 1\n")
    (repo / "poetry.lock").write_text("lock\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
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
        subprocess.run(["git", "add", "mystery.bin"], cwd=repo, capture_output=True)
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
        import subprocess as sp

        repo2 = tmp_path / "clean"
        repo2.mkdir()
        for cmd in [
            ["git", "init"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "T"],
        ]:
            sp.run(cmd, cwd=repo2, capture_output=True, check=False)
        (repo2 / "main.py").write_text("x = 1\n")
        sp.run(["git", "add", "."], cwd=repo2, capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=repo2, capture_output=True, check=True)
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
        repo2 = tmp_path / "clean2"
        repo2.mkdir()
        import subprocess as sp

        for cmd in [
            ["git", "init"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "T"],
        ]:
            sp.run(cmd, cwd=repo2, capture_output=True, check=False)
        (repo2 / "main.py").write_text("x = 1\n")
        sp.run(["git", "add", "."], cwd=repo2, capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=repo2, capture_output=True, check=True)
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
        import subprocess as sp

        repo2 = tmp_path / "artifacts_only"
        repo2.mkdir()
        for cmd in [
            ["git", "init"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "T"],
        ]:
            sp.run(cmd, cwd=repo2, capture_output=True, check=False)
        (repo2 / "poetry.lock").write_text("lock\n")
        sp.run(["git", "add", "."], cwd=repo2, capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=repo2, capture_output=True, check=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo2), "--verbose"])
        assert result.exit_code == 0
        assert "SOURCE" not in result.output

    def test_emit_flags_empty_repo_no_output(self, tmp_path: Path) -> None:
        repo2 = tmp_path / "clean3"
        repo2.mkdir()
        import subprocess as sp

        for cmd in [
            ["git", "init"],
            ["git", "config", "user.email", "t@t.com"],
            ["git", "config", "user.name", "T"],
        ]:
            sp.run(cmd, cwd=repo2, capture_output=True, check=False)
        (repo2 / "main.py").write_text("x = 1\n")
        sp.run(["git", "add", "."], cwd=repo2, capture_output=True)
        sp.run(["git", "commit", "-m", "init"], cwd=repo2, capture_output=True, check=True)
        runner = CliRunner()
        result = runner.invoke(cli, ["preflight", str(repo2), "--emit-flags"])
        assert result.exit_code == 0
        assert result.output.strip() == ""
