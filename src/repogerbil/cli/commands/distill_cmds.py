# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for snapshot/distill operations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click
import yaml

from repogerbil.core.cadence import group_by_cadence, groups_to_json
from repogerbil.core.config import load_settings
from repogerbil.core.consolidate import generate_consolidation_preview
from repogerbil.core.git import get_active_dates, get_commits_for_date


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.argument("dest_path", type=click.Path())
@click.option("--cadence", type=click.Choice(["hourly", "daily", "weekly"]), default=None)
@click.option("--since", help="Only include dates >= this (YYYY-MM-DD)")
@click.option("--source-branch", default="main", help="Source branch to read from")
@click.option(
    "--changelog-dir", type=click.Path(), default=None, help="Dir with changelog YAML for commit messages"
)
def snapshot(
    repo_path: str,
    dest_path: str,
    cadence: str | None,
    since: str | None,
    source_branch: str,
    changelog_dir: str | None,
) -> None:
    """Create a new repo with distilled daily commits (read-tree based)."""
    from repogerbil.core.snapshot import create_snapshot

    path = Path(repo_path)
    dest = Path(dest_path)
    settings = load_settings(repo=path.name)
    cad = cadence or settings.cadence

    all_commits = _collect_commits(path, since)
    if not all_commits:
        click.echo("No commits found")
        return

    groups = group_by_cadence(all_commits, cad)
    click.echo(f"{len(all_commits)} commits → {len(groups)} {cad} groups")

    changelog_messages = _load_changelog_messages(changelog_dir, path.name) if changelog_dir else None

    result = create_snapshot(
        source_path=path,
        dest_path=dest,
        groups=groups,
        source_branch=source_branch,
        changelog_messages=changelog_messages,
        preserve_timestamps=settings.preserve_timestamps,
    )
    click.echo(f"Snapshot created at {result.dest_path} ({result.commits_created} commits)")


@click.command(name="export-cadence")
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--cadence", type=click.Choice(["hourly", "daily", "weekly"]), default=None)
@click.option("--since", help="Only include dates >= this")
@click.option("--output", "-o", type=click.Path(), default=None, help="Output file (default: stdout)")
def export_cadence(
    repo_path: str,
    cadence: str | None,
    since: str | None,
    output: str | None,
) -> None:
    """Export cadence-grouped commits as JSON."""
    path = Path(repo_path)
    settings = load_settings(repo=path.name)
    cad = cadence or settings.cadence

    all_commits = _collect_commits(path, since)
    if not all_commits:
        click.echo("No commits found")
        return

    groups = group_by_cadence(all_commits, cad)
    json_str = groups_to_json(groups, cad)

    if output:
        Path(output).write_text(json_str)
        click.echo(f"Exported {len(groups)} groups to {output}")
    else:
        click.echo(json_str)


@click.command(name="preview")
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--cadence", type=click.Choice(["hourly", "daily", "weekly"]), default=None)
@click.option("--since", help="Only include dates >= this")
def preview(
    repo_path: str,
    cadence: str | None,
    since: str | None,
) -> None:
    """Rich preview of what distillation would produce."""
    path = Path(repo_path)
    settings = load_settings(repo=path.name)
    cad = cadence or settings.cadence

    all_commits = _collect_commits(path, since)
    if not all_commits:
        click.echo("No commits found")
        return

    groups = group_by_cadence(all_commits, cad)
    previews = generate_consolidation_preview(groups)

    total_commits = sum(p["commit_count"] for p in previews)
    click.echo(f"\n  {total_commits} commits → {len(previews)} {cad} groups\n")
    click.echo(f"  {'Date':<12} {'Commits':>8} {'Files':>8}  Subjects")
    click.echo(f"  {'─' * 12} {'─' * 8} {'─' * 8}  {'─' * 40}")

    for p in previews:
        subjects = p["subjects"]
        first = subjects[0][:40] if subjects else ""
        click.echo(f"  {p['date']:<12} {p['commit_count']:>8} {p['files_affected']:>8}  {first}")
        for s in subjects[1:3]:
            click.echo(f"  {'':12} {'':8} {'':8}  {s[:40]}")
        if len(subjects) > 3:
            click.echo(f"  {'':12} {'':8} {'':8}  ... and {len(subjects) - 3} more")

    click.echo(f"\n  Total: {total_commits} commits → {len(previews)} daily commits")


def _collect_commits(path: Path, since: str | None) -> list[Any]:
    """Collect all commits, optionally filtered by date."""
    dates = sorted(get_active_dates(path))
    if since:
        dates = [d for d in dates if d >= since]
    all_commits: list[Any] = []
    for date_str in dates:
        all_commits.extend(get_commits_for_date(path, date_str, include_files=True))
    return all_commits


def _load_changelog_messages(changelog_dir: str, repo_name: str) -> dict[str, str]:
    """Load changelog titles+summaries as commit messages."""
    messages: dict[str, str] = {}
    cl_path = Path(changelog_dir)
    for yaml_file in cl_path.glob(f"*-{repo_name}-changelog.yaml"):
        data = yaml.safe_load(yaml_file.read_text())
        if isinstance(data, dict) and data.get("date") and data.get("title"):  # pragma: no branch
            date_key = str(data["date"])[:10]
            messages[date_key] = f"{data['title']}\n\n{data.get('summary', '')}"
    return messages
