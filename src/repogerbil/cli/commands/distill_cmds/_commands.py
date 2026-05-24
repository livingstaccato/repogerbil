# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Core snapshot/distill CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import click

from repogerbil.core.cadence import group_by_cadence, groups_to_json
from repogerbil.core.config import load_settings
from repogerbil.core.consolidate import generate_consolidation_preview
from repogerbil.core.git import get_commits_for_path

from ._helpers import _collect_commits, _load_changelog_messages


def _validate_snapshot_timing(
    commit_time: str | None,
    time_window_start: str | None,
    time_window_end: str | None,
) -> None:
    """Validate mutually exclusive snapshot timestamp options."""
    if commit_time and (time_window_start or time_window_end):
        raise click.UsageError(
            "--commit-time and --time-window-start/--time-window-end are mutually exclusive"
        )
    if (time_window_start is None) != (time_window_end is None):
        raise click.UsageError("--time-window-start and --time-window-end must both be provided")


def _collect_snapshot_commits(
    path: Path,
    since: str | None,
    source_branch: str,
    extra_sources: tuple[str, ...],
    all_branches: bool,
    source_subdir: str | None,
) -> list[Any]:
    """Collect and sort commits for the snapshot command."""
    if source_subdir:
        all_commits = (
            get_commits_for_path(  # pragma: no cover — integration test needed for monorepo extraction
                path, source_subdir, all_branches=all_branches
            )
        )
    else:
        branch = None if all_branches else source_branch
        all_commits = _collect_commits(path, since, branch=branch)

    for extra in extra_sources:
        all_commits.extend(_collect_commits(Path(extra), since))
    all_commits.sort(key=lambda c: c.date)
    return all_commits


def _build_llm_generator(settings: Any) -> Any:
    """Create the configured Ollama-backed message generator."""
    from repogerbil.llm.client import HTTPOllamaClient
    from repogerbil.llm.generator import MessageGenerator

    client = HTTPOllamaClient(base_url=settings.llm_ollama_url)
    return MessageGenerator(
        client=client,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )


def _parse_repo_specs(repos: tuple[str, ...]) -> dict[str, Path]:
    """Parse NAME:PATH CLI pairs for multi-snapshot."""
    source_repos: dict[str, Path] = {}
    for repo_spec in repos:
        if ":" not in repo_spec:
            click.echo(f"Error: --repo must be NAME:PATH format, got: {repo_spec}", err=True)
            raise SystemExit(1)
        name, path_str = repo_spec.split(":", 1)
        source_repos[name] = Path(path_str)

    if not source_repos:
        click.echo("Error: at least one --repo is required", err=True)
        raise SystemExit(1)

    return source_repos


def _filter_since_dates(active_dates: list[Any], since_date: Any) -> list[Any]:
    """Apply the optional since date filter."""
    if since_date:
        return [d for d in active_dates if d >= since_date]
    return active_dates


def _print_date_preview(active_dates: list[Any], repo_count: int) -> None:
    """Print the first few active dates for a dry run."""
    click.echo(f"Would create {len(active_dates)} daily commits from {repo_count} repos")
    for d in active_dates[:10]:
        click.echo(f"  {d.isoformat()}")
    if len(active_dates) > 10:
        click.echo(f"  ... and {len(active_dates) - 10} more")


def _preview_multi_snapshot(source_repos: dict[str, Path], since_date: Any) -> None:
    """Print a dry-run preview for multi-snapshot."""
    from repogerbil.core.multi_snapshot import _collect_all_active_dates

    active_dates = _filter_since_dates(_collect_all_active_dates(source_repos), since_date)
    _print_date_preview(active_dates, len(source_repos))


def _print_snapshot_result(result: Any) -> None:
    """Print snapshot completion details."""
    dedup_msg = f" ({result.groups_skipped} duplicate tree states removed)" if result.groups_skipped else ""
    click.echo(f"Snapshot created at {result.dest_path} ({result.commits_created} commits){dedup_msg}")


