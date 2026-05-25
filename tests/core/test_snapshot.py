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

    def test_build_message_mixes_conventional_and_other(self) -> None:
        """When a group has both well-formed and freeform commits, the trailing
        ``- (N commits)`` line accounts for the non-conventional ones."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[
                CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: clean one"),
                CommitInfo(hash="b" * 40, date="2026-04-07", subject="fix: clean two"),
                # Freeform / non-conventional subjects:
                CommitInfo(hash="c" * 40, date="2026-04-07", subject="wip stuff"),
                CommitInfo(hash="d" * 40, date="2026-04-07", subject="more wip"),
            ],
        )

        msg = _build_snapshot_message(group, changelog_messages=None, used_keys=None)

        assert "2026-04-07: 4 commits" in msg
        assert "- feat: clean one" in msg
        assert "- fix: clean two" in msg
        # The two non-conventional commits are bucketed:
        assert "- (2 commits)" in msg

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

    def test_llm_timeout_falls_back_to_builtin_message(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """When LLM raises, snapshot falls back to built-in message and logs a warning."""
        import logging
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

        with caplog.at_level(logging.WARNING, logger="repogerbil.core.snapshot"):
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
        # Warning was emitted with the date and the exception
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        # Pin: the date in the log must NOT contain "XX" wrapping (which would
        # indicate mutation of the strftime format string), nor case-flipped
        # markers like "lLM" or "FAILED".
        matching = [r for r in warning_records if "LLM refinement failed" in r.getMessage()]
        assert matching, f"Expected LLM warning, got: {[r.getMessage() for r in warning_records]}"
        for r in matching:
            msg = r.getMessage()
            # Date in args must be exactly "2026-04-07" — not "XX2026-04-07XX"
            assert "2026-04-07" in msg
            assert "XX" not in msg
            # Format string is the original lowercase "non-LLM"
            assert "non-LLM" in msg or "LLM refinement failed" in msg
            # The exception text must appear (mutant could replace exc with None)
            assert "timed out" in msg
            assert "None" not in msg.split("non-LLM message: ")[-1]


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


class TestBuildSnapshotMessageExact:
    """Pin exact string formats in _build_snapshot_message to kill mutations."""

    def test_single_conventional_returns_subject_unchanged(self) -> None:
        """A single well-formed commit returns the bare subject — no decoration."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: single thing")],
        )
        msg = _build_snapshot_message(group, None, None)
        assert msg == "feat: single thing"

    def test_no_conventional_count_only_format_exact(self) -> None:
        """Non-conventional commits yield exact 'YYYY-MM-DD: N commits' format."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[
                CommitInfo(hash="a" * 40, date="2026-04-07", subject="random garbage"),
                CommitInfo(hash="b" * 40, date="2026-04-07", subject="more garbage"),
                CommitInfo(hash="c" * 40, date="2026-04-07", subject="yet more"),
            ],
        )
        msg = _build_snapshot_message(group, None, None)
        assert msg == "2026-04-07: 3 commits"

    def test_no_conventional_count_one(self) -> None:
        """Count-only format with N=1 reads 'YYYY-MM-DD: 1 commits' (not '1 commit')."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="just freeform")],
        )
        msg = _build_snapshot_message(group, None, None)
        assert msg == "2026-04-07: 1 commits"

    def test_mixed_conventional_and_other_exact_format(self) -> None:
        """Mixed groups produce a precise multi-line message with bullets."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[
                CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: one"),
                CommitInfo(hash="b" * 40, date="2026-04-07", subject="fix: two"),
                CommitInfo(hash="c" * 40, date="2026-04-07", subject="freeform"),
                CommitInfo(hash="d" * 40, date="2026-04-07", subject="another"),
            ],
        )
        msg = _build_snapshot_message(group, None, None)
        expected = "2026-04-07: 4 commits\n\n- feat: one\n- fix: two\n- (2 commits)"
        assert msg == expected

    def test_all_conventional_no_other_line(self) -> None:
        """When all commits are conventional, no '(N commits)' trailer appears."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[
                CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: one"),
                CommitInfo(hash="b" * 40, date="2026-04-07", subject="fix: two"),
            ],
        )
        msg = _build_snapshot_message(group, None, None)
        expected = "2026-04-07: 2 commits\n\n- feat: one\n- fix: two"
        assert msg == expected
        assert "(0 commits)" not in msg
        assert "- (" not in msg

    def test_changelog_used_when_present(self) -> None:
        """Changelog message is returned verbatim, no transformation."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: x")],
        )
        result = _build_snapshot_message(group, {"2026-04-07": "EXACT_VALUE"}, set())
        assert result == "EXACT_VALUE"

    def test_changelog_key_added_to_used_keys(self) -> None:
        """used_keys is mutated to include the consumed date."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: x")],
        )
        used: set[str] = set()
        _build_snapshot_message(group, {"2026-04-07": "M"}, used)
        assert used == {"2026-04-07"}

    def test_changelog_skipped_when_date_already_used(self) -> None:
        """If date is in used_keys, falls back to non-changelog message."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: x")],
        )
        used: set[str] = {"2026-04-07"}
        msg = _build_snapshot_message(group, {"2026-04-07": "SHOULD_NOT_APPEAR"}, used)
        assert msg == "feat: x"
        assert "SHOULD_NOT_APPEAR" not in msg

    def test_changelog_empty_dict_falls_through(self) -> None:
        """Empty changelog dict triggers the non-changelog branch."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: x")],
        )
        msg = _build_snapshot_message(group, {}, set())
        assert msg == "feat: x"

    def test_changelog_date_not_in_messages(self) -> None:
        """Date missing from changelog → fallback."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="feat: x")],
        )
        msg = _build_snapshot_message(group, {"2099-01-01": "wrong"}, set())
        assert msg == "feat: x"

    def test_period_start_date_format_used_not_period_end(self) -> None:
        """The message header uses period_start.strftime — confirm the date string."""
        from repogerbil.core.snapshot import _build_snapshot_message

        group = TimeGroup(
            period_start=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
            period_end=datetime(2026, 4, 8, 0, 1, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="garbage")],
        )
        msg = _build_snapshot_message(group, None, None)
        # Must use period_start date (2026-04-07), not period_end (2026-04-08)
        assert msg.startswith("2026-04-07:")
        assert "2026-04-08" not in msg


class TestCreateSnapshotExact:
    """Pin exact behavior of create_snapshot to kill mutations."""

    def test_groups_created_matches_input(self, tmp_path: Path) -> None:
        """SnapshotResult.groups_created equals len(input groups), even after dedup."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-gc"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, h, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, h, 30, tzinfo=UTC),
                commits=apr7,
            )
            for h in (10, 11, 12)
        ]
        result = create_snapshot(source, dest, groups)
        # 3 groups input → groups_created=3, but groups_skipped=2 (dedup)
        assert result.groups_created == 3
        assert result.commits_created == 1
        assert result.groups_skipped == 2

    def test_dest_path_field_matches_input(self, tmp_path: Path) -> None:
        """SnapshotResult.dest_path equals str(dest_path)."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-dp"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        result = create_snapshot(source, dest, groups)
        assert result.dest_path == str(dest)

    def test_summaries_path_none_when_no_llm(self, tmp_path: Path) -> None:
        """summaries_path is None unless an LLM generator is passed."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-no-llm"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        result = create_snapshot(source, dest, groups)
        assert result.summaries_path is None

    def test_groups_skipped_zero_when_unique(self, tmp_path: Path) -> None:
        """groups_skipped is exactly 0 when every group is unique."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-no-skip"
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]
        result = create_snapshot(source, dest, groups)
        assert result.groups_skipped == 0
        assert result.commits_created == 2

    def test_groups_created_is_zero_only_for_empty_input(self, tmp_path: Path) -> None:
        """groups_created equals input length (sanity-check on basic counting)."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-one"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        result = create_snapshot(source, dest, groups)
        assert result.groups_created == 1

    def test_remotes_removed_after_snapshot(self, tmp_path: Path) -> None:
        """All source remotes are removed at the end."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-remotes"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        create_snapshot(source, dest, groups)
        remotes = subprocess.run(
            ["git", "remote"], cwd=dest, capture_output=True, text=True, check=True
        ).stdout.strip()
        # No remotes should remain
        assert remotes == ""

    def test_final_branch_is_main(self, tmp_path: Path) -> None:
        """After snapshot, HEAD points at main (not at any other branch name)."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-main"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        create_snapshot(source, dest, groups)
        branch = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert branch == "main"

    def test_create_snapshot_passes_source_subdir_to_dedup(self, tmp_path: Path) -> None:
        """source_subdir reaches dedup — pin via two commits with same subdir
        tree (different full tree) being deduplicated to 1 commit.

        A mutation passing None for source_subdir in the dedup call would
        produce 2 distinct snapshot commits (different full trees).
        """
        source = tmp_path / "mono"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=source, capture_output=True, check=True
        )
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (source / "pkg").mkdir()
        (source / "pkg" / "a.py").write_text("a\n")
        (source / "root.txt").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: c1"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
        )
        (source / "root.txt").write_text("v2\n")  # change OUTSIDE pkg
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: c2"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
        )
        all_commits = get_commits_for_date(source, "2026-04-07")
        assert len(all_commits) == 2
        dest = tmp_path / "mono-cs"
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
                commits=[all_commits[0]],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 11, 30, tzinfo=UTC),
                commits=[all_commits[1]],
            ),
        ]
        result = create_snapshot(source, dest, groups, source_subdir="pkg")
        # With source_subdir reaching dedup → same subdir → 1 commit, 1 skipped
        assert result.commits_created == 1
        assert result.groups_skipped == 1

    def test_create_snapshot_passes_exclude_paths_to_dedup(self, tmp_path: Path) -> None:
        """exclude_paths reaches dedup — pin via two commits that differ only
        in excluded files being deduplicated."""
        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # Commit modifying ONLY a lock file (after the base apr-7/-8 setup)
        (source / "poetry.lock").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: lock v1"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-09T10:00:00", "GIT_COMMITTER_DATE": "2026-04-09T10:00:00"},
        )
        (source / "poetry.lock").write_text("v2\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: lock v2"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-09T11:00:00", "GIT_COMMITTER_DATE": "2026-04-09T11:00:00"},
        )
        commits = get_commits_for_date(source, "2026-04-09")
        assert len(commits) == 2
        dest = tmp_path / "snap-excl-dedup"
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 9, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 9, 10, 30, tzinfo=UTC),
                commits=[commits[0]],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 9, 11, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 9, 11, 30, tzinfo=UTC),
                commits=[commits[1]],
            ),
        ]
        # With exclude_paths=[".*\\.lock$"] reaching dedup, two commits become identical
        result = create_snapshot(source, dest, groups, exclude_paths=[r".*\.lock$"])
        assert result.commits_created == 1
        assert result.groups_skipped == 1

    def test_preserve_timestamps_default_is_true(self, tmp_path: Path) -> None:
        """preserve_timestamps defaults to True — commits use the period_end timestamp.

        Pins ``preserve_timestamps: bool = True`` against a default flip to False.
        """
        source = _init_repo(tmp_path)
        dest = tmp_path / "preserve-default"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        # Default behavior — no preserve_timestamps arg
        create_snapshot(source, dest, groups)
        # Commit author time must be the period_end (2026-04-07 23:59:59), NOT current time
        ai = subprocess.run(
            ["git", "log", "-1", "--format=%ai"], cwd=dest, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert ai.startswith("2026-04-07 23:59:59")

    def test_final_checkout_uses_main_branch(self, tmp_path: Path) -> None:
        """The final ``git checkout --force main`` actually targets the 'main' ref.

        Pins the literal ``"main"`` argument. A mutation removing it would
        silently re-check-out HEAD instead.
        """
        source = _init_repo(tmp_path)
        dest = tmp_path / "checkout-main"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        create_snapshot(source, dest, groups)
        # HEAD must be on the main branch (the snapshot creates commits on refs/heads/main).
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert branch == "main"
        # Working tree must reflect the snapshot tree (a.py present).
        assert (dest / "a.py").exists()

    def test_existing_empty_dest_does_not_raise(self, tmp_path: Path) -> None:
        """Empty dest dir (exists but no iterdir entries) is allowed."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "empty-dest"
        dest.mkdir()  # exists but empty
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        # Empty dir is allowed (any(iterdir()) is False)
        result = create_snapshot(source, dest, groups)
        assert result.commits_created == 1

    def test_nonexistent_dest_does_not_raise(self, tmp_path: Path) -> None:
        """Non-existent dest is also allowed (will be created)."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "deep" / "nested" / "dest"
        # dest.exists() is False — must not raise
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        result = create_snapshot(source, dest, groups)
        assert result.commits_created == 1
        # Verify the nested dirs were created
        assert dest.exists()

    def test_dest_not_empty_error_message_includes_path(self, tmp_path: Path) -> None:
        """Error message contains the destination path verbatim."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "occupied"
        dest.mkdir()
        (dest / "thing").write_text("x")
        with pytest.raises(RuntimeError, match=str(dest)):
            create_snapshot(source, dest, [])

    def test_extra_sources_appended_as_extra_zero(self, tmp_path: Path) -> None:
        """Extra source 0 is added (and then removed); commits from it are reachable."""
        primary = _init_repo(tmp_path)
        # Build a second source with a unique commit
        extra = tmp_path / "extra"
        extra.mkdir()
        subprocess.run(["git", "init"], cwd=extra, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=extra, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=extra, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=extra, capture_output=True, check=True
        )
        (extra / "z.py").write_text("z\n")
        subprocess.run(["git", "add", "."], cwd=extra, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add z"],
            cwd=extra,
            capture_output=True,
            check=True,
            env={
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "GIT_AUTHOR_DATE": "2026-04-10T10:00:00",
                "GIT_COMMITTER_DATE": "2026-04-10T10:00:00",
            },
        )
        extra_commits = get_commits_for_date(extra, "2026-04-10")
        dest = tmp_path / "snap-extras"
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 10, tzinfo=UTC),
                period_end=datetime(2026, 4, 10, 23, 59, tzinfo=UTC),
                commits=extra_commits,
            ),
        ]
        result = create_snapshot(primary, dest, groups, extra_sources=[extra])
        assert result.commits_created == 1


class TestInitAndFetchExact:
    """Pin exact behavior of _init_and_fetch."""

    def test_returns_source_only_when_no_extras(self, tmp_path: Path) -> None:
        """When extra_sources is None, only 'source' remote name is returned."""
        from repogerbil.core.snapshot import _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "iaf-1"
        result = _init_and_fetch(dest, source, None)
        assert result == ["source"]

    def test_returns_source_only_when_extras_empty_list(self, tmp_path: Path) -> None:
        """Empty extras list is equivalent to None — only 'source' remote returned."""
        from repogerbil.core.snapshot import _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "iaf-2"
        result = _init_and_fetch(dest, source, [])
        assert result == ["source"]

    def test_returns_source_and_extras_indexed_from_zero(self, tmp_path: Path) -> None:
        """Extra sources produce 'extra-0', 'extra-1', ... names in order."""
        from repogerbil.core.snapshot import _init_and_fetch

        source = _init_repo(tmp_path)

        extras = []
        for i in range(3):
            ex = tmp_path / f"ex{i}"
            ex.mkdir()
            subprocess.run(["git", "init"], cwd=ex, capture_output=True, check=True)
            extras.append(ex)

        dest = tmp_path / "iaf-3"
        result = _init_and_fetch(dest, source, extras)
        assert result == ["source", "extra-0", "extra-1", "extra-2"]

    def test_skips_nonexistent_extra_paths(self, tmp_path: Path) -> None:
        """Non-existent extras are silently skipped (their slot not added)."""
        from repogerbil.core.snapshot import _init_and_fetch

        source = _init_repo(tmp_path)
        existing = tmp_path / "exists"
        existing.mkdir()
        subprocess.run(["git", "init"], cwd=existing, capture_output=True, check=True)
        missing = tmp_path / "nope"

        dest = tmp_path / "iaf-4"
        # Order: missing, existing → existing should still be extra-1 since slots are by index
        result = _init_and_fetch(dest, source, [missing, existing])
        assert result == ["source", "extra-1"]

    def test_destination_is_git_repo_after_init(self, tmp_path: Path) -> None:
        """After _init_and_fetch, dest is a git repo."""
        from repogerbil.core.snapshot import _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "iaf-5"
        _init_and_fetch(dest, source, None)
        assert (dest / ".git").exists()


class TestFetchSourceRefspec:
    """Verify _fetch_source uses the precise refspec '+refs/*:refs/fetch-<name>/*'."""

    def test_creates_fetch_refs_with_remote_name(self, tmp_path: Path) -> None:
        """After fetch, refs are stored under refs/fetch-<remote>/*."""
        from repogerbil.core.snapshot import _fetch_source

        source = _init_repo(tmp_path)
        dest = tmp_path / "fs-1"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        _fetch_source(dest, "myremote", source)
        refs = subprocess.run(
            ["git", "for-each-ref", "--format=%(refname)"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        # The refspec must produce refs under refs/fetch-myremote/
        assert "refs/fetch-myremote/" in refs

    def test_remote_added_with_provided_name(self, tmp_path: Path) -> None:
        """The 'git remote add' uses the exact provided name."""
        from repogerbil.core.snapshot import _fetch_source

        source = _init_repo(tmp_path)
        dest = tmp_path / "fs-2"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        _fetch_source(dest, "abc123", source)
        remotes = (
            subprocess.run(["git", "remote"], cwd=dest, capture_output=True, text=True, check=True)
            .stdout.strip()
            .splitlines()
        )
        assert "abc123" in remotes


class TestResolveTimestampExact:
    """Pin exact behavior of _resolve_timestamp."""

    def test_uses_period_end_iso_when_no_commit_time(self) -> None:
        """Without commit_time, returns period_end as ISO8601 (no tz suffix)."""
        from repogerbil.core.snapshot import _resolve_timestamp

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        result = _resolve_timestamp(g, None, None)
        assert result == "2026-04-07T23:59:59"

    def test_uses_period_end_iso_when_only_commit_time(self) -> None:
        """commit_time alone (no tz) still triggers fallback to period_end."""
        from repogerbil.core.snapshot import _resolve_timestamp

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        result = _resolve_timestamp(g, "20:00", None)
        assert result == "2026-04-07T23:59:59"

    def test_uses_period_end_iso_when_only_timezone(self) -> None:
        """timezone alone (no commit_time) still triggers fallback to period_end."""
        from repogerbil.core.snapshot import _resolve_timestamp

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        result = _resolve_timestamp(g, None, "UTC")
        assert result == "2026-04-07T23:59:59"

    def test_uses_make_timestamp_with_period_start_day(self) -> None:
        """When both commit_time & timezone set, uses period_start.year/month/day."""
        from repogerbil.core.snapshot import _resolve_timestamp

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 8, 23, 59, 59, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        result = _resolve_timestamp(g, "20:00", "UTC")
        # Day comes from period_start (2026-04-07), not period_end (2026-04-08)
        assert result.startswith("2026-04-07T20:00:00")
        assert "2026-04-08" not in result


class TestCommitWithTimestampExact:
    """Pin behavior of _commit_with_timestamp."""

    def test_preserve_true_sets_author_and_committer_date(self, tmp_path: Path) -> None:
        """preserve=True writes GIT_AUTHOR_DATE and GIT_COMMITTER_DATE."""
        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-1"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)

        commits = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree_sha], cwd=dest, capture_output=True, check=True)

        sha = _commit_with_timestamp(dest, tree_sha, "msg", "2026-05-15T12:34:56", True)
        # Both author and committer date should be the provided value
        author = subprocess.run(
            ["git", "log", "-1", "--format=%ai", sha], cwd=dest, capture_output=True, text=True, check=True
        ).stdout.strip()
        committer = subprocess.run(
            ["git", "log", "-1", "--format=%ci", sha], cwd=dest, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert author.startswith("2026-05-15 12:34:56")
        assert committer.startswith("2026-05-15 12:34:56")

    def test_updates_refs_heads_main(self, tmp_path: Path) -> None:
        """After commit, refs/heads/main points to the new commit."""
        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-2"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        commits = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree_sha], cwd=dest, capture_output=True, check=True)

        sha = _commit_with_timestamp(dest, tree_sha, "msg", "2026-05-15T12:34:56", False)
        main = subprocess.run(
            ["git", "rev-parse", "refs/heads/main"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert main == sha

    def test_first_commit_no_parent(self, tmp_path: Path) -> None:
        """The first commit has no parent (HEAD not yet set)."""
        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-3"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        commits = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree_sha], cwd=dest, capture_output=True, check=True)

        sha = _commit_with_timestamp(dest, tree_sha, "first", "2026-05-15T12:34:56", False)
        # Verify no parent
        parents = subprocess.run(
            ["git", "log", "-1", "--format=%P", sha],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert parents == ""

    def test_second_commit_has_first_as_parent(self, tmp_path: Path) -> None:
        """Subsequent commits chain off the existing HEAD."""
        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-4"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)

        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        tree1 = subprocess.run(
            ["git", "rev-parse", f"{apr7[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        tree2 = subprocess.run(
            ["git", "rev-parse", f"{apr8[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree1], cwd=dest, capture_output=True, check=True)
        first = _commit_with_timestamp(dest, tree1, "first", "2026-05-15T12:00:00", False)
        subprocess.run(["git", "read-tree", tree2], cwd=dest, capture_output=True, check=True)
        second = _commit_with_timestamp(dest, tree2, "second", "2026-05-15T13:00:00", False)
        parents = subprocess.run(
            ["git", "log", "-1", "--format=%P", second],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert parents == first


class TestDeduplicateGroupsExact:
    """Pin exact behavior of _deduplicate_groups."""

    def test_no_duplicates_returns_all(self, tmp_path: Path) -> None:
        """All-unique groups → returned unchanged with 0 skipped."""
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "dg-1"
        _init_and_fetch(dest, source, None)
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]
        unique, skipped = _deduplicate_groups(dest, groups, None, None)
        assert skipped == 0
        assert len(unique) == 2
        assert unique == groups

    def test_duplicate_skipped_keeps_first_group(self, tmp_path: Path) -> None:
        """First group with a given tree state is kept; later duplicates are skipped."""
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "dg-2"
        _init_and_fetch(dest, source, None)
        apr7 = get_commits_for_date(source, "2026-04-07")
        first = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
            commits=apr7,
        )
        second = TimeGroup(
            period_start=datetime(2026, 4, 7, 14, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 14, 30, tzinfo=UTC),
            commits=apr7,  # same commit → same tree
        )
        unique, skipped = _deduplicate_groups(dest, [first, second], None, None)
        assert skipped == 1
        assert unique == [first]

    def test_three_duplicates_keeps_first_skips_two(self, tmp_path: Path) -> None:
        """With three identical groups, two are skipped (exact count)."""
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "dg-3"
        _init_and_fetch(dest, source, None)
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, h, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, h, 30, tzinfo=UTC),
                commits=apr7,
            )
            for h in (9, 10, 11)
        ]
        unique, skipped = _deduplicate_groups(dest, groups, None, None)
        assert skipped == 2
        assert len(unique) == 1

    def test_source_subdir_invalid_falls_back_to_full_tree_for_dedup(self, tmp_path: Path) -> None:
        """When source_subdir is set but DOES NOT EXIST in the commit, dedup
        falls back to the full-tree hash. Two commits with different full trees
        must therefore NOT be deduped.

        Pins the GitCommandError fallback path:
        ``tree_sha = _run_git(dest_path, "rev-parse", f"{hash}^{{tree}}", ...)``.
        A mutation setting ``tree_sha = None`` in the except clause would
        dedupe all groups to one (None == None).
        """
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # Make TWO commits with distinct full trees but neither has "ghost/" subdir
        (source / "z.py").write_text("z\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: z1"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-10T10:00:00", "GIT_COMMITTER_DATE": "2026-04-10T10:00:00"},
        )
        (source / "z.py").write_text("z2\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: z2"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-10T11:00:00", "GIT_COMMITTER_DATE": "2026-04-10T11:00:00"},
        )
        commits = get_commits_for_date(source, "2026-04-10")
        assert len(commits) == 2
        dest = tmp_path / "ghost-fallback"
        _init_and_fetch(dest, source, None)
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 10, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 10, 10, 30, tzinfo=UTC),
                commits=[commits[0]],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 10, 11, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 10, 11, 30, tzinfo=UTC),
                commits=[commits[1]],
            ),
        ]
        # source_subdir="ghost" does not exist in either commit. The except path
        # must compute distinct full-tree SHAs and KEEP both groups.
        unique, skipped = _deduplicate_groups(dest, groups, source_subdir="ghost", exclude_paths=None)
        assert skipped == 0
        assert len(unique) == 2

    def test_source_subdir_dedup_keeps_distinct_subdir_trees(self, tmp_path: Path) -> None:
        """With source_subdir set and two commits having DIFFERENT subdir trees,
        dedup must keep BOTH groups (skipped=0)."""
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        source = tmp_path / "mono-distinct"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=source, capture_output=True, check=True
        )
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # Commit 1: pkg/a.py = "v1"
        (source / "pkg").mkdir()
        (source / "pkg" / "a.py").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: c1"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
        )
        # Commit 2: pkg/a.py = "v2" (subdir DIFFERS)
        (source / "pkg" / "a.py").write_text("v2\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: c2"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
        )
        all_commits = get_commits_for_date(source, "2026-04-07")
        assert len(all_commits) == 2

        dest = tmp_path / "mono-distinct-dedup"
        _init_and_fetch(dest, source, None)

        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
                commits=[all_commits[0]],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 11, 30, tzinfo=UTC),
                commits=[all_commits[1]],
            ),
        ]
        unique, skipped = _deduplicate_groups(dest, groups, source_subdir="pkg", exclude_paths=None)
        # Both subdir trees DIFFER → both groups must be kept.
        assert skipped == 0
        assert len(unique) == 2

    def test_source_subdir_dedup_uses_subdir_tree(self, tmp_path: Path) -> None:
        """When source_subdir is set, dedup compares ONLY the subdir's tree.

        Two commits that change the subdir identically but differ outside the
        subdir must be deduped to ONE group.
        """
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        # Build a source with two commits that differ outside pkg/ but the
        # pkg/ contents are identical.
        source = tmp_path / "mono"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=source, capture_output=True, check=True
        )
        env = {
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin:/usr/local/bin",
        }
        # Commit 1: pkg/a.py + root.txt=v1
        (source / "pkg").mkdir()
        (source / "pkg" / "a.py").write_text("a\n")
        (source / "root.txt").write_text("v1\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: c1"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
        )
        # Commit 2: same pkg/, change only root.txt
        (source / "root.txt").write_text("v2\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: c2"],
            cwd=source,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
        )
        all_commits = get_commits_for_date(source, "2026-04-07")
        assert len(all_commits) == 2

        dest = tmp_path / "mono-dedup"
        _init_and_fetch(dest, source, None)

        # Two groups — each holding one of the commits. With source_subdir="pkg",
        # both should have IDENTICAL subdir tree → dedup to 1.
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
                commits=[all_commits[0]],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 11, 30, tzinfo=UTC),
                commits=[all_commits[1]],
            ),
        ]
        unique, skipped = _deduplicate_groups(dest, groups, source_subdir="pkg", exclude_paths=None)
        assert skipped == 1, "With identical subdir trees, second group must be deduped"
        assert len(unique) == 1

    def test_empty_input_returns_empty(self, tmp_path: Path) -> None:
        """No groups → empty result, 0 skipped."""
        from repogerbil.core.snapshot import _deduplicate_groups, _init_and_fetch

        source = _init_repo(tmp_path)
        dest = tmp_path / "dg-4"
        _init_and_fetch(dest, source, None)
        unique, skipped = _deduplicate_groups(dest, [], None, None)
        assert unique == []
        assert skipped == 0


class TestComputeWindowTimestampsExact:
    """Pin precise timestamp math in _compute_window_timestamps."""

    def _make_group(self, date_str: str, n_files: int = 1) -> TimeGroup:
        dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        return TimeGroup(
            period_start=dt,
            period_end=dt,
            commits=[CommitInfo(hash="a" * 40, date=date_str[:10], subject="feat: x")],
            files_affected=["f"] * n_files,
        )

    def test_returns_same_length_as_input(self) -> None:
        """One ts per group."""
        groups = [self._make_group(f"2026-04-{10 + i}T10:00:00") for i in range(5)]
        ts = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=1)
        assert len(ts) == 5

    def test_window_normal_lands_in_range_each_day(self) -> None:
        """For non-crossing window, all timestamps land between start_hm and end_hm."""
        groups = [self._make_group(f"2026-04-{10 + i}T10:00:00") for i in range(3)]
        ts = _compute_window_timestamps(groups, "14:00", "16:00", "UTC", seed=2)
        for t in ts:
            d = datetime.fromisoformat(t)
            assert 14 <= d.hour < 16 or (d.hour == 16 and d.minute == 0)

    def test_seed_zero_is_explicit_and_deterministic(self) -> None:
        """seed=0 (falsy) is still respected (not replaced with the default)."""
        groups = [self._make_group("2026-04-10T10:00:00") for _ in range(2)]
        a = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=0)
        b = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=0)
        assert a == b

    def test_different_seeds_produce_different_output(self) -> None:
        """Different seeds give different timestamps."""
        groups = [self._make_group("2026-04-10T10:00:00", 5) for _ in range(3)]
        a = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=1)
        b = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=2)
        assert a != b

    def test_midnight_crossing_when_end_lt_start(self) -> None:
        """end_hm < start_hm triggers next-day rollover."""
        groups = [self._make_group("2026-04-10T10:00:00", 1)]
        ts = _compute_window_timestamps(groups, "23:30", "02:00", "UTC", seed=1)
        d = datetime.fromisoformat(ts[0])
        # Window is 23:30 Apr 10 → 02:00 Apr 11. Result must land in [23:30 Apr10, 02:00 Apr11].
        assert (d.day == 10 and d.hour == 23 and d.minute >= 30) or (
            d.day == 11 and (d.hour < 2 or (d.hour == 2 and d.minute == 0))
        )

    def test_midnight_crossing_when_eh_eq_sh_and_em_le_sm(self) -> None:
        """eh==sh AND em<=sm also crosses midnight."""
        groups = [self._make_group("2026-04-10T10:00:00", 1)]
        # 20:30 → 20:30 should be a 24h window (em == sm), crossing midnight
        ts = _compute_window_timestamps(groups, "20:30", "20:30", "UTC", seed=1)
        d = datetime.fromisoformat(ts[0])
        # Should land between Apr 10 20:30 and Apr 11 20:30 (full 24h span)
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = datetime(2026, 4, 10, 20, 30, tzinfo=tz)
        end = datetime(2026, 4, 11, 20, 30, tzinfo=tz)
        assert start <= d <= end

    def test_non_crossing_when_end_gt_start(self) -> None:
        """end_hm > start_hm → same-day window, no rollover."""
        groups = [self._make_group("2026-04-10T10:00:00", 1)]
        ts = _compute_window_timestamps(groups, "08:00", "09:00", "UTC", seed=5)
        d = datetime.fromisoformat(ts[0])
        assert d.date().isoformat() == "2026-04-10"

    def test_multi_day_each_in_own_day(self) -> None:
        """Groups on different days bucketed independently."""
        groups = [
            self._make_group("2026-04-10T10:00:00", 1),
            self._make_group("2026-04-12T10:00:00", 1),
            self._make_group("2026-04-11T10:00:00", 1),
        ]
        ts = _compute_window_timestamps(groups, "14:00", "15:00", "UTC", seed=9)
        d0 = datetime.fromisoformat(ts[0])
        d1 = datetime.fromisoformat(ts[1])
        d2 = datetime.fromisoformat(ts[2])
        assert d0.date().isoformat() == "2026-04-10"
        assert d1.date().isoformat() == "2026-04-12"
        assert d2.date().isoformat() == "2026-04-11"

    def test_seed_change_changes_output(self) -> None:
        """Default seed depends on input — changing window changes the seed/output."""
        groups = [self._make_group("2026-04-10T10:00:00", 3) for _ in range(2)]
        a = _compute_window_timestamps(groups, "20:00", "21:00", "UTC")
        b = _compute_window_timestamps(groups, "20:00", "22:00", "UTC")
        # Different window → different default seed → different output
        assert a != b


class TestSpreadTimestampsForDayExact:
    """Pin precise math in _spread_timestamps_for_day."""

    def _make_group(self, n_files: int) -> TimeGroup:
        return TimeGroup(
            period_start=datetime(2026, 4, 10, tzinfo=UTC),
            period_end=datetime(2026, 4, 10, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-10", subject="feat: x")],
            files_affected=["f"] * n_files,
        )

    def test_returns_list_of_strings(self) -> None:
        """Output is a list of ISO timestamp strings, one per group."""
        from datetime import datetime as dt_cls
        import random
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 21, 0, tzinfo=tz)
        groups = [self._make_group(1), self._make_group(1)]
        result = _spread_timestamps_for_day(groups, start, end, random.Random(0))
        assert len(result) == 2
        assert all(isinstance(r, str) for r in result)

    def test_zero_files_treated_as_weight_one(self) -> None:
        """Groups with 0 files_affected use min weight = 1 (not 0 → ZeroDivision)."""
        from datetime import datetime as dt_cls
        import random
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 21, 0, tzinfo=tz)
        groups = [self._make_group(0), self._make_group(0), self._make_group(0)]
        # Must not raise — fall-back weight=1 means equal slots.
        result = _spread_timestamps_for_day(groups, start, end, random.Random(0))
        assert len(result) == 3
        parsed = [datetime.fromisoformat(t) for t in result]
        for i in range(len(parsed) - 1):
            assert parsed[i] < parsed[i + 1]

    def test_single_group_one_result(self) -> None:
        """Single-group path returns exactly one timestamp."""
        from datetime import datetime as dt_cls
        import random
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 21, 0, tzinfo=tz)
        result = _spread_timestamps_for_day([self._make_group(5)], start, end, random.Random(0))
        assert len(result) == 1

    def test_format_includes_timezone_offset(self) -> None:
        """Result strings include a numeric timezone offset (strftime %z)."""
        from datetime import datetime as dt_cls
        import random
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 21, 0, tzinfo=tz)
        result = _spread_timestamps_for_day([self._make_group(1)], start, end, random.Random(0))
        # UTC → "+0000"
        assert result[0].endswith("+0000")


class TestCreateCommitsProgressFormat:
    """Pin exact progress-line format produced by _create_commits."""

    def test_progress_format_idx_slash_total(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """Progress shows '[<idx>/<total>]' with zero-padded idx matching total width."""
        source = _init_repo(tmp_path)
        # Add an Apr-09 commit to ensure 3-digit count is exercised? Use 2 to test [1/2] and [2/2].
        dest = tmp_path / "prog-1"
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]
        create_snapshot(source, dest, groups, progress=True)
        err = capsys.readouterr().err
        lines = [ln for ln in err.splitlines() if ln.strip()]
        assert len(lines) == 2
        # idx-1 is 1, total is 2; width = len(str(2)) = 1 → "[1/2]"
        assert lines[0].startswith("[1/2] ")
        assert lines[1].startswith("[2/2] ")
        # period_start.strftime("%Y-%m-%d %H:%M") format — confirm precise pattern,
        # not just a substring (a mutation like "XX%Y-%m-%d %H:%MXX" would still
        # contain the date substring).
        assert "XX" not in lines[0] and "XX" not in lines[1]
        # The ts portion is exactly 16 chars (YYYY-MM-DD HH:MM).
        # After "[1/2] " (6 chars), the timestamp begins.
        assert lines[0][6:22] == "2026-04-07 00:00"
        assert lines[1][6:22] == "2026-04-08 00:00"

    def test_progress_default_is_false(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """progress defaults to False — no stderr output when not requested.

        Pins the default to ``progress: bool = False`` against a mutation
        flipping it to ``True``.
        """
        source = _init_repo(tmp_path)
        dest = tmp_path / "prog-default"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        # Call WITHOUT progress kwarg → default. Must produce no per-commit progress line.
        result = create_snapshot(source, dest, groups)
        assert result.commits_created == 1
        err = capsys.readouterr().err
        # No "[1/1]" style progress line should appear (which is the marker
        # progress=True produces).
        assert "[1/1]" not in err

    def test_progress_first_line_truncated_to_72_chars(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Progress shows only the first line of the message, truncated to 72 chars."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "prog-2"
        apr7 = get_commits_for_date(source, "2026-04-07")
        # Build a multi-line, very long subject. The first line will be truncated to 72 chars.
        long_subject = "feat: " + "x" * 200
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=[
                    CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject=long_subject),
                ],
            ),
        ]
        create_snapshot(source, dest, groups, progress=True)
        err = capsys.readouterr().err
        lines = [ln for ln in err.splitlines() if ln.strip()]
        assert len(lines) == 1
        # After "[1/1] YYYY-MM-DD HH:MM  " the remainder is at most 72 chars
        # Find the message portion after the timestamp by splitting on the 2-space delimiter
        _prefix, _, msg_part = lines[0].partition("  ")
        # msg_part is the truncated message. The subject starts with "feat: " (6 chars),
        # so truncated form is "feat: " + 66 'x'.
        assert msg_part == "feat: " + "x" * 66
        assert len(msg_part) == 72


class TestGetFilesForCommitExact:
    """Pin exact behavior of _get_files_for_commit beyond the bad-hash case."""

    def test_returns_sorted_unique_paths(self, tmp_path: Path) -> None:
        """Files are returned sorted; whitespace-only lines filtered."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "gfc-1"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        commits = get_commits_for_date(source, "2026-04-08")
        files = _get_files_for_commit(dest, commits[0].hash)
        # The apr-08 commit added "b.py"
        assert files == ["b.py"]


class TestGetCommitBodyExact:
    """Pin exact behavior of _get_commit_body."""

    def test_strips_trailing_whitespace(self, tmp_path: Path) -> None:
        """Output is .strip()ed."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "gcb-1"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        commits = get_commits_for_date(source, "2026-04-07")
        body = _get_commit_body(dest, commits[0].hash)
        # No leading or trailing whitespace
        assert body == body.strip()
        assert body == "add a"


class TestLlmSummariesSidecarExact:
    """Pin exact JSONL record fields written to the summaries sidecar."""

    def test_record_has_required_keys(self, tmp_path: Path) -> None:
        """LLM sidecar record contains exactly hash, date, subjects, body, changes."""
        import json
        from pathlib import Path as _Path

        from repogerbil.llm.client import FakeOllamaClient
        from repogerbil.llm.generator import MessageGenerator

        fixtures = _Path(__file__).parent.parent / "fixtures" / "ollama_responses"
        response = json.loads((fixtures / "valid_single.json").read_text())

        source = _init_repo(tmp_path)
        dest = tmp_path / "ll-sidecar"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        gen = MessageGenerator(client=FakeOllamaClient([response]), model="gemma4")
        result = create_snapshot(source, dest, groups, llm_generator=gen)
        assert result.summaries_path is not None
        sidecar = Path(result.summaries_path)
        rec = json.loads(sidecar.read_text().strip())
        assert set(rec.keys()) == {"hash", "date", "subjects", "body", "changes"}
        # date format is %Y-%m-%d
        assert rec["date"] == "2026-04-07"

    def test_sidecar_filename_is_dest_dot_summaries_jsonl(self, tmp_path: Path) -> None:
        """Sidecar path is '<dest>.summaries.jsonl' next to dest."""
        import json
        from pathlib import Path as _Path

        from repogerbil.llm.client import FakeOllamaClient
        from repogerbil.llm.generator import MessageGenerator

        fixtures = _Path(__file__).parent.parent / "fixtures" / "ollama_responses"
        response = json.loads((fixtures / "valid_single.json").read_text())

        source = _init_repo(tmp_path)
        dest = tmp_path / "sidecar-name"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        gen = MessageGenerator(client=FakeOllamaClient([response]), model="gemma4")
        result = create_snapshot(source, dest, groups, llm_generator=gen)
        expected = str(dest.parent / "sidecar-name.summaries.jsonl")
        assert result.summaries_path == expected

    def test_llm_generate_called_with_correct_kwargs(self, tmp_path: Path) -> None:
        """LLM generator.generate is called with date_str, files, commit_count,
        original_subjects, original_bodies — pinned by name, not position."""
        from unittest.mock import MagicMock

        from repogerbil.llm.generator import GeneratedMessage

        source = _init_repo(tmp_path)
        dest = tmp_path / "llm-kwargs"
        apr7 = get_commits_for_date(source, "2026-04-07")
        # Non-conventional subject so LLM is triggered
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=[CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="freeform")],
            ),
        ]
        gen = MagicMock()
        gen.generate.return_value = GeneratedMessage(
            message="feat: refined message",
            body="body text",
            changes=[{"file": "a.py", "description": "added"}],
        )
        create_snapshot(source, dest, groups, llm_generator=gen)
        # Exactly one call
        gen.generate.assert_called_once()
        call_kwargs = gen.generate.call_args.kwargs
        # Exact keyword names — no positional fallbacks
        assert call_kwargs["date_str"] == "2026-04-07"
        assert call_kwargs["commit_count"] == 1
        assert call_kwargs["original_subjects"] == ["freeform"]
        assert call_kwargs["original_bodies"] == ["add a"]
        # files is sorted list
        assert call_kwargs["files"] == sorted(call_kwargs["files"])

    def test_llm_failure_falls_back_to_changelog_message(self, tmp_path: Path) -> None:
        """When LLM raises AND changelog has the date, fallback message is the
        changelog message (not date-count format).

        Pins the LLM-error recovery branch's _build_snapshot_message call:
        ``_build_snapshot_message(group, changelog_messages, used_changelog_keys)``.
        A mutation passing ``None`` for changelog_messages would force the
        date-count fallback even with a valid changelog.
        """
        from unittest.mock import MagicMock

        source = _init_repo(tmp_path)
        dest = tmp_path / "llm-fail-cl"
        apr7 = get_commits_for_date(source, "2026-04-07")
        # Non-conventional subject → LLM is triggered
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=[CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="garbage")],
            ),
        ]
        gen = MagicMock()
        gen.generate.side_effect = TimeoutError("boom")
        result = create_snapshot(
            source,
            dest,
            groups,
            changelog_messages={"2026-04-07": "feat(yaml): from-changelog message"},
            llm_generator=gen,
        )
        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%B", "-1"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        # Must be the changelog message — NOT the date-count fallback
        assert log == "feat(yaml): from-changelog message"

    def test_llm_failure_uses_changelog_tracking_across_same_day(self, tmp_path: Path) -> None:
        """Even in the LLM-failure fallback path, ``used_changelog_keys`` must
        be honoured: same-day groups don't reuse the same changelog entry.

        Pins the LLM-error branch's 3rd positional arg
        (``used_changelog_keys``); a mutation to ``None`` would let both
        groups reuse the same changelog entry.
        """
        from unittest.mock import MagicMock

        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # Add second Apr-7 commit for distinct trees
        (source / "c.py").write_text("c\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "more freeform"],
            cwd=source,
            capture_output=True,
            check=True,
            env={
                **env,
                "GIT_AUTHOR_DATE": "2026-04-07T15:00:00",
                "GIT_COMMITTER_DATE": "2026-04-07T15:00:00",
            },
        )
        dest = tmp_path / "llm-fail-2g"
        apr7 = get_commits_for_date(source, "2026-04-07")
        # Both subjects non-conventional → LLM triggered for both
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
                commits=[CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="freeform a")],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 7, 15, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 15, 30, tzinfo=UTC),
                commits=[CommitInfo(hash=apr7[1].hash, date=apr7[1].date, subject="freeform b")],
            ),
        ]
        gen = MagicMock()
        gen.generate.side_effect = TimeoutError("boom")
        result = create_snapshot(
            source,
            dest,
            groups,
            changelog_messages={"2026-04-07": "feat(yaml): only-once"},
            llm_generator=gen,
        )
        assert result.commits_created == 2
        msgs = subprocess.run(
            ["git", "log", "--format=%B---END---", "--reverse"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("---END---")
        msgs = [m.strip() for m in msgs if m.strip()]
        assert len(msgs) == 2
        # Exactly one of the two commits should carry the changelog text
        changelog_count = sum(1 for m in msgs if m == "feat(yaml): only-once")
        assert changelog_count == 1

    def test_llm_files_filtered_by_exclude_paths(self, tmp_path: Path) -> None:
        """exclude_paths is forwarded to _exclude_files when collecting the
        LLM file list. Pins ``_exclude_files(all_files, exclude_paths)`` against
        a mutation passing ``None`` for the regex list."""
        from unittest.mock import MagicMock

        from repogerbil.llm.generator import GeneratedMessage

        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # Add a lock file at root + Apr-7 commit
        (source / "poetry.lock").write_text("locked\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "freeform"],
            cwd=source,
            capture_output=True,
            check=True,
            env={
                **env,
                "GIT_AUTHOR_DATE": "2026-04-09T10:00:00",
                "GIT_COMMITTER_DATE": "2026-04-09T10:00:00",
            },
        )
        dest = tmp_path / "llm-excl"
        apr9 = get_commits_for_date(source, "2026-04-09")
        # Non-conventional subject to trigger LLM
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 9, tzinfo=UTC),
                period_end=datetime(2026, 4, 9, 23, 59, tzinfo=UTC),
                commits=[CommitInfo(hash=apr9[0].hash, date=apr9[0].date, subject="freeform")],
            ),
        ]
        gen = MagicMock()
        gen.generate.return_value = GeneratedMessage(
            message="feat: x",
            body="b",
            changes=[],
        )
        create_snapshot(
            source,
            dest,
            groups,
            llm_generator=gen,
            exclude_paths=[r".*\.lock$"],
        )
        gen.generate.assert_called_once()
        files = gen.generate.call_args.kwargs["files"]
        # poetry.lock must be excluded from the files passed to LLM
        assert "poetry.lock" not in files

    def test_llm_not_called_when_all_well_formed(self, tmp_path: Path) -> None:
        """LLM generator is NOT invoked when every subject is well-formed."""
        from unittest.mock import MagicMock

        source = _init_repo(tmp_path)
        dest = tmp_path / "llm-skip"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                # Use a conventional subject
                commits=[CommitInfo(hash=apr7[0].hash, date=apr7[0].date, subject="feat: hello")],
            ),
        ]
        gen = MagicMock()
        create_snapshot(source, dest, groups, llm_generator=gen)
        # Generator must not be called when all subjects are well-formed
        gen.generate.assert_not_called()


class TestCreateCommitsBoundary:
    """Pin boundary behavior in _create_commits — index, counter, idx-1 offset."""

    def test_commits_created_counter_matches_groups_processed(self, tmp_path: Path) -> None:
        """commits_created increments by exactly 1 per processed group."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "cc-count"
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]
        # Set 3 groups, but apr7-only twice so dedup removes 1
        groups_with_dup = [groups[0], groups[0], groups[1]]
        result = create_snapshot(source, dest, groups_with_dup)
        # commits_created must equal len(deduplicated) == 2
        assert result.commits_created == 2

    def test_window_timestamps_idx_offset_is_minus_one(self, tmp_path: Path) -> None:
        """Each group is matched to window_timestamps[idx-1], so timestamps line up."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "wt-idx"
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]
        create_snapshot(
            source,
            dest,
            groups,
            timezone="UTC",
            time_window_start="10:00",
            time_window_end="14:00",
        )
        # Both timestamps must be in the 10:00-14:00 window. If idx offset is off-by-one
        # (e.g. idx+1 instead of idx-1), one would IndexError, the other would land wrong.
        ts_lines = (
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
        assert len(ts_lines) == 2
        for line in ts_lines:
            t = datetime.strptime(line.strip(), "%Y-%m-%d %H:%M:%S %z")
            assert 10 <= t.hour < 14 or (t.hour == 14 and t.minute == 0)

    def test_source_subdir_success_path(self, tmp_path: Path) -> None:
        """When source_subdir EXISTS in the commit, its subtree is used."""
        # Build a source with a subdirectory
        source = tmp_path / "mono"
        source.mkdir()
        subprocess.run(["git", "init"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=source, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=source, capture_output=True, check=True
        )
        # Create both a subdir and a root file
        (source / "pkg").mkdir()
        (source / "pkg" / "a.py").write_text("a\n")
        (source / "other.txt").write_text("other\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: pkg + other"],
            cwd=source,
            capture_output=True,
            check=True,
            env={
                "HOME": str(tmp_path),
                "PATH": "/usr/bin:/bin:/usr/local/bin",
                "GIT_AUTHOR_DATE": "2026-04-07T10:00:00",
                "GIT_COMMITTER_DATE": "2026-04-07T10:00:00",
            },
        )
        dest = tmp_path / "mono-snap"
        commits = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=commits,
            ),
        ]
        result = create_snapshot(source, dest, groups, source_subdir="pkg")
        assert result.commits_created == 1
        # The committed tree must have a.py at root (subdir was used) and NOT other.txt
        tree = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "a.py" in tree
        assert "other.txt" not in tree

    def test_multi_commit_group_uses_last_tree(self, tmp_path: Path) -> None:
        """Multi-commit groups commit the tree from the LAST commit (group.commits[-1])."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "last-tree"
        apr7 = get_commits_for_date(source, "2026-04-07")
        apr8 = get_commits_for_date(source, "2026-04-08")
        # One group spanning both commits — order: apr7 first, apr8 last
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, tzinfo=UTC),
                commits=[apr7[0], apr8[0]],
            ),
        ]
        create_snapshot(source, dest, groups)
        tree = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        # Apr 8's tree has both a.py and b.py; Apr 7's only has a.py.
        # If the code used [0] or [+1] etc, b.py would be missing.
        assert "a.py" in tree
        assert "b.py" in tree


class TestComputeWindowDayBucketing:
    """Pin _compute_window_timestamps day-bucketing math."""

    def _make_group(self, date_str: str, n_files: int = 1) -> TimeGroup:
        dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        return TimeGroup(
            period_start=dt,
            period_end=dt,
            commits=[CommitInfo(hash="a" * 40, date=date_str[:10], subject="feat: x")],
            files_affected=["f"] * n_files,
        )

    def test_default_window_seed_changes_with_window_args(self) -> None:
        """_default_window_seed considers window_start, end, timezone — not just groups."""
        from repogerbil.core._snapshot_timestamps import _default_window_seed

        groups = [self._make_group("2026-04-10T10:00:00", 3)]
        s1 = _default_window_seed(groups, "20:00", "23:00", "UTC")
        s2 = _default_window_seed(groups, "20:00", "23:00", "America/Los_Angeles")
        s3 = _default_window_seed(groups, "21:00", "23:00", "UTC")
        s4 = _default_window_seed(groups, "20:00", "22:00", "UTC")
        # All four seeds should be distinct (any pair-wise equal hints at a mutation)
        assert len({s1, s2, s3, s4}) == 4

    def test_default_window_seed_includes_files_affected_count(self) -> None:
        """Changing files_affected length changes the seed."""
        from repogerbil.core._snapshot_timestamps import _default_window_seed

        s1 = _default_window_seed([self._make_group("2026-04-10T10:00:00", 1)], "20:00", "23:00", "UTC")
        s2 = _default_window_seed([self._make_group("2026-04-10T10:00:00", 5)], "20:00", "23:00", "UTC")
        assert s1 != s2

    def test_default_window_seed_includes_commit_hash(self) -> None:
        """Changing the commit hash changes the seed."""
        from repogerbil.core._snapshot_timestamps import _default_window_seed

        g1 = TimeGroup(
            period_start=datetime(2026, 4, 10, tzinfo=UTC),
            period_end=datetime(2026, 4, 10, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-10", subject="x")],
        )
        g2 = TimeGroup(
            period_start=datetime(2026, 4, 10, tzinfo=UTC),
            period_end=datetime(2026, 4, 10, tzinfo=UTC),
            commits=[CommitInfo(hash="b" * 40, date="2026-04-10", subject="x")],
        )
        s1 = _default_window_seed([g1], "20:00", "23:00", "UTC")
        s2 = _default_window_seed([g2], "20:00", "23:00", "UTC")
        assert s1 != s2

    def test_default_window_seed_includes_period_end(self) -> None:
        """Changing period_end (not just start) changes the seed."""
        from repogerbil.core._snapshot_timestamps import _default_window_seed

        g1 = TimeGroup(
            period_start=datetime(2026, 4, 10, tzinfo=UTC),
            period_end=datetime(2026, 4, 10, 12, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-10", subject="x")],
        )
        g2 = TimeGroup(
            period_start=datetime(2026, 4, 10, tzinfo=UTC),
            period_end=datetime(2026, 4, 10, 13, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-10", subject="x")],
        )
        s1 = _default_window_seed([g1], "20:00", "23:00", "UTC")
        s2 = _default_window_seed([g2], "20:00", "23:00", "UTC")
        assert s1 != s2

    def test_default_window_seed_is_deterministic(self) -> None:
        """Identical inputs give identical seeds."""
        from repogerbil.core._snapshot_timestamps import _default_window_seed

        groups = [self._make_group("2026-04-10T10:00:00", 3)]
        s1 = _default_window_seed(groups, "20:00", "23:00", "UTC")
        s2 = _default_window_seed(groups, "20:00", "23:00", "UTC")
        assert s1 == s2

    def test_default_window_seed_int_in_uint64_range(self) -> None:
        """Seed is an int derived from first 16 hex chars (fits in 64 bits)."""
        from repogerbil.core._snapshot_timestamps import _default_window_seed

        groups = [self._make_group("2026-04-10T10:00:00", 3)]
        s = _default_window_seed(groups, "20:00", "23:00", "UTC")
        assert isinstance(s, int)
        assert 0 <= s < 2**64


class TestResolveTimestampAdditional:
    """More precise tests of _resolve_timestamp."""

    def test_uses_period_end_format_exact(self) -> None:
        """Fallback format is exactly '%Y-%m-%dT%H:%M:%S' (no offset, no microseconds)."""
        from repogerbil.core.snapshot import _resolve_timestamp

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 12, 31, 5, 7, 9, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        result = _resolve_timestamp(g, None, None)
        # Pin precise format: 4-digit year, 2-digit month/day/H/M/S, 'T' separator, no offset
        assert result == "2026-12-31T05:07:09"

    def test_make_timestamp_called_with_period_start_year_month_day(self) -> None:
        """Day construction uses period_start.year/month/day individually."""
        from repogerbil.core.snapshot import _resolve_timestamp

        g = TimeGroup(
            # Distinct year/month/day so any single-arg mutation visibly changes output
            period_start=datetime(2026, 7, 21, 10, 0, tzinfo=UTC),
            period_end=datetime(2099, 1, 1, 23, 59, 59, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-07-21", subject="x")],
        )
        result = _resolve_timestamp(g, "12:34", "UTC")
        # Day comes from period_start (2026-07-21), not period_end (2099-01-01)
        assert result.startswith("2026-07-21T12:34:00")


class TestCommitWithTimestampAdditional:
    """Additional tests for _commit_with_timestamp."""

    def test_preserve_false_does_not_inherit_envs(self, tmp_path: Path) -> None:
        """preserve=False doesn't pass GIT_AUTHOR_DATE — current time is used."""
        from datetime import datetime as dt_cls

        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-nopreserve"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        commits = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{commits[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree_sha], cwd=dest, capture_output=True, check=True)
        before = dt_cls.now()
        sha = _commit_with_timestamp(dest, tree_sha, "msg", "2020-01-01T00:00:00", False)
        after = dt_cls.now()
        # When preserve=False, the date_str is ignored — current time is committed
        author_unix = int(
            subprocess.run(
                ["git", "log", "-1", "--format=%at", sha],
                cwd=dest,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        # Must be in [before, after] window — not the 2020 date
        assert before.timestamp() - 5 <= author_unix <= after.timestamp() + 5

    def test_subsequent_commits_have_HEAD_as_parent(self, tmp_path: Path) -> None:
        """The second commit's parent is the HEAD that was set by update-ref."""
        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-head"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        apr7 = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{apr7[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree_sha], cwd=dest, capture_output=True, check=True)
        first = _commit_with_timestamp(dest, tree_sha, "first", "2026-05-01T00:00:00", False)
        # Verify refs/heads/main moved
        main = subprocess.run(
            ["git", "rev-parse", "refs/heads/main"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert main == first

    def test_message_committed_exactly(self, tmp_path: Path) -> None:
        """The provided message ends up as the commit's message (no mutation)."""
        from repogerbil.core.snapshot import _commit_with_timestamp

        source = _init_repo(tmp_path)
        dest = tmp_path / "cwt-msg"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "remote", "add", "src", str(source)], cwd=dest, capture_output=True, check=True)
        subprocess.run(["git", "fetch", "src"], cwd=dest, capture_output=True, check=True)
        apr7 = get_commits_for_date(source, "2026-04-07")
        tree_sha = subprocess.run(
            ["git", "rev-parse", f"{apr7[0].hash}^{{tree}}"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        subprocess.run(["git", "read-tree", tree_sha], cwd=dest, capture_output=True, check=True)
        sha = _commit_with_timestamp(dest, tree_sha, "EXACT_TEST_MESSAGE_XYZ", "2026-05-01T12:00:00", False)
        body = subprocess.run(
            ["git", "log", "-1", "--format=%B", sha],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert body == "EXACT_TEST_MESSAGE_XYZ"


class TestBuildSnapshotMessageNoneUsedKeys:
    """Additional tests of _build_snapshot_message used_keys=None branch."""

    def test_used_keys_none_does_not_track(self) -> None:
        """used_keys=None means the same changelog can be reused across groups."""
        from repogerbil.core.snapshot import _build_snapshot_message

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        msg1 = _build_snapshot_message(g, {"2026-04-07": "M"}, used_keys=None)
        msg2 = _build_snapshot_message(g, {"2026-04-07": "M"}, used_keys=None)
        assert msg1 == "M"
        assert msg2 == "M"

    def test_used_keys_default_is_none(self) -> None:
        """used_keys parameter defaults to None — call without it works."""
        from repogerbil.core.snapshot import _build_snapshot_message

        g = TimeGroup(
            period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 11, 0, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-07", subject="x")],
        )
        msg = _build_snapshot_message(g, {"2026-04-07": "M"})
        assert msg == "M"


class TestSnapshotResultDataclass:
    """SnapshotResult field defaults / construction."""

    def test_defaults(self) -> None:
        """SnapshotResult has the expected defaults."""
        r = SnapshotResult(dest_path="/x", groups_created=1, commits_created=1)
        assert r.groups_skipped == 0
        assert r.summaries_path is None

    def test_explicit_construction(self) -> None:
        """All five fields can be set explicitly."""
        r = SnapshotResult(
            dest_path="/p",
            groups_created=10,
            commits_created=7,
            groups_skipped=3,
            summaries_path="/p.summaries.jsonl",
        )
        assert r.dest_path == "/p"
        assert r.groups_created == 10
        assert r.commits_created == 7
        assert r.groups_skipped == 3
        assert r.summaries_path == "/p.summaries.jsonl"

    def test_is_frozen(self) -> None:
        """SnapshotResult is frozen — assignment raises."""
        r = SnapshotResult(dest_path="/x", groups_created=1, commits_created=1)
        import dataclasses

        with pytest.raises(dataclasses.FrozenInstanceError):
            r.dest_path = "/y"  # type: ignore[misc]


class TestSpreadTimestampsAdditional:
    """Additional tests for _spread_timestamps_for_day."""

    def _g(self, n_files: int) -> TimeGroup:
        return TimeGroup(
            period_start=datetime(2026, 4, 10, tzinfo=UTC),
            period_end=datetime(2026, 4, 10, tzinfo=UTC),
            commits=[CommitInfo(hash="a" * 40, date="2026-04-10", subject="feat: x")],
            files_affected=["f"] * n_files,
        )

    def test_weighted_spacing_keeps_results_strictly_increasing(self) -> None:
        """Even with very uneven weights, output is strictly increasing."""
        from datetime import datetime as dt_cls
        import random
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 23, 0, tzinfo=tz)
        # Weights: 1, 100, 1
        groups = [self._g(1), self._g(100), self._g(1)]
        result = _spread_timestamps_for_day(groups, start, end, random.Random(42))
        parsed = [datetime.fromisoformat(r) for r in result]
        assert parsed[0] < parsed[1] < parsed[2]
        # All within window
        for p in parsed:
            assert start <= p <= end

    def test_single_group_with_zero_files_uses_full_window(self) -> None:
        """Single group with zero files_affected still works (no ZeroDiv)."""
        from datetime import datetime as dt_cls
        import random
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("UTC")
        start = dt_cls(2026, 4, 10, 20, 0, tzinfo=tz)
        end = dt_cls(2026, 4, 10, 23, 0, tzinfo=tz)
        # files_affected=0 — single group branch
        result = _spread_timestamps_for_day([self._g(0)], start, end, random.Random(0))
        assert len(result) == 1
        d = datetime.fromisoformat(result[0])
        assert start <= d <= end


class TestComputeWindowTimestampsAdditional:
    """Additional checks for _compute_window_timestamps."""

    def _make_group(self, date_str: str, n_files: int = 1) -> TimeGroup:
        dt = datetime.fromisoformat(date_str).replace(tzinfo=UTC)
        return TimeGroup(
            period_start=dt,
            period_end=dt,
            commits=[CommitInfo(hash="a" * 40, date=date_str[:10], subject="feat: x")],
            files_affected=["f"] * n_files,
        )

    def test_returns_in_input_order(self) -> None:
        """Timestamps are returned in input order (not sorted-by-time)."""
        # Build groups in reverse chronological order
        groups = [
            self._make_group("2026-04-12T10:00:00"),
            self._make_group("2026-04-10T10:00:00"),
        ]
        result = _compute_window_timestamps(groups, "20:00", "23:00", "UTC", seed=1)
        # Result[0] corresponds to groups[0] (Apr 12)
        d0 = datetime.fromisoformat(result[0])
        d1 = datetime.fromisoformat(result[1])
        assert d0.date().isoformat() == "2026-04-12"
        assert d1.date().isoformat() == "2026-04-10"

    def test_partial_window_args_do_not_trigger_window_branch(self, tmp_path: Path) -> None:
        """time_window_start without end/timezone must NOT invoke window logic.

        Pins ``and``: with ``or``, the partial-args case would proceed and crash
        on _compute_window_timestamps' integer parse.
        """
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-partial-window"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        # Pass only time_window_start (no end, no tz). Must succeed via period_end fallback.
        result = create_snapshot(
            source,
            dest,
            groups,
            time_window_start="20:00",  # alone — no end, no tz
        )
        assert result.commits_created == 1

    def test_partial_window_only_timezone_does_not_trigger(self, tmp_path: Path) -> None:
        """timezone alone (no time_window_*) must NOT invoke window logic."""
        source = _init_repo(tmp_path)
        dest = tmp_path / "snap-only-tz"
        apr7 = get_commits_for_date(source, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        result = create_snapshot(
            source,
            dest,
            groups,
            timezone="UTC",  # alone
        )
        assert result.commits_created == 1

    def test_used_changelog_keys_tracked_across_groups(self, tmp_path: Path) -> None:
        """When two groups share a date and a changelog message exists, only the
        first group gets the changelog; the second falls back to the date-count
        format. This pins ``used_changelog_keys: set[str] = set()`` (mutation to
        ``= None`` would let both groups reuse the same changelog message)."""
        source = _init_repo(tmp_path)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        # Add another Apr-7 commit so we have two distinct commit hashes on the
        # same day (otherwise dedup collapses them).
        (source / "c.py").write_text("c\n")
        subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add c"],
            cwd=source,
            capture_output=True,
            check=True,
            env={
                **env,
                "GIT_AUTHOR_DATE": "2026-04-07T15:00:00",
                "GIT_COMMITTER_DATE": "2026-04-07T15:00:00",
            },
        )
        dest = tmp_path / "snap-changelog-dedup"
        apr7 = get_commits_for_date(source, "2026-04-07")
        # Build two groups on Apr 7 with distinct commits each
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, 10, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 10, 30, tzinfo=UTC),
                commits=[apr7[0]],
            ),
            TimeGroup(
                period_start=datetime(2026, 4, 7, 15, 0, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 15, 30, tzinfo=UTC),
                commits=[apr7[1]],
            ),
        ]
        result = create_snapshot(
            source,
            dest,
            groups,
            changelog_messages={"2026-04-07": "feat(changelog): same-day changelog message"},
        )
        # Both groups should produce commits (distinct trees)
        assert result.commits_created == 2
        # Inspect commit messages — exactly one should equal the changelog,
        # the other should fall back to the date-count format.
        msgs = subprocess.run(
            ["git", "log", "--format=%B---END---", "--reverse"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("---END---")
        msgs = [m.strip() for m in msgs if m.strip()]
        assert len(msgs) == 2
        changelog_count = sum(1 for m in msgs if m == "feat(changelog): same-day changelog message")
        # Exactly one commit should carry the changelog text
        assert changelog_count == 1

    def test_timezone_applied_to_window(self) -> None:
        """The window's tz is the configured tz (not UTC)."""
        groups = [self._make_group("2026-04-10T10:00:00")]
        # 20:00 LA is 03:00 UTC next day
        result = _compute_window_timestamps(groups, "20:00", "20:01", "America/Los_Angeles", seed=1)
        ts = datetime.fromisoformat(result[0])
        # Must have non-UTC offset (LA is -07:00 or -08:00)
        utc_off = ts.utcoffset()
        assert utc_off is not None
        offset_minutes = utc_off.total_seconds() / 60
        assert offset_minutes != 0
        assert offset_minutes in (-480, -420)  # PST or PDT
