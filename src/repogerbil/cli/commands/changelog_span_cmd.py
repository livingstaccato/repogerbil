# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command: generate an LLM prompt for a release-span changelog."""

from __future__ import annotations

from pathlib import Path

import click

from repogerbil.core.changelog import generate_prompt_span
from repogerbil.core.git import get_commits_for_range, get_diff_stats
from repogerbil.core.llm_runner import (
    LlmRunnerError,
    agent_dispatch_instructions,
    run_claude_cli,
)


@click.command(name="changelog-span")
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False))
@click.option("--from", "from_ref", required=True, help="Inclusive lower bound ref (tag/SHA/branch).")
@click.option("--to", "to_ref", required=True, help="Inclusive upper bound ref (tag/SHA/branch).")
@click.option(
    "--output",
    "output_path",
    type=click.Path(),
    default=None,
    help="Write the output here instead of stdout (prompt if --run unset, changelog otherwise).",
)
@click.option(
    "--include-files/--no-include-files",
    default=True,
    help="Attach per-commit file lists (default: on).",
)
@click.option(
    "--run",
    "runner",
    type=click.Choice(["claude", "agent"], case_sensitive=False),
    default=None,
    help=(
        "Synthesize the changelog automatically. "
        "'claude' shells out to the Claude Code CLI. "
        "'agent' prints dispatch instructions for the repogerbil analyzer subagent."
    ),
)
def changelog_span_cmd(
    repo_path: str,
    from_ref: str,
    to_ref: str,
    output_path: str | None,
    include_files: bool,
    runner: str | None,
) -> None:
    """Generate an LLM prompt (or synthesized changelog) for a release span.

    Walks commits in ``from_ref..to_ref``, collects diff stats, and:

    - with no ``--run``: emits the LLM prompt (manual / pipe-to-LLM workflow);
    - with ``--run claude``: invokes ``claude -p`` and returns the resulting
      changelog markdown;
    - with ``--run agent``: prints dispatch instructions for the repogerbil
      analyzer subagent (use from inside Claude Code).

    Examples:

        gerbil changelog-span /path/to/repo --from v0.3.21 --to v0.4.0 \\
            --output prompt.md

        gerbil changelog-span /path/to/repo --from v0.3.21 --to v0.4.0 \\
            --run claude --output CHANGELOG.md
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

    if runner is None:
        _write_or_echo(prompt, output_path, label="prompt", commit_count=len(commits))
        return

    runner_lc = runner.lower()
    if runner_lc == "claude":
        try:
            changelog = run_claude_cli(prompt)
        except LlmRunnerError as exc:
            raise click.ClickException(str(exc)) from exc
        _write_or_echo(changelog, output_path, label="changelog", commit_count=len(commits))
        return

    # runner_lc == "agent"
    prompt_path = Path(output_path) if output_path else Path(f"/tmp/{repo_name}-changelog-prompt.md")
    prompt_path.write_text(prompt, encoding="utf-8")
    click.echo(agent_dispatch_instructions(prompt_path))


def _write_or_echo(content: str, output_path: str | None, label: str, commit_count: int) -> None:
    if output_path:
        Path(output_path).write_text(content, encoding="utf-8")
        click.echo(f"Wrote {label} to {output_path} ({commit_count} commits)")
    else:
        click.echo(content)
