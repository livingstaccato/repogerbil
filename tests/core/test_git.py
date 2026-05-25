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
    get_commits_for_path,
    get_diff_stats,
    get_hidden_ref_dates,
    get_hidden_ref_hashes,
    parse_shortstat,
    resolve_head_branch,
)


@pytest.fixture()
def repo_with_commits(tmp_path: Path) -> Path:
    """Create a temporary git repo seeded with a few fixed-date commits.

    Distinct from the shared empty ``git_repo`` fixture in
    ``tests/conftest.py``; this one seeds the repo with three commits across
    two dates (2026-04-07 and 2026-04-08) so the tests below can verify
    date/commit-lookup behavior without re-creating commits each time.
    Renamed from ``git_repo`` to avoid shadowing the conftest fixture.
    """
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
    def test_returns_dates(self, repo_with_commits: Path) -> None:
        dates = get_active_dates(repo_with_commits)
        assert "2026-04-07" in dates
        assert "2026-04-08" in dates

    def test_empty_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        dates = get_active_dates(repo)
        assert dates == set()


class TestResolveHeadBranch:
    def test_returns_current_branch(self, repo_with_commits: Path) -> None:
        branch = resolve_head_branch(repo_with_commits)
        assert branch != ""

    def test_detached_head_raises(self, repo_with_commits: Path) -> None:
        subprocess.run(["git", "checkout", "--detach"], cwd=repo_with_commits, capture_output=True, check=True)
        with pytest.raises(GitCommandError, match="Unable to resolve source branch"):
            resolve_head_branch(repo_with_commits)

    def test_empty_branch_name_raises(self) -> None:
        with (
            patch("repogerbil.core.git._commits._run_git", return_value="  \n"),
            pytest.raises(GitCommandError, match="Unable to resolve source branch"),
        ):
            resolve_head_branch(".")


