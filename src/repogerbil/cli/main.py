# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI entry point for repogerbil."""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any

import click
from rich.console import Console

from repogerbil.core.changelog import (
    generate_analyzed,
    generate_draft,
    generate_prompt,
    write_changelog,
)
from repogerbil.core.config import load_settings
from repogerbil.core.errors import RepogerbilError
from repogerbil.core.git import get_diff_stats
from repogerbil.core.provenance import resolve_provenance


def _configure_cli_logging(level: int = logging.WARNING) -> None:
    """Attach a stderr handler to the ``repogerbil`` package logger.

    The package itself only attaches a ``NullHandler`` (library hygiene), so
    without this configuration ``logger.warning(...)`` from core modules
    would be swallowed for CLI users. Safe to call multiple times — the Click
    test runner can invoke the CLI repeatedly in one process and we must not
    pile on duplicate handlers each time.

    Library-consumer hygiene: ``pkg_logger.setLevel`` is only invoked on
    first-time configuration. Subsequent calls (e.g. ``--verbose`` bumping
    on a later CLI invocation) update *our handler's* level instead, so an
    embedder's previously-set package-logger level is preserved. The handler's
    own level filter is sufficient to route records to stderr.
    """
    pkg_logger = logging.getLogger("repogerbil")
    # Only attach our handler once — identify it by an internal marker so we
    # never clash with handlers a host app may have already attached.
    for h in pkg_logger.handlers:
        if getattr(h, "_repogerbil_cli_handler", False):
            # Bump only the handler level so --verbose still works on repeat
            # invocations, but DO NOT touch pkg_logger.level — that belongs to
            # whoever configured the logger first (embedder or first CLI call).
            h.setLevel(level)
            return
    # First-time setup: take ownership of the package-logger level, but only
    # if no embedder has already configured it (NOTSET means "untouched").
    if pkg_logger.level == logging.NOTSET:
        pkg_logger.setLevel(level)
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter("%(message)s"))
    # Marker used above to avoid duplicate registration across CliRunner calls.
    handler._repogerbil_cli_handler = True  # type: ignore[attr-defined]  # private marker on the handler instance
    pkg_logger.addHandler(handler)


@click.group()
@click.version_option()
# NOTE: deliberately no ``-v`` short form — it collides with subcommand flags
# (e.g. ``gerbil preflight -v``, which is the long-standing preflight verbose
# source-listing flag). Use ``--verbose`` at the group level.
@click.option("--verbose", is_flag=True, help="Enable INFO-level logging to stderr.")
def cli(verbose: bool) -> None:
    """gerbil — Git history documentation and consolidation."""
    _configure_cli_logging(level=logging.INFO if verbose else logging.WARNING)


def main() -> None:
    """Entry point with error handling."""
    debug = "--debug" in sys.argv
    try:
        if debug:
            sys.argv.remove("--debug")

        cli()
    except RepogerbilError as e:
        console = Console(stderr=True)
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(1)
    except Exception as e:
        if debug:  # pragma: no cover — debug path is exercised manually
            raise
        console = Console(stderr=True)
        console.print(f"[bold red]Unexpected Error:[/] {str(e) or type(e).__name__}")
        sys.exit(1)


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--date", required=True, help="Date (YYYY-MM-DD)")
@click.option("--output-dir", type=click.Path(), default=".", help="Output directory")
@click.option("--analyze", is_flag=True, help="Generate complete changelog (not just draft)")
@click.option("--prompt", "prompt_mode", is_flag=True, help="Output LLM prompt instead of YAML")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--message-depth", type=click.Choice(["subject", "refs", "full"]), default=None)
@click.option(
    "--extra-source",
    "extra_sources",
    multiple=True,
    type=click.Path(),
    help="Additional source repos or worktrees to probe",
)
def changelog(
    repo_path: str,
    date: str,
    output_dir: str,
    analyze: bool,
    prompt_mode: bool,
    force: bool,
    message_depth: str | None,
    extra_sources: tuple[str, ...],
) -> None:
    """Generate a changelog for a repository date."""
    path = Path(repo_path)
    out = Path(output_dir)
    repo_name = path.name
    settings = load_settings(repo=repo_name)
    depth = message_depth or settings.message_depth
    extra_paths = [Path(p) for p in extra_sources]

    resolution = resolve_provenance(
        repo_name,
        date,
        path,
        extra_sources=extra_paths,
        message_depth=depth,
        include_files=True,
    )
    if not resolution.commits:
        click.echo(f"No commits found for {repo_name} on {date}")
        return

    commits = resolution.commits
    stats = resolution.stats or get_diff_stats(path, commits[0].hash, commits[-1].hash)
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
    from repogerbil.core.diff import get_diff_content

    diff_content: dict[str, str] = {}
    if settings.backfill_depth == "thorough":  # pragma: no cover — requires thorough config in CWD
        diff_content = get_diff_content(path, commits[0].hash, commits[-1].hash)

    prompt_text = generate_prompt(repo_name, date, commits, stats, diff_content)
    prompt_path = out / repo_name / f"{date}-{repo_name}-prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text(prompt_text)
    click.echo(f"Wrote {prompt_path}")


