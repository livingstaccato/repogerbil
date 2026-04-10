# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""YAML changelog schema validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.vocabulary import CATEGORIES, SEVERITIES

# Valid values include canonical + alt-labels
VALID_CATEGORIES = set(CATEGORIES.keys()) | {
    "realize",
    "provision",
    "actualize",
    "commission",
    "manifest",
    "rectify",
    "correct",
    "mitigate",
    "resolve",
    "restore",
    "modularize",
    "partition",
    "decompose",
    "isolate",
    "extract",
    "decommission",
    "retire",
    "sunset",
    "expunge",
    "phase-out",
    "integrate",
    "bridge",
    "interoperate",
    "bind",
    "wire",
    "formalize",
    "define",
    "prescribe",
    "annotate",
    "articulate",
    "verify",
    "validate",
    "certify",
    "demonstrate",
    "confirm",
    "buffer",
    "headroom",
    "slack",
    "tolerance",
    "reserve",
    "fortify",
    "ruggedize",
    "armor",
    "guard",
    "optimize",
    "tune",
    "refine",
    "accelerate",
    "reduce-drag",
    "pin",
    "lock",
    "freeze",
    "normalize",
    "standardize",
}

VALID_SEVERITIES = (
    set(SEVERITIES.keys())
    | {v for v in SEVERITIES.values() if v is not None}
    | {
        "structural",
        "foundational",
        "systemic",
        "sweeping",
        "functional",
        "operational",
        "observable",
        "external",
        "mechanical",
        "cosmetic",
        "superficial",
        "incidental",
        "negligible",
    }
)


@dataclass
class LintResult:
    """Result of linting a single changelog file."""

    path: Path
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_file(path: Path, errors_only: bool = False) -> LintResult:
    """Validate a single changelog YAML file against the schema.

    Args:
        path: Path to the YAML file.
        errors_only: If True, skip warnings.

    Returns:
        LintResult with errors and warnings.
    """
    result = LintResult(path=path)

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        result.errors.append(f"YAML parse error: {e}")
        return result

    if not isinstance(data, dict):
        result.errors.append("top-level value is not a mapping")
        return result

    _check_top_level(data, result, errors_only)
    _check_stats(data, result)
    _check_bulk(data, result)
    _check_changes(data, result, errors_only)

    return result


def _check_top_level(data: dict[str, Any], result: LintResult, errors_only: bool) -> None:
    for f in ("date", "repo", "title", "summary"):
        if not data.get(f):
            result.errors.append(f"missing required field: {f!r}")


def _check_stats(data: dict[str, Any], result: LintResult) -> None:
    stats = data.get("stats")
    if not isinstance(stats, dict):
        result.errors.append("missing or invalid 'stats' block")
        return
    for sf in ("files_changed", "insertions", "deletions"):
        if sf not in stats:
            result.errors.append(f"stats missing field: {sf!r}")


def _check_bulk(data: dict[str, Any], result: LintResult) -> None:
    bulk = data.get("bulk")
    if bulk is None:
        return
    if not isinstance(bulk, list):
        result.errors.append("'bulk' must be a list")
        return
    for bi, entry in enumerate(bulk):
        bloc = f"bulk[{bi}]"
        if not isinstance(entry, dict):
            result.errors.append(f"{bloc}: must be a mapping")
            continue
        bcat = entry.get("category")
        if bcat is None:
            result.errors.append(f"{bloc}: missing 'category'")
        elif bcat not in VALID_CATEGORIES:
            result.errors.append(f"{bloc}: unknown category {bcat!r}")
        bfiles = entry.get("files")
        if not isinstance(bfiles, int) or bfiles < 0:
            result.errors.append(f"{bloc}: 'files' must be a positive integer")
        if not entry.get("reason"):
            result.errors.append(f"{bloc}: missing 'reason'")


def _check_changes(data: dict[str, Any], result: LintResult, errors_only: bool) -> None:
    changes = data.get("changes")
    if not isinstance(changes, list):
        result.errors.append("'changes' must be a list")
        return

    if not changes and not errors_only:
        result.warnings.append("'changes' list is empty")

    for ci, change in enumerate(changes):
        loc = f"changes[{ci}]"
        if not isinstance(change, dict):
            result.errors.append(f"{loc}: must be a mapping")
            continue

        if not change.get("title"):
            result.errors.append(f"{loc}: missing 'title'")

        _check_section_stats(change, loc, result)
        _check_impact(change, loc, result)
        _check_category_severity(change, loc, result, errors_only)
        _check_files(change, loc, result, errors_only)
        _check_points(change, loc, result, errors_only)


