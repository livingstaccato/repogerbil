# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for vector database wrapper."""

from pathlib import Path

import pytest

from repogerbil.core.embeddings import SimpleHashEmbedder

# Skip entire module if chromadb not installed
chromadb = pytest.importorskip("chromadb")

from repogerbil.core.vectordb import VectorStore  # noqa: E402


@pytest.fixture()
def store(tmp_path: Path) -> VectorStore:
    return VectorStore(tmp_path / "testdb", SimpleHashEmbedder())


class TestUpsertChangelog:
    def test_upsert_and_count(self, store: VectorStore) -> None:
        store.upsert_changelog("repo-a", "2026-04-07", "Add feature", "New feature added")
        assert store.changelog_count == 1

    def test_upsert_idempotent(self, store: VectorStore) -> None:
        store.upsert_changelog("repo-a", "2026-04-07", "Title", "Summary")
        store.upsert_changelog("repo-a", "2026-04-07", "Updated", "New summary")
        assert store.changelog_count == 1

    def test_metadata(self, store: VectorStore) -> None:
        store.upsert_changelog("repo-a", "2026-04-07", "Title", "Sum", metadata={"commits": 5})
        results = store.search_changelogs("Title", n=1)
        assert results[0]["metadata"]["commits"] == 5


class TestUpsertChange:
    def test_upsert_and_count(self, store: VectorStore) -> None:
        store.upsert_change("repo-a/2026-04-07", 0, "Fix bug", "Fixed the crash")
        assert store.change_count == 1

    def test_multiple_changes(self, store: VectorStore) -> None:
        store.upsert_change("repo-a/2026-04-07", 0, "Fix A", "Fixed A")
        store.upsert_change("repo-a/2026-04-07", 1, "Add B", "Added B")
        assert store.change_count == 2


class TestSearchChangelogs:
    def test_search_returns_results(self, store: VectorStore) -> None:
        store.upsert_changelog("repo-a", "2026-04-07", "Security hardening", "Hardened auth")
        store.upsert_changelog("repo-b", "2026-04-07", "Add feature", "New feature")
        results = store.search_changelogs("security", n=2)
        assert len(results) == 2
        assert results[0]["id"] is not None

    def test_search_with_repo_filter(self, store: VectorStore) -> None:
        store.upsert_changelog("repo-a", "2026-04-07", "Title A", "Sum A")
        store.upsert_changelog("repo-b", "2026-04-07", "Title B", "Sum B")
        results = store.search_changelogs("title", n=10, repo="repo-a")
        assert all(r["metadata"]["repo"] == "repo-a" for r in results)

    def test_empty_store(self, store: VectorStore) -> None:
        results = store.search_changelogs("anything")
        assert results == []


class TestSearchChanges:
    def test_search_returns_results(self, store: VectorStore) -> None:
        store.upsert_change("repo-a/2026-04-07", 0, "Fix auth", "Hardened authentication")
        results = store.search_changes("auth", n=5)
        assert len(results) >= 1


class TestFindRelated:
    def test_find_related(self, store: VectorStore) -> None:
        store.upsert_changelog("repo-a", "2026-04-07", "Security fix", "Hardened auth")
        store.upsert_changelog("repo-b", "2026-04-07", "Security update", "Updated auth")
        store.upsert_changelog("repo-c", "2026-04-07", "Add tests", "Test coverage")
        related = store.find_related("repo-a/2026-04-07", n=2)
        assert len(related) <= 2
        assert all(r["id"] != "repo-a/2026-04-07" for r in related)

    def test_find_related_nonexistent(self, store: VectorStore) -> None:
        results = store.find_related("nonexistent/2026-01-01")
        assert results == []


class TestSearchChangesWithFilter:
    def test_search_with_repo_filter(self, store: VectorStore) -> None:
        store.upsert_change("repo-a/2026-04-07", 0, "Fix A", "auth fix", metadata={"repo": "repo-a"})
        store.upsert_change("repo-b/2026-04-07", 0, "Fix B", "auth fix", metadata={"repo": "repo-b"})
        results = store.search_changes("auth", n=10, repo="repo-a")
        assert len(results) >= 1
