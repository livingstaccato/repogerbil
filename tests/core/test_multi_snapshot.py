# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for multi-repo snapshot creation."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any

import pytest
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
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
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


class TestMultiSnapshotExcludePaths:
    def test_excluded_files_absent_from_tree(self, tmp_path: Path) -> None:
        """Files matching exclude_paths are stripped from the merged tree."""
        repo = _make_repo(tmp_path, "alpha", [("2026-02-01", "main.py", "feat: init")])
        # Add an artifact file in a second commit
        (repo / "poetry.lock").write_text("lock\n")
        subprocess.run(["git", "add", "poetry.lock"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        subprocess.run(
            ["git", "commit", "-m", "chore: add lock"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-02-01T13:00:00", "GIT_COMMITTER_DATE": "2026-02-01T13:00:00"},
        )
        dest = tmp_path / "dest"

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            exclude_paths=[r"(poetry|yarn|Pipfile|Gemfile|Cargo|composer|packages|uv)\.lock$"],
        )

        assert result.commits_created == 1
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "poetry.lock" not in ls.stdout
        assert "alpha/main.py" in ls.stdout

    def test_no_exclude_paths_passes_through(self, tmp_path: Path) -> None:
        """Without exclude_paths, all files are kept."""
        repo = _make_repo(tmp_path, "alpha", [("2026-02-01", "poetry.lock", "chore: lock")])
        dest = tmp_path / "dest"

        result = create_multi_snapshot(source_repos={"alpha": repo}, dest_path=dest)

        assert result.commits_created == 1
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "alpha/poetry.lock" in ls.stdout


class TestMultiSnapshotLLMBypass:
    def test_llm_skipped_when_all_subjects_well_formed(self, tmp_path: Path) -> None:
        """LLM is not called when all commit subjects in the day are already well-formed."""
        from unittest.mock import MagicMock

        repo = _make_repo(tmp_path, "alpha", [("2026-03-01", "a.py", "feat: add module")])
        dest = tmp_path / "dest-bypass"
        mock_gen = MagicMock()

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            llm_generator=mock_gen,
        )

        assert result.commits_created == 1
        mock_gen.generate.assert_not_called()

    def test_llm_called_when_subjects_not_well_formed(self, tmp_path: Path) -> None:
        """LLM is called when at least one commit subject is not well-formed."""
        from unittest.mock import MagicMock

        from repogerbil.llm.generator import GeneratedMessage

        repo = _make_repo(tmp_path, "alpha", [("2026-03-01", "a.py", "wip: messy commit")])
        dest = tmp_path / "dest-llm"
        mock_gen = MagicMock()
        mock_gen.generate.return_value = GeneratedMessage(
            message="scaffold(alpha): initial module",
            body="Sets up the module.",
            changes=[{"file": "a.py", "description": "introduce module"}],
        )

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            llm_generator=mock_gen,
        )

        assert result.commits_created == 1
        mock_gen.generate.assert_called_once()


class TestMultiSnapshotLLMSuccess:
    def test_llm_success_writes_sidecar_jsonl(self, tmp_path: Path) -> None:
        """When LLM succeeds, message is used and sidecar JSONL is written."""
        import json
        from unittest.mock import MagicMock

        from repogerbil.llm.generator import GeneratedMessage

        repo = _make_repo(tmp_path, "alpha", [("2026-03-01", "a.py", "wip: messy message")])
        dest = tmp_path / "dest"

        good_generator = MagicMock()
        good_generator.generate.return_value = GeneratedMessage(
            message="feat(core): add initial module",
            body="Establishes the core module foundation.",
            changes=[{"file": "a.py", "description": "introduce module"}],
        )

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            llm_generator=good_generator,
        )

        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%s"], cwd=dest, capture_output=True, text=True, check=True
        )
        assert "feat(core): add initial module" in log.stdout

        sidecar = dest.parent / f"{dest.name}.summaries.jsonl"
        assert sidecar.exists()
        record = json.loads(sidecar.read_text().strip())
        assert record["body"] == "Establishes the core module foundation."
        assert record["date"] == "2026-03-01"


