# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for high-level search functions."""

from pathlib import Path

import pytest
import yaml

from repogerbil.core.embeddings import SimpleHashEmbedder

chromadb = pytest.importorskip("chromadb")

from repogerbil.core.search import (  # noqa: E402
    find_related_work,
    index_changelogs,
    search_across_repos,
    search_by_category,
)
from repogerbil.core.vectordb import VectorStore  # noqa: E402


def _write_changelog(path: Path, repo: str, date_str: str, title: str, category: str = "instantiate") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "date": date_str,
                "repo": repo,
                "title": title,
                "summary": f"Summary for {title}",
                "stats": {"commits": 3, "files_changed": 10, "insertions": 100, "deletions": 50},
                "changes": [
                    {
                        "title": title,
                        "category": category,
                        "severity": "behavioral",
                        "files": [{"path": "src/main.py", "summary": title}],
                        "points": [{"text": f"Did {title.lower()}", "files": ["src/main.py"]}],
                    },
                ],
            }
        )
    )


@pytest.fixture()
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path / "testdb", SimpleHashEmbedder())


class TestIndexChangelogs:
    def test_indexes_from_directory(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "Add auth"
        )
        _write_changelog(
            cl_dir / "repo-b" / "2026-04-07-repo-b-changelog.yaml", "repo-b", "2026-04-07", "Fix bug"
        )

        count = index_changelogs(store, cl_dir)
        assert count == 2
        assert store.changelog_count == 2
        assert store.change_count == 2

    def test_skips_todo_titles(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "TODO: summarize"
        )

        count = index_changelogs(store, cl_dir)
        assert count == 0

    def test_skips_invalid_yaml(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs" / "repo-a"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-04-07-repo-a-changelog.yaml").write_text("not: valid: yaml: {{")

        count = index_changelogs(store, cl_dir.parent)
        assert count == 0

    def test_skips_hidden_dirs(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        cl_dir.mkdir()
        (cl_dir / ".git").mkdir()
        count = index_changelogs(store, cl_dir)
        assert count == 0

    def test_incremental(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "Work"
        )
        index_changelogs(store, cl_dir)
        # Index again — should upsert, not duplicate
        index_changelogs(store, cl_dir)
        assert store.changelog_count == 1


class TestSearchAcrossRepos:
    def test_basic_search(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml",
            "repo-a",
            "2026-04-07",
            "Security hardening",
        )
        _write_changelog(
            cl_dir / "repo-b" / "2026-04-07-repo-b-changelog.yaml", "repo-b", "2026-04-07", "Add feature"
        )
        index_changelogs(store, cl_dir)

        results = search_across_repos(store, "security", n=5)
        assert len(results) >= 1


class TestSearchByCategory:
    def test_filters_by_category(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "Fix", "remediate"
        )
        _write_changelog(
            cl_dir / "repo-b" / "2026-04-07-repo-b-changelog.yaml",
            "repo-b",
            "2026-04-07",
            "Add",
            "instantiate",
        )
        index_changelogs(store, cl_dir)

        results = search_by_category(store, "work", "remediate", n=5)
        assert all(r.get("metadata", {}).get("category") == "remediate" for r in results)


class TestFindRelatedWork:
    def test_finds_cross_repo_work(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "Auth security"
        )
        _write_changelog(
            cl_dir / "repo-b" / "2026-04-07-repo-b-changelog.yaml", "repo-b", "2026-04-07", "Auth update"
        )
        _write_changelog(
            cl_dir / "repo-c" / "2026-04-07-repo-c-changelog.yaml", "repo-c", "2026-04-07", "Unrelated thing"
        )
        index_changelogs(store, cl_dir)

        related = find_related_work(store, "repo-a", "2026-04-07", n=5)
        # Should not include repo-a itself
        assert all(not r["id"].startswith("repo-a/") for r in related)


class TestSearchFilepaths:
    def test_search_by_filepath(self, tmp_path: Path, store: VectorStore) -> None:
        from repogerbil.core.search import search_filepaths

        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "Work"
        )
        index_changelogs(store, cl_dir)
        results = search_filepaths(store, "main.py", n=5)
        assert isinstance(results, list)
        assert len(results) >= 1

    def test_search_diffs(self, tmp_path: Path, store: VectorStore) -> None:
        from repogerbil.core.search import search_diffs

        store.upsert_diff("repo-a/2026-04-07", "src/main.py", "+print('hello')", metadata={"repo": "repo-a"})
        results = search_diffs(store, "print hello", n=5)
        assert len(results) >= 1


