# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI command for changelog linting."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import click

from repogerbil.core.lint import LintResult, lint_directory


def _count_checked_files(changelog_dir: Path, repo_list: list[str] | None) -> int:
    """Count changelog files considered for the current lint run."""
    files_checked = 0
    for repo_dir in sorted(changelog_dir.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):  # pragma: no cover
            continue
        if repo_list and repo_dir.name not in repo_list:  # pragma: no branch
            continue
        files_checked += len(list(repo_dir.glob("*-changelog.yaml")))
    return files_checked


def _echo_lint_results(changelog_dir: Path, results: Sequence[LintResult]) -> tuple[int, int]:
    """Print lint results and return total error and warning counts."""
    errors = 0
    warnings = 0
    for lint_result in results:
        rel = lint_result.path.relative_to(changelog_dir)
        click.echo(f"\n{rel}")
        for error in lint_result.errors:
            click.echo(f"  ERROR  {error}")
            errors += 1
        for warning in lint_result.warnings:
            click.echo(f"  WARN   {warning}")
            warnings += 1
    return errors, warnings


@click.command()
@click.argument("changelog_dir", type=click.Path(exists=True))
@click.option("--errors-only", is_flag=True, help="Only show errors, skip warnings")
@click.argument("repos", nargs=-1)
def lint(changelog_dir: str, errors_only: bool, repos: tuple[str, ...]) -> None:
    """Validate changelog YAML files against the schema."""
    changelog_path = Path(changelog_dir)
    repo_list = list(repos) if repos else None
    results = lint_directory(changelog_path, repos=repo_list, errors_only=errors_only)
    files_checked = _count_checked_files(changelog_path, repo_list)
    errors, warnings = _echo_lint_results(changelog_path, results)

    click.echo(f"\n{files_checked} files checked — {errors} errors, {warnings} warnings")
    if errors:
        raise SystemExit(1)
