# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command for pre-flight repo inspection before distilling."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import click

from repogerbil.core.config import load_settings
from repogerbil.core.preflight import FileRecord, PreflightReport, scan_repo


def _print_artifacts(report: PreflightReport) -> None:
    """Print the ARTIFACTS section."""
    if not report.artifacts:
        click.echo("\nARTIFACTS: none found")
        return
    click.echo(f"\nARTIFACTS (safe to exclude -- {len(report.artifacts)} files)")
    by_label_flag: dict[tuple[str, str], list[FileRecord]] = defaultdict(list)
    for rec in report.artifacts:
        label = rec.rule.label if rec.rule else "unknown"
        flag = rec.rule.flag if rec.rule else ""
        by_label_flag[(label, flag)].append(rec)
    for (label, flag), recs in sorted(by_label_flag.items()):
        click.echo(f"  {label:<28}  {len(recs):>4} files   --exclude-path '{flag}'")


def _print_unknown(report: PreflightReport) -> None:
    """Print the UNKNOWN section."""
    if report.unknown:
        click.echo(f"\nUNKNOWN (evaluate manually -- {len(report.unknown)} files)")
        for rec in sorted(report.unknown, key=lambda r: -r.commit_count):
            click.echo(f"  {rec.path:<50}  {rec.commit_count:>3} commit(s)")
    else:
        click.echo("\nUNKNOWN: none")


def _print_source(report: PreflightReport) -> None:
    """Print the SOURCE section (verbose only)."""
    if report.source:
        click.echo(f"\nSOURCE ({len(report.source)} files)")
        for rec in report.source:
            click.echo(f"  {rec.path}")


def _print_suggested_flags(report: PreflightReport) -> None:
    """Print the suggested flags section."""
    if report.suggested_flags:
        click.echo("\nSuggested flags for `gerbil snapshot`:")
        for flag in report.suggested_flags:
            click.echo(f"  --exclude-path '{flag}'")
    else:
        click.echo("\nNo exclude flags suggested.")


@click.command("preflight")
@click.argument("source", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--since", default=None, help="Only commits after this date (ISO or relative)")
@click.option("--until", default=None, help="Only commits before this date")
@click.option(
    "--emit-flags",
    is_flag=True,
    default=False,
    help="Print only the --exclude-path flags, one per line (pipe-friendly)",
)
@click.option("--verbose", is_flag=True, default=False, help="Also list all source files")
def preflight_cmd(
    source: Path,
    since: str | None,
    until: str | None,
    emit_flags: bool,
    verbose: bool,
) -> None:
    """Scan SOURCE repo and report files to exclude before distilling."""
    settings = load_settings()
    report = scan_repo(source, since=since, until=until, settings=settings)

    if emit_flags:
        for flag in report.suggested_flags:
            click.echo(f"--exclude-path '{flag}'")
        return

    _print_artifacts(report)
    _print_unknown(report)
    if verbose:
        _print_source(report)
    _print_suggested_flags(report)
