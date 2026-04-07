# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for repogerbil."""

from __future__ import annotations

import click


@click.group()
@click.version_option()
def cli() -> None:
    """repogerbil — Git history documentation and consolidation."""


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
def status(repo_path: str) -> None:
    """Show repository status and what needs work."""
    click.echo(f"Status for {repo_path}: not yet implemented")
