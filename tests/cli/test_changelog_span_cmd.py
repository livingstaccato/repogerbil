# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the changelog-span CLI command."""

from __future__ import annotations

from pathlib import Path
import subprocess

from click.testing import CliRunner
import pytest

from repogerbil.cli.commands.changelog_span_cmd import changelog_span_cmd


@pytest.fixture()
def tagged_repo(tmp_path: Path) -> Path:
    """Git repo with two commits and a tag between them."""
    repo = tmp_path / "repo"
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

    (repo / "a.py").write_text("a\n")
    subprocess.run(["git", "add", "a.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial"], cwd=repo, capture_output=True, check=True, env=env
    )
    subprocess.run(["git", "tag", "v0.0.1"], cwd=repo, capture_output=True, check=True)

    env["GIT_AUTHOR_DATE"] = "2026-04-08T10:00:00"
    env["GIT_COMMITTER_DATE"] = "2026-04-08T10:00:00"
    (repo / "b.py").write_text("b\n")
    subprocess.run(["git", "add", "b.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "fix: bugfix"], cwd=repo, capture_output=True, check=True, env=env)
    subprocess.run(["git", "tag", "v0.0.2"], cwd=repo, capture_output=True, check=True)
    return repo


def test_prints_prompt_when_no_output(tagged_repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        changelog_span_cmd,
        [str(tagged_repo), "--from", "v0.0.1", "--to", "v0.0.2"],
    )
    assert result.exit_code == 0
    assert "# Generate a release changelog" in result.output
    assert "v0.0.1" in result.output
    assert "v0.0.2" in result.output
    assert "fix: bugfix" in result.output
    assert "## Instructions" in result.output


def test_writes_output_file(tagged_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "prompt.md"
    runner = CliRunner()
    result = runner.invoke(
        changelog_span_cmd,
        [str(tagged_repo), "--from", "v0.0.1", "--to", "v0.0.2", "--output", str(out)],
    )
    assert result.exit_code == 0
    assert out.exists()
    assert "fix: bugfix" in out.read_text()
    assert f"Wrote prompt to {out}" in result.output


def test_empty_range_reports_message(tagged_repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        changelog_span_cmd,
        [str(tagged_repo), "--from", "v0.0.2", "--to", "v0.0.2"],
    )
    assert result.exit_code == 0
    assert "No commits" in result.output


def test_no_include_files_flag(tagged_repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        changelog_span_cmd,
        [str(tagged_repo), "--from", "v0.0.1", "--to", "v0.0.2", "--no-include-files"],
    )
    assert result.exit_code == 0
    assert "fix: bugfix" in result.output
