# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for commit consolidation."""

from datetime import UTC, datetime
from pathlib import Path
import subprocess

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.consolidate import (
    ConsolidationResult,
    consolidate,
    generate_consolidation_preview,
)
from repogerbil.core.git import CommitInfo


def _init_repo(tmp_path: Path) -> Path:
    """Create a temp git repo with 3 commits across 2 days."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)

    env_base = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}

    (repo / "f1.py").write_text("a\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add f1"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={
            **env_base,
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
            **env_base,
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
            **env_base,
            "GIT_AUTHOR_DATE": "2026-04-08T09:00:00",
            "GIT_COMMITTER_DATE": "2026-04-08T09:00:00",
        },
    )

    return repo


class TestConsolidateDryRun:
    def test_dry_run_returns_preview(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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

    def test_dry_run_doesnt_create_branch(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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
    def test_creates_branch_with_backup(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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

    def test_no_backup(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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

    def test_changelog_message_used(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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

    def test_no_timestamp_preservation(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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

    def test_auto_message_single_commit(self, tmp_path: Path) -> None:
        repo = _init_repo(tmp_path)
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
