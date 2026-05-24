# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for vector database wrapper."""

import multiprocessing
from pathlib import Path
import sqlite3
from typing import Any

import pytest

from repogerbil.core.embeddings import SimpleHashEmbedder

# Skip entire module if chromadb not installed
chromadb = pytest.importorskip("chromadb")

from repogerbil.core.vectordb import VectorStore  # noqa: E402


def _open_store_worker(db_path: str, q: Any) -> None:
    try:
        store = VectorStore(Path(db_path), SimpleHashEmbedder())
        store.upsert_changelog("repo-x", "2026-04-07", "Title", "Summary")
        q.put(("ok", str(store.changelog_count)))
    except Exception as exc:  # pragma: no cover - defensive for child-process reporting
        q.put(("err", f"{type(exc).__name__}: {exc}"))


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


class TestUpsertFilepaths:
    def test_upsert_and_search(self, store: VectorStore) -> None:
        store.upsert_filepaths(
            "repo-a/2026-04-07", ["src/main.py", "src/utils.py"], metadata={"repo": "repo-a"}
        )
        assert store.filepath_count == 1
        results = store.search_filepaths("main.py", n=5)
        assert len(results) >= 1

    def test_empty_filepaths(self, store: VectorStore) -> None:
        store.upsert_filepaths("repo-a/2026-04-07", [])
        assert store.filepath_count == 0


class TestUpsertDiff:
    def test_upsert_and_search(self, store: VectorStore) -> None:
        store.upsert_diff(
            "repo-a/2026-04-07", "src/main.py", "+print('hello')\n-print('bye')", metadata={"repo": "repo-a"}
        )
        assert store.diff_count == 1
        results = store.search_diffs("print hello", n=5)
        assert len(results) >= 1


class TestConcurrentInitialization:
    @pytest.mark.integration
    def test_parallel_initialization_same_db_path(self, tmp_path: Path) -> None:
        db_path = tmp_path / "shared-db"
        q: Any = multiprocessing.Queue()

        p1 = multiprocessing.Process(target=_open_store_worker, args=(str(db_path), q))
        p2 = multiprocessing.Process(target=_open_store_worker, args=(str(db_path), q))
        p1.start()
        p2.start()
        p1.join(timeout=20)
        p2.join(timeout=20)

        if p1.is_alive():
            p1.terminate()
        if p2.is_alive():
            p2.terminate()

        assert p1.exitcode == 0
        assert p2.exitcode == 0
        results = [q.get(timeout=5), q.get(timeout=5)]
        assert all(status == "ok" for status, _ in results)


class TestVectorStoreInitRetry:
    def test_retries_on_runtime_already_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        class DummyLock:
            def acquire(self, timeout: int) -> object:
                class _Ctx:
                    def __enter__(self) -> None:
                        return None

                    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
                        return None

                assert timeout == 15
                return _Ctx()

        class DummyChromadb:
            attempts = 0

            @classmethod
            def PersistentClient(cls, *, path: str) -> object:
                cls.attempts += 1
                if cls.attempts == 1:
                    raise RuntimeError("table collections already exists")
                return {"path": path}

        monkeypatch.setattr("repogerbil.core.vectordb.time.sleep", lambda _s: None)
        store = object.__new__(VectorStore)
        client = store._create_client_with_retry(DummyChromadb, DummyLock(), tmp_path / "db")
        assert client == {"path": str(tmp_path / "db")}
        assert DummyChromadb.attempts == 2

    def test_retries_on_sqlite_already_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        class DummyLock:
            def acquire(self, timeout: int) -> object:
                class _Ctx:
                    def __enter__(self) -> None:
                        return None

                    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
                        return None

                assert timeout == 15
                return _Ctx()

        class DummyChromadb:
            attempts = 0

            @classmethod
            def PersistentClient(cls, *, path: str) -> object:
                cls.attempts += 1
                if cls.attempts == 1:
                    raise sqlite3.OperationalError("table collections already exists")
                return {"path": path}

        monkeypatch.setattr("repogerbil.core.vectordb.time.sleep", lambda _s: None)
        store = object.__new__(VectorStore)
        client = store._create_client_with_retry(DummyChromadb, DummyLock(), tmp_path / "db")
        assert client == {"path": str(tmp_path / "db")}
        assert DummyChromadb.attempts == 2

    def test_raises_runtime_non_retryable(self, tmp_path: Path) -> None:
        class DummyLock:
            def acquire(self, timeout: int) -> object:
                class _Ctx:
                    def __enter__(self) -> None:
                        return None

                    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
                        return None

                assert timeout == 15
                return _Ctx()

        class DummyChromadb:
            @staticmethod
            def PersistentClient(*, path: str) -> object:
                _ = path
                raise RuntimeError("disk full")

        store = object.__new__(VectorStore)
        with pytest.raises(RuntimeError, match="disk full"):
            store._create_client_with_retry(DummyChromadb, DummyLock(), tmp_path / "db")

    def test_raises_sqlite_non_retryable(self, tmp_path: Path) -> None:
        class DummyLock:
            def acquire(self, timeout: int) -> object:
                class _Ctx:
                    def __enter__(self) -> None:
                        return None

                    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
                        return None

                assert timeout == 15
                return _Ctx()

        class DummyChromadb:
            @staticmethod
            def PersistentClient(*, path: str) -> object:
                _ = path
                raise sqlite3.OperationalError("database is locked")

        store = object.__new__(VectorStore)
        with pytest.raises(sqlite3.OperationalError, match="database is locked"):
            store._create_client_with_retry(DummyChromadb, DummyLock(), tmp_path / "db")
