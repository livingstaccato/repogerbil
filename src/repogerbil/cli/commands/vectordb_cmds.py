# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for vector database operations (optional)."""

from __future__ import annotations

from pathlib import Path

import click


def _get_store(db_path: str | None) -> object:
    """Create a VectorStore with SimpleHashEmbedder or SentenceTransformerEmbedder."""
    try:
        from repogerbil.core.embeddings import SimpleHashEmbedder
        from repogerbil.core.vectordb import VectorStore
    except ImportError:
        click.echo("Vector DB not available. Run: pip install repogerbil[vectordb]")
        raise SystemExit(1)  # noqa: B904

    path = Path(db_path) if db_path else Path(".repogerbil/vectordb")

    try:
        from repogerbil.core.embeddings import SentenceTransformerEmbedder

        embedder = SentenceTransformerEmbedder()
    except ImportError:
        embedder = SimpleHashEmbedder()  # type: ignore[assignment]

    return VectorStore(path, embedder)


@click.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--db-path", default=None, help="Vector DB path (default: .repogerbil/vectordb)")
def index(changelog_dir: str, db_path: str | None) -> None:
    """Index all changelogs into the vector database."""
    from repogerbil.core.search import index_changelogs

    store = _get_store(db_path)
    count = index_changelogs(store, Path(changelog_dir))  # type: ignore[arg-type]
    click.echo(f"Indexed {count} changelogs")


@click.command()
@click.argument("query")
@click.option("--top", default=10, help="Number of results")
@click.option("--repo", default=None, help="Filter by repo")
@click.option("--db-path", default=None, help="Vector DB path")
def search(query: str, top: int, repo: str | None, db_path: str | None) -> None:
    """Semantic search across changelogs."""
    store = _get_store(db_path)
    results = store.search_changelogs(query, n=top, repo=repo)  # type: ignore[attr-defined]
    if not results:
        click.echo("No results found.")
        return
    for r in results:
        meta = r.get("metadata", {})
        click.echo(f"  {r['id']}: {meta.get('title', '?')} (distance: {r['distance']:.3f})")


@click.command()
@click.argument("repo")
@click.option("--date", required=True, help="Date (YYYY-MM-DD)")
@click.option("--top", default=5, help="Number of results")
@click.option("--db-path", default=None, help="Vector DB path")
def related(repo: str, date: str, top: int, db_path: str | None) -> None:
    """Find related work in other repos for a specific date."""
    from repogerbil.core.search import find_related_work

    store = _get_store(db_path)
    results = find_related_work(store, repo, date, n=top)  # type: ignore[arg-type]
    if not results:
        click.echo("No related work found.")
        return
    for r in results:
        meta = r.get("metadata", {})
        click.echo(f"  {r['id']}: {meta.get('title', '?')}")
