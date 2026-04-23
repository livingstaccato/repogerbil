# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Vector database abstraction for changelog semantic search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repogerbil.core.embeddings import Embedder


class VectorStore:
    """ChromaDB-backed vector store for changelog data."""

    def __init__(self, db_path: str | Path, embedder: Embedder) -> None:
        try:
            import chromadb
        except ImportError as e:  # pragma: no cover
            msg = "chromadb not installed. Run: pip install repogerbil[vectordb]"
            raise ImportError(msg) from e  # pragma: no cover

        self._client = chromadb.PersistentClient(path=str(db_path))
        self._embedder = embedder
        self._changelogs = self._client.get_or_create_collection(
            "changelogs",
            metadata={"hnsw:space": "cosine"},
        )
        self._changes = self._client.get_or_create_collection(
            "changes",
            metadata={"hnsw:space": "cosine"},
        )
        self._filepaths = self._client.get_or_create_collection(
            "filepaths",
            metadata={"hnsw:space": "cosine"},
        )
        self._diffs = self._client.get_or_create_collection(
            "diffs",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_changelog(
        self,
        repo: str,
        date_str: str,
        title: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a changelog document with its embedding."""
        doc_id = f"{repo}/{date_str}"
        text = f"{title}. {summary}"
        embedding = self._embedder.embed(text)
        meta = {
            "repo": repo,
            "date": date_str,
            "title": title,
            **(metadata or {}),
        }
        # ChromaDB requires string/int/float/bool metadata values
        meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
        self._changelogs.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta],
        )

    def upsert_change(
        self,
        changelog_id: str,
        index: int,
        title: str,
        points_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a change section document."""
        doc_id = f"{changelog_id}/{index}"
        text = f"{title}. {points_text}"
        embedding = self._embedder.embed(text)
        meta = {
            "changelog_id": changelog_id,
            "index": index,
            "title": title,
            **(metadata or {}),
        }
        meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
        self._changes.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta],
        )

    def search_changelogs(
        self,
        query: str,
        n: int = 10,
        repo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search changelogs by semantic similarity."""
        embedding = self._embedder.embed(query)
        where = {"repo": repo} if repo else None
        results = self._changelogs.query(
            query_embeddings=[embedding],
            n_results=n,
            where=where,
        )
        return _format_results(results)

    def search_changes(
        self,
        query: str,
        n: int = 10,
        repo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search change sections by semantic similarity."""
        embedding = self._embedder.embed(query)
        results = self._changes.query(
            query_embeddings=[embedding],
            n_results=n * 3 if repo else n,
        )
        formatted = _format_results(results)
        if repo:
            formatted = [r for r in formatted if r.get("metadata", {}).get("repo") == repo][:n]
        return formatted

    def find_related(
        self,
        changelog_id: str,
        n: int = 5,
    ) -> list[dict[str, Any]]:
        """Find changelogs similar to a specific one."""
        existing = self._changelogs.get(ids=[changelog_id], include=["embeddings"])
        embeddings = existing.get("embeddings")
        if embeddings is None or len(embeddings) == 0:
            return []
        embedding = embeddings[0]
        results = self._changelogs.query(
            query_embeddings=[embedding],
            n_results=n + 1,  # +1 to exclude self
        )
        formatted = _format_results(results)
        return [r for r in formatted if r["id"] != changelog_id][:n]

    def upsert_filepaths(
        self,
        changelog_id: str,
        filepaths: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert file paths as a single embedded document per changelog."""
        if not filepaths:
            return
        doc_id = f"{changelog_id}/files"
        text = " ".join(filepaths)
        embedding = self._embedder.embed(text)
        meta = {"changelog_id": changelog_id, **(metadata or {})}
        meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
        self._filepaths.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta],
        )

    def upsert_diff(
        self,
        changelog_id: str,
        filepath: str,
        diff_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a diff chunk for a specific file."""
        doc_id = f"{changelog_id}/diff/{filepath}"
        embedding = self._embedder.embed(diff_text[:2000])  # cap embedding input
        meta = {
            "changelog_id": changelog_id,
            "filepath": filepath,
            **(metadata or {}),
        }
        meta = {k: v for k, v in meta.items() if isinstance(v, (str, int, float, bool))}
        self._diffs.upsert(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[diff_text[:5000]],  # cap stored text
            metadatas=[meta],
        )

    def search_filepaths(
        self,
        query: str,
        n: int = 10,
    ) -> list[dict[str, Any]]:
        """Search by file path similarity."""
        embedding = self._embedder.embed(query)
        results = self._filepaths.query(
            query_embeddings=[embedding],
            n_results=n,
        )
        return _format_results(results)

    def search_diffs(
        self,
        query: str,
        n: int = 10,
    ) -> list[dict[str, Any]]:
        """Search diff content by semantic similarity."""
        embedding = self._embedder.embed(query)
        results = self._diffs.query(
            query_embeddings=[embedding],
            n_results=n,
        )
        return _format_results(results)

    @property
    def changelog_count(self) -> int:
        """Number of indexed changelogs."""
        return int(self._changelogs.count())

    @property
    def change_count(self) -> int:
        """Number of indexed change sections."""
        return int(self._changes.count())

    @property
    def filepath_count(self) -> int:
        """Number of indexed filepath documents."""
        return int(self._filepaths.count())

    @property
    def diff_count(self) -> int:
        """Number of indexed diff chunks."""
        return int(self._diffs.count())


def _format_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    """Format ChromaDB query results into a flat list."""
    formatted: list[dict[str, Any]] = []
    ids = results.get("ids", [[]])[0]
    docs = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    for i, doc_id in enumerate(ids):
        entry: dict[str, Any] = {
            "id": doc_id,
            "document": docs[i] if i < len(docs) else "",
            "distance": distances[i] if i < len(distances) else 0.0,
        }
        if i < len(metadatas) and metadatas[i]:  # pragma: no branch
            entry["metadata"] = metadatas[i]
        formatted.append(entry)

    return formatted
