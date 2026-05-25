# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Ecosystem-level distillation CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from repogerbil.core.cadence import group_by_cadence
from repogerbil.core.config import load_settings
from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import resolve_head_branch

from ._helpers import _collect_commits, _find_source_repo, _load_changelog_messages

if TYPE_CHECKING:
    from repogerbil.core.ecosystem_snapshot import EcosystemTarget


def _build_ecosystem_targets(
    repo_names: list[str],
    source_base_path: Path,
    report_base_path: Path,
    dest_base_path: Path,
    all_branches: bool,
    settings: Any,
) -> list[EcosystemTarget]:
    """Build ecosystem targets from repo names, logging warnings for missing/empty repos."""
    from repogerbil.core.ecosystem_snapshot import EcosystemTarget

    ecosystem_targets: list[EcosystemTarget] = []
    for name in repo_names:
        source_path = _find_source_repo(name, source_base_path)
        if not source_path:
            click.echo(f"⚠ {name:35s} source not found")
            continue

        # Collect commits from source (same as snapshot command)
        try:
            branch = None if all_branches else resolve_head_branch(source_path)
        except GitCommandError:
            click.echo(f"⚠ {name:35s} unable to resolve HEAD branch")
            continue
        all_commits = _collect_commits(source_path, since=None, branch=branch)
        if not all_commits:
            click.echo(f"⚠ {name:35s} no commits found")
            continue

        all_commits.sort(key=lambda c: (c.timestamp, c.hash))
        groups = group_by_cadence(all_commits, settings.cadence or "daily")

        # Load changelog messages
        changelog_dir = report_base_path / name
        changelog_messages = _load_changelog_messages(str(changelog_dir), name, vocabulary=settings.vocabulary)

        ecosystem_targets.append(
            EcosystemTarget(
                name=name,
                source_path=source_path,
                dest_path=dest_base_path / name,
                groups=groups,
                changelog_messages=changelog_messages,
                source_branch=branch or "",
            )
        )

    return ecosystem_targets


def _discover_repo_names(
    targets: str | None,
    report_base_path: Path,
    min_changelogs: int,
) -> list[str]:
    """Return explicit target names or discover repos from changelog directories."""
    if targets:
        return [name.strip() for name in targets.split(",")]

    repo_names: list[str] = []
    for repo_dir in sorted(report_base_path.iterdir()):
        if not repo_dir.is_dir():
            continue
        changelog_count = len(list(repo_dir.glob("*-changelog.yaml")))
        if changelog_count >= min_changelogs:
            repo_names.append(repo_dir.name)
    return repo_names


def _print_ecosystem_results(results: list[Any]) -> None:
    """Print distill-ecosystem result summary."""
    click.echo("\nResults:")
    for result in results:
        _print_ecosystem_result(result)

    click.echo(_ecosystem_summary(results))


def _print_ecosystem_result(result: Any) -> None:
    """Print one ecosystem result line."""
    if not result.success:
        click.echo(f"  ✗ {result.name:35s} {result.error}")
        return

    pct = (result.prefixed * 100) // result.commits_created if result.commits_created > 0 else 0
    click.echo(
        f"  ✓ {result.name:35s} {result.commits_created:4d} commits  {result.prefixed:4d}/{result.commits_created} ({pct:3d}%)"
    )


def _ecosystem_summary(results: list[Any]) -> str:
    """Return the aggregate ecosystem result summary."""
    successes = sum(1 for r in results if r.success)
    total_commits = sum(r.commits_created for r in results if r.success)
    total_prefixed = sum(r.prefixed for r in results if r.success)
    return f"\n{successes}/{len(results)} repos distilled — {total_prefixed}/{total_commits} commits prefixed"


@click.command(name="distill-ecosystem")
@click.option(
    "--source-base", type=click.Path(exists=True), required=True, help="Root dir where source repos live"
)
@click.option(
    "--report-base", type=click.Path(exists=True), required=True, help="Dir with {repo}/ changelog subdirs"
)
@click.option("--dest-base", type=click.Path(), required=True, help="Dir where snapshot repos are created")
@click.option(
    "--targets",
    default=None,
    help="Comma-separated repo names to distill (omit to auto-discover by --min-changelogs)",
)
@click.option("--min-changelogs", type=int, default=1, help="Skip repos with fewer changelogs than this")
@click.option("--parallel", type=int, default=4, help="Max concurrent workers")
@click.option("--commit-time", default="20:00", help="Override commit time (HH:MM)")
@click.option("--timezone", default="America/Los_Angeles", help="IANA timezone for timestamps")
@click.option("--all-branches", is_flag=True, help="Include commits from all branches")
@click.option("--dry-run", is_flag=True, help="Print plan, skip git work")
def distill_ecosystem(
    source_base: str,
    report_base: str,
    dest_base: str,
    targets: str | None,
    min_changelogs: int,
    parallel: int,
    commit_time: str,
    timezone: str,
    all_branches: bool,
    dry_run: bool,
) -> None:
    """Distill multiple repos in parallel with conventional commit prefixes."""
    from repogerbil.core.ecosystem_snapshot import run_ecosystem_snapshot

    source_base_path = Path(source_base)
    report_base_path = Path(report_base)
    dest_base_path = Path(dest_base)
    settings = load_settings()

    repo_names = _discover_repo_names(targets, report_base_path, min_changelogs)
    if not repo_names:
        click.echo("No repos found matching criteria")
        return

    # Build targets
    ecosystem_targets = _build_ecosystem_targets(
        repo_names, source_base_path, report_base_path, dest_base_path, all_branches, settings
    )

    if not ecosystem_targets:
        click.echo("No valid targets to distill")
        return

    click.echo(f"\ndistill-ecosystem: {len(ecosystem_targets)} targets ({parallel} workers)")
    if dry_run:
        click.echo("\n[DRY RUN] Target repos:")
        for target in ecosystem_targets:
            click.echo(f"  - {target.name}")
        return

    # Run in parallel
    results = run_ecosystem_snapshot(
        ecosystem_targets, parallel=parallel, commit_time=commit_time, timezone=timezone
    )

    _print_ecosystem_results(results)
