# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command to realign legacy jsonl records to current local commit SHAs."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.realign import realign_jsonl


@click.command("realign")
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.argument("jsonl_path", type=click.Path(path_type=Path))
@click.option("--dry-run", is_flag=True, help="Compute realignment without writing.")
def realign_cmd(repo_path: Path, jsonl_path: Path, dry_run: bool) -> None:
    """Realign legacy records in JSONL_PATH to current commit SHAs in REPO_PATH.

    For records whose hash no longer exists in the local repo (history was
    rewritten since the jsonl was written), finds the best-matching current
    local commit by (date, file-set) and rewrites hash + date. LLM-refined
    subjects, body, and changes are preserved untouched.

    Any malformed (non-JSON) lines in the input are preserved verbatim in the
    rewritten file and reported as ``corrupt lines (preserved)`` in the output
    so no data is silently dropped.

    Idempotent: re-running realigns nothing new if every record already
    resolves to a current local hash.
    """
    result = realign_jsonl(repo_path, jsonl_path, dry_run=dry_run)
    verb = "would realign" if dry_run else "realigned"
    click.echo(f"jsonl: {result.jsonl_path}")
    click.echo(f"  total records: {result.total_records}")
    click.echo(f"  already verified: {result.already_verified}")
    click.echo(f"  {verb}: {result.realigned} (exact match: {result.exact_matches})")
    click.echo(f"  unalignable: {result.unalignable}")
    if result.corrupt_lines:
        click.echo(f"  corrupt lines (preserved): {result.corrupt_lines}")
