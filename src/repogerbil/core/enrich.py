# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Changelog enrichment — per-section stats and impact analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git, get_commits_for_date, parse_shortstat


def enrich_changelog(
    yaml_path: Path,
    repo_path: str | Path,
    depth: str = "package",
) -> bool:
    """Add per-section stats and impact analysis to an existing changelog.

    Args:
        yaml_path: Path to the changelog YAML file.
        repo_path: Path to the source git repository.
        depth: "file", "package", or "cross-repo".

    Returns:
        True if the file was modified.
    """
    data = _load_yaml(yaml_path)
    if not data or not data.get("changes"):
        return False

    date_str = str(data.get("date", ""))[:10]
    if not date_str:
        return False

    commits = get_commits_for_date(repo_path, date_str)
    if not commits:
        return False

    first_hash = commits[0].hash
    last_hash = commits[-1].hash
    modified = False

    for change in data["changes"]:
        section_files = _get_section_files(change)
        if not section_files:
            continue

        section_stats = _get_file_stats(repo_path, first_hash, last_hash, section_files)
        if section_stats.get("files_changed", 0) > 0:
            change["stats"] = section_stats
            modified = True

        if depth in ("file", "package", "cross-repo"):  # pragma: no cover — grep-based
            impact = _find_importers(repo_path, section_files, depth)
            if impact:
                change["impact"] = impact
                modified = True

    if modified:
        yaml_path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False))

    return modified


def _get_section_files(change: dict[str, Any]) -> set[str]:
    """Extract all file paths from a change section."""
    paths: set[str] = set()
    for f in change.get("files") or []:
        if isinstance(f, dict) and f.get("path"):  # pragma: no branch
            paths.add(f["path"])
    for point in change.get("points") or []:
        if isinstance(point, dict):  # pragma: no branch
            for pf in point.get("files") or []:
                if isinstance(pf, str):  # pragma: no branch
                    paths.add(pf)
    return paths


def _get_file_stats(
    repo_path: str | Path,
    first_hash: str,
    last_hash: str,
    files: set[str],
) -> dict[str, int]:
    """Get diff stats for specific files in a commit range."""
    if not files:  # pragma: no cover — caller checks before calling
        return {"files_changed": 0, "insertions": 0, "deletions": 0}

    stat_line = _run_file_shortstat(repo_path, first_hash, last_hash, files).strip()
    if not stat_line:
        return {"files_changed": 0, "insertions": 0, "deletions": 0}
    return parse_shortstat(stat_line)


def _run_file_shortstat(
    repo_path: str | Path,
    first_hash: str,
    last_hash: str,
    files: set[str],
) -> str:
    """Run inclusive shortstat for file-filtered commit range."""
    span = f"{first_hash}^..{last_hash}"
    target = first_hash if first_hash == last_hash else last_hash
    file_args = ["--", *sorted(files)]
    try:
        return _run_git(repo_path, "diff", "--shortstat", span, *file_args, timeout=30)
    except GitCommandError:
        return _run_git(
            repo_path, "show", "--shortstat", "--format=", "--root", target, *file_args, timeout=30
        )


def _find_importers(  # pragma: no cover — grep-based, environment-dependent
    repo_path: str | Path,
    changed_files: set[str],
    depth: str,
) -> dict[str, Any]:
    """Find files/packages that depend on the changed files."""
    impact: dict[str, Any] = {}

    importing_files: set[str] = set()
    for changed in changed_files:
        base_name = Path(changed).stem
        try:
            result = _run_git(repo_path, "grep", "-l", base_name, "HEAD", timeout=10)
            for line in result.strip().splitlines():
                path = line.split(":", 1)[-1] if ":" in line else line
                if path not in changed_files and not path.endswith(
                    (".md", ".yaml", ".yml", ".json", ".lock"),
                ):
                    importing_files.add(path)
        except Exception:  # noqa: S110 — grep may fail on some repos  # pragma: no cover
            pass

    if importing_files:
        impact["files"] = sorted(importing_files)[:20]

    if depth in ("package", "cross-repo"):
        packages: set[str] = set()
        for f in importing_files:
            pkg = str(Path(f).parent) + "/"
            if pkg != "./":
                packages.add(pkg)
        if packages:
            impact["packages"] = sorted(packages)[:10]

    return impact


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load YAML file, return None on error."""
    try:
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover
        return None
