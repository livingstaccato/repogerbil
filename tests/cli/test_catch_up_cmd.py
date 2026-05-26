# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the sidecar metadata catch-up CLI command."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import subprocess

from click.testing import CliRunner

from repogerbil.cli.main import cli


def _commit(repo: Path, file: str, content: str, message: str) -> None:
    (repo / file).write_text(content)
    subprocess.run(["git", "add", file], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, capture_output=True, check=True)


class TestCatchUpCmd:
    def test_basic_run_writes_jsonl(self, tmp_path: Path, make_git_repo: Callable[[str], Path]) -> None:
        repo = make_git_repo("r")
        _commit(repo, "a.txt", "1", "feat: one")
        _commit(repo, "b.txt", "2", "fix: two")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = CliRunner().invoke(cli, ["catch-up", str(repo), str(jsonl)])
        assert result.exit_code == 0, result.output
        assert jsonl.exists()
        lines = [line for line in jsonl.read_text().splitlines() if line.strip()]
        assert len(lines) == 2
        assert "recorded: 2" in result.output

    def test_dry_run_does_not_write(self, tmp_path: Path, make_git_repo: Callable[[str], Path]) -> None:
        repo = make_git_repo("r")
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = CliRunner().invoke(cli, ["catch-up", str(repo), str(jsonl), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert not jsonl.exists()
        assert "would record: 1" in result.output

    def test_idempotent_second_run_reports_zero(
        self, tmp_path: Path, make_git_repo: Callable[[str], Path]
    ) -> None:
        repo = make_git_repo("r")
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        first = CliRunner().invoke(cli, ["catch-up", str(repo), str(jsonl)])
        assert first.exit_code == 0
        second = CliRunner().invoke(cli, ["catch-up", str(repo), str(jsonl)])
        assert second.exit_code == 0
        assert "recorded: 0" in second.output
        assert "already recorded: 1" in second.output

    def test_legacy_append_alias_still_works(
        self, tmp_path: Path, make_git_repo: Callable[[str], Path]
    ) -> None:
        repo = make_git_repo("r")
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = CliRunner().invoke(cli, ["append", str(repo), str(jsonl)])
        assert result.exit_code == 0, result.output
        assert "recorded: 1" in result.output
