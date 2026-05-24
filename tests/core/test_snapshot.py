# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for snapshot engine."""

from datetime import UTC, datetime
from pathlib import Path
import subprocess

import pytest

from repogerbil.core._snapshot_git import _get_commit_body, _get_files_for_commit
from repogerbil.core.cadence import TimeGroup
from repogerbil.core.git import CommitInfo, get_commits_for_date
from repogerbil.core.snapshot import (
    SnapshotResult,
    _compute_window_timestamps,
    _spread_timestamps_for_day,
    create_snapshot,
)
from repogerbil.core.tree_filter import exclude_files as _exclude_files, filter_tree as _filter_tree


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
        ["git", "commit", "-m", "add a"],
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

    def test_progress_output(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """progress=True prints one stderr line per commit created."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "progress"
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
        result = create_snapshot(source, dest, groups, progress=True)
        assert result.commits_created == 2
        err = capsys.readouterr().err
        lines = [line for line in err.splitlines() if line.strip()]
        assert len(lines) == 2
        assert "[1/2]" in lines[0]
        assert "[2/2]" in lines[1]
        assert "2026-04-07" in lines[0]
        assert "2026-04-08" in lines[1]

    def test_multi_commit_group_message(self, tmp_path: Path) -> None:
        """Test auto-generated message for group with multiple commits."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "multi"
        # Both commits are on different days but we'll group them into one.
        # Override subjects explicitly so the test is independent of _init_repo commit messages.
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, 59, tzinfo=UTC),
                commits=[
                    CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="feat: add a"),
                    CommitInfo(hash=apr8[0].hash, date=apr8[0].date, subject="fix: add b"),
                ],
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

        monkeypatch.setattr("repogerbil.core.snapshot._run_git", mock_run_git)
        result = create_snapshot(source, dest, groups, source_subdir="nonexistent")
        assert result.commits_created == 1
        # Verify snapshot was created successfully
        assert dest.exists()

    def test_snapshot_deduplicates_tree_states(self, tmp_path: Path) -> None:
        """snapshot skips groups with duplicate tree states."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot"
        apr7 = get_commits_for_date(source, "2026-04-07")

        # Create two groups pointing to the same commit (same tree)
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 14, 30, tzinfo=UTC),
                commits=apr7,  # Same commits = same tree state
            ),
        ]

        result = create_snapshot(source, dest, groups)
        # Should deduplicate: only 1 commit created instead of 2
        assert result.commits_created == 1
        assert result.groups_created == 2  # But we grouped 2 groups

    def test_time_window_produces_commits_within_range(self, tmp_path: Path) -> None:
        """create_snapshot with time_window_start/end stamps commits inside the window."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot-tw"
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

        result = create_snapshot(
            source,
            dest,
            groups,
            timezone="UTC",
            time_window_start="20:00",
            time_window_end="23:00",
        )
        assert result.commits_created == 2

        # Inspect actual commit timestamps in the snapshot repo
        timestamps = (
            subprocess.run(
                ["git", "log", "--format=%ai", "--reverse"],
                cwd=dest,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert len(timestamps) == 2

        for ts_str in timestamps:
            # git %ai format: "2026-04-07 20:14:33 +0000"
            ts = datetime.strptime(ts_str.strip(), "%Y-%m-%d %H:%M:%S %z")
            hour = ts.hour
            assert 20 <= hour <= 23, f"Commit timestamp {ts_str} outside 20:00-23:00 window"

        # Apr 7 commit must be on Apr 7, Apr 8 on Apr 8
        assert "2026-04-07" in timestamps[0]
        assert "2026-04-08" in timestamps[1]

    def test_exclude_paths_regex_absent_from_snapshot_commits(self, tmp_path: Path) -> None:
        """Regex exclude patterns strip matching files from every snapshot commit tree."""
        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}

        # Add a lock file and .claude dir to the source repo
        (source / "poetry.lock").write_text("lock content\n")
        (source / ".claude").mkdir()
        (source / ".claude" / "settings.json").write_text("{}")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: add lock and claude"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-09T10:00:00", "GIT_COMMITTER_DATE": "2026-04-09T10:00:00"},
        )

        dest = tmp_path / "snapshot-excl"
        apr9 = get_commits_for_date(source, "2026-04-09")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 9, tzinfo=UTC),
                period_end=datetime(2026, 4, 9, 23, 59, 59, tzinfo=UTC),
                commits=apr9,
            ),
        ]

        result = create_snapshot(
            source,
            dest,
            groups,
            exclude_paths=[r".*\.lock$", r"^\.claude(/|$)"],
        )
        assert result.commits_created == 1

        # Inspect the committed tree — excluded files must be absent
        tree_files = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "poetry.lock" not in tree_files
        assert ".claude" not in tree_files
        # Regular files must still be present
        assert "a.py" in tree_files
        assert "b.py" in tree_files

    def test_llm_refine_uses_generator_message(self, tmp_path: Path) -> None:
        """When llm_generator is provided, snapshot uses its output as commit messages."""
        import json
        from pathlib import Path as _Path

        from repogerbil.llm.client import FakeOllamaClient
        from repogerbil.llm.generator import MessageGenerator

        fixtures = _Path(__file__).parent.parent / "fixtures" / "ollama_responses"
        response = json.loads((fixtures / "valid_single.json").read_text())

        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot-llm"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]

        client = FakeOllamaClient([response])
        generator = MessageGenerator(client=client, model="gemma4")

        result = create_snapshot(source, dest, groups, llm_generator=generator)
        assert result.commits_created == 1

        log = subprocess.run(
            ["git", "log", "--format=%s", "-1"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert log == "instantiate(core): base type definitions introduced"

        # Verify body NOT in commit message
        full_log = subprocess.run(
            ["git", "log", "--format=%B", "-1"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert "base type definitions" in full_log
        assert "primitive value layer" not in full_log  # body stays in sidecar

        # Verify sidecar JSONL was created with structured format
        assert result.summaries_path is not None
        sidecar = Path(result.summaries_path)
        assert sidecar.exists()
        record = json.loads(sidecar.read_text().strip())
        assert record["date"] == "2026-04-07"
        assert record["subjects"] == ["instantiate(core): base type definitions introduced"]
        assert "primitive value layer" in record["body"]
        assert isinstance(record["changes"], list)
        assert len(record["changes"]) >= 1
        assert "file" in record["changes"][0]
        assert "description" in record["changes"][0]
        assert len(record["hash"]) == 40

    def test_llm_timeout_falls_back_to_builtin_message(self, tmp_path: Path) -> None:
        """When LLM raises, snapshot falls back to built-in message instead of aborting."""
        from unittest.mock import MagicMock

        source = _init_repo(tmp_path)
        dest = tmp_path / "snapshot-timeout"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=[CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="add a")],
            ),
        ]

        generator = MagicMock()
        generator.generate.side_effect = TimeoutError("timed out")

        result = create_snapshot(source, dest, groups, llm_generator=generator)
        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%B", "-1"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        # Fell back to built-in count-only message (no LLM output)
        assert "1 commits" in log
        generator.generate.assert_called_once()


class TestGetFilesForCommit:
    def test_returns_empty_list_on_bad_hash(self, tmp_path: Path) -> None:
        """_get_files_for_commit returns [] for an invalid commit hash."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = _get_files_for_commit(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        assert result == []


class TestGetCommitBody:
    def test_returns_full_message_for_valid_commit(self, tmp_path: Path) -> None:
        """_get_commit_body returns subject + body for a valid commit."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        # Add source as remote and fetch
        subprocess.run(
            ["git", "remote", "add", "src", str(source)],
            cwd=dest,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "fetch", "src"],
            cwd=dest,
            capture_output=True,
            check=True,
        )
        from repogerbil.core.git import get_commits_for_date

        commits = get_commits_for_date(source, "2026-04-07")
        body = _get_commit_body(dest, commits[0].hash)
        assert "add a" in body

    def test_returns_empty_string_on_bad_hash(self, tmp_path: Path) -> None:
        """_get_commit_body returns '' for an invalid commit hash."""
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = _get_commit_body(repo, "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef")
        assert result == ""