def _check_section_stats(change: dict[str, Any], loc: str, result: LintResult) -> None:
    section_stats = change.get("stats")
    if section_stats is None:
        return
    if not isinstance(section_stats, dict):
        result.errors.append(f"{loc}.stats: must be a mapping")
        return
    for sf in ("files_changed", "insertions", "deletions"):
        val = section_stats.get(sf)
        if val is not None and not isinstance(val, int):
            result.errors.append(f"{loc}.stats.{sf}: must be an integer")


def _check_impact(change: dict[str, Any], loc: str, result: LintResult) -> None:
    impact = change.get("impact")
    if impact is None:
        return
    if not isinstance(impact, dict):
        result.errors.append(f"{loc}.impact: must be a mapping")
        return
    for f in ("files", "packages", "repos"):
        val = impact.get(f)
        if val is not None and not isinstance(val, list):
            result.errors.append(f"{loc}.impact.{f}: must be a list")


def _check_category_severity(change: dict[str, Any], loc: str, result: LintResult, errors_only: bool) -> None:
    cat = change.get("category")
    if cat is None:
        if not errors_only:
            result.warnings.append(f"{loc}: 'category' not set")
    elif cat not in VALID_CATEGORIES:
        result.errors.append(f"{loc}: unknown category {cat!r}")

    sev = change.get("severity")
    if sev is None:
        if not errors_only:
            result.warnings.append(f"{loc}: 'severity' not set")
    elif sev not in VALID_SEVERITIES:
        result.errors.append(f"{loc}: unknown severity {sev!r}")


def _check_files(change: dict[str, Any], loc: str, result: LintResult, errors_only: bool) -> None:
    files = change.get("files", [])
    if not isinstance(files, list):
        result.errors.append(f"{loc}: 'files' must be a list")
        return
    for fi, fentry in enumerate(files):
        floc = f"{loc}.files[{fi}]"
        if not isinstance(fentry, dict):
            result.errors.append(f"{floc}: must be a mapping with 'path' and 'summary'")
        else:
            if not fentry.get("path"):
                result.errors.append(f"{floc}: missing 'path'")
            if not fentry.get("summary") and not errors_only:
                result.warnings.append(f"{floc}: missing 'summary'")


def _check_points(change: dict[str, Any], loc: str, result: LintResult, errors_only: bool) -> None:
    points = change.get("points", [])
    if not isinstance(points, list):
        result.errors.append(f"{loc}: 'points' must be a list")
        return
    for pi, point in enumerate(points):
        ploc = f"{loc}.points[{pi}]"
        if isinstance(point, str):
            if not errors_only:
                result.warnings.append(f"{ploc}: plain string — consider adding category/severity/files")
            continue
        if not isinstance(point, dict):
            result.errors.append(f"{ploc}: must be a string or mapping")
            continue
        if not point.get("text"):
            result.errors.append(f"{ploc}: missing 'text'")
        _check_point_files(point, ploc, result)
        _check_point_category_severity(point, ploc, result, errors_only)


def _check_point_files(point: dict[str, Any], ploc: str, result: LintResult) -> None:
    pfiles = point.get("files", [])
    if not isinstance(pfiles, list):
        result.errors.append(f"{ploc}: 'files' must be a list")
        return
    for pfi, pf in enumerate(pfiles):
        if not isinstance(pf, str):
            result.errors.append(f"{ploc}.files[{pfi}]: must be a string (path only)")


def _check_point_category_severity(
    point: dict[str, Any], ploc: str, result: LintResult, errors_only: bool
) -> None:
    pcat = point.get("category")
    if pcat is None:
        if not errors_only:
            result.warnings.append(f"{ploc}: 'category' not set")
    elif pcat not in VALID_CATEGORIES:
        result.errors.append(f"{ploc}: unknown category {pcat!r}")

    psev = point.get("severity")
    if psev is None:
        if not errors_only:
            result.warnings.append(f"{ploc}: 'severity' not set")
    elif psev not in VALID_SEVERITIES:
        result.errors.append(f"{ploc}: unknown severity {psev!r}")


def lint_directory(
    changelog_dir: Path,
    repos: list[str] | None = None,
    errors_only: bool = False,
) -> list[LintResult]:
    """Lint all changelog YAML files in a directory.

    Args:
        changelog_dir: Root directory with per-repo subdirectories.
        repos: Optional list of repo names to filter.
        errors_only: If True, skip warnings.

    Returns:
        List of LintResult for files with issues.
    """
    results: list[LintResult] = []

    for repo_dir in sorted(changelog_dir.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue
        if repos and repo_dir.name not in repos:
            continue
        for yaml_file in sorted(repo_dir.glob("*-changelog.yaml")):
            lr = lint_file(yaml_file, errors_only=errors_only)
            if lr.errors or lr.warnings:
                results.append(lr)

    return results
