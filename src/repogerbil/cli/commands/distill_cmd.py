# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command for commit distillation (consolidation)."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.cadence import group_by_cadence
from repogerbil.core.config import load_settings
from repogerbil.core.consolidate import consolidate, generate_consolidation_preview


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--cadence", type=click.Choice(["hourly", "daily", "weekly"]), default=None)
@click.option("--since", help="Only distill dates >= this (YYYY-MM-DD)")
@click.option("--target-branch", default=None, help="Target branch name")
@click.option("--dry-run", is_flag=True, help="Preview only")
@click.option(
    "--changelog-dir", type=click.Path(), default=None, help="Dir with changelog YAML for commit messages"
)
def distill(
    repo_path: str,
    cadence: str | None,
    since: str | None,
    target_branch: str | None,
    dry_run: bool,
    changelog_dir: str | None,
) -> None:
    """Distill commits into daily/weekly consolidated commits."""
    from repogerbil.cli.commands.distill_cmds import _collect_commits, _load_changelog_messages

    path = Path(repo_path)
    settings = load_settings(repo=path.name)
    cad = cadence or settings.cadence
    branch = target_branch or settings.target_branch

    all_commits = _collect_commits(path, since)
    if not all_commits:
        click.echo("No commits found")
        return

    groups = group_by_cadence(all_commits, cad)
    click.echo(f"{len(all_commits)} commits → {len(groups)} {cad} groups")

    changelog_messages = _load_changelog_messages(changelog_dir, path.name) if changelog_dir else None

    if dry_run:
        for p in generate_consolidation_preview(groups):
            click.echo(f"  {p['date']}: {p['commit_count']} commits, {p['files_affected']} files")
        return

    result = consolidate(
        path,
        groups,
        target_branch=branch,
        changelog_messages=changelog_messages,
        preserve_timestamps=settings.preserve_timestamps,
        create_backup=settings.create_backup,
    )
    click.echo(f"Consolidated to {result.target_branch}")
    if result.backup_branch:  # pragma: no branch — backup always on unless configured off
        click.echo(f"Backup: {result.backup_branch}")
    if result.backup_tag:  # pragma: no branch — tag always on unless configured off
        click.echo(f"Tag: {result.backup_tag}")