class TestFilterTree:
    def test_no_exclude_returns_same_sha(self, tmp_path: Path) -> None:
        """_filter_tree with no excludes returns the original tree SHA."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        from repogerbil.core.git import get_commits_for_date

        commits = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        result = _filter_tree(dest, tree_sha, None)
        assert result == tree_sha

    def test_excludes_path_from_tree(self, tmp_path: Path) -> None:
        """_filter_tree removes the specified path and returns a new tree SHA."""
        source = _init_repo(tmp_path)
        # Add a .claude directory to the source repo
        (source / ".claude").mkdir()
        (source / ".claude" / "settings.json").write_text("{}")
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: add .claude"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-09T10:00:00", "GIT_COMMITTER_DATE": "2026-04-09T10:00:00"},
        )
        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        from repogerbil.core.git import get_commits_for_date

        commits = get_commits_for_date(source, "2026-04-09")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        filtered = _filter_tree(dest, tree_sha, [".claude"])
        assert filtered != tree_sha
        # Filtered tree should not contain .claude
        ls = subprocess.run(
            ["git", "ls-tree", filtered],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert ".claude" not in ls


class TestExcludeFiles:
    def test_no_excludes_returns_all(self) -> None:
        files = {"src/core/api.py", "vendor/lib.py", ".claude/settings.json"}
        assert _exclude_files(files, None) == files
        assert _exclude_files(files, []) == files

    def test_excludes_exact_match(self) -> None:
        files = {"src/core/api.py", ".claude/settings.json"}
        result = _exclude_files(files, [r"^\.claude(/|$)"])
        assert ".claude/settings.json" not in result
        assert "src/core/api.py" in result

    def test_excludes_directory_prefix(self) -> None:
        files = {"src/core/api.py", "vendor/lib.py", "vendor/other.py"}
        result = _exclude_files(files, ["^vendor/"])
        assert result == {"src/core/api.py"}

    def test_does_not_exclude_partial_prefix(self) -> None:
        files = {"src/core/api.py", "vendor_util.py"}
        result = _exclude_files(files, ["^vendor/"])
        assert "vendor_util.py" in result

    def test_regex_extension_match(self) -> None:
        files = {"poetry.lock", "src/core/api.py", "subdir/package.lock"}
        result = _exclude_files(files, [r".*\.lock$"])
        assert result == {"src/core/api.py"}

    def test_regex_anchored_prevents_false_positive(self) -> None:
        files = {"src/.claude/config", ".claude/settings.json"}
        # Anchored pattern only removes top-level .claude
        result = _exclude_files(files, [r"^\.claude(/|$)"])
        assert ".claude/settings.json" not in result
        assert "src/.claude/config" in result


class TestFilterTreeRegex:
    def _init_repo_with_files(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create source with .claude dir and a lock file; return (source, dest)."""
        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (source / ".claude").mkdir()
        (source / ".claude" / "settings.json").write_text("{}")
        (source / "poetry.lock").write_text("lock\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: add extras"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-09T10:00:00", "GIT_COMMITTER_DATE": "2026-04-09T10:00:00"},
        )
        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        return source, dest

    def _get_tree_sha(self, dest: Path, source: Path, date: str) -> str:
        from repogerbil.core.git import get_commits_for_date

        commits = get_commits_for_date(source, date)
        return subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()

    def test_regex_removes_extension(self, tmp_path: Path) -> None:
        """Regex .*\\.lock$ removes lock file but not other files."""
        source, dest = self._init_repo_with_files(tmp_path)
        tree_sha = self._get_tree_sha(dest, source, "2026-04-09")
        filtered = _filter_tree(dest, tree_sha, [r".*\.lock$"])
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", filtered],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "poetry.lock" not in ls
        assert "a.py" in ls  # original files still present

    def test_regex_removes_directory(self, tmp_path: Path) -> None:
        """Anchored regex removes .claude directory."""
        source, dest = self._init_repo_with_files(tmp_path)
        tree_sha = self._get_tree_sha(dest, source, "2026-04-09")
        filtered = _filter_tree(dest, tree_sha, [r"^\.claude(/|$)"])
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", filtered],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert ".claude" not in ls
        assert "poetry.lock" in ls  # other files unaffected

    def test_multiple_patterns(self, tmp_path: Path) -> None:
        """Multiple patterns — both matched files removed."""
        source, dest = self._init_repo_with_files(tmp_path)
        tree_sha = self._get_tree_sha(dest, source, "2026-04-09")
        filtered = _filter_tree(dest, tree_sha, [r"^\.claude(/|$)", r".*\.lock$"])
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", filtered],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert ".claude" not in ls
        assert "poetry.lock" not in ls
        assert "a.py" in ls


