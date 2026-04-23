# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Ecosystem-level distillation CLI command."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from repogerbil.core.cadence import group_by_cadence
from repogerbil.core.config import load_settings

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
        branch = None if all_branches else "main"
        all_commits = _collect_commits(source_path, since=None, branch=branch)
        if not all_commits:
            click.echo(f"⚠ {name:35s} no commits found")
            continue

        all_commits.sort(key=lambda c: c.date)
        groups = group_by_cadence(all_commits, settings.cadence or "daily")

        # Load changelog messages
        changelog_dir = report_base_path / name
        changelog_messages = _load_changelog_messages(str(changelog_dir), name)

        ecosystem_targets.append(
            EcosystemTarget(
                name=name,
                source_path=source_path,
                dest_path=dest_base_path / name,
                groups=groups,
                changelog_messages=changelog_messages,
                source_branch="main",
            )
        )

    return ecosystem_targets


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
def distill_ecosystem(  # noqa: C901 — orchestrates discovery, building, and execution
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

    # Discover repos or parse explicit targets
    if targets:
        repo_names = [name.strip() for name in targets.split(",")]
    else:
        # Auto-discover by min_changelogs threshold
        repo_names = []
        for repo_dir in sorted(report_base_path.iterdir()):
            if not repo_dir.is_dir():
                continue
            changelog_count = len(list(repo_dir.glob("*-changelog.yaml")))
            if changelog_count >= min_changelogs:
                repo_names.append(repo_dir.name)

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

    click.echo("\nResults:")
    for result in results:
        if result.success:
            pct = (result.prefixed * 100) // result.commits_created if result.commits_created > 0 else 0
            click.echo(
                f"  ✓ {result.name:35s} {result.commits_created:4d} commits  {result.prefixed:4d}/{result.commits_created} ({pct:3d}%)"
            )
        else:
            click.echo(f"  ✗ {result.name:35s} {result.error}")

    successes = sum(1 for r in results if r.success)
    total_commits = sum(r.commits_created for r in results if r.success)
    total_prefixed = sum(r.prefixed for r in results if r.success)
    click.echo(
        f"\n{successes}/{len(results)} repos distilled — {total_prefixed}/{total_commits} commits prefixed"
    )
