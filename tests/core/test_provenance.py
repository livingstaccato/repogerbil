# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for provenance-aware source resolution.

This file is a worked example of migrating off the historical ``_init_repo``
helper to the shared ``git_repo`` / ``make_git_repo`` fixtures defined in
``tests/conftest.py``. The primary repo for each test comes from
``git_repo``; secondary repos (backup history sources) are created via the
``make_git_repo`` factory so we never re-implement the same defaults.
"""

from collections.abc import Callable
from pathlib import Path
import subprocess

from repogerbil.core.audit import MissingDate, find_missing
from repogerbil.core.provenance import collect_effective_dates, describe_resolution, resolve_provenance


def _commit(repo: Path, filename: str, text: str, message: str, date: str) -> None:
    env = {"HOME": str(repo.parent), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / filename).write_text(text)
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": f"{date}T10:00:00", "GIT_COMMITTER_DATE": f"{date}T10:00:00"},
    )


def _add_hidden_commit(repo: Path) -> None:
    """Add the visible+hidden commit pair used across resolution tests."""
    _commit(repo, "visible.py", "print('visible')\n", "feat: visible", "2025-07-23")
    subprocess.run(["git", "checkout", "-b", "hidden"], cwd=repo, capture_output=True, check=True)
    _commit(repo, "hidden.py", "print('hidden')\n", "feat: hidden", "2025-07-28")
    subprocess.run(["git", "checkout", "-"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "branch", "-D", "hidden"], cwd=repo, capture_output=True, check=True)


class TestProvenanceResolution:
    def test_resolves_visible_commits(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-23", git_repo, include_files=True)
        assert res.mode == "visible"
        assert len(res.commits) == 1
        assert res.stats is not None
        assert res.stats.commits == 1

    def test_resolves_hidden_ref_commits(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo, include_files=True)
        assert res.mode == "hidden_ref"
        assert len(res.commits) == 1
        assert res.commits[0].subject == "feat: hidden"
        assert res.stats is not None

    def test_resolves_backup_source(self, make_git_repo: Callable[[str], Path], git_repo: Path) -> None:
        backup = make_git_repo("backup")
        _commit(backup, "old.py", "print('old')\n", "feat: old era", "2025-02-03")

        res = resolve_provenance("primary", "2025-02-03", git_repo, extra_sources=[backup], include_files=True)
        assert res.mode == "backup"
        assert res.source_path == str(backup)
        assert len(res.commits) == 1
        assert res.commits[0].subject == "feat: old era"

    def test_unresolved_without_hidden_refs(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo, include_hidden_refs=False)
        assert res.mode == "unresolved"
        assert res.source_path is None
        assert res.notes

    def test_no_git_root(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing"
        res = resolve_provenance("missing", "2025-07-28", missing)
        assert res.mode == "unresolved"
        assert res.source_path is None
        assert "no git root" in res.notes[0]

    def test_nested_file_path_resolves_root(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        file_path = git_repo / "visible.py"
        res = resolve_provenance("primary", "2025-07-23", file_path, include_hidden_refs=False)
        assert res.mode == "visible"
        assert res.source_path == str(git_repo)

    def test_describe_resolution(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-23", git_repo)
        lines = describe_resolution(res)
        assert any("primary/2025-07-23" in line for line in lines)
        assert any("candidate" in line for line in lines)

    def test_describe_unresolved(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        res = resolve_provenance("primary", "2025-07-28", git_repo, include_hidden_refs=False)
        lines = describe_resolution(res)
        assert any("note:" in line for line in lines)

    def test_duplicate_extra_source_roots_are_ignored(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        nested = git_repo / "nested"
        nested.mkdir()
        res = resolve_provenance("primary", "2025-07-29", git_repo, extra_sources=[nested])
        assert res.mode == "unresolved"
        assert len(res.candidates) == 2


class TestEffectiveDates:
    def test_collects_visible_and_hidden_dates(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        dates = collect_effective_dates(git_repo)
        assert "2025-07-23" in dates
        assert "2025-07-28" in dates

    def test_collects_union_from_extra_sources(
        self, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        backup = make_git_repo("backup")
        _commit(git_repo, "primary.py", "print('primary')\n", "feat: primary", "2025-07-23")
        _commit(backup, "backup.py", "print('backup')\n", "feat: backup", "2025-07-28")

        dates = collect_effective_dates(git_repo, extra_sources=[backup])
        assert dates == {"2025-07-23", "2025-07-28"}

    def test_without_hidden_refs(self, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        dates = collect_effective_dates(git_repo, include_hidden_refs=False)
        assert "2025-07-23" in dates
        assert "2025-07-28" not in dates


class TestMissingWithHiddenRefs:
    def test_missing_reports_hidden_ref_date(self, tmp_path: Path, git_repo: Path) -> None:
        _add_hidden_commit(git_repo)
        cl_dir = tmp_path / "changelogs"
        repo_dir = cl_dir / "primary"
        repo_dir.mkdir(parents=True)
        (repo_dir / "2025-07-23-primary-changelog.yaml").write_text("date: 2025-07-23\nrepo: primary\n")

        result = find_missing({"primary": str(git_repo)}, cl_dir)
        assert MissingDate(repo="primary", date="2025-07-28") in result

    def test_missing_with_backup_source(
        self, tmp_path: Path, make_git_repo: Callable[[str], Path], git_repo: Path
    ) -> None:
        backup = make_git_repo("backup")
        _commit(git_repo, "primary.py", "print('primary')\n", "feat: primary", "2025-02-02")
        _commit(backup, "old.py", "print('old')\n", "feat: old era", "2025-02-03")
        cl_dir = tmp_path / "changelogs"
        repo_dir = cl_dir / "primary"
        repo_dir.mkdir(parents=True)
        (repo_dir / "2025-02-02-primary-changelog.yaml").write_text("date: 2025-02-02\nrepo: primary\n")

        result = find_missing({"primary": str(git_repo)}, cl_dir, extra_sources=[backup])
        assert MissingDate(repo="primary", date="2025-02-03") in result
