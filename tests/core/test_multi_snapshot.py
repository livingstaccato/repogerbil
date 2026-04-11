# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for multi-repo snapshot creation."""

from __future__ import annotations

from pathlib import Path
import subprocess

import yaml

from repogerbil.core.multi_snapshot import (
    MultiSnapshotResult,
    create_multi_snapshot,
)


def _make_repo(tmp_path: Path, name: str, commits: list[tuple[str, str, str]]) -> Path:
    """Create a test git repo with commits at specific dates.

    Args:
        tmp_path: Temporary directory.
        name: Repo directory name.
        commits: List of (date, filename, message) tuples.

    Returns:
        Path to the created repo.
    """
    repo = tmp_path / name
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}

    for date_str, filename, message in commits:
        (repo / filename).write_text(f"content for {filename}\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=repo,
            capture_output=True,
            check=True,
            env={
                **env,
                "GIT_AUTHOR_DATE": f"{date_str}T12:00:00",
                "GIT_COMMITTER_DATE": f"{date_str}T12:00:00",
            },
        )
    return repo


class TestCreateMultiSnapshot:
    def test_two_repos_same_day(self, tmp_path: Path) -> None:
        """Two repos with commits on the same day produce one combined commit."""
        repo_a = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: alpha init")])
        repo_b = _make_repo(tmp_path, "beta", [("2026-01-15", "b.py", "feat: beta init")])
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo_a, "beta": repo_b},
            dest_path=dest,
        )

        assert isinstance(result, MultiSnapshotResult)
        assert result.commits_created == 1
        assert result.repos_included == ["alpha", "beta"]

        # Verify tree structure has subdirectories
        log = subprocess.run(["git", "log", "--oneline"], cwd=dest, capture_output=True, text=True, check=True)
        assert log.stdout.strip().count("\n") == 0  # exactly 1 commit

        # Check subdirectory layout
        ls_tree = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD"], cwd=dest, capture_output=True, text=True, check=True
        )
        dirs = ls_tree.stdout.strip().split("\n")
        assert "alpha" in dirs
        assert "beta" in dirs

    def test_two_repos_different_days(self, tmp_path: Path) -> None:
        """Two repos with commits on different days produce multiple commits."""
        repo_a = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: alpha")])
        repo_b = _make_repo(tmp_path, "beta", [("2026-01-16", "b.py", "feat: beta")])
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo_a, "beta": repo_b},
            dest_path=dest,
        )

        assert result.commits_created == 2

        # Second commit should have BOTH repos in tree (beta active, alpha carried forward)
        ls_tree = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD"], cwd=dest, capture_output=True, text=True, check=True
        )
        dirs = ls_tree.stdout.strip().split("\n")
        assert "alpha" in dirs
        assert "beta" in dirs

    def test_commit_timestamp_is_20_00_la(self, tmp_path: Path) -> None:
        """Commits are stamped at 20:00 America/Los_Angeles."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            commit_time="20:00",
            timezone="America/Los_Angeles",
        )

        log = subprocess.run(
            ["git", "log", "--format=%ai"], cwd=dest, capture_output=True, text=True, check=True
        )
        timestamp = log.stdout.strip()
        # Should be 20:00:00 with PST offset (-0800 in January)
        assert "20:00:00" in timestamp
        assert "-0800" in timestamp

    def test_commit_timestamp_dst(self, tmp_path: Path) -> None:
        """DST is handled correctly (PDT in July = -0700)."""
        repo = _make_repo(tmp_path, "alpha", [("2026-07-15", "a.py", "feat: summer")])
        dest = tmp_path / "dest"

        create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            commit_time="20:00",
            timezone="America/Los_Angeles",
        )

        log = subprocess.run(
            ["git", "log", "--format=%ai"], cwd=dest, capture_output=True, text=True, check=True
        )
        timestamp = log.stdout.strip()
        assert "20:00:00" in timestamp
        assert "-0700" in timestamp

    def test_repo_not_included_before_first_commit(self, tmp_path: Path) -> None:
        """A repo doesn't appear in the tree before its first commit date."""
        repo_a = _make_repo(tmp_path, "alpha", [("2026-01-10", "a.py", "feat: early")])
        repo_b = _make_repo(tmp_path, "beta", [("2026-01-20", "b.py", "feat: later")])
        dest = tmp_path / "dest"

        create_multi_snapshot(
            source_repos={"alpha": repo_a, "beta": repo_b},
            dest_path=dest,
        )

        # First commit (Jan 10): only alpha should be in tree
        ls_tree = subprocess.run(
            ["git", "ls-tree", "--name-only", "HEAD~1"], cwd=dest, capture_output=True, text=True, check=True
        )
        dirs = ls_tree.stdout.strip().split("\n")
        assert "alpha" in dirs
        assert "beta" not in dirs

    def test_changelog_messages_used(self, tmp_path: Path) -> None:
        """Commit message is assembled from changelog YAML when available."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "autocommit garbage")])
        dest = tmp_path / "dest"

        # Create changelog dir with proper YAML
        cl_dir = tmp_path / "changelogs" / "alpha"
        cl_dir.mkdir(parents=True)
        changelog = {
            "date": "2026-01-15",
            "repo": "alpha",
            "title": "Add widget system",
            "summary": "Introduces the widget abstraction layer.",
        }
        (cl_dir / "2026-01-15-alpha-changelog.yaml").write_text(yaml.dump(changelog))

        create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            changelog_dir=tmp_path / "changelogs",
        )

        log = subprocess.run(
            ["git", "log", "--format=%B"], cwd=dest, capture_output=True, text=True, check=True
        )
        message = log.stdout.strip()
        assert "Add widget system" in message
        assert "Introduces the widget abstraction layer" in message
        assert "autocommit garbage" not in message

    def test_since_filters_dates(self, tmp_path: Path) -> None:
        """The --since parameter filters out earlier dates."""
        repo = _make_repo(
            tmp_path,
            "alpha",
            [
                ("2026-01-10", "a.py", "feat: early"),
                ("2026-01-20", "b.py", "feat: later"),
            ],
        )
        dest = tmp_path / "dest"

        from datetime import date

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            since=date(2026, 1, 15),
        )

        assert result.commits_created == 1

    def test_empty_repos_skipped(self, tmp_path: Path) -> None:
        """Repos with no commits are skipped gracefully."""
        repo_a = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        repo_b = tmp_path / "empty"
        repo_b.mkdir()
        subprocess.run(["git", "init"], cwd=repo_b, capture_output=True, check=True)
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo_a, "empty": repo_b},
            dest_path=dest,
        )

        assert result.commits_created == 1
        assert "alpha" in result.repos_included

    def test_dest_must_not_exist_or_be_empty(self, tmp_path: Path) -> None:
        """Raises RuntimeError if dest exists and is non-empty."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"
        dest.mkdir()
        (dest / "blocker.txt").write_text("existing content")

        import pytest

        with pytest.raises(RuntimeError, match="not empty"):
            create_multi_snapshot(
                source_repos={"alpha": repo},
                dest_path=dest,
            )

    def test_result_dataclass(self, tmp_path: Path) -> None:
        """MultiSnapshotResult has expected fields."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
        )

        assert result.dest_path == dest
        assert isinstance(result.commits_created, int)
        assert isinstance(result.repos_included, list)

    def test_nonexistent_repo_path_skipped(self, tmp_path: Path) -> None:
        """Non-existent repo paths are skipped gracefully."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo, "ghost": tmp_path / "nonexistent"},
            dest_path=dest,
        )

        assert result.commits_created == 1
        assert "alpha" in result.repos_included
        assert "ghost" not in result.repos_included

    def test_since_filters_all_dates_returns_empty(self, tmp_path: Path) -> None:
        """If --since excludes all dates, returns 0 commits."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        from datetime import date

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            since=date(2027, 1, 1),
        )

        assert result.commits_created == 0

    def test_changelog_dir_nonexistent(self, tmp_path: Path) -> None:
        """Non-existent changelog_dir doesn't crash — just no messages."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            changelog_dir=tmp_path / "no-such-dir",
        )

        assert result.commits_created == 1

    def test_changelog_dir_with_invalid_yaml(self, tmp_path: Path) -> None:
        """Invalid YAML in changelog dir is skipped."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        cl_dir = tmp_path / "changelogs" / "alpha"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-01-15-alpha-changelog.yaml").write_text(": invalid yaml {{{}}")

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            changelog_dir=tmp_path / "changelogs",
        )

        assert result.commits_created == 1

    def test_changelog_dir_with_file_not_dir(self, tmp_path: Path) -> None:
        """Files in changelog_dir root are ignored (not directories)."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        cl_dir = tmp_path / "changelogs"
        cl_dir.mkdir(parents=True)
        (cl_dir / "alpha").mkdir()  # real dir
        (cl_dir / "README.md").write_text("not a dir")  # file in root

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            changelog_dir=cl_dir,
        )

        assert result.commits_created == 1

    def test_changelog_yaml_missing_title(self, tmp_path: Path) -> None:
        """Changelog YAML without a title field is skipped."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        cl_dir = tmp_path / "changelogs" / "alpha"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-01-15-alpha-changelog.yaml").write_text(yaml.dump({"date": "2026-01-15"}))

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            changelog_dir=tmp_path / "changelogs",
        )

        assert result.commits_created == 1

    def test_changelog_title_only_no_summary(self, tmp_path: Path) -> None:
        """Changelog with title but no summary still works."""
        repo = _make_repo(
            tmp_path,
            "alpha",
            [("2026-01-15", "a.py", "feat: init"), ("2026-01-16", "b.py", "feat: second")],
        )
        dest = tmp_path / "dest"

        cl_dir = tmp_path / "changelogs" / "alpha"
        cl_dir.mkdir(parents=True)
        # First: title only, no summary key
        changelog1 = {"date": "2026-01-15", "repo": "alpha", "title": "Just a title"}
        (cl_dir / "2026-01-15-alpha-changelog.yaml").write_text(yaml.dump(changelog1))
        # Second: title with summary (same repo dir = covers 358->360 branch)
        changelog2 = {"date": "2026-01-16", "repo": "alpha", "title": "Second", "summary": "With summary."}
        (cl_dir / "2026-01-16-alpha-changelog.yaml").write_text(yaml.dump(changelog2))

        create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            changelog_dir=tmp_path / "changelogs",
        )

        log = subprocess.run(
            ["git", "log", "--format=%B"], cwd=dest, capture_output=True, text=True, check=True
        )
        assert "Just a title" in log.stdout
        assert "With summary." in log.stdout

    def test_repo_with_no_matching_trees(self, tmp_path: Path) -> None:
        """When a repo's tree can't be resolved for a day, that day is skipped."""
        # Create repo alpha with a commit on Jan 20
        repo_a = _make_repo(tmp_path, "alpha", [("2026-01-20", "a.py", "feat: init")])
        # Create repo beta as a bare init (no commits — won't have fetchable trees)
        repo_b = tmp_path / "beta"
        repo_b.mkdir()
        subprocess.run(["git", "init"], cwd=repo_b, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo_b, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo_b, capture_output=True, check=True)
        # Add a commit on a MUCH earlier date (before alpha)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (repo_b / "x.py").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=repo_b, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: beta early"],
            cwd=repo_b,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-01-10T12:00:00", "GIT_COMMITTER_DATE": "2026-01-10T12:00:00"},
        )
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo_a, "beta": repo_b},
            dest_path=dest,
        )

        # Both dates should produce commits (Jan 10 for beta only, Jan 20 for both)
        assert result.commits_created == 2
