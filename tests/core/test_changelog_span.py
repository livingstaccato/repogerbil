# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for generate_prompt_span and get_commits_for_range."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from repogerbil.core.changelog import generate_prompt_span
from repogerbil.core.git import CommitInfo, DiffStats, get_commits_for_range


@pytest.fixture()
def range_repo(tmp_path: Path) -> Path:
    """Repo with three commits + two tags at boundaries."""
    repo = tmp_path / "r"
    repo.mkdir()
    env = {
        "GIT_AUTHOR_DATE": "2026-04-01T10:00:00",
        "GIT_COMMITTER_DATE": "2026-04-01T10:00:00",
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

    for idx, (day, subj, fname) in enumerate(
        [
            ("2026-04-01T10:00:00", "feat: one", "a.py"),
            ("2026-04-02T10:00:00", "fix: two", "b.py"),
            ("2026-04-03T10:00:00", "docs: three", "c.py"),
        ]
    ):
        env["GIT_AUTHOR_DATE"] = day
        env["GIT_COMMITTER_DATE"] = day
        (repo / fname).write_text(f"commit {idx}\n")
        subprocess.run(["git", "add", fname], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", subj], cwd=repo, capture_output=True, check=True, env=env)

    subprocess.run(
        ["git", "tag", "start"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-01T10:00:01"},
    )
    subprocess.run(["git", "tag", "start", "HEAD~2", "-f"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "tag", "end", "HEAD", "-f"], cwd=repo, capture_output=True, check=True)
    return repo


def test_get_commits_for_range_oldest_first(range_repo: Path) -> None:
    commits = get_commits_for_range(range_repo, "start", "end")
    assert len(commits) == 2
    assert commits[0].subject == "fix: two"
    assert commits[1].subject == "docs: three"


def test_get_commits_for_range_include_files(range_repo: Path) -> None:
    commits = get_commits_for_range(range_repo, "start", "end", include_files=True)
    assert commits[0].files == ["b.py"]
    assert commits[1].files == ["c.py"]


def test_get_commits_for_range_empty(range_repo: Path) -> None:
    commits = get_commits_for_range(range_repo, "end", "end")
    assert commits == []


def _make_commit(sha: str, subject: str, files: list[str] | None = None) -> CommitInfo:
    return CommitInfo(hash=sha, date="2026-04-01", subject=subject, timestamp=1, files=files or [])


def test_generate_prompt_span_includes_commits_and_stats() -> None:
    commits = [
        _make_commit("aaa", "feat: add thing", ["src/a.py"]),
        _make_commit("bbb", "fix: correct it", ["src/b.py"]),
    ]
    stats = DiffStats(commits=2, files_changed=2, insertions=10, deletions=3)
    prompt = generate_prompt_span("repo", "v0.1.0", "v0.1.1", commits, stats, {})
    assert "# Generate a release changelog for repo" in prompt
    assert "v0.1.0" in prompt
    assert "v0.1.1" in prompt
    assert "2 commits, 2 files changed, +10/-3" in prompt
    assert "feat: add thing" in prompt
    assert "fix: correct it" in prompt
    assert "files: src/a.py" in prompt
    assert "Output the markdown block only" in prompt


def test_generate_prompt_span_with_diffs_attached() -> None:
    commits = [_make_commit("aaa", "feat: x")]
    stats = DiffStats(commits=1, files_changed=1, insertions=1, deletions=0)
    diffs = {"src/x.py": "@@ -0 +1 @@\n+print('x')\n"}
    prompt = generate_prompt_span("r", "a", "b", commits, stats, diffs)
    assert "## Diffs (key files)" in prompt
    assert "### src/x.py" in prompt


def test_generate_prompt_span_commit_without_files() -> None:
    commits = [_make_commit("aaa", "docs: readme")]
    stats = DiffStats(commits=1, files_changed=0, insertions=0, deletions=0)
    prompt = generate_prompt_span("r", "a", "b", commits, stats, {})
    assert "docs: readme" in prompt
    assert "files:" not in prompt.split("## Instructions")[0].split("docs: readme")[1]