class TestSpreadTimestamps:
    def _make_group(self, date_str: str, n_files: int) -> TimeGroup:
        from repogerbil.core.git import CommitInfo

        dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        c = CommitInfo(hash="a" * 40, date=date_str[:10], subject="feat: x")
        return TimeGroup(
            period_start=dt,
            period_end=dt,
            commits=[c],
            files_affected=["f"] * n_files,
        )

    def test_single_group_within_window(self) -> None:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Los_Angeles")
        from datetime import datetime as dt_cls

        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 11, 0, 0, tzinfo=tz)
        group = self._make_group("2026-04-10T10:00:00", 3)
        import random

        rng = random.Random(42)
        result = _spread_timestamps_for_day([group], start, end, rng)
        assert len(result) == 1
        ts = datetime.fromisoformat(result[0])
        assert start <= ts <= end

    def test_multiple_groups_strictly_increasing(self) -> None:
        groups = [self._make_group("2026-04-10T10:00:00", i + 1) for i in range(5)]
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Los_Angeles")
        from datetime import datetime as dt_cls

        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 11, 0, 0, tzinfo=tz)
        import random

        rng = random.Random(42)
        result = _spread_timestamps_for_day(groups, start, end, rng)
        parsed = [datetime.fromisoformat(ts) for ts in result]
        import itertools

        for a, b in itertools.pairwise(parsed):
            assert a < b

    def test_timestamps_within_window(self) -> None:
        groups = [self._make_group("2026-04-10T10:00:00", i + 2) for i in range(4)]
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("America/Los_Angeles")
        from datetime import datetime as dt_cls

        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 11, 0, 0, tzinfo=tz)
        import random

        rng = random.Random(7)
        result = _spread_timestamps_for_day(groups, start, end, rng)
        for ts_str in result:
            ts = datetime.fromisoformat(ts_str)
            assert start <= ts <= end

    def test_weighting_larger_groups_get_later_slot(self) -> None:
        """Group with more files should land in a later slot."""
        group_small = self._make_group("2026-04-10T10:00:00", 1)
        group_large = self._make_group("2026-04-10T11:00:00", 20)
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        from datetime import datetime as dt_cls

        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 23, 59, tzinfo=tz)
        import random

        rng = random.Random(0)
        result = _spread_timestamps_for_day([group_small, group_large], start, end, rng)
        ts_small = datetime.fromisoformat(result[0])
        ts_large = datetime.fromisoformat(result[1])
        assert ts_small < ts_large

    def test_deterministic_with_seed(self) -> None:
        groups = [self._make_group("2026-04-10T10:00:00", i + 1) for i in range(3)]
        ts1 = _compute_window_timestamps(groups, "20:00", "00:00", "America/Los_Angeles", seed=42)
        ts2 = _compute_window_timestamps(groups, "20:00", "00:00", "America/Los_Angeles", seed=42)
        assert ts1 == ts2

    def test_deterministic_without_seed(self) -> None:
        groups = [self._make_group("2026-04-10T10:00:00", i + 1) for i in range(3)]
        ts1 = _compute_window_timestamps(groups, "20:00", "00:00", "America/Los_Angeles")
        ts2 = _compute_window_timestamps(groups, "20:00", "00:00", "America/Los_Angeles")
        assert ts1 == ts2

    def test_window_crossing_midnight(self) -> None:
        """Window 23:00-01:00 spans midnight; all timestamps land in that range."""
        group = self._make_group("2026-04-10T22:00:00", 3)
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        from datetime import datetime as dt_cls

        start = dt_cls(2026, 4, 10, 23, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 11, 1, 0, tzinfo=tz)
        import random

        rng = random.Random(1)
        result = _spread_timestamps_for_day([group], start, end, rng)
        ts = datetime.fromisoformat(result[0])
        assert start <= ts <= end

    def test_compute_window_timestamps_multiple_days(self) -> None:
        """Groups on different days each span their own full window."""
        groups = [
            self._make_group("2026-04-10T10:00:00", 2),
            self._make_group("2026-04-11T10:00:00", 2),
        ]
        result = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=5)
        assert len(result) == 2
        ts0 = datetime.fromisoformat(result[0])
        ts1 = datetime.fromisoformat(result[1])
        # Each should be on their respective day at 20:00-23:00 UTC
        assert ts0.date().isoformat() == "2026-04-10"
        assert ts1.date().isoformat() == "2026-04-11"

    def test_midnight_crossing_via_compute(self) -> None:
        """_compute_window_timestamps handles 23:00-01:00 correctly."""
        group = self._make_group("2026-04-10T10:00:00", 3)
        result = _compute_window_timestamps([group], "23:00", "01:00", "UTC", seed=0)
        assert len(result) == 1
        ts = datetime.fromisoformat(result[0])
        # Should be between 23:00 on Apr 10 and 01:00 on Apr 11
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        from datetime import datetime as dt_cls

        assert ts >= dt_cls(2026, 4, 10, 23, 0, tzinfo=tz)
        assert ts <= dt_cls(2026, 4, 11, 1, 0, tzinfo=tz)