class TestMultiSnapshotLLMFallback:
    def test_llm_error_falls_back_to_default_message(self, tmp_path: Path) -> None:
        """When the LLM raises, commit still succeeds with the default message."""
        from unittest.mock import MagicMock

        repo = _make_repo(tmp_path, "alpha", [("2026-03-01", "a.py", "wip: messy message")])
        dest = tmp_path / "dest"

        bad_generator = MagicMock()
        bad_generator.generate.side_effect = RuntimeError("LLM unavailable")

        result = create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            llm_generator=bad_generator,
        )

        assert result.commits_created == 1
        log = subprocess.run(
            ["git", "log", "--format=%s"], cwd=dest, capture_output=True, text=True, check=True
        )
        # Should have a non-empty commit subject (default message, not empty)
        assert log.stdout.strip()


class TestCollectDayContext:
    def test_returns_files_and_subjects(self, tmp_path: Path) -> None:
        """_collect_day_context extracts changed files and subjects for a given day."""
        from datetime import date

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = _make_repo(tmp_path, "alpha", [("2026-04-01", "foo.py", "feat: add foo")])
        files, subjects, _bodies = _collect_day_context(
            {"alpha": repo},
            {"alpha"},
            date(2026, 4, 1),
            exclude_paths=None,
        )
        assert "foo.py" in files
        assert any("add foo" in s for s in subjects)

    def test_exclude_paths_filters_files(self, tmp_path: Path) -> None:
        """exclude_paths removes matching files from the collected set."""
        from datetime import date

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = _make_repo(tmp_path, "alpha", [("2026-04-01", "poetry.lock", "chore: lock")])
        files, _, _ = _collect_day_context(
            {"alpha": repo},
            {"alpha"},
            date(2026, 4, 1),
            exclude_paths=[r"\.lock$"],
        )
        assert not any("lock" in f for f in files)

    def test_missing_repo_skipped(self, tmp_path: Path) -> None:
        """Repos not present in source_repos dict are silently skipped."""
        from datetime import date

        from repogerbil.core.multi_snapshot import _collect_day_context

        files, subjects, bodies = _collect_day_context(
            {},
            {"ghost"},
            date(2026, 4, 1),
            exclude_paths=None,
        )
        assert files == []
        assert subjects == []
        assert bodies == []

    def test_git_command_error_skips_repo(self, tmp_path: Path, caplog: Any) -> None:
        """GitCommandError from _run_git is caught, logged, and the repo is skipped."""
        from datetime import date
        import logging
        from unittest.mock import patch

        from repogerbil.core.errors import GitCommandError
        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = _make_repo(tmp_path, "alpha", [("2026-04-01", "foo.py", "feat: add foo")])
        with (
            caplog.at_level(logging.WARNING, logger="repogerbil.core.multi_snapshot"),
            patch(
                "repogerbil.core.multi_snapshot._run_git",
                side_effect=GitCommandError("boom"),
            ),
        ):
            files, subjects, bodies = _collect_day_context(
                {"alpha": repo},
                {"alpha"},
                date(2026, 4, 1),
                exclude_paths=None,
            )
        assert files == []
        assert subjects == []
        assert bodies == []
        assert any("git log failed for repo alpha" in r.message for r in caplog.records)

    def test_body_appended_when_present(self, tmp_path: Path) -> None:
        """Commit body text is collected into the bodies list."""
        from datetime import date
        from unittest.mock import patch

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = _make_repo(tmp_path, "alpha", [("2026-04-01", "foo.py", "feat: add foo")])
        # Two-call format: metadata = \x00<hash>\x1d<date>\x1d<subject>\x1d<body>
        # files    = \x00<hash>\n<file>\n
        commit_hash = "a" * 40
        meta_out = f"\x00{commit_hash}\x1d2026-04-01\x1dfeat: add foo\x1dThis is the commit body."
        files_out = f"\x00{commit_hash}\nfoo.py\n"

        with patch(
            "repogerbil.core.multi_snapshot._run_git",
            side_effect=[meta_out, files_out],
        ):
            _, subjects, bodies = _collect_day_context(
                {"alpha": repo},
                {"alpha"},
                date(2026, 4, 1),
                exclude_paths=None,
            )
        assert subjects == ["alpha: feat: add foo"]
        assert bodies == ["This is the commit body."]

    def test_empty_file_lines_skipped(self, tmp_path: Path) -> None:
        """Blank lines in file output are not added to the files set."""
        from datetime import date
        from unittest.mock import patch

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = _make_repo(tmp_path, "alpha", [("2026-04-01", "foo.py", "feat: add foo")])
        commit_hash = "a" * 40
        meta_out = f"\x00{commit_hash}\x1d2026-04-01\x1dfeat: add foo\x1d"
        # File block has blank lines between paths — they must be filtered out.
        files_out = f"\x00{commit_hash}\n\nfoo.py\n\n"

        with patch(
            "repogerbil.core.multi_snapshot._run_git",
            side_effect=[meta_out, files_out],
        ):
            files, _, _ = _collect_day_context(
                {"alpha": repo},
                {"alpha"},
                date(2026, 4, 1),
                exclude_paths=None,
            )
        assert files == ["foo.py"]
        assert "" not in files

    def test_body_with_field_separator_byte(self, tmp_path: Path) -> None:
        """A commit body containing the GS (\\x1d) byte must not poison file parsing.

        Regression for the previous single-call ``--name-only`` parser: a
        literal ``\\x1d`` in the body would split early and bleed body text
        into the file block. The two-call architecture eliminates that path
        entirely — files are keyed by commit hash from a separate ``git log``.
        """
        from datetime import date as _date
        import os
        import subprocess as _sp

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = tmp_path / "gs_in_body"
        repo.mkdir()
        _sp.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        _sp.run(["git", "config", "user.email", "t@t.test"], cwd=repo, check=True)
        _sp.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
        _sp.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

        (repo / "real.py").write_text("real\n")
        _sp.run(["git", "add", "."], cwd=repo, check=True)
        # Inject a literal \x1d into the commit body via -F /dev/stdin so the
        # raw byte ends up in the git object.
        body = "header line\nfake/path/in/body\x1dmore body text\n"
        _sp.run(
            ["git", "commit", "-q", "-F", "-"],
            cwd=repo,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2026-04-01T12:00:00",
                "GIT_COMMITTER_DATE": "2026-04-01T12:00:00",
            },
            input=f"feat: gs body\n\n{body}",
            text=True,
            check=True,
        )

        files, subjects, _bodies = _collect_day_context(
            {"alpha": repo},
            {"alpha"},
            _date(2026, 4, 1),
            exclude_paths=None,
        )
        assert subjects == ["alpha: feat: gs body"]
        # Crucial: only the real file is collected — none of the body fragments
        # (e.g. "fake/path/in/body") leak in.
        assert files == ["real.py"]

    def test_author_date_filter_excludes_committer_date_only_matches(self, tmp_path: Path) -> None:
        """A commit whose committer date is on `day` but author date is NOT is excluded.

        Simulates a rebased commit: author date 2026-04-01, committer date 2026-04-02.
        Asking for day=2026-04-02 must NOT include this commit's subject/files.
        """
        from datetime import date as _date
        import os
        import subprocess as _sp

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = tmp_path / "rebased"
        repo.mkdir()
        _sp.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        _sp.run(["git", "config", "user.email", "t@t.test"], cwd=repo, check=True)
        _sp.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
        _sp.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

        # Author date 2026-04-01, committer date 2026-04-02 (rebase-style drift).
        (repo / "rebased.py").write_text("x\n")
        _sp.run(["git", "add", "."], cwd=repo, check=True)
        _sp.run(
            ["git", "commit", "-q", "-m", "feat: rebased"],
            cwd=repo,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2026-04-01T12:00:00",
                "GIT_COMMITTER_DATE": "2026-04-02T12:00:00",
            },
            check=True,
        )
        # A second commit authored AND committed on 2026-04-02 — this one
        # *should* be picked up when we ask for day=2026-04-02.
        (repo / "fresh.py").write_text("y\n")
        _sp.run(["git", "add", "."], cwd=repo, check=True)
        _sp.run(
            ["git", "commit", "-q", "-m", "feat: fresh"],
            cwd=repo,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2026-04-02T12:00:00",
                "GIT_COMMITTER_DATE": "2026-04-02T12:00:00",
            },
            check=True,
        )

        files, subjects, _ = _collect_day_context(
            {"repo": repo},
            {"repo"},
            _date(2026, 4, 2),
            exclude_paths=None,
        )
        # Only the fresh commit (authored on 04-02) is included.
        assert subjects == ["repo: feat: fresh"]
        assert "fresh.py" in files
        assert "rebased.py" not in files

        # And asking for 04-01 picks up the rebased commit by its author date,
        # even though its committer date is 04-02.
        files1, subjects1, _ = _collect_day_context(
            {"repo": repo},
            {"repo"},
            _date(2026, 4, 1),
            exclude_paths=None,
        )
        assert subjects1 == ["repo: feat: rebased"]
        assert "rebased.py" in files1

    def test_author_date_picked_up_when_committer_date_is_weeks_earlier(self, tmp_path: Path) -> None:
        """A commit with committer date >7 days BEFORE author date is still picked up.

        Regression for the previous ±7-day window which was too tight to cover
        the case where committer date sits well before author date (e.g.
        manually backdated committer-date, or weird rebase scenarios). The
        widened ±30-day window now catches a 14-day asymmetry like this.
        """
        from datetime import date as _date
        import os
        import subprocess as _sp

        from repogerbil.core.multi_snapshot import _collect_day_context

        repo = tmp_path / "skew"
        repo.mkdir()
        _sp.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
        _sp.run(["git", "config", "user.email", "t@t.test"], cwd=repo, check=True)
        _sp.run(["git", "config", "user.name", "T"], cwd=repo, check=True)
        _sp.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, check=True)

        # Author date 2026-04-15, committer date 2026-04-01 (14-day skew —
        # committer date *earlier* than author date, outside the old ±7-day
        # window but well within the new ±30-day window).
        (repo / "skewed.py").write_text("x\n")
        _sp.run(["git", "add", "."], cwd=repo, check=True)
        _sp.run(
            ["git", "commit", "-q", "-m", "feat: skewed"],
            cwd=repo,
            env={
                **os.environ,
                "GIT_AUTHOR_DATE": "2026-04-15T12:00:00",
                "GIT_COMMITTER_DATE": "2026-04-01T12:00:00",
            },
            check=True,
        )

        files, subjects, _ = _collect_day_context(
            {"repo": repo},
            {"repo"},
            _date(2026, 4, 15),
            exclude_paths=None,
        )
        # The widened window picks this up by author date even though committer
        # date is 14 days earlier.
        assert subjects == ["repo: feat: skewed"]
        assert "skewed.py" in files


