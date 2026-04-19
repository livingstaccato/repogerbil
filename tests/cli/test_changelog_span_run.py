# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the --run flag on the changelog-span CLI command."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

from click.testing import CliRunner
import pytest

from repogerbil.cli.commands.changelog_span_cmd import changelog_span_cmd
from repogerbil.core.llm_runner import LlmRunnerError


@pytest.fixture()
def small_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "r"
    repo.mkdir()
    env = {
        "GIT_AUTHOR_DATE": "2026-04-07T10:00:00",
        "GIT_COMMITTER_DATE": "2026-04-07T10:00:00",
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }
    for cmd in (
        ["git", "init"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
    ):
        subprocess.run(cmd, cwd=repo, capture_output=True, check=True)
    (repo / "a.py").write_text("x\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "feat: init"], cwd=repo, capture_output=True, check=True, env=env)
    subprocess.run(["git", "tag", "start"], cwd=repo, capture_output=True, check=True)

    env["GIT_AUTHOR_DATE"] = "2026-04-08T10:00:00"
    env["GIT_COMMITTER_DATE"] = "2026-04-08T10:00:00"
    (repo / "b.py").write_text("y\n")
    subprocess.run(["git", "add", "b.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "fix: more"], cwd=repo, capture_output=True, check=True, env=env)
    subprocess.run(["git", "tag", "end"], cwd=repo, capture_output=True, check=True)
    return repo


def test_run_claude_writes_changelog(small_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "CHANGELOG.md"
    with patch(
        "repogerbil.cli.commands.changelog_span_cmd.run_claude_cli",
        return_value="## [0.0.2] — 2026-04-08\n\n### Fixes\n- fix stuff\n",
    ):
        runner = CliRunner()
        result = runner.invoke(
            changelog_span_cmd,
            [
                str(small_repo),
                "--from",
                "start",
                "--to",
                "end",
                "--run",
                "claude",
                "--output",
                str(out),
            ],
        )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "## [0.0.2]" in out.read_text()
    assert "Wrote changelog to" in result.output


def test_run_claude_failure_raises_click_exception(small_repo: Path) -> None:
    with patch(
        "repogerbil.cli.commands.changelog_span_cmd.run_claude_cli",
        side_effect=LlmRunnerError("claude CLI failed (rc=2)"),
    ):
        runner = CliRunner()
        result = runner.invoke(
            changelog_span_cmd,
            [str(small_repo), "--from", "start", "--to", "end", "--run", "claude"],
        )
    assert result.exit_code != 0
    assert "claude CLI failed" in result.output


def test_run_agent_prints_dispatch(small_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "prompt.md"
    runner = CliRunner()
    result = runner.invoke(
        changelog_span_cmd,
        [str(small_repo), "--from", "start", "--to", "end", "--run", "agent", "--output", str(out)],
    )
    assert result.exit_code == 0
    assert "repogerbil:analyzer:analyzer" in result.output
    assert str(out) in result.output
    assert out.exists()


def test_run_agent_default_path(small_repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        changelog_span_cmd,
        [str(small_repo), "--from", "start", "--to", "end", "--run", "agent"],
    )
    assert result.exit_code == 0
    assert "-changelog-prompt.md" in result.output
