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
                        "points": [{"text": f"Did {title.lower()}"}],
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
