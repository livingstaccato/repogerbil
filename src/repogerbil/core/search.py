# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""High-level search queries over the vector store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.vectordb import VectorStore


def index_changelogs(store: VectorStore, changelog_dir: Path) -> int:
    """Index all changelog YAML files into the vector store.

    Returns the number of changelogs indexed.
    """
    indexed = 0

    for repo_dir in sorted(changelog_dir.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        for yaml_file in sorted(repo_dir.glob("*-changelog.yaml")):
            data = _load_yaml(yaml_file)
            if not data or not data.get("title") or not data.get("date"):
                continue

            repo = data.get("repo", repo_dir.name)
            date_str = str(data["date"])[:10]
            title = data["title"]
            summary = data.get("summary", "")
            stats = data.get("stats", {})

            if title.startswith("TODO"):
                continue

            store.upsert_changelog(
                repo=repo,
                date_str=date_str,
                title=title,
                summary=summary,
                metadata={
                    "commits": stats.get("commits", 0),
                    "files_changed": stats.get("files_changed", 0),
                },
            )

            for i, change in enumerate(data.get("changes") or []):
                change_title = change.get("title", "")
                points_text = " ".join(
                    p.get("text", "") for p in (change.get("points") or []) if isinstance(p, dict)
                )
                category = change.get("category", "")
                severity = change.get("severity", "")

                store.upsert_change(
                    changelog_id=f"{repo}/{date_str}",
                    index=i,
                    title=change_title,
                    points_text=points_text,
                    metadata={
                        "category": category or "",
                        "severity": severity or "",
                        "repo": repo,
                        "date": date_str,
                    },
                )

            indexed += 1

    return indexed


def search_across_repos(
    store: VectorStore,
    query: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Search all changelogs across all repos."""
    return store.search_changelogs(query, n=n)


def search_by_category(
    store: VectorStore,
    query: str,
    category: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Search change sections filtered by category."""
    results = store.search_changes(query, n=n * 3)
    return [r for r in results if r.get("metadata", {}).get("category") == category][:n]


def find_related_work(
    store: VectorStore,
    repo: str,
    date_str: str,
    n: int = 5,
) -> list[dict[str, Any]]:
    """Find work in other repos related to a specific day's changes."""
    changelog_id = f"{repo}/{date_str}"
    related = store.find_related(changelog_id, n=n + 5)
    return [r for r in related if not r["id"].startswith(f"{repo}/")][:n]


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load YAML file, return None on error."""
    try:
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover
        return None
