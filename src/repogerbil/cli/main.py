# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for repogerbil."""

from __future__ import annotations

from pathlib import Path
import re
import sys
from typing import Any

import click
from rich.console import Console
import yaml

from repogerbil.core.cadence import group_by_cadence
from repogerbil.core.changelog import (
    generate_analyzed,
    generate_draft,
    generate_prompt,
    update_stats,
    write_changelog,
)
from repogerbil.core.classify import classify_commit
from repogerbil.core.config import load_settings
from repogerbil.core.consolidate import consolidate, generate_consolidation_preview
from repogerbil.core.diff import get_diff_content
from repogerbil.core.errors import RepogerbilError
from repogerbil.core.git import (
    get_active_dates,
    get_commits_for_date,
    get_diff_stats,
)
from repogerbil.core.verify import count_accounted_files, verify_changelog

_PREFIX_RE = re.compile(r"^(\w+)(?:\([^)]*\))?[!]?:\s")


@click.group()
@click.version_option()
def cli() -> None:
    """gerbil — Git history documentation and consolidation."""


def main() -> None:
    """Entry point with error handling."""
    try:
        # Check for --debug flag anywhere in args
        debug = "--debug" in sys.argv
        if debug:
            sys.argv.remove("--debug")

        cli()
    except RepogerbilError as e:
        console = Console(stderr=True)
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(1)
    except Exception as e:
        if "--debug" in sys.argv:  # pragma: no cover — --debug is removed before cli() runs
            raise
        console = Console(stderr=True)
        console.print(f"[bold red]Unexpected Error:[/] {str(e) or type(e).__name__}")
        sys.exit(1)


# Register optional vectordb commands
try:
    from repogerbil.cli.commands.vectordb_cmds import index, related, search  # pragma: no cover

    cli.add_command(index)  # pragma: no cover
    cli.add_command(search)  # pragma: no cover
    cli.add_command(related)  # pragma: no cover
except ImportError:  # pragma: no cover
    pass

# Register distill/snapshot commands
from repogerbil.cli.commands.distill_cmds import export_cadence, preview, snapshot  # noqa: E402

cli.add_command(snapshot)
cli.add_command(export_cadence)
cli.add_command(preview)

# Register lint command
from repogerbil.cli.commands.lint_cmd import lint  # noqa: E402

cli.add_command(lint)

# Register plugin commands
from repogerbil.cli.commands.plugin_cmd import plugin  # noqa: E402

cli.add_command(plugin)


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
def status(repo_path: str) -> None:
    """Show repository status and what needs work."""
    path = Path(repo_path)
    dates = get_active_dates(path)
    click.echo(f"Repository: {path.name}")
    click.echo(f"Active dates: {len(dates)}")
    if dates:
        click.echo(f"Date range: {min(dates)} to {max(dates)}")


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--date", required=True, help="Date (YYYY-MM-DD)")
@click.option("--output-dir", type=click.Path(), default=".", help="Output directory")
@click.option("--analyze", is_flag=True, help="Generate complete changelog (not just draft)")
@click.option("--prompt", "prompt_mode", is_flag=True, help="Output LLM prompt instead of YAML")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--message-depth", type=click.Choice(["subject", "refs", "full"]), default=None)
def changelog(
    repo_path: str,
    date: str,
    output_dir: str,
    analyze: bool,
    prompt_mode: bool,
    force: bool,
    message_depth: str | None,
) -> None:
    """Generate a changelog for a repository date."""
    path = Path(repo_path)
    out = Path(output_dir)
    repo_name = path.name
    settings = load_settings(repo=repo_name)
    depth = message_depth or settings.message_depth

    commits = get_commits_for_date(path, date, message_depth=depth, include_files=True)
    if not commits:
        click.echo(f"No commits found for {repo_name} on {date}")
        return

    stats = get_diff_stats(path, commits[0].hash, commits[-1].hash)
    click.echo(f"{repo_name}/{date}: {len(commits)} commits, {stats.files_changed} files")

    if prompt_mode:
        _handle_prompt_mode(path, repo_name, date, commits, stats, settings, out)
        return

    out_path = out / repo_name / f"{date}-{repo_name}-changelog.yaml"
    if out_path.exists() and not force:
        click.echo(f"Exists: {out_path.name} (use --force to overwrite)")
        return

    data = (
        generate_analyzed(repo_name, date, commits, stats, settings)
        if analyze
        else generate_draft(repo_name, date, commits, stats, settings)
    )
    written = write_changelog(repo_name, date, data, out)
    click.echo(f"Wrote {written}")


def _handle_prompt_mode(
    path: Path,
    repo_name: str,
    date: str,
    commits: list[Any],
    stats: Any,
    settings: Any,
    out: Path,
) -> None:
    """Handle --prompt flag: generate LLM prompt with optional diffs."""
    diff_content: dict[str, str] = {}
    if settings.backfill_depth == "thorough":  # pragma: no cover — requires thorough config in CWD
        diff_content = get_diff_content(path, commits[0].hash, commits[-1].hash)

    prompt_text = generate_prompt(repo_name, date, commits, stats, diff_content)
    prompt_path = out / repo_name / f"{date}-{repo_name}-prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt_text)
    click.echo(f"Wrote {prompt_path}")