def _print_preview_row(preview_data: dict[str, Any]) -> None:
    """Print one preview table row plus truncated subject details."""
    subjects = preview_data["subjects"]
    first = subjects[0][:40] if subjects else ""
    click.echo(
        f"  {preview_data['date']:<12} {preview_data['commit_count']:>8} {preview_data['files_affected']:>8}  {first}"
    )
    for subject in subjects[1:3]:
        click.echo(f"  {'':12} {'':8} {'':8}  {subject[:40]}")
    if len(subjects) > 3:
        click.echo(f"  {'':12} {'':8} {'':8}  ... and {len(subjects) - 3} more")


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.argument("dest_path", type=click.Path())
@click.option(
    "--cadence",
    default=None,
    help="Grouping cadence: hourly, daily, weekly, or gap:NNm/gap:NNh (e.g., gap:30m)",
)
@click.option("--since", help="Only include dates >= this (YYYY-MM-DD)")
@click.option("--source-branch", default="main", help="Source branch to read from")
@click.option(
    "--changelog-dir", type=click.Path(), default=None, help="Dir with changelog YAML for commit messages"
)
@click.option("--commit-time", default=None, help="Override commit time (HH:MM, e.g. 20:00)")
@click.option("--timezone", default=None, help="IANA timezone for --commit-time (e.g. America/Los_Angeles)")
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos for multi-era history (repeatable)",
)
@click.option("--all-branches", is_flag=True, help="Include commits from all branches, not just source-branch")
@click.option(
    "--source-subdir",
    default=None,
    help="For monorepo sources: subdirectory to extract and use its tree state",
)
@click.option("--llm-refine", is_flag=True, help="Use Ollama LLM to generate narrative commit messages")
@click.option(
    "--exclude-path",
    "exclude_paths",
    multiple=True,
    help=(
        "Regex pattern to strip matching paths from every committed tree (repeatable). "
        "Uses re.search so the pattern matches anywhere in the file path unless anchored. "
        "E.g. --exclude-path '^\\.claude(/|$)' or --exclude-path '.*\\.lock$'"
    ),
)
@click.option(
    "--time-window-start",
    default=None,
    help="Start of daily commit window as HH:MM (use with --timezone and --time-window-end)",
)
@click.option(
    "--time-window-end",
    default=None,
    help="End of daily commit window as HH:MM. Supports midnight-crossing windows.",
)
def snapshot(
    repo_path: str,
    dest_path: str,
    cadence: str | None,
    since: str | None,
    source_branch: str,
    changelog_dir: str | None,
    commit_time: str | None,
    timezone: str | None,
    extra_sources: tuple[str, ...] = (),
    all_branches: bool = False,
    source_subdir: str | None = None,
    llm_refine: bool = False,
    exclude_paths: tuple[str, ...] = (),
    time_window_start: str | None = None,
    time_window_end: str | None = None,
) -> None:
    """Create a new repo with distilled daily commits (read-tree based)."""
    from repogerbil.core.snapshot import create_snapshot

    _validate_snapshot_timing(commit_time, time_window_start, time_window_end)
    path = Path(repo_path)
    dest = Path(dest_path)
    settings = load_settings(repo=path.name)
    cad = cadence or settings.cadence

    all_commits = _collect_snapshot_commits(
        path, since, source_branch, extra_sources, all_branches, source_subdir
    )
    if not all_commits:
        click.echo("No commits found")
        return

    groups = group_by_cadence(all_commits, cad)
    click.echo(f"{len(all_commits)} commits → {len(groups)} {cad} groups")

    changelog_messages = _load_changelog_messages(changelog_dir, path.name) if changelog_dir else None

    llm_generator = _build_llm_generator(settings) if llm_refine else None

    result = create_snapshot(
        source_path=path,
        dest_path=dest,
        groups=groups,
        source_branch=source_branch,
        progress=True,
        changelog_messages=changelog_messages,
        preserve_timestamps=settings.preserve_timestamps,
        commit_time=commit_time,
        timezone=timezone,
        extra_sources=[Path(e) for e in extra_sources],
        source_subdir=source_subdir,
        llm_generator=llm_generator,
        exclude_paths=list(exclude_paths) or None,
        time_window_start=time_window_start,
        time_window_end=time_window_end,
    )
    _print_snapshot_result(result)


@click.command(name="multi-snapshot")
@click.argument("dest_path", type=click.Path())
@click.option("--repo", "repos", multiple=True, help="NAME:PATH pairs (repeatable)")
@click.option("--commit-time", default="20:00", help="Time for daily commits (HH:MM)")
@click.option("--timezone", default="America/Los_Angeles", help="IANA timezone for timestamps")
@click.option("--since", help="Only include dates >= this (YYYY-MM-DD)")
@click.option(
    "--changelog-dir", type=click.Path(), default=None, help="Dir with changelog YAML for commit messages"
)
@click.option("--dry-run", is_flag=True, help="Preview only, no git changes")
@click.option("--llm-refine", is_flag=True, default=False, help="Refine commit messages with local Ollama LLM")
@click.option(
    "--exclude-path",
    "exclude_paths",
    multiple=True,
    help="Regex patterns to strip from every committed tree (repeatable)",
)
def multi_snapshot(
    dest_path: str,
    repos: tuple[str, ...],
    commit_time: str,
    timezone: str,
    since: str | None,
    changelog_dir: str | None,
    dry_run: bool,
    llm_refine: bool,
    exclude_paths: tuple[str, ...],
) -> None:
    """Create a new repo merging multiple source repos into daily commits."""
    from datetime import date as date_type

    from repogerbil.core.multi_snapshot import create_multi_snapshot

    source_repos = _parse_repo_specs(repos)
    since_date = date_type.fromisoformat(since) if since else None
    cl_dir = Path(changelog_dir) if changelog_dir else None
    settings = load_settings()

    if dry_run:
        _preview_multi_snapshot(source_repos, since_date)
        return

    llm_generator = _build_llm_generator(settings) if llm_refine else None

    result = create_multi_snapshot(
        source_repos=source_repos,
        dest_path=Path(dest_path),
        since=since_date,
        commit_time=commit_time,
        timezone=timezone,
        changelog_dir=cl_dir,
        exclude_paths=list(exclude_paths) or None,
        llm_generator=llm_generator,
    )
    click.echo(
        f"Multi-snapshot created at {result.dest_path} "
        f"({result.commits_created} commits, {len(result.repos_included)} repos)"
    )


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
        _print_preview_row(p)

    click.echo(f"\n  Total: {total_commits} commits → {len(previews)} daily commits")
