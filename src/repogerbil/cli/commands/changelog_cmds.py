# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for changelog status and fix-stats operations."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.changelog import update_stats
from repogerbil.core.git import get_active_dates, get_diff_stats
from repogerbil.core.provenance import resolve_provenance


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
def status(repo_path: str) -> None:
    """Show repository status and what needs work."""
    path = Path(repo_path)
    dates = get_active_dates(path)
    click.echo(f"Repository: {path.name}")
    click.echo(f"Active dates: {len(dates)}")
    if dates:
        click.echo(f"Date range: {min(dates)} to {max(dates)}")


@click.command(name="fix-stats")
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only fix dates >= this (YYYY-MM-DD)")
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos or worktrees to probe",
)
def fix_stats(changelog_dir: str, repo_path: str, since: str | None, extra_sources: tuple[str, ...]) -> None:
    """Fix stats in existing changelogs to match git truth."""
    cl_dir = Path(changelog_dir)
    rp = Path(repo_path)
    repo_name = rp.name
    extra_paths = [Path(p) for p in extra_sources]
    fixed = 0

    for yaml_file in sorted(cl_dir.glob(f"*-{repo_name}-changelog.yaml")):
        date_str = "-".join(yaml_file.name.split("-")[:3])
        if since and date_str < since:
            continue
        resolution = resolve_provenance(
            repo_name,
            date_str,
            rp,
            extra_sources=extra_paths,
            include_files=False,
        )
        commits = resolution.commits
        if not commits:  # pragma: no cover — changelog date with no git commits
            continue
        stats = resolution.stats or get_diff_stats(rp, commits[0].hash, commits[-1].hash)
        if update_stats(yaml_file, stats, len(commits)):
            click.echo(f"Fixed {repo_name}/{date_str}: {len(commits)} commits, {stats.files_changed} files")
            fixed += 1

    click.echo(f"{fixed} files updated")
