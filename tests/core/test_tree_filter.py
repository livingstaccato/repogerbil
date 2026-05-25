# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for tree_filter — the shared filtering utilities."""

from __future__ import annotations

from pathlib import Path
import subprocess

from repogerbil.core.tree_filter import exclude_files, filter_tree


class TestExcludeFiles:
    def test_no_exclude_returns_unchanged(self) -> None:
        files = {"src/foo.py", "poetry.lock"}
        assert exclude_files(files, None) == files
        assert exclude_files(files, []) == files

    def test_matches_lock_file(self) -> None:
        files = {"src/foo.py", "poetry.lock"}
        result = exclude_files(files, [r"\.lock$"])
        assert result == {"src/foo.py"}

    def test_matches_multiple_patterns(self) -> None:
        files = {"src/foo.py", "poetry.lock", ".claude/settings.json", "README.md"}
        result = exclude_files(files, [r"\.lock$", r"^\.claude(/|$)"])
        assert result == {"src/foo.py", "README.md"}

    def test_empty_files_returns_empty(self) -> None:
        assert exclude_files(set(), [r"\.lock$"]) == set()


def _make_git_repo(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    """Create a git repo with the given files and return (repo_path, tree_sha)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)

    for path, content in files.items():
        full = repo / path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)

    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)

    tree_sha = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return repo, tree_sha


class TestFilterTree:
    def test_no_exclude_returns_same_sha(self, tmp_path: Path) -> None:
        repo, tree_sha = _make_git_repo(tmp_path, {"main.py": "x=1\n"})
        result = filter_tree(repo, tree_sha, None)
        assert result == tree_sha

    def test_empty_exclude_returns_same_sha(self, tmp_path: Path) -> None:
        repo, tree_sha = _make_git_repo(tmp_path, {"main.py": "x=1\n"})
        result = filter_tree(repo, tree_sha, [])
        assert result == tree_sha

    def test_removes_matched_file(self, tmp_path: Path) -> None:
        repo, tree_sha = _make_git_repo(tmp_path, {"main.py": "x=1\n", "poetry.lock": "lock\n"})
        filtered_sha = filter_tree(repo, tree_sha, [r"\.lock$"])
        assert filtered_sha != tree_sha

        # Verify the lock file is gone
        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", filtered_sha],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert "poetry.lock" not in ls
        assert "main.py" in ls

    def test_removes_directory_pattern(self, tmp_path: Path) -> None:
        repo, tree_sha = _make_git_repo(tmp_path, {"src/foo.py": "x\n", ".claude/settings.json": "{}"})
        filtered_sha = filter_tree(repo, tree_sha, [r"^\.claude(/|$)"])

        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", filtered_sha],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert not any(".claude" in p for p in ls)
        assert "src/foo.py" in ls

    def test_multiple_patterns(self, tmp_path: Path) -> None:
        repo, tree_sha = _make_git_repo(
            tmp_path,
            {"main.py": "x\n", "poetry.lock": "lock\n", ".claude/cfg": "cfg"},
        )
        filtered_sha = filter_tree(repo, tree_sha, [r"\.lock$", r"^\.claude(/|$)"])

        ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", filtered_sha],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert ls == ["main.py"]

    def test_no_index_temp_files_leak(self, tmp_path: Path) -> None:
        """After a successful filter_tree call, no idx temp file remains in .git."""
        repo, tree_sha = _make_git_repo(tmp_path, {"main.py": "x\n", "poetry.lock": "lock\n"})
        filter_tree(repo, tree_sha, [r"\.lock$"])

        leftovers = sorted((repo / ".git").glob("filter-tree-idx-*"))
        assert leftovers == []


class TestFilterTreeCleanup:
    def test_cleanup_index_files_removes_index_and_lock(self, tmp_path: Path) -> None:
        """Helper removes both the index file and its sibling .lock if present."""
        from repogerbil.core.tree_filter import _cleanup_index_files

        idx = tmp_path / "some-idx"
        idx.write_text("x")
        lock = tmp_path / "some-idx.lock"
        lock.write_text("y")

        _cleanup_index_files(idx)

        assert not idx.exists()
        assert not lock.exists()

    def test_cleanup_index_files_missing_paths_ok(self, tmp_path: Path) -> None:
        """Helper is a no-op when neither file exists (safe in finally)."""
        from repogerbil.core.tree_filter import _cleanup_index_files

        # Should not raise — both paths missing.
        _cleanup_index_files(tmp_path / "absent-idx")