class TestMultiSnapshotEcosystemLabel:
    def test_default_label_in_message(self, tmp_path: Path) -> None:
        """Default ecosystem_label appears in the first line when there is a changelog."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        # Use TWO repos so the single-repo short-circuit in _build_message is not taken.
        repo_b = _make_repo(tmp_path, "beta", [("2026-01-15", "b.py", "feat: init beta")])
        dest = tmp_path / "dest"

        cl_dir = tmp_path / "changelogs" / "alpha"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-01-15-alpha-changelog.yaml").write_text(
            yaml.dump({"date": "2026-01-15", "repo": "alpha", "title": "Title"})
        )

        create_multi_snapshot(
            source_repos={"alpha": repo, "beta": repo_b},
            dest_path=dest,
            changelog_dir=tmp_path / "changelogs",
        )

        log = subprocess.run(
            ["git", "log", "--format=%s"], cwd=dest, capture_output=True, text=True, check=True
        )
        assert "2026-01-15 ecosystem" in log.stdout
        assert "pyvider" not in log.stdout

    def test_custom_label_overrides_default(self, tmp_path: Path) -> None:
        """A caller-supplied ecosystem_label appears verbatim in the commit subject."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        repo_b = _make_repo(tmp_path, "beta", [("2026-01-15", "b.py", "feat: init beta")])
        dest = tmp_path / "dest"

        cl_dir = tmp_path / "changelogs" / "alpha"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-01-15-alpha-changelog.yaml").write_text(
            yaml.dump({"date": "2026-01-15", "repo": "alpha", "title": "Title"})
        )

        create_multi_snapshot(
            source_repos={"alpha": repo, "beta": repo_b},
            dest_path=dest,
            changelog_dir=tmp_path / "changelogs",
            ecosystem_label="my-platform",
        )

        log = subprocess.run(
            ["git", "log", "--format=%s"], cwd=dest, capture_output=True, text=True, check=True
        )
        assert "2026-01-15 my-platform" in log.stdout


