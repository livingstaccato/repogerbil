# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""High-level search queries over the vector store."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from repogerbil.core.state import StateStore
from repogerbil.core.vectordb import VectorStore

_DRAFT_PLACEHOLDER_RE = re.compile(r"^(TODO|Draft)\s*:", re.IGNORECASE)


def index_changelogs(
    store: VectorStore,
    changelog_dir: Path,
    include_diffs: bool = False,
    diff_source_repos: dict[str, str] | None = None,
    incremental: bool = True,
) -> int:
    """Index all changelog YAML files into the vector store.

    Indexes: changelogs, changes, file paths, category distributions,
    and optionally diff content.

    Args:
        store: VectorStore instance.
        changelog_dir: Root directory with per-repo changelog subdirs.
        include_diffs: Whether to read and index git diffs.
        diff_source_repos: {repo_name: repo_path} for diff reading.
        incremental: Whether to skip files already in the state.

    Returns:
        Number of changelogs indexed.
    """
    indexed = 0
    state_store = StateStore(changelog_dir)

    for repo_dir in sorted(changelog_dir.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        for yaml_file in sorted(repo_dir.glob("*-changelog.yaml")):
            if incremental and not state_store.is_changed(yaml_file):
                continue

            if _index_single_changelog(store, yaml_file, repo_dir.name, include_diffs, diff_source_repos):
                indexed += 1
                state_store.update(yaml_file)

    if indexed > 0:
        state_store.save()

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


def search_by_scope(
    store: VectorStore,
    scope: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Find changes tagged with a specific scope (e.g., parity, worker, go)."""
    results = store.search_changes(scope, n=n * 3)
    return [r for r in results if scope in r.get("metadata", {}).get("scopes", "").split()][:n]


def find_low_quality(
    store: VectorStore,
    n: int = 20,
) -> list[dict[str, Any]]:
    """Find changelogs with lowest quality scores (most needing work)."""
    # Search broadly, then sort by coverage
    results = store.search_changelogs("changelog", n=n * 5)
    scored = []
    for r in results:
        meta = r.get("metadata", {})
        coverage = meta.get("quality_coverage", 100)
        review_count = meta.get("quality_review_count", 0)
        has_title = meta.get("quality_has_title", True)
        # Lower is worse
        score = coverage - (review_count * 10) - (0 if has_title else 50)
        scored.append((score, r))
    scored.sort(key=lambda x: x[0])
    return [r for _, r in scored[:n]]


def find_work_pattern(
    store: VectorStore,
    category: str,
    n: int = 10,
) -> list[dict[str, Any]]:
    """Find changelogs with a specific dominant work pattern."""
    results = store.search_changelogs(category, n=n * 3)
    return [r for r in results if r.get("metadata", {}).get("dominant_category") == category][:n]


# ── Internal helpers ──────────────────────────────────────────────────────────


def _index_single_changelog(
    store: VectorStore,
    yaml_file: Path,
    default_repo: str,
    include_diffs: bool,
    diff_source_repos: dict[str, str] | None,
) -> bool:
    """Index a single changelog file into the store. Returns True if indexed."""
    data = _load_yaml(yaml_file)
    if not data or not data.get("title") or not data.get("date"):
        return False

    repo = data.get("repo", default_repo)
    date_str = str(data["date"])[:10]
    title = data["title"]
    summary = data.get("summary", "")
    stats = data.get("stats", {})

    if _is_draft_placeholder(title):
        return False

    categories = _extract_categories(data)
    cat_str = " ".join(f"{k}:{v}" for k, v in sorted(categories.items(), key=lambda x: -x[1]))
    dominant_cat = max(categories, key=categories.get) if categories else ""  # type: ignore[arg-type]
    scopes = _extract_scopes(data)
    quality = _compute_quality(data)

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
            "scopes": " ".join(scopes),
            **quality,
        },
    )

    all_filepaths = _extract_filepaths(data)
    if all_filepaths:  # pragma: no branch
        store.upsert_filepaths(
            changelog_id=f"{repo}/{date_str}",
            filepaths=all_filepaths,
            metadata={"repo": repo, "date": date_str},
        )

    _index_change_sections(store, data, repo, date_str)

    if include_diffs and diff_source_repos and repo in diff_source_repos:  # pragma: no cover
        _index_diffs(store, repo, date_str, diff_source_repos[repo])

    return True


def _index_change_sections(store: VectorStore, data: dict[str, Any], repo: str, date_str: str) -> None:
    """Index individual change sections from a changelog."""
    for i, change in enumerate(data.get("changes") or []):
        change_title = change.get("title", "")
        points_text = " ".join(p.get("text", "") for p in (change.get("points") or []) if isinstance(p, dict))
        category = change.get("category", "")
        severity = change.get("severity", "")

        section_scopes: set[str] = set()
        for p in change.get("points") or []:
            if isinstance(p, dict):  # pragma: no branch
                m = _SCOPE_RE.match(p.get("text", ""))
                if m:
                    section_scopes.add(m.group(1).lower())

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
                "scopes": " ".join(sorted(section_scopes)),
            },
        )


def _extract_categories(data: dict[str, Any]) -> dict[str, int]:
    """Extract category distribution from changelog data."""
    categories: dict[str, int] = {}
    for change in data.get("changes") or []:
        cat = change.get("category")
        if cat:  # pragma: no branch
            categories[cat] = categories.get(cat, 0) + 1
    return categories


_SCOPE_RE = __import__("re").compile(r"^\w+\(([^)]+)\)[!]?:\s")


def _extract_scopes(data: dict[str, Any]) -> list[str]:
    """Extract unique scopes from commit subjects in points."""
    scopes: set[str] = set()
    for change in data.get("changes") or []:
        for point in change.get("points") or []:
            if isinstance(point, dict):  # pragma: no branch
                text = point.get("text", "")
                m = _SCOPE_RE.match(text)
                if m:
                    scopes.add(m.group(1).lower())
    return sorted(scopes)


def _compute_quality(data: dict[str, Any]) -> dict[str, Any]:
    """Compute quality metrics for a changelog.

    Returns metadata dict with quality indicators.
    """
    stats = data.get("stats", {})
    files_changed = stats.get("files_changed", 0)

    bulk_files = _count_bulk_files(data)
    accounted = bulk_files + len(_collect_change_files(data))

    # Coverage ratio
    coverage = (accounted / files_changed * 100) if files_changed > 0 else 100.0

    # Review items
    review_count = len(data.get("review") or [])

    # Bulk ratio
    bulk_ratio = (bulk_files / files_changed * 100) if files_changed > 0 else 0.0

    # Has real title (not a draft placeholder)
    title = data.get("title", "")
    has_title = bool(title) and not _is_draft_placeholder(str(title))

    # Has summary
    summary = data.get("summary", "")
    has_summary = bool(summary) and not _is_draft_placeholder(str(summary))

    # Change section count
    change_count = len(data.get("changes") or [])

    return {
        "quality_coverage": round(coverage, 1),
        "quality_review_count": review_count,
        "quality_bulk_pct": round(bulk_ratio, 1),
        "quality_has_title": has_title,
        "quality_has_summary": has_summary,
        "quality_change_sections": change_count,
    }


def _count_bulk_files(data: dict[str, Any]) -> int:
    """Count files represented by bulk entries."""
    return sum(bulk.get("files", 0) for bulk in (data.get("bulk") or []))


def _collect_change_files(data: dict[str, Any]) -> set[str]:
    """Collect unique file paths represented by change entries and points."""
    change_files: set[str] = set()
    for change in data.get("changes") or []:
        _add_change_file_paths(change_files, change)
    return change_files


def _add_change_file_paths(change_files: set[str], change: dict[str, Any]) -> None:
    """Add all explicit file paths from a single change block."""
    for file_entry in change.get("files") or []:
        if isinstance(file_entry, dict) and file_entry.get("path"):  # pragma: no branch
            change_files.add(str(file_entry["path"]))
    for point in change.get("points") or []:
        if isinstance(point, dict):  # pragma: no branch
            _add_point_file_paths(change_files, point)


def _add_point_file_paths(change_files: set[str], point: dict[str, Any]) -> None:
    """Add all file paths referenced by a single point."""
    for point_file in point.get("files") or []:
        if isinstance(point_file, str):  # pragma: no branch
            change_files.add(point_file)


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


def _is_draft_placeholder(text: str) -> bool:
    """Return True when title/summary text is a draft placeholder marker."""
    return bool(_DRAFT_PLACEHOLDER_RE.match(text.strip()))


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