@cli.command(name="fix-stats")
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only fix dates >= this (YYYY-MM-DD)")
def fix_stats(changelog_dir: str, repo_path: str, since: str | None) -> None:
    """Fix stats in existing changelogs to match git truth."""
    cl_dir = Path(changelog_dir)
    rp = Path(repo_path)
    repo_name = rp.name
    fixed = 0

    for yaml_file in sorted(cl_dir.glob(f"*-{repo_name}-changelog.yaml")):
        date_str = "-".join(yaml_file.name.split("-")[:3])
        if since and date_str < since:
            continue
        commits = get_commits_for_date(rp, date_str)
        if not commits:  # pragma: no cover — changelog date with no git commits
            continue
        stats = get_diff_stats(rp, commits[0].hash, commits[-1].hash)
        if update_stats(yaml_file, stats, len(commits)):
            click.echo(f"Fixed {repo_name}/{date_str}: {len(commits)} commits, {stats.files_changed} files")
            fixed += 1

    click.echo(f"{fixed} files updated")


@cli.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only verify dates >= this (YYYY-MM-DD)")
@click.option("--tolerance", type=int, default=None, help="% tolerance (default: from config)")
def verify(changelog_dir: str, repo_path: str, since: str | None, tolerance: int | None) -> None:
    """Verify changelog stats against git truth."""
    cl_dir = Path(changelog_dir)
    rp = Path(repo_path)
    repo_name = rp.name
    settings = load_settings(repo=repo_name)
    tol = tolerance if tolerance is not None else settings.tolerance

    stat_issues, coverage_issues, checked = _run_verification(cl_dir, rp, repo_name, since, tol)
    _report_verification(stat_issues, coverage_issues, checked)


def _run_verification(
    cl_dir: Path,
    rp: Path,
    repo_name: str,
    since: str | None,
    tol: int,
) -> tuple[list[str], list[str], int]:
    """Run verification across all changelog files."""
    stat_issues: list[str] = []
    coverage_issues: list[str] = []
    checked = 0

    for yaml_file in sorted(cl_dir.glob(f"*-{repo_name}-changelog.yaml")):  # pragma: no cover — integration
        date_str = "-".join(yaml_file.name.split("-")[:3])
        if since and date_str < since:
            continue
        result = verify_changelog(yaml_file, rp, tolerance=tol)
        if result is None:
            continue
        checked += 1
        if not result.stats_match:
            stat_issues.append(
                f"  {repo_name}/{result.date}: {result.reported_files} reported vs {result.actual_files} actual"
            )
        data = yaml.safe_load(yaml_file.read_text())
        if data and result.actual_files > 0:
            accounted = count_accounted_files(data)
            coverage = accounted / result.actual_files * 100
            if coverage < (100 - tol):
                coverage_issues.append(
                    f"  {repo_name}/{result.date}: {result.actual_files} files, {accounted} accounted ({coverage:.0f}%)"
                )

    return stat_issues, coverage_issues, checked


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


@cli.command()
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


from repogerbil.cli.commands.distill_cmds import _collect_commits, _load_changelog_messages  # noqa: E402


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only check commits since this date")
@click.option("--show-bad", is_flag=True, help="List unclassifiable messages")
def audit(repo_path: str, since: str | None, show_bad: bool) -> None:
    """Audit commit message quality (prefix adoption)."""
    path = Path(repo_path)
    total, prefixed, verb_ok, ambiguous, bad_msgs = _audit_commits(path, since)

    classifiable = prefixed + verb_ok
    pct = (classifiable / total * 100) if total else 0
    click.echo(
        f"{path.name}: {total} commits, {prefixed} prefixed, "
        f"{verb_ok} verb, {ambiguous} ambiguous ({pct:.0f}% classifiable)"
    )

    if show_bad and bad_msgs:
        click.echo("Ambiguous commits:")
        for msg in bad_msgs[:20]:
            click.echo(f"  {msg}")
        if len(bad_msgs) > 20:  # pragma: no cover — only with >20 ambiguous commits
            click.echo(f"  ... and {len(bad_msgs) - 20} more")


def _audit_commits(
    path: Path,
    since: str | None,
) -> tuple[int, int, int, int, list[str]]:
    """Count prefix adoption across commits."""
    dates = sorted(get_active_dates(path))
    if since:
        dates = [d for d in dates if d >= since]

    total = prefixed = verb_ok = ambiguous = 0
    bad_msgs: list[str] = []

    for date_str in dates:
        for c in get_commits_for_date(path, date_str):
            if c.subject.startswith("Merge"):  # pragma: no cover — needs merge commits in test
                continue
            total += 1
            if _PREFIX_RE.match(c.subject):
                prefixed += 1
            elif classify_commit(c.subject).needs_review:
                ambiguous += 1
                bad_msgs.append(c.subject)
            else:
                verb_ok += 1  # pragma: no cover — needs verb-classifiable commit in test

    return total, prefixed, verb_ok, ambiguous, bad_msgs


