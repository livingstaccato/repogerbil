# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for weekly summary and missing-date reporting."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.config import load_settings


@click.command()
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


@click.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--config", "config_path", type=click.Path(), default=None, help="Path to .repogerbil.toml")
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos or worktrees to probe",
)
def missing(changelog_dir: str, config_path: str | None, extra_sources: tuple[str, ...]) -> None:
    """Show missing changelog dates across all tracked repos."""
    from repogerbil.core.audit import find_missing

    cfg_path = Path(config_path) if config_path else None
    settings = load_settings(config_path=cfg_path)

    if not settings.tracked:
        click.echo("No tracked repos configured. Add [tracked] to .repogerbil.toml")
        return

    results = find_missing(
        settings.tracked,
        Path(changelog_dir),
        repo_overrides=settings.repos,
        extra_sources=[Path(p) for p in extra_sources],
    )
    if not results:  # pragma: no cover
        click.echo("All reports up to date.")
    else:
        for m in results:
            click.echo(f"{m.repo}/{m.date}")
        click.echo(f"\n{len(results)} missing")