class TestFindWorkPattern:
    def test_finds_by_dominant_category(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml",
            "repo-a",
            "2026-04-07",
            "Fix bugs",
            "remediate",
        )
        _write_changelog(
            cl_dir / "repo-b" / "2026-04-07-repo-b-changelog.yaml",
            "repo-b",
            "2026-04-07",
            "Add feature",
            "instantiate",
        )
        index_changelogs(store, cl_dir)

        from repogerbil.core.search import find_work_pattern

        results = find_work_pattern(store, "remediate", n=5)
        assert all(r.get("metadata", {}).get("dominant_category") == "remediate" for r in results)


class TestFindSimilarFileChanges:
    def test_finds_similar(self, tmp_path: Path, store: VectorStore) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml", "repo-a", "2026-04-07", "Work"
        )
        index_changelogs(store, cl_dir)

        from repogerbil.core.search import find_similar_file_changes

        results = find_similar_file_changes(store, ["src/main.py"], n=5)
        assert isinstance(results, list)


class TestSearchByScope:
    def test_finds_by_scope(self, tmp_path: Path, store: VectorStore) -> None:
        from repogerbil.core.search import search_by_scope

        cl_dir = tmp_path / "changelogs"
        repo_dir = cl_dir / "repo-a"
        repo_dir.mkdir(parents=True)
        # Write changelog with scoped commit messages
        (repo_dir / "2026-04-07-repo-a-changelog.yaml").write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo-a",
                    "title": "Parity fixes",
                    "summary": "Fixed parity issues",
                    "stats": {"commits": 2, "files_changed": 3, "insertions": 10, "deletions": 5},
                    "changes": [
                        {
                            "title": "Parity",
                            "category": "remediate",
                            "severity": "behavioral",
                            "files": [{"path": "src/parity.py", "summary": "fix"}],
                            "points": [
                                {"text": "fix(parity): sync twcfig.dat", "files": ["src/parity.py"]},
                                {"text": "fix(worker): handle timeout", "files": ["src/worker.py"]},
                            ],
                        }
                    ],
                }
            )
        )
        index_changelogs(store, cl_dir)
        results = search_by_scope(store, "parity", n=5)
        assert len(results) >= 1
        assert "parity" in results[0].get("metadata", {}).get("scopes", "")


class TestFindLowQuality:
    def test_finds_low_quality(self, tmp_path: Path, store: VectorStore) -> None:
        from repogerbil.core.search import find_low_quality

        cl_dir = tmp_path / "changelogs"
        # Write a low-quality changelog (TODO title, no files)
        repo_dir = cl_dir / "repo-bad"
        repo_dir.mkdir(parents=True)
        (repo_dir / "2026-04-07-repo-bad-changelog.yaml").write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo-bad",
                    "title": "Quick fix",
                    "summary": "Did stuff",
                    "stats": {"commits": 5, "files_changed": 20, "insertions": 100, "deletions": 50},
                    "review": ["ambiguous commit 1", "ambiguous commit 2"],
                    "changes": [{"title": "Stuff", "category": "baseline", "points": []}],
                }
            )
        )
        # And a high-quality one
        _write_changelog(
            cl_dir / "repo-good" / "2026-04-07-repo-good-changelog.yaml",
            "repo-good",
            "2026-04-07",
            "Detailed work",
        )
        index_changelogs(store, cl_dir)
        results = find_low_quality(store, n=5)
        # Low quality should appear first
        assert len(results) >= 1


class TestExtractScopes:
    def test_extracts_scopes(self) -> None:
        from repogerbil.core.search import _extract_scopes

        data = {
            "changes": [
                {
                    "points": [
                        {"text": "fix(parity): something"},
                        {"text": "feat(go): something else"},
                        {"text": "just a plain message"},
                    ]
                }
            ]
        }
        scopes = _extract_scopes(data)
        assert scopes == ["go", "parity"]

    def test_empty(self) -> None:
        from repogerbil.core.search import _extract_scopes

        assert _extract_scopes({}) == []


class TestComputeQuality:
    def test_full_quality(self) -> None:
        from repogerbil.core.search import _compute_quality

        data = {
            "title": "Real title",
            "summary": "Real summary",
            "stats": {"files_changed": 10},
            "bulk": [{"files": 5}],
            "changes": [
                {
                    "files": [{"path": "a.py"}, {"path": "b.py"}],
                    "points": [{"files": ["c.py"]}],
                }
            ],
        }
        q = _compute_quality(data)
        assert q["quality_has_title"] is True
        assert q["quality_has_summary"] is True
        assert q["quality_coverage"] == 80.0
        assert q["quality_review_count"] == 0

    def test_low_quality(self) -> None:
        from repogerbil.core.search import _compute_quality

        data = {
            "title": "TODO: summarize",
            "summary": "TODO: write",
            "stats": {"files_changed": 100},
            "review": ["a", "b", "c"],
            "changes": [],
        }
        q = _compute_quality(data)
        assert q["quality_has_title"] is False
        assert q["quality_has_summary"] is False
        assert q["quality_review_count"] == 3
        assert q["quality_coverage"] == 0.0
