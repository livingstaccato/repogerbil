# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command: generate an LLM prompt for a release-span changelog."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.changelog import generate_prompt_span
from repogerbil.core.git import get_commits_for_range, get_diff_stats


@click.command(name="changelog-span")
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--from", "from_ref", required=True, help="Inclusive lower bound ref (tag/SHA/branch).")
@click.option("--to", "to_ref", required=True, help="Inclusive upper bound ref (tag/SHA/branch).")
@click.option(
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write the LLM prompt here instead of stdout.",
)
@click.option(
    "--include-files/--no-include-files",
    default=True,
    help="Attach per-commit file lists (default: on).",
)
def changelog_span_cmd(
    repo_path: str,
    from_ref: str,
    to_ref: str,
    output_path: str | None,
    include_files: bool,
) -> None:
    """Generate an LLM prompt for a release-span changelog.

    Walks commits in ``from_ref..to_ref``, collects diff stats, and writes a
    prompt file an LLM (or the repogerbil analyzer agent) can turn into a
    polished release changelog section.

    Example:

        gerbil changelog-span /path/to/repo --from v0.3.21 --to v0.4.0 \\
            --output release-notes-prompt.md
    """
    repo_name = Path(repo_path).name
    commits = get_commits_for_range(repo_path, from_ref, to_ref, include_files=include_files)
    if not commits:
        click.echo(f"No commits in {from_ref}..{to_ref}", err=True)
        return

    stats = get_diff_stats(repo_path, commits[0].hash, commits[-1].hash)
    prompt = generate_prompt_span(
        repo=repo_name,
        from_ref=from_ref,
        to_ref=to_ref,
        commits=commits,
        stats=stats,
        diff_content={},
    )

    if output_path:
        Path(output_path).write_text(prompt, encoding="utf-8")
        click.echo(f"Wrote prompt to {output_path} ({len(commits)} commits)")
    else:
        click.echo(prompt)