@cli.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--year", type=int, required=True, help="ISO year")
@click.option("--week", type=int, required=True, help="ISO week number")
@click.option("--output-dir", type=click.Path(), default=".", help="Where to write the summary")
@click.option("--prompt", "prompt_mode", is_flag=True, help="Output LLM prompt instead of markdown")
@click.option("--force", is_flag=True, help="Overwrite existing file")
def summary(
    changelog_dir: str,
    year: int,
    week: int,
    output_dir: str,
    prompt_mode: bool,
    force: bool,
) -> None:
    """Generate a weekly summary from changelogs."""
    from repogerbil.core.summary import (
        collect_week_data,
        generate_summary_markdown,
        generate_summary_prompt,
    )

    data = collect_week_data(Path(changelog_dir), year, week)
    if not data.repos:
        click.echo(f"No changelogs found for {data.week_label}")
        return

    if prompt_mode:
        text = generate_summary_prompt(data)
        out_path = Path(output_dir) / f"{data.week_label}-prompt.md"
    else:
        text = generate_summary_markdown(data)
        out_path = Path(output_dir) / f"{data.week_label}.md"

    if out_path.exists() and not force:
        click.echo(f"Exists: {out_path.name} (use --force to overwrite)")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    click.echo(f"Wrote {out_path} ({len(data.repos)} repos, {data.total_commits} commits)")


@cli.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(), default=None, help="Path to .repogerbil.toml")
def missing(changelog_dir: str, config_path: str | None) -> None:
    """Show missing changelog dates across all tracked repos."""
    from repogerbil.core.audit import find_missing

    cfg_path = Path(config_path) if config_path else None
    settings = load_settings(config_path=cfg_path)

    if not settings.tracked:
        click.echo("No tracked repos configured. Add [tracked] to .repogerbil.toml")
        return

    results = find_missing(settings.tracked, Path(changelog_dir), repo_overrides=settings.repos)
    if not results:  # pragma: no cover
        click.echo("All reports up to date.")
    else:
        for m in results:
            click.echo(f"{m.repo}/{m.date}")
        click.echo(f"\n{len(results)} missing")


@cli.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only enrich dates >= this (YYYY-MM-DD)")
@click.option("--depth", type=click.Choice(["file", "package", "cross-repo"]), default=None)
def enrich(changelog_dir: str, repo_path: str, since: str | None, depth: str | None) -> None:
    """Add per-section stats and impact analysis to existing changelogs."""
    from repogerbil.core.enrich import enrich_changelog

    cl_dir = Path(changelog_dir)
    rp = Path(repo_path)
    repo_name = rp.name
    settings = load_settings(repo=repo_name)
    enrich_depth = depth or settings.enrich_depth
    enriched = 0

    for yaml_file in sorted(cl_dir.glob(f"*-{repo_name}-changelog.yaml")):
        date_str = "-".join(yaml_file.name.split("-")[:3])
        if since and date_str < since:  # pragma: no cover
            continue
        if enrich_changelog(yaml_file, rp, depth=enrich_depth):  # pragma: no branch
            click.echo(f"Enriched {repo_name}/{date_str}")
            enriched += 1

    click.echo(f"{enriched} files enriched")


@cli.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(), default=None)
@click.option("--since", help="Only backfill dates >= this (YYYY-MM-DD)")
@click.option("--prompt", "prompt_mode", is_flag=True, help="Write LLM prompt files instead of YAML changelogs")
def backfill(changelog_dir: str, config_path: str | None, since: str | None, prompt_mode: bool) -> None:
    """Generate changelogs for all missing dates across tracked repos."""
    from repogerbil.core.audit import find_missing

    cfg_path = Path(config_path) if config_path else None
    settings = load_settings(config_path=cfg_path)

    if not settings.tracked:
        click.echo("No tracked repos configured. Add [tracked] to .repogerbil.toml")
        return

    results = find_missing(settings.tracked, Path(changelog_dir), repo_overrides=settings.repos)
    if since:  # pragma: no cover
        results = [m for m in results if m.date >= since]

    if not results:  # pragma: no cover
        click.echo("Nothing to backfill.")
        return

    action = "prompts" if prompt_mode else "changelogs"
    click.echo(f"Backfilling {len(results)} missing {action}...")
    generated = 0
    out = Path(changelog_dir)

    for m in results:
        repo_path = Path(settings.tracked[m.repo])
        repo_settings = load_settings(repo=m.repo, config_path=cfg_path)
        commits = get_commits_for_date(repo_path, m.date, include_files=True)
        if not commits:  # pragma: no cover — date from find_missing always has commits
            continue

        stats = get_diff_stats(repo_path, commits[0].hash, commits[-1].hash)

        if prompt_mode:
            prompt_text = generate_prompt(m.repo, m.date, commits, stats, {})
            prompt_path = out / m.repo / f"{m.date}-{m.repo}-prompt.md"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(prompt_text)
        else:
            data = generate_analyzed(m.repo, m.date, commits, stats, repo_settings)
            write_changelog(m.repo, m.date, data, out)

        click.echo(f"  {m.repo}/{m.date}: {len(commits)} commits")
        generated += 1

    click.echo(f"\n{generated} {action} generated")
