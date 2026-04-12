# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for snapshot engine."""

from datetime import UTC, datetime
from pathlib import Path
import subprocess

import pytest

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.git import CommitInfo, get_commits_for_date
from repogerbil.core.snapshot import SnapshotResult, create_snapshot


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "source"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}

    (repo / "a.py").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add a"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
    )
    (repo / "b.py").write_text("b\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: add b"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-08T10:00:00", "GIT_COMMITTER_DATE": "2026-04-08T10:00:00"},
    )
    return repo


class TestCreateSnapshot:
    def test_creates_new_repo(self, tmp_path: Path) -> None:
        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot"
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]

        result = create_snapshot(source, dest, groups)
        assert isinstance(result, SnapshotResult)
        assert result.commits_created == 2
        assert dest.exists()

        # Verify the snapshot has 2 commits
        log = (
            subprocess.run(
                ["git", "log", "--oneline"],
                cwd=dest,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert len(log) == 2

    def test_with_changelog_messages(self, tmp_path: Path) -> None:
        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot-msg"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        msgs = {"2026-04-07": "Custom message for Apr 7"}
        result = create_snapshot(source, dest, groups, changelog_messages=msgs)
        assert result.commits_created == 1

        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert log == "Custom message for Apr 7"

    def test_dest_not_empty_raises(self, tmp_path: Path) -> None:
        source = _init_repo(tmp_path)
        dest = tmp_path / "notempty"
        dest.mkdir()
        (dest / "file.txt").write_text("exists")

        import pytest

        with pytest.raises(RuntimeError, match="not empty"):
            create_snapshot(source, dest, [])

    def test_no_timestamp_preservation(self, tmp_path: Path) -> None:
        source = _init_repo(tmp_path)
        dest = tmp_path / "no-ts"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        result = create_snapshot(source, dest, groups, preserve_timestamps=False)
        assert result.commits_created == 1

    def test_multi_commit_group_message(self, tmp_path: Path) -> None:
        """Test auto-generated message for group with multiple commits."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "multi"
        # Both commits are on different days but we'll group them into one
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        combined = apr7 + apr8
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, 59, tzinfo=UTC),
                commits=combined,
            ),
        ]
        result = create_snapshot(source, dest, groups)
        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%B", "-1"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert "2 commits" in log
        assert "feat: add a" in log

    def test_no_conventional_commits_message(self, tmp_path: Path) -> None:
        """Non-conventional commits get a count-only message."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "noconv"
        apr7 = get_commits_for_date(source, "2026-04-07")
        # Override subjects to be garbage
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=[CommitInfo(hash=c.hash, date=c.date, subject="random garbage") for c in apr7[:1]],
            )
        ]
        result = create_snapshot(source, dest, groups)
        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%B", "-1"], cwd=dest, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert "1 commits" in log

    def test_single_conventional_commit_message(self, tmp_path: Path) -> None:
        """A single conventional commit uses its subject directly."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "single"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=[CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="feat: single thing")],
            )
        ]
        result = create_snapshot(source, dest, groups)
        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%B", "-1"], cwd=dest, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert log == "feat: single thing"

    def test_same_day_gap_groups_distinct_messages(self, tmp_path: Path) -> None:
        """With gap cadence, two same-day groups get distinct messages.

        First group (session 1) uses changelog if available.
        Subsequent groups (session 2+) use the fallback format.
        """
        from repogerbil.core.snapshot import _build_snapshot_message

        # Two groups on the same day (group2 has multiple commits to trigger date+count format)
        group1 = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: feature 1")],
        )
        group2 = TimeGroup(
            period_start=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 14, 30, tzinfo=UTC),
            commits=[
                CommitInfo(hash="b" * 40, date="2026-04-07", subject="fix: fix 1"),
                CommitInfo(hash="c" * 40, date="2026-04-07", subject="chore: update"),
            ],
        )

        changelog = {"2026-04-07": "feat(changelog): changelog message for 2026-04-07"}
        used_keys: set[str] = set()

        # First group gets the changelog
        msg1 = _build_snapshot_message(group1, changelog, used_keys)
        assert msg1 == "feat(changelog): changelog message for 2026-04-07"
        assert "2026-04-07" in used_keys

        # Second group falls back to date+count format (different message)
        msg2 = _build_snapshot_message(group2, changelog, used_keys)
        assert msg2 != msg1
        assert "2026-04-07: 2 commits" in msg2
        assert "fix: fix 1" in msg2

    def test_used_keys_none_backward_compat(self, tmp_path: Path) -> None:
        """When used_keys=None, both groups get the same changelog (backward compat)."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group1 = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: feature 1")],
        )
        group2 = TimeGroup(
            period_start=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 14, 30, tzinfo=UTC),
            commits=[CommitInfo(hash="b" * 40, date="2026-04-07", subject="fix: feature 2")],
        )

        changelog = {"2026-04-07": "feat(changelog): changelog message for 2026-04-07"}

        # Without tracking, both get the same message (old behavior)
        msg1 = _build_snapshot_message(group1, changelog, used_keys=None)
        msg2 = _build_snapshot_message(group2, changelog, used_keys=None)
        assert msg1 == msg2 == "feat(changelog): changelog message for 2026-04-07"

    def test_source_subdir_fallback_to_full_tree(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """snapshot falls back to full tree when subdir doesn't exist in commit."""
        from repogerbil.core.errors import GitCommandError
        from repogerbil.core.git import _run_git

        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]

        # Mock _run_git to fail on subdir lookup, then fall back to full tree
        original_run_git = _run_git
        call_count: list[int] = [0]

        def mock_run_git(repo_path: str | Path, *args: str, timeout: int = 60) -> str:
            call_count[0] += 1
            # Fail on first rev-parse with subdir (HASH:subdir)
            if len(args) >= 2 and ":" in str(args[1]):
                raise GitCommandError(
                    "Git command failed: git rev-parse HASH:nonexistent",
                    returncode=128,
                    stderr="path 'nonexistent' does not exist",
                )
            return original_run_git(repo_path, *args, timeout=timeout)

        monkeypatch.setattr("repogerbil.core.snapshot._run_git", mock_run_git)
        result = create_snapshot(source, dest, groups, source_subdir="nonexistent")
        assert result.commits_created == 1
        # Verify snapshot was created successfully
        assert dest.exists()
