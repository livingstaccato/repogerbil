# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for recording missing commit metadata in a JSONL ledger."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.append import append_new_commits


def _run_catch_up(
    repo_path: Path,
    jsonl_path: Path,
    since_ref: str | None,
    since_date: str | None,
    full_scan: bool,
    dry_run: bool,
) -> None:
    """Record missing commit metadata in JSONL_PATH."""
    result = append_new_commits(
        repo_path,
        jsonl_path,
        since_ref=since_ref,
        since_date=since_date,
        full_scan=full_scan,
        dry_run=dry_run,
    )
    verb = "would record" if dry_run else "recorded"
    click.echo(f"ledger: {result.jsonl_path}")
    click.echo(f"  already recorded: {result.existing_entries}")
    click.echo(f"  {verb}: {result.new_entries}")
    click.echo(f"  already in ledger: {result.skipped_dedup}")
    if result.latest_hash:
        click.echo(f"  latest recorded hash: {result.latest_hash[:12]}")


@click.command("catch-up")
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("jsonl_path", type=click.Path(path_type=Path))
@click.option(
    "--since",
    "since_ref",
    default=None,
    help="Exclusive lower-bound ref (tag/branch/SHA). Use to bound the scan by commit.",
)
@click.option(
    "--since-date",
    "since_date",
    default=None,
    help="git --since= date (YYYY-MM-DD). Overrides the default jsonl-derived cutoff.",
)
@click.option(
    "--full",
    "full_scan",
    is_flag=True,
    help="Scan all HEAD history; dedup only by hash (use when jsonl hashes match local).",
)
@click.option("--dry-run", is_flag=True, help="Report planned work without writing.")
def append_cmd(
    repo_path: Path,
    jsonl_path: Path,
    since_ref: str | None,
    since_date: str | None,
    full_scan: bool,
    dry_run: bool,
) -> None:
    """Record missing commit metadata for HEAD commits into JSONL_PATH.

    Forward-only, LLM-free, idempotent. Each recorded commit contains:
    hash, author-date, subject (as a single-element subjects list), body,
    and a changes list of {file, description} pairs (description is empty
    since no LLM summary is generated).

    By default, uses the latest date in JSONL_PATH as a --since= cutoff.
    This is safe for repos whose history was rewritten by an earlier
    snapshot run (local hashes won't match the recorded upstream hashes).
    """
    _run_catch_up(repo_path, jsonl_path, since_ref, since_date, full_scan, dry_run)


@click.command("append", hidden=True)
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("jsonl_path", type=click.Path(path_type=Path))
@click.option(
    "--since",
    "since_ref",
    default=None,
    help="Exclusive lower-bound ref (tag/branch/SHA). Use to bound the scan by commit.",
)
@click.option(
    "--since-date",
    "since_date",
    default=None,
    help="git --since= date (YYYY-MM-DD). Overrides the default jsonl-derived cutoff.",
)
@click.option(
    "--full",
    "full_scan",
    is_flag=True,
    help="Scan all HEAD history; dedup only by hash (use when jsonl hashes match local).",
)
@click.option("--dry-run", is_flag=True, help="Report planned work without writing.")
def append_alias_cmd(
    repo_path: Path,
    jsonl_path: Path,
    since_ref: str | None,
    since_date: str | None,
    full_scan: bool,
    dry_run: bool,
) -> None:
    """Compatibility alias for catch-up."""
    _run_catch_up(repo_path, jsonl_path, since_ref, since_date, full_scan, dry_run)
