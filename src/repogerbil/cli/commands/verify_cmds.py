# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for changelog verification."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from repogerbil.core.config import load_settings
from repogerbil.core.provenance import resolve_provenance
from repogerbil.core.verify import _within_tolerance, count_accounted_files


@click.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only verify dates >= this (YYYY-MM-DD)")
@click.option("--tolerance", type=int, default=None, help="% tolerance (default: from config)")
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos or worktrees to probe",
)
def verify(
    changelog_dir: str,
    repo_path: str,
    since: str | None,
    tolerance: int | None,
    extra_sources: tuple[str, ...],
) -> None:
    """Verify changelog stats against git truth."""
    cl_dir = Path(changelog_dir)
    rp = Path(repo_path)
    repo_name = rp.name
    settings = load_settings(repo=repo_name)
    tol = tolerance if tolerance is not None else settings.tolerance
    extra_paths = [Path(p) for p in extra_sources]

    stat_issues, coverage_issues, checked = _run_verification(cl_dir, rp, repo_name, since, tol, extra_paths)
    _report_verification(stat_issues, coverage_issues, checked)


def _run_verification(
    cl_dir: Path,
    rp: Path,
    repo_name: str,
    since: str | None,
    tol: int,
    extra_sources: list[Path] | None = None,
) -> tuple[list[str], list[str], int]:
    """Run verification across all changelog files."""
    stat_issues: list[str] = []
    coverage_issues: list[str] = []
    checked = 0

    for yaml_file in sorted(cl_dir.glob(f"*-{repo_name}-changelog.yaml")):  # pragma: no cover — integration
        date_str = "-".join(yaml_file.name.split("-")[:3])
        if since and date_str < since:
            continue
        resolution = resolve_provenance(
            repo_name,
            date_str,
            rp,
            extra_sources=extra_sources or [],
            include_files=True,
        )
        if not resolution.commits:
            continue
        checked += 1
        stats = resolution.stats
        if stats is None:
            continue
        data = yaml.safe_load(yaml_file.read_text())
        if data is None:
            continue
        actual_files = stats.files_changed
        mismatches = _collect_stat_mismatches(data, actual_files, stats.insertions, stats.deletions, tol)
        if mismatches:
            stat_issues.append(f"  {repo_name}/{date_str}: " + ", ".join(mismatches))
        if data and actual_files > 0:
            accounted = count_accounted_files(data)
            coverage = accounted / actual_files * 100
            if coverage < (100 - tol):
                coverage_issues.append(
                    f"  {repo_name}/{date_str}: {actual_files} files, {accounted} accounted ({coverage:.0f}%)"
                )

    return stat_issues, coverage_issues, checked


def _collect_stat_mismatches(
    data: dict[object, object],
    actual_files: int,
    actual_insertions: int,
    actual_deletions: int,
    tolerance: int,
) -> list[str]:
    stats_map = data.get("stats") if isinstance(data, dict) else {}
    if not isinstance(stats_map, dict):
        stats_map = {}

    reported_files = int(stats_map.get("files_changed", 0))
    reported_insertions = int(stats_map.get("insertions", 0))
    reported_deletions = int(stats_map.get("deletions", 0))

    mismatches: list[str] = []
    if not _within_tolerance(reported_files, actual_files, tolerance):
        mismatches.append(f"files {reported_files} vs {actual_files}")
    if not _within_tolerance(reported_insertions, actual_insertions, tolerance):
        mismatches.append(f"insertions {reported_insertions} vs {actual_insertions}")
    if not _within_tolerance(reported_deletions, actual_deletions, tolerance):
        mismatches.append(f"deletions {reported_deletions} vs {actual_deletions}")
    return mismatches


def _report_verification(
    stat_issues: list[str], coverage_issues: list[str], checked: int
) -> None:  # pragma: no cover
    """Report verification results."""
    if stat_issues:
        click.echo("Stats mismatches:")
        for line in stat_issues:
            click.echo(line)
    if coverage_issues:
        click.echo("Coverage gaps:")
        for line in coverage_issues:
            click.echo(line)
    if not stat_issues and not coverage_issues:
        click.echo(f"All good ({checked} checked)")
    else:
        click.echo(f"{len(stat_issues)} stat issues, {len(coverage_issues)} coverage gaps ({checked} checked)")
