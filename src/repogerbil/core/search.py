# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""High-level search queries over the vector store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.vectordb import VectorStore


def index_changelogs(
    store: VectorStore,
    changelog_dir: Path,
    include_diffs: bool = False,
    diff_source_repos: dict[str, str] | None = None,
) -> int:
    """Index all changelog YAML files into the vector store.

    Indexes: changelogs, changes, file paths, category distributions,
    and optionally diff content.

    Args:
        store: VectorStore instance.
        changelog_dir: Root directory with per-repo changelog subdirs.
        include_diffs: Whether to read and index git diffs.
        diff_source_repos: {repo_name: repo_path} for diff reading.

    Returns:
        Number of changelogs indexed.
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

            # #4: Cross-repo timeline — embed date + category distribution as metadata
            categories = _extract_categories(data)
            cat_str = " ".join(f"{k}:{v}" for k, v in sorted(categories.items(), key=lambda x: -x[1]))

            # #5: Category distribution as metadata
            dominant_cat = max(categories, key=categories.get) if categories else ""  # type: ignore[arg-type]

            store.upsert_changelog(
                repo=repo,
                date_str=date_str,
                title=title,
                summary=summary,
                metadata={
                    "commits": stats.get("commits", 0),
                    "files_changed": stats.get("files_changed", 0),
                    "dominant_category": dominant_cat,
                    "category_distribution": cat_str,
                },
            )

            # #1: File path embeddings
            all_filepaths = _extract_filepaths(data)
            if all_filepaths:  # pragma: no branch
                store.upsert_filepaths(
                    changelog_id=f"{repo}/{date_str}",
                    filepaths=all_filepaths,
                    metadata={"repo": repo, "date": date_str},
                )

            # Index change sections with enriched metadata
            for i, change in enumerate(data.get("changes") or []):
                change_title = change.get("title", "")
                # #2: Commit message clusters — embed all point texts together
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

            # #3: Diff content embeddings (optional)
            if include_diffs and diff_source_repos and repo in diff_source_repos:  # pragma: no cover
                _index_diffs(store, repo, date_str, diff_source_repos[repo])

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


def search_filepaths(
    store: VectorStore,
    query: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Search by file path patterns."""
    return store.search_filepaths(query, n=n)


def search_diffs(
    store: VectorStore,
    query: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Search diff content semantically."""
    return store.search_diffs(query, n=n)


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


def find_similar_file_changes(
    store: VectorStore,
    filepaths: list[str],
    n: int = 5,
) -> list[dict[str, Any]]:
    """Find changelogs that touched similar file paths."""
    query = " ".join(filepaths)
    return store.search_filepaths(query, n=n)


def find_work_pattern(
    store: VectorStore,
    category: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Find changelogs with a specific dominant work pattern."""
    results = store.search_changelogs(category, n=n * 3)
    return [r for r in results if r.get("metadata", {}).get("dominant_category") == category][:n]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _extract_categories(data: dict[str, Any]) -> dict[str, int]:
    """Extract category distribution from changelog data."""
    categories: dict[str, int] = {}
    for change in data.get("changes") or []:
        cat = change.get("category")
        if cat:  # pragma: no branch
            categories[cat] = categories.get(cat, 0) + 1
    return categories


def _extract_filepaths(data: dict[str, Any]) -> list[str]:
    """Extract all unique file paths from changelog data."""
    paths: set[str] = set()
    for change in data.get("changes") or []:
        for f in change.get("files") or []:
            if isinstance(f, dict) and f.get("path"):  # pragma: no branch
                paths.add(f["path"])
        for point in change.get("points") or []:
            if isinstance(point, dict):  # pragma: no branch
                for pf in point.get("files") or []:
                    if isinstance(pf, str):  # pragma: no branch
                        paths.add(pf)
    return sorted(p for p in paths if isinstance(p, str))


def _index_diffs(  # pragma: no cover — requires real git repos with multi-commit dates
    store: VectorStore,
    repo: str,
    date_str: str,
    repo_path: str,
) -> None:
    """Index diff content for a specific date."""
    from repogerbil.core.diff import get_diff_content
    from repogerbil.core.git import get_commits_for_date

    commits = get_commits_for_date(repo_path, date_str)
    if len(commits) < 2:
        return

    diffs = get_diff_content(
        repo_path, commits[0].hash, commits[-1].hash, max_files=20, max_lines_per_file=100
    )
    changelog_id = f"{repo}/{date_str}"

    for filepath, diff_text in diffs.items():
        if diff_text.strip():
            store.upsert_diff(
                changelog_id=changelog_id,
                filepath=filepath,
                diff_text=diff_text,
                metadata={"repo": repo, "date": date_str},
            )


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load YAML file, return None on error."""
    try:
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover
        return None
