# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command for commit distillation (consolidation).

.. warning::
    ``gerbil distill`` is the **destructive** distillation path — it mutates the
    *source* repository (creates backup + target branches and tags on it). For a
    read-only workflow that emits a fresh destination repo instead, use
    ``gerbil snapshot`` / ``gerbil multi-snapshot``. See
    :mod:`repogerbil.core.consolidate` for the underlying contract.
"""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.cadence import group_by_cadence
from repogerbil.core.config import load_settings
from repogerbil.core.consolidate import consolidate, generate_consolidation_preview
from repogerbil.core.git import resolve_head_branch


def _warn_source_write(path: Path, confirm_source_write: bool) -> None:
    if confirm_source_write:
        return
    click.echo(
        "WARNING: `gerbil distill` writes to the SOURCE repository "
        f"({path}) — creating backup/target branches and tags on it. "
        "Pass --confirm-source-write to suppress this warning, or use "
        "`gerbil snapshot` for a read-only workflow.",
        err=True,
    )


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--cadence", type=click.Choice(["hourly", "daily", "weekly"]), default=None)
@click.option("--since", help="Only distill dates >= this (YYYY-MM-DD)")
@click.option(
    "--source-branch", default=None, help="Source branch to read from (default: current HEAD branch)"
)
@click.option("--target-branch", default=None, help="Target branch name")
@click.option("--dry-run", is_flag=True, help="Preview only")
@click.option(
    "--changelog-dir", type=click.Path(), default=None, help="Dir with changelog YAML for commit messages"
)
@click.option(
    "--confirm-source-write",
    is_flag=True,
    default=False,
    help=(
        "Acknowledge that distill writes to the SOURCE repository "
        "(creates backup/target branches and tags on it). Suppresses the "
        "destructive-operation warning. Prefer `gerbil snapshot` for "
        "read-only distillation."
    ),
)
def distill(
    repo_path: str,
    cadence: str | None,
    since: str | None,
    source_branch: str | None,
    target_branch: str | None,
    dry_run: bool,
    changelog_dir: str | None,
    confirm_source_write: bool,
) -> None:
    """Distill commits into daily/weekly consolidated commits.

    WARNING: this command WRITES TO THE SOURCE repository (creates branches
    and tags on it). For read-only distillation that emits a fresh destination
    repository instead, use `gerbil snapshot` / `gerbil multi-snapshot`.
    """
    from repogerbil.cli.commands.distill_cmds._helpers import _collect_commits, _load_changelog_messages

    path = Path(repo_path)
    settings = load_settings(repo=path.name)
    cad = cadence or settings.cadence
    branch = target_branch or settings.target_branch
    source = source_branch or resolve_head_branch(path)

    all_commits = _collect_commits(path, since, branch=source)
    if not all_commits:
        click.echo("No commits found")
        return

    groups = group_by_cadence(all_commits, cad)
    click.echo(f"{len(all_commits)} commits → {len(groups)} {cad} groups")

    changelog_messages = (
        _load_changelog_messages(changelog_dir, path.name, vocabulary=settings.vocabulary)
        if changelog_dir
        else None
    )

    if dry_run:
        for p in generate_consolidation_preview(groups):
            click.echo(f"  {p['date']}: {p['commit_count']} commits, {p['files_affected']} files")
        return

    _warn_source_write(path, confirm_source_write)

    result = consolidate(
        path,
        groups,
        target_branch=branch,
        source_branch=source,
        changelog_messages=changelog_messages,
        preserve_timestamps=settings.preserve_timestamps,
        create_backup=settings.create_backup,
    )
    click.echo(f"Consolidated to {result.target_branch}")
    if result.backup_branch:
        click.echo(f"Backup: {result.backup_branch}")
    if result.backup_tag:
        click.echo(f"Tag: {result.backup_tag}")