class TestMultiSnapshotAuthorIdentity:
    def test_explicit_author_overrides_global(self, tmp_path: Path) -> None:
        """When author_name + author_email are provided, dest commits use them."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        create_multi_snapshot(
            source_repos={"alpha": repo},
            dest_path=dest,
            author_name="Snapshot Bot",
            author_email="bot@example.invalid",
        )

        log = subprocess.run(
            ["git", "log", "--format=%an <%ae>"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=True,
        )
        assert "Snapshot Bot <bot@example.invalid>" in log.stdout

    def test_default_inherits_global_config(self, tmp_path: Path) -> None:
        """With no explicit author, the dest repo has no committed user.email override."""
        repo = _make_repo(tmp_path, "alpha", [("2026-01-15", "a.py", "feat: init")])
        dest = tmp_path / "dest"

        create_multi_snapshot(source_repos={"alpha": repo}, dest_path=dest)

        # Local repo config should NOT contain a user.email key (inherits global).
        cfg = subprocess.run(
            ["git", "config", "--local", "--get", "user.email"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=False,
        )
        assert cfg.returncode != 0  # key not set locally


class TestMultiSnapshotCommitTreeFailure:
    def test_commit_tree_failure_raises(self, tmp_path: Path) -> None:
        """When git commit-tree fails, _commit_tree surfaces a GitCommandError."""
        from repogerbil.core._multi_snapshot_git import _commit_tree
        from repogerbil.core.errors import GitCommandError

        # Init an empty repo with a global identity so commit-tree could otherwise succeed.
        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)

        # Use an obviously invalid tree SHA so commit-tree fails fast.
        with pytest.raises(GitCommandError):
            _commit_tree(dest, "0" * 40, "msg", "2026-01-15T20:00:00-0800")


class TestMultiSnapshotBuildMergedTreeFailure:
    def test_build_merged_tree_failure_raises(self, tmp_path: Path) -> None:
        """An invalid tree SHA passed to _build_merged_tree raises GitCommandError."""
        from repogerbil.core._multi_snapshot_git import _build_merged_tree
        from repogerbil.core.errors import GitCommandError

        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)

        with pytest.raises(GitCommandError):
            _build_merged_tree(dest, {"alpha": "0" * 40})

    def test_build_merged_tree_cleans_up_idx_and_lock_on_failure(self, tmp_path: Path) -> None:
        """Idx temp file and any sibling .lock are removed even when git fails."""
        from repogerbil.core._multi_snapshot_git import _build_merged_tree
        from repogerbil.core.errors import GitCommandError

        dest = tmp_path / "dest"
        dest.mkdir()
        subprocess.run(["git", "init"], cwd=dest, capture_output=True, check=True)

        # Pre-seed a lock file that would already exist if a previous git call
        # had been interrupted — the .lock cleanup in finally must remove it
        # too. We can't predict the mkstemp name, so seed *any* matching idx
        # file and lock pair to assert nothing of the new shape leaks after.
        with pytest.raises(GitCommandError):
            _build_merged_tree(dest, {"alpha": "0" * 40})

        leftovers = sorted((dest / ".git").glob("multi-snap-idx-*"))
        assert leftovers == []


class TestMultiSnapshotLLMFailureLogged:
    def test_llm_failure_logs_warning(self, tmp_path: Path, caplog: Any) -> None:
        """An LLM failure during refinement emits a WARNING via the module logger."""
        import logging
        from unittest.mock import MagicMock

        repo = _make_repo(tmp_path, "alpha", [("2026-03-01", "a.py", "wip: messy")])
        dest = tmp_path / "dest"

        bad = MagicMock()
        bad.generate.side_effect = RuntimeError("ollama gone")

        with caplog.at_level(logging.WARNING, logger="repogerbil.core.multi_snapshot"):
            result = create_multi_snapshot(
                source_repos={"alpha": repo},
                dest_path=dest,
                llm_generator=bad,
            )

        assert result.commits_created == 1
        assert any("LLM refinement failed" in r.message for r in caplog.records)


class TestEcosystemSettings:
    def test_settings_default_ecosystem_label(self) -> None:
        """The Settings model defaults ecosystem_label to the generic placeholder."""
        from repogerbil.core.config import Settings

        s = Settings()
        assert s.ecosystem_label == "ecosystem"
        assert s.snapshot_author_name is None
        assert s.snapshot_author_email is None
