# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for commit consolidation."""

from datetime import UTC, datetime
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.consolidate import (
    ConsolidationResult,
    consolidate,
    generate_consolidation_preview,
)
from repogerbil.core.git import CommitInfo


def _seed_three_commits(repo: Path) -> Path:
    """Seed an existing repo with 3 commits across 2 days (2026-04-07 / 04-08)."""
    (repo / "f1.py").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add f1"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-07T10:00:00",
            "GIT_COMMITTER_DATE": "2026-04-07T10:00:00",
        },
    )

    (repo / "f2.py").write_text("b\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: add f2"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-07T11:00:00",
            "GIT_COMMITTER_DATE": "2026-04-07T11:00:00",
        },
    )

    (repo / "f3.py").write_text("c\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: add f3"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            "GIT_AUTHOR_DATE": "2026-04-08T09:00:00",
            "GIT_COMMITTER_DATE": "2026-04-08T09:00:00",
        },
    )

    return repo


class TestConsolidateDryRun:
    def test_dry_run_returns_preview(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr7 = get_commits_for_date(repo, "2026-04-07")
        apr8 = get_commits_for_date(repo, "2026-04-08")
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

        result = consolidate(repo, groups, dry_run=True)
        assert isinstance(result, ConsolidationResult)
        assert result.groups_consolidated == 2
        assert result.commits_consolidated == 3
        assert result.target_branch == "repogerbil-consolidated"

    def test_dry_run_doesnt_create_branch(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        commits = get_commits_for_date(repo, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=commits,
            ),
        ]

        consolidate(repo, groups, dry_run=True)
        branches = subprocess.run(
            ["git", "branch"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert "repogerbil-consolidated" not in branches


class TestGeneratePreview:
    def test_basic_preview(self) -> None:
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="feat: add thing", files=["src/a.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: broken", files=["src/b.py"]),
        ]
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=commits,
                files_affected=["src/a.py", "src/b.py"],
            ),
        ]
        previews = generate_consolidation_preview(groups)
        assert len(previews) == 1
        assert previews[0]["date"] == "2026-04-07"
        assert previews[0]["commit_count"] == 2
        assert previews[0]["files_affected"] == 2
        assert len(previews[0]["subjects"]) == 2

    def test_empty_groups(self) -> None:
        assert generate_consolidation_preview([]) == []


class TestConsolidateReal:
    def test_creates_branch_with_backup(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr7 = get_commits_for_date(repo, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]

        result = consolidate(repo, groups, create_backup=True)
        assert result.backup_branch != ""
        assert result.backup_tag != ""

        # Verify backup branch exists
        branches = subprocess.run(
            ["git", "branch"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert result.backup_branch in branches
        assert "repogerbil-consolidated" in branches

    def test_no_backup(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr7 = get_commits_for_date(repo, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]

        result = consolidate(repo, groups, create_backup=False, target_branch="no-backup-test")
        assert result.backup_branch == ""
        assert result.backup_tag == ""

    def test_changelog_message_used(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr7 = get_commits_for_date(repo, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        msgs = {"2026-04-07": "feat: custom changelog message for Apr 7"}

        consolidate(repo, groups, changelog_messages=msgs, target_branch="msg-test")

        # Check the commit message on the consolidated branch
        log_output = subprocess.run(
            ["git", "log", "--format=%s", "-1", "msg-test"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert log_output == "feat: custom changelog message for Apr 7"

    def test_no_timestamp_preservation(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr8 = get_commits_for_date(repo, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]

        result = consolidate(repo, groups, target_branch="no-ts-test", preserve_timestamps=False)
        assert result.groups_consolidated == 1

    def test_auto_message_single_commit(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr8 = get_commits_for_date(repo, "2026-04-08")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 8, tzinfo=UTC),
                period_end=datetime(2026, 4, 8, 23, 59, 59, tzinfo=UTC),
                commits=apr8,
            ),
        ]

        consolidate(repo, groups, target_branch="single-test")
        log_output = subprocess.run(
            ["git", "log", "--format=%s", "-1", "single-test"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert log_output == "chore: add f3"

    def test_failure_restores_original_branch_and_removes_target(self, git_repo: Path) -> None:
        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr7 = get_commits_for_date(repo, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]
        start_branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        with (
            patch("repogerbil.core.consolidate._consolidate_group", side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom"),
        ):
            consolidate(repo, groups, target_branch="should-not-survive")

        current_branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        assert current_branch == start_branch
        branches = subprocess.run(
            ["git", "branch", "--list", "should-not-survive"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert branches == ""

    def test_failure_before_target_creation_skips_delete_branch(self, git_repo: Path) -> None:
        from repogerbil.core.git import _run_git as git_run

        repo = _seed_three_commits(git_repo)
        from repogerbil.core.git import get_commits_for_date

        apr7 = get_commits_for_date(repo, "2026-04-07")
        groups = [
            TimeGroup(
                period_start=datetime(2026, 4, 7, tzinfo=UTC),
                period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
                commits=apr7,
            ),
        ]

        def fail_before_target(
            repo_path: Path,
            *args: str,
            timeout: int = 60,
            env: dict[str, str] | None = None,
        ) -> str:
            if args[:3] == ("rev-list", "--parents", "-n"):
                raise RuntimeError("boom-early")
            return git_run(repo_path, *args, timeout=timeout, env=env)

        with (
            patch("repogerbil.core.consolidate._run_git", side_effect=fail_before_target),
            pytest.raises(RuntimeError, match="boom-early"),
        ):
            consolidate(repo, groups, create_backup=False, target_branch="never-created")
