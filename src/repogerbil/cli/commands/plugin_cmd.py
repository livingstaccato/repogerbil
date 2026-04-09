# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for exporting assistant plugin files."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.assistant_plugins import export_bundled_plugin, install_bundled_plugin


@click.group()
def plugin() -> None:
    """Export or install bundled assistant plugin files."""


@plugin.command("export")
@click.option("--target", type=click.Choice(["codex", "claude"]), required=True)
@click.option("--dest", type=click.Path(path_type=Path, file_okay=False), required=True)
def export_command(target: str, dest: Path) -> None:
    """Export plugin files into a destination root."""
    plugin_dest = export_bundled_plugin(target, dest)
    click.echo(f"Exported {target} plugin to {plugin_dest}")


@plugin.command("install")
@click.option("--target", type=click.Choice(["codex", "claude"]), required=True)
@click.option("--root", type=click.Path(path_type=Path, file_okay=False), default=None)
def install_command(target: str, root: Path | None) -> None:
    """Install plugin files into a home-like root."""
    plugin_dest = install_bundled_plugin(target, root=root)
    click.echo(f"Installed {target} plugin to {plugin_dest}")
