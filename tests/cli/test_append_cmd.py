# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the append CLI command."""

from __future__ import annotations

from pathlib import Path
import subprocess

from click.testing import CliRunner

from repogerbil.cli.main import cli


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    for cmd in [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.test"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
    ]:
        subprocess.run(cmd, cwd=repo, capture_output=True, check=False)


def _commit(repo: Path, file: str, content: str, message: str) -> None:
    (repo / file).write_text(content)
    subprocess.run(["git", "add", file], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, capture_output=True, check=True)


class TestAppendCmd:
    def test_basic_run_writes_jsonl(self, tmp_path: Path) -> None:
        repo = tmp_path / "r"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        _commit(repo, "b.txt", "2", "fix: two")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = CliRunner().invoke(cli, ["append", str(repo), str(jsonl)])
        assert result.exit_code == 0, result.output
        assert jsonl.exists()
        lines = [line for line in jsonl.read_text().splitlines() if line.strip()]
        assert len(lines) == 2
        assert "appended: 2" in result.output

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        repo = tmp_path / "r"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = CliRunner().invoke(cli, ["append", str(repo), str(jsonl), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert not jsonl.exists()
        assert "would append: 1" in result.output

    def test_idempotent_second_run_reports_zero(self, tmp_path: Path) -> None:
        repo = tmp_path / "r"
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        first = CliRunner().invoke(cli, ["append", str(repo), str(jsonl)])
        assert first.exit_code == 0
        second = CliRunner().invoke(cli, ["append", str(repo), str(jsonl)])
        assert second.exit_code == 0
        assert "appended: 0" in second.output
        assert "skipped (already recorded): 1" in second.output