class TestGetCommitsForDate:
    def test_returns_commits_for_date(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        assert len(commits) == 2
        assert all(isinstance(c, CommitInfo) for c in commits)
        assert commits[0].subject == "feat: add file1"
        assert commits[1].subject == "fix: add file2"

    def test_no_commits_for_date(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-01-01")
        assert commits == []

    def test_include_files(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07", include_files=True)
        assert len(commits) == 2
        assert "file1.py" in commits[0].files
        assert "file2.py" in commits[1].files

    def test_message_depth_subject(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07", message_depth="subject")
        assert commits[0].body == ""
        assert commits[0].refs == []

    def test_message_depth_refs(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07", message_depth="refs")
        assert len(commits) == 2
        # No refs in these commits
        assert commits[0].refs == []

    def test_message_depth_full(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07", message_depth="full")
        assert len(commits) == 2

    def test_oldest_first(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        assert commits[0].subject == "feat: add file1"

    def test_include_files_with_body(self, repo_with_commits: Path) -> None:
        """include_files works with message_depth=full."""
        commits = get_commits_for_date(
            repo_with_commits,
            "2026-04-07",
            message_depth="full",
            include_files=True,
        )
        assert len(commits) == 2
        assert len(commits[0].files) >= 1


class TestGetDiffStats:
    def test_returns_stats(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        stats = get_diff_stats(repo_with_commits, commits[0].hash, commits[-1].hash)
        assert isinstance(stats, DiffStats)
        assert stats.files_changed >= 1
        assert stats.insertions >= 1

    def test_root_commit_fallback(self, repo_with_commits: Path) -> None:
        """Single-commit call on the root commit exercises the --root fallback and returns real stats."""
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        # Passing the same hash for first and last triggers the single-commit path.
        # The root commit adds file1.py, so stats must be non-zero.
        stats = get_diff_stats(repo_with_commits, commits[0].hash, commits[0].hash)
        assert isinstance(stats, DiffStats)
        assert stats.files_changed >= 1
        assert stats.insertions >= 1

    def test_single_commit_root(self, tmp_path: Path) -> None:
        """Repo with exactly one commit exercises the --root fallback for a true root commit."""
        repo = tmp_path / "single"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
        (repo / "hello.py").write_text("print('hello')\n")
        subprocess.run(["git", "add", "hello.py"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
        out = subprocess.run(
            ["git", "log", "--format=%H", "-1"], cwd=repo, capture_output=True, text=True, check=True
        )
        h = out.stdout.strip()
        stats = get_diff_stats(repo, h, h)
        assert isinstance(stats, DiffStats)
        assert stats.files_changed >= 1
        assert stats.insertions >= 1

    def test_empty_diff(self, tmp_path: Path) -> None:
        """A truly empty commit (no file changes) returns zero stats."""
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
        # Use --allow-empty with no staged files so the commit itself has no diff
        subprocess.run(
            ["git", "commit", "--allow-empty", "-m", "empty"], cwd=repo, capture_output=True, check=True
        )
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
            "repogerbil.core.git._commits._run_git",
            side_effect=GitCommandError("boom", returncode=1, stderr="boom"),
        ):
            assert get_hidden_ref_hashes(".") == []

    def test_hidden_ref_dates_git_failure(self) -> None:
        with (
            patch("repogerbil.core.git._commits.get_hidden_ref_hashes", return_value=["a" * 40]),
            patch(
                "repogerbil.core.git._commits._run_git",
                side_effect=GitCommandError("boom", returncode=1, stderr="boom"),
            ),
        ):
            assert get_hidden_ref_dates(".") == set()

    def test_hidden_ref_dates_ignores_empty_date(self) -> None:
        with (
            patch("repogerbil.core.git._commits.get_hidden_ref_hashes", return_value=["a" * 40]),
            patch("repogerbil.core.git._commits._run_git", return_value=" \n"),
        ):
            assert get_hidden_ref_dates(".") == set()


class TestCommitLookup:
    def test_get_commit_for_hash_invalid_output(self) -> None:
        with (
            patch("repogerbil.core.git._commits._run_git", return_value="bad-output"),
            pytest.raises(GitCommandError),
        ):
            get_commit_for_hash(".", "a" * 40)

    def test_get_commits_for_hashes(self, repo_with_commits: Path) -> None:
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        hashes = [c.hash for c in commits]
        resolved = get_commits_for_hashes(repo_with_commits, hashes, include_files=True)
        assert len(resolved) == len(hashes)
        assert all(c.files for c in resolved)

    def test_get_commit_for_hash_empty_files_output(self) -> None:
        h = "a" * 40
        with patch("repogerbil.core.git._commits._run_git") as mock_run:
            mock_run.side_effect = [
                f"{h}\x002026-04-07\x001234567890\x00feat: test\x00body\n",
                "\n",
            ]
            commit = get_commit_for_hash(".", h, include_files=True)
            assert commit.files == []


class TestGetCommitsMocked:
    def test_full_message_with_body(self) -> None:
        h1, h2 = "a" * 40, "b" * 40
        output = (
            f"{h1}\x002026-04-10\x001234567890\x00feat: test\x00Body text\nFixes #123\x00END"
            f"{h2}\x002026-04-10\x001234567891\x00fix: other\x00\x00END"
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=output)
            commits = get_commits_for_date(".", "2026-04-10", message_depth="full")
            assert len(commits) == 2
            assert commits[1].body == "Body text\nFixes #123"
            assert commits[1].refs == ["#123"]

    def test_subject_only_filters_by_date(self) -> None:
        h1, h2 = "a" * 40, "b" * 40
        output = f"{h1}\t2026-04-10\t1234567890\tfeat: test\n{h2}\t2026-04-11\t1234567891\tfix: other\n"
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
                MagicMock(returncode=0, stdout=f"{h1}\t2026-04-10\t1234567890\tfeat: test\n"),
                MagicMock(returncode=0, stdout=f"\x00{h1}\nfile1.py\nfile2.py\n"),
            ]
            commits = get_commits_for_date(".", "2026-04-10", include_files=True)
            assert commits[0].files == ["file1.py", "file2.py"]

    def test_edge_case_empty_lines(self) -> None:
        h1 = "a" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=f"\n\x00{h1}\nfile1.py\n\n")
            commits = [CommitInfo(hash=h1, date="2026-04-10", subject="test")]
            res = _attach_file_lists(".", commits)
            assert res[0].files == ["file1.py"]

    def test_preserves_timestamp(self) -> None:
        """_attach_file_lists must preserve CommitInfo.timestamp (regression: was dropped)."""
        h1 = "a" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=f"\x00{h1}\nfile1.py\n")
            commits = [CommitInfo(hash=h1, date="2026-04-10", subject="test", timestamp=1234567890)]
            res = _attach_file_lists(".", commits)
            assert res[0].timestamp == 1234567890

    def test_attach_handles_hex_like_filename(self) -> None:
        """A filename of exactly 40 lowercase hex chars must not be misread as a hash."""
        h1 = "a" * 40
        hex_filename = "0" * 40
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=f"\x00{h1}\n{hex_filename}\nother.py\n")
            commits = [CommitInfo(hash=h1, date="2026-04-10", subject="test")]
            res = _attach_file_lists(".", commits)
            assert res[0].files == [hex_filename, "other.py"]

    def test_attach_handles_sha256_hash(self) -> None:
        """Parser must accept 64-char SHA-256 hashes via the NUL sentinel."""
        h1 = "b" * 64
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=f"\x00{h1}\nfile1.py\n")
            commits = [CommitInfo(hash=h1, date="2026-04-10", subject="test")]
            res = _attach_file_lists(".", commits)
            assert res[0].files == ["file1.py"]


class TestCommitTimestamps:
    def test_timestamp_populated_from_git_log(self, repo_with_commits: Path) -> None:
        """CommitInfo.timestamp is populated from git log %at field."""
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        assert len(commits) == 2
        # Both commits should have non-zero timestamp
        assert commits[0].timestamp != 0
        assert commits[1].timestamp != 0
        # Second commit (11:00) should have later timestamp than first (10:00)
        assert commits[1].timestamp > commits[0].timestamp

    def test_timestamp_with_message_depth_full(self, repo_with_commits: Path) -> None:
        """Timestamp is populated with message_depth='full'."""
        commits = get_commits_for_date(repo_with_commits, "2026-04-07", message_depth="full")
        assert all(c.timestamp != 0 for c in commits)

    def test_timestamp_with_message_depth_refs(self, repo_with_commits: Path) -> None:
        """Timestamp is populated with message_depth='refs'."""
        commits = get_commits_for_date(repo_with_commits, "2026-04-07", message_depth="refs")
        assert all(c.timestamp != 0 for c in commits)

    def test_get_commit_for_hash_includes_timestamp(self, repo_with_commits: Path) -> None:
        """get_commit_for_hash includes timestamp."""
        commits = get_commits_for_date(repo_with_commits, "2026-04-07")
        commit = get_commit_for_hash(repo_with_commits, commits[0].hash)
        assert commit.timestamp != 0
        assert commit.timestamp == commits[0].timestamp


@pytest.fixture()
def monorepo(tmp_path: Path) -> Path:
    """Create a temporary monorepo with nested package structure."""
    repo = tmp_path / "mono"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)

    env = {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }

    # Commit 1: add pyvider-cty files
    (repo / "pyvider-cty").mkdir()
    (repo / "pyvider-cty" / "file1.py").write_text("cty code\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add pyvider-cty"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
    )

    # Commit 2: add pyvider-rpcplugin files
    (repo / "pyvider-rpcplugin").mkdir()
    (repo / "pyvider-rpcplugin" / "file2.py").write_text("rpc code\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add pyvider-rpcplugin"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
    )

    # Commit 3: modify pyvider-cty only
    (repo / "pyvider-cty" / "file1.py").write_text("cty code v2\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: update pyvider-cty"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-08T10:00:00", "GIT_COMMITTER_DATE": "2026-04-08T10:00:00"},
    )

    return repo


class TestGetCommitsForPath:
    def test_filters_commits_by_subdir(self, monorepo: Path) -> None:
        """Returns only commits that touched the specified subdirectory."""
        commits = get_commits_for_path(monorepo, "pyvider-cty")
        # Should get commits 1 and 3 (added cty, then modified cty)
        assert len(commits) == 2
        assert "pyvider-cty" in commits[0].subject
        assert "pyvider-cty" in commits[1].subject

    def test_excludes_unrelated_subdir(self, monorepo: Path) -> None:
        """Excludes commits that didn't touch this subdirectory."""
        commits = get_commits_for_path(monorepo, "pyvider-rpcplugin")
        # Should get only commit 2 (added rpc)
        assert len(commits) == 1
        assert "rpcplugin" in commits[0].subject

    def test_chronological_order(self, monorepo: Path) -> None:
        """Results are in chronological order (oldest first)."""
        commits = get_commits_for_path(monorepo, "pyvider-cty")
        assert commits[0].date == "2026-04-07"
        assert commits[1].date == "2026-04-08"

    def test_includes_timestamp(self, monorepo: Path) -> None:
        """Commits include timestamp field."""
        commits = get_commits_for_path(monorepo, "pyvider-cty")
        assert all(c.timestamp != 0 for c in commits)

    def test_with_message_depth_full(self, monorepo: Path) -> None:
        """get_commits_for_path supports message_depth parameter."""
        commits = get_commits_for_path(monorepo, "pyvider-cty", message_depth="full")
        assert len(commits) == 2
        # With full depth, body should be populated (even if empty)
        assert all(isinstance(c.body, str) for c in commits)

    def test_with_message_depth_refs(self, monorepo: Path) -> None:
        """get_commits_for_path with message_depth='refs' extracts issue refs."""
        commits = get_commits_for_path(monorepo, "pyvider-cty", message_depth="refs")
        assert len(commits) == 2
        # Refs depth should have empty body
        assert all(c.body == "" for c in commits)
        # Should have refs list (even if empty for these test commits)
        assert all(isinstance(c.refs, list) for c in commits)

    def test_all_branches_false(self, monorepo: Path) -> None:
        """get_commits_for_path respects all_branches=False."""
        # On main branch, should still get both commits (both are on main)
        commits = get_commits_for_path(monorepo, "pyvider-cty", all_branches=False)
        assert len(commits) == 2

    def test_with_include_files(self, monorepo: Path) -> None:
        """get_commits_for_path attaches per-commit file lists when requested."""
        commits = get_commits_for_path(monorepo, "pyvider-cty", include_files=True)
        assert len(commits) == 2
        # Files should be attached
        assert commits[0].files is not None
        assert len(commits[0].files) > 0  # pyvider-cty/ was created/modified

    def test_subject_only_skips_malformed_lines(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """A line with too few NUL separators is silently skipped.

        The subject-only branch in get_commits_for_path uses ``%H%x00%as%x00%at%x00%s``
        and splits on ``\\x00`` with maxsplit 3. If git produces a malformed line
        with fewer separators (defensive guard for unexpected output), the parser
        must not crash — it skips the line and continues with the valid ones.
        """
        import repogerbil.core.git._commits as commits_mod

        valid = "a" * 40 + "\x002026-04-07\x00123\x00feat: valid"
        # Single NUL → only 2 parts after split → must be skipped (no IndexError).
        malformed = "garbage\x00line"

        def fake_run_git(repo_path: object, *args: object, **kwargs: object) -> str:
            return f"{malformed}\n{valid}\n"

        monkeypatch.setattr(commits_mod, "_run_git", fake_run_git)

        result = commits_mod.get_commits_for_path(tmp_path, "any-subdir")

        assert len(result) == 1
        assert result[0].hash == "a" * 40
        assert result[0].subject == "feat: valid"


class TestDeduplication:
    def test_get_commits_for_range_ignores_malformed_lines(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        from repogerbil.core.git import get_commits_for_range
        import repogerbil.core.git._trees as trees

        def fake_run_git(repo_path: Path, *args: str) -> str:
            return "malformed\n" + "a" * 40 + "\t2026-04-07\t123\tfeat: valid\n"

        monkeypatch.setattr(trees, "_run_git", fake_run_git)

        commits = get_commits_for_range(tmp_path, "old", "new")

        assert len(commits) == 1
        assert commits[0].subject == "feat: valid"

    def test_attach_commit_files_from_range_ignores_lines_before_hash(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        import repogerbil.core.git._trees as trees

        def fake_run_git(repo_path: Path, *args: str) -> str:
            return "orphan.py\n\x00" + "a" * 40 + "\ntracked.py\n"

        monkeypatch.setattr(trees, "_run_git", fake_run_git)
        commit = CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: valid", timestamp=123)

        [attached] = trees._attach_commit_files_from_range(tmp_path, [commit], "old", "new")

        assert attached.files == ["tracked.py"]

    def test_attach_commit_files_from_range_handles_hex_filename(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A 40-hex-char filename must not be misread as a commit hash."""
        import repogerbil.core.git._trees as trees

        commit_hash = "a" * 40
        hex_filename = "0" * 40

        def fake_run_git(repo_path: Path, *args: str) -> str:
            return f"\x00{commit_hash}\n{hex_filename}\nreal.py\n"

        monkeypatch.setattr(trees, "_run_git", fake_run_git)
        commit = CommitInfo(hash=commit_hash, date="2026-04-07", subject="feat: valid", timestamp=123)

        [attached] = trees._attach_commit_files_from_range(tmp_path, [commit], "old", "new")

        assert attached.files == [hex_filename, "real.py"]

    def test_attach_commit_files_from_range_handles_sha256_hash(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Parser must accept 64-char SHA-256 hashes."""
        import repogerbil.core.git._trees as trees

        commit_hash = "b" * 64

        def fake_run_git(repo_path: Path, *args: str) -> str:
            return f"\x00{commit_hash}\nreal.py\n"

        monkeypatch.setattr(trees, "_run_git", fake_run_git)
        commit = CommitInfo(hash=commit_hash, date="2026-04-07", subject="feat: valid", timestamp=123)

        [attached] = trees._attach_commit_files_from_range(tmp_path, [commit], "old", "new")

        assert attached.files == ["real.py"]

    def test_resolve_commit_trees(self, monorepo: Path) -> None:
        """resolve_commit_trees maps commit hashes to tree SHAs."""
        from repogerbil.core.git import resolve_commit_trees

        commits = get_commits_for_path(monorepo, "pyvider-cty")
        tree_map = resolve_commit_trees(monorepo, commits)

        assert len(tree_map) == len(commits)
        # Each commit should map to a valid SHA
        for commit in commits:
            assert commit.hash in tree_map
            assert len(tree_map[commit.hash]) == 40  # SHA1 length

    def test_deduplicate_by_tree_removes_duplicates(self, monorepo: Path) -> None:
        """deduplicate_by_tree keeps only unique tree states."""
        from repogerbil.core.git import deduplicate_by_tree, resolve_commit_trees

        commits = get_commits_for_path(monorepo, "pyvider-cty")
        # Create artificial duplicates by repeating commits
        duplicated = commits + commits
        tree_map = resolve_commit_trees(monorepo, duplicated)
        unique = deduplicate_by_tree(duplicated, tree_map)

        # Should deduplicate back to original count
        assert len(unique) == len(commits)
        # Should maintain chronological order
        assert unique[0].date <= unique[1].date

    def test_deduplicate_by_tree_empty(self) -> None:
        """deduplicate_by_tree handles empty input."""
        from repogerbil.core.git import deduplicate_by_tree

        unique = deduplicate_by_tree([], {})
        assert len(unique) == 0

    def test_resolve_commit_trees_with_subdir(self, monorepo: Path) -> None:
        """resolve_commit_trees resolves subdir trees when path exists."""
        from repogerbil.core.git import resolve_commit_trees

        commits = get_commits_for_path(monorepo, "pyvider-cty")
        tree_map = resolve_commit_trees(monorepo, commits, source_subdir="pyvider-cty")

        # Should still get valid tree SHAs for all commits
        assert len(tree_map) == len(commits)
        for commit in commits:
            assert commit.hash in tree_map
            assert len(tree_map[commit.hash]) == 40

    def test_resolve_commit_trees_subdir_fallback(
        self, monorepo: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """resolve_commit_trees falls back to full tree if subdir doesn't exist."""
        from repogerbil.core.errors import GitCommandError
        from repogerbil.core.git import _run_git, resolve_commit_trees

        original_run_git = _run_git
        call_count: list[int] = [0]

        def mock_run_git(
            repo_path: str | Path,
            *args: str,
            timeout: int = 60,
            env: dict[str, str] | None = None,
        ) -> str:
            call_count[0] += 1
            # Fail on first rev-parse with subdir (HASH:subdir)
            if len(args) >= 2 and ":" in str(args[1]):
                raise GitCommandError(
                    "Git command failed: git rev-parse HASH:nonexistent",
                    returncode=128,
                    stderr="path 'nonexistent' does not exist",
                )
            return original_run_git(repo_path, *args, timeout=timeout, env=env)

        monkeypatch.setattr("repogerbil.core.git._trees._run_git", mock_run_git)
        commits = get_commits_for_path(monorepo, "pyvider-cty")
        tree_map = resolve_commit_trees(monorepo, commits, source_subdir="nonexistent")

        # Should still succeed by falling back to full tree
        assert len(tree_map) == len(commits)
        for commit in commits:
            assert commit.hash in tree_map
            assert len(tree_map[commit.hash]) == 40


class TestPublicApi:
    """Underscore-prefixed helpers must remain importable but stay out of ``__all__``."""

    def test_internal_helpers_excluded_from_all(self) -> None:
        import repogerbil.core.git as git_pkg

        assert "_run_git" not in git_pkg.__all__
        assert "_attach_file_lists" not in git_pkg.__all__

    def test_internal_helpers_still_importable(self) -> None:
        from repogerbil.core.git import _attach_file_lists, _run_git

        assert callable(_run_git)
        assert callable(_attach_file_lists)
