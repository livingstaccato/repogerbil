# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for changelog enrichment."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.config import load_settings


@click.command()
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
