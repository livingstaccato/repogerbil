# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for git analysis module using temporary git repositories."""

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import (
    CommitInfo,
    DiffStats,
    _attach_file_lists,
    get_active_dates,
    get_commit_for_hash,
    get_commits_for_date,
    get_commits_for_hashes,
    get_diff_stats,
    get_hidden_ref_dates,
    get_hidden_ref_hashes,
    parse_shortstat,
)


@pytest.fixture()
def git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with a few commits."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)

    # Commit 1
    (repo / "file1.py").write_text("print('hello')\n")
    subprocess.run(["git", "add", "file1.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add file1"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-07T10:00:00",
            "GIT_COMMITTER_DATE": "2026-04-07T10:00:00",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )

    # Commit 2
    (repo / "file2.py").write_text("print('world')\n")
    subprocess.run(["git", "add", "file2.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: add file2"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-07T11:00:00",
            "GIT_COMMITTER_DATE": "2026-04-07T11:00:00",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )

    # Commit 3 — different day
    (repo / "file3.py").write_text("print('other')\n")
    subprocess.run(["git", "add", "file3.py"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: add file3"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-08T09:00:00",
            "GIT_COMMITTER_DATE": "2026-04-08T09:00:00",
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        },
    )

    return repo


class TestParseShortstat:
    def test_full_stat(self) -> None:
        result = parse_shortstat(" 3 files changed, 100 insertions(+), 50 deletions(-)")
        assert result == {"files_changed": 3, "insertions": 100, "deletions": 50}

    def test_insertions_only(self) -> None:
        result = parse_shortstat(" 1 file changed, 10 insertions(+)")
        assert result == {"files_changed": 1, "insertions": 10, "deletions": 0}

    def test_deletions_only(self) -> None:
        result = parse_shortstat(" 2 files changed, 5 deletions(-)")
        assert result == {"files_changed": 2, "insertions": 0, "deletions": 5}

    def test_empty_string(self) -> None:
        result = parse_shortstat("")
        assert result == {"files_changed": 0, "insertions": 0, "deletions": 0}


class TestGetActiveDates:
    def test_returns_dates(self, git_repo: Path) -> None:
        dates = get_active_dates(git_repo)
        assert "2026-04-07" in dates
        assert "2026-04-08" in dates

    def test_empty_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        dates = get_active_dates(repo)
        assert dates == set()


class TestGetCommitsForDate:
    def test_returns_commits_for_date(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07")
        assert len(commits) == 2
        assert all(isinstance(c, CommitInfo) for c in commits)
        assert commits[0].subject == "feat: add file1"
        assert commits[1].subject == "fix: add file2"

    def test_no_commits_for_date(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-01-01")
        assert commits == []

    def test_include_files(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07", include_files=True)
        assert len(commits) == 2
        assert "file1.py" in commits[0].files
        assert "file2.py" in commits[1].files

    def test_message_depth_subject(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07", message_depth="subject")
        assert commits[0].body == ""
        assert commits[0].refs == []

    def test_message_depth_refs(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07", message_depth="refs")
        assert len(commits) == 2
        # No refs in these commits
        assert commits[0].refs == []

    def test_message_depth_full(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07", message_depth="full")
        assert len(commits) == 2

    def test_oldest_first(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07")
        assert commits[0].subject == "feat: add file1"

    def test_include_files_with_body(self, git_repo: Path) -> None:
        """include_files works with message_depth=full."""
        commits = get_commits_for_date(
            git_repo,
            "2026-04-07",
            message_depth="full",
            include_files=True,
        )
        assert len(commits) == 2
        assert len(commits[0].files) >= 1


class TestGetDiffStats:
    def test_returns_stats(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07")
        stats = get_diff_stats(git_repo, commits[0].hash, commits[-1].hash)
        assert isinstance(stats, DiffStats)
        assert stats.files_changed >= 1
        assert stats.insertions >= 1

    def test_root_commit_fallback(self, git_repo: Path) -> None:
        """First commit in repo uses --root fallback."""
        commits = get_commits_for_date(git_repo, "2026-04-07")
        # The first commit's parent doesn't exist, triggering the --root path
        stats = get_diff_stats(git_repo, commits[0].hash, commits[0].hash)
        assert isinstance(stats, DiffStats)

    def test_empty_diff(self, tmp_path: Path) -> None:
        """Empty repo returns zero stats."""
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
        (repo / "f.txt").write_text("x")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init", "--allow-empty"], cwd=repo, capture_output=True, check=True
        )
        # Diff a commit with itself — no changes
        out = subprocess.run(
            ["git", "log", "--format=%H", "-1"], cwd=repo, capture_output=True, text=True, check=True
        )
        h = out.stdout.strip()
        stats = get_diff_stats(repo, h, h)
        assert stats.files_changed == 0


class TestGetDiffStatsMocked:
    def test_first_commit_fallback(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="\n"),
                MagicMock(returncode=0, stdout=" 1 file changed, 1 insertion(+)"),
            ]
            res = get_diff_stats(".", "hash1", "hash2")
            assert res.files_changed == 1
            assert mock_run.call_count == 2

    def test_empty_output(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="\n")
            res = get_diff_stats(".", "h1", "h2")
            assert res.files_changed == 0


class TestHiddenRefs:
    def test_hidden_ref_hashes_git_failure(self) -> None:
        with patch(
            "repogerbil.core.git._run_git",
            side_effect=GitCommandError("boom", returncode=1, stderr="boom"),
        ):
            assert get_hidden_ref_hashes(".") == []

    def test_hidden_ref_dates_git_failure(self) -> None:
        with (
            patch("repogerbil.core.git.get_hidden_ref_hashes", return_value=["a" * 40]),
            patch(
                "repogerbil.core.git._run_git",
                side_effect=GitCommandError("boom", returncode=1, stderr="boom"),
            ),
        ):
            assert get_hidden_ref_dates(".") == set()

    def test_hidden_ref_dates_ignores_empty_date(self) -> None:
        with (
            patch("repogerbil.core.git.get_hidden_ref_hashes", return_value=["a" * 40]),
            patch("repogerbil.core.git._run_git", return_value=" \n"),
        ):
            assert get_hidden_ref_dates(".") == set()


class TestCommitLookup:
    def test_get_commit_for_hash_invalid_output(self) -> None:
        with patch("repogerbil.core.git._run_git", return_value="bad-output"), pytest.raises(GitCommandError):
            get_commit_for_hash(".", "a" * 40)

    def test_get_commits_for_hashes(self, git_repo: Path) -> None:
        commits = get_commits_for_date(git_repo, "2026-04-07")
        hashes = [c.hash for c in commits]
        resolved = get_commits_for_hashes(git_repo, hashes, include_files=True)
        assert len(resolved) == len(hashes)
        assert all(c.files for c in resolved)

    def test_get_commit_for_hash_empty_files_output(self) -> None:
        h = "a" * 40
        with patch("repogerbil.core.git._run_git") as mock_run:
            mock_run.side_effect = [
                f"{h}\x002026-04-07\x00feat: test\x00body\n",
                "\n",
            ]
            commit = get_commit_for_hash(".", h, include_files=True)
            assert commit.files == []


class TestGetCommitsMocked:
    def test_full_message_with_body(self) -> None:
        h1, h2 = "a" * 40, "b" * 40
        output = (
            f"{h1}\x002026-04-10\x00feat: test\x00Body text\nFixes #123\x00END"
            f"{h2}\x002026-04-10\x00fix: other\x00\x00END"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            commits = get_commits_for_date(".", "2026-04-10", message_depth="full")
            assert len(commits) == 2
            assert commits[1].body == "Body text\nFixes #123"
            assert commits[1].refs == ["#123"]

    def test_subject_only_filters_by_date(self) -> None:
        h1, h2 = "a" * 40, "b" * 40
        output = f"{h1}\t2026-04-10\tfeat: test\n{h2}\t2026-04-11\tfix: other\n"
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            commits = get_commits_for_date(".", "2026-04-10", message_depth="subject")
            assert len(commits) == 1
            assert commits[0].subject == "feat: test"

    def test_empty_output_returns_empty(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            assert get_commits_for_date(".", "2026-04-10") == []

    def test_active_dates_empty(self) -> None:
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="\n")
            assert get_active_dates(".") == set()


class TestAttachFileLists:
    def test_basic_attach(self) -> None:
        h1 = "a" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout=f"{h1}\t2026-04-10\tfeat: test\n"),
                MagicMock(returncode=0, stdout=f"{h1}\nfile1.py\nfile2.py\n"),
            ]
            commits = get_commits_for_date(".", "2026-04-10", include_files=True)
            assert commits[0].files == ["file1.py", "file2.py"]

    def test_edge_case_empty_lines(self) -> None:
        h1 = "a" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=f"\n{h1}\nfile1.py\n\n")
            commits = [CommitInfo(hash=h1, date="2026-04-10", subject="test")]
            res = _attach_file_lists(".", commits)
            assert res[0].files == ["file1.py"]