# Re-export helpers that tests import directly from this module
from repogerbil.cli.commands.verify_cmds import _report_verification as _report_verification  # noqa: E402

# Register optional vectordb commands
try:
    from repogerbil.cli.commands.vectordb_cmds import (
        impact,
        index,
        related,
        search,
        similar,
    )  # pragma: no cover

    cli.add_command(index)  # pragma: no cover
    cli.add_command(search)  # pragma: no cover
    cli.add_command(related)  # pragma: no cover
    cli.add_command(similar)  # pragma: no cover
    cli.add_command(impact)  # pragma: no cover
except ImportError:  # pragma: no cover
    pass

# Register distill/snapshot commands
from repogerbil.cli.commands.distill_cmds import (  # noqa: E402
    distill_ecosystem,
    export_cadence,
    multi_snapshot,
    preview,
    snapshot,
)

cli.add_command(snapshot)
cli.add_command(multi_snapshot)
cli.add_command(export_cadence)
cli.add_command(distill_ecosystem)
cli.add_command(preview)

# Register distill command
from repogerbil.cli.commands.distill_cmd import distill  # noqa: E402

cli.add_command(distill)

# Register lint command
from repogerbil.cli.commands.lint_cmd import lint  # noqa: E402

cli.add_command(lint)

# Register preflight command
from repogerbil.cli.commands.preflight_cmd import preflight_cmd  # noqa: E402

cli.add_command(preflight_cmd)

# Register changelog-span command
from repogerbil.cli.commands.changelog_span_cmd import changelog_span_cmd  # noqa: E402

cli.add_command(changelog_span_cmd)

# Register sidecar metadata catch-up command (+ legacy append alias)
from repogerbil.cli.commands.catch_up_cmd import catch_up_cmd, legacy_append_alias_cmd  # noqa: E402

cli.add_command(catch_up_cmd)
cli.add_command(legacy_append_alias_cmd)

# Register realign command (legacy jsonl record → current local hash)
from repogerbil.cli.commands.realign_cmd import realign_cmd  # noqa: E402

cli.add_command(realign_cmd)

# Register plugin commands
from repogerbil.cli.commands.plugin_cmd import plugin  # noqa: E402

cli.add_command(plugin)

# Register changelog helper commands
from repogerbil.cli.commands.changelog_cmds import fix_stats, status  # noqa: E402

cli.add_command(status)
cli.add_command(fix_stats)

# Register verify command
from repogerbil.cli.commands.verify_cmds import verify  # noqa: E402

cli.add_command(verify)

# Register audit command
from repogerbil.cli.commands.audit_cmds import audit  # noqa: E402

cli.add_command(audit)

# Register summary and missing commands
from repogerbil.cli.commands.summary_cmds import missing, summary  # noqa: E402

cli.add_command(summary)
cli.add_command(missing)

# Register enrich command
from repogerbil.cli.commands.enrich_cmds import enrich  # noqa: E402

cli.add_command(enrich)

# Register backfill and probe commands
from repogerbil.cli.commands.backfill_cmds import backfill, probe  # noqa: E402

cli.add_command(backfill)
cli.add_command(probe)


if __name__ == "__main__":  # pragma: no cover
    main()
