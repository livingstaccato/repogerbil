# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for backfill and probe operations."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.changelog import generate_analyzed, generate_prompt, write_changelog
from repogerbil.core.config import load_settings
from repogerbil.core.git import get_diff_stats
from repogerbil.core.provenance import describe_resolution, resolve_provenance


@click.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(), default=None)
@click.option("--since", help="Only backfill dates >= this (YYYY-MM-DD)")
@click.option(
    "--prompt", "prompt_mode", is_flag=True, help="Write LLM prompt files instead of YAML changelogs"
)
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos or worktrees to probe",
)
def backfill(
    changelog_dir: str,
    config_path: str | None,
    since: str | None,
    prompt_mode: bool,
    extra_sources: tuple[str, ...],
) -> None:
    """Generate changelogs for all missing dates across tracked repos."""
    from repogerbil.core.audit import find_missing

    cfg_path = Path(config_path) if config_path else None
    settings = load_settings(config_path=cfg_path)

    if not settings.tracked:
        click.echo("No tracked repos configured. Add [tracked] to .repogerbil.toml")
        return

    extra_paths = [Path(p) for p in extra_sources]
    results = find_missing(
        settings.tracked,
        Path(changelog_dir),
        repo_overrides=settings.repos,
        extra_sources=extra_paths,
    )
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
        resolution = resolve_provenance(
            m.repo,
            m.date,
            repo_path,
            extra_sources=extra_paths,
            message_depth=repo_settings.message_depth,
            include_files=True,
        )
        commits = resolution.commits
        if not commits:  # pragma: no cover — date from find_missing always has commits
            continue

        stats = resolution.stats or get_diff_stats(repo_path, commits[0].hash, commits[-1].hash)

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


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--date", required=True, help="Date (YYYY-MM-DD)")
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos or worktrees to probe",
)
@click.option("--message-depth", type=click.Choice(["subject", "refs", "full"]), default=None)
@click.option("--files/--no-files", default=False, help="Include file lists when probing")
def probe(
    repo_path: str,
    date: str,
    extra_sources: tuple[str, ...],
    message_depth: str | None,
    files: bool,
) -> None:
    """Probe candidate sources for a repo/date pair."""
    path = Path(repo_path)
    settings = load_settings(repo=path.name)
    depth = message_depth or settings.message_depth
    resolution = resolve_provenance(
        path.name,
        date,
        path,
        extra_sources=[Path(p) for p in extra_sources],
        message_depth=depth,
        include_files=files,
    )

    for line in describe_resolution(resolution):
        click.echo(line)
