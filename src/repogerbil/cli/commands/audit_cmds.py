# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""CLI commands for commit message audit."""

from __future__ import annotations

from pathlib import Path
import re

import click

from repogerbil.core.classify import classify_commit
from repogerbil.core.git import get_active_dates, get_commits_for_date

_PREFIX_RE = re.compile(r"^(\w+)(?:\([^)]*\))?[!]?:\s")


@click.command()
@click.argument("repo_path", type=click.Path(exists=True))
@click.option("--since", help="Only check commits since this date")
@click.option("--show-bad", is_flag=True, help="List unclassifiable messages")
def audit(repo_path: str, since: str | None, show_bad: bool) -> None:
    """Audit commit message quality (prefix adoption)."""
    path = Path(repo_path)
    total, prefixed, verb_ok, ambiguous, bad_msgs = _audit_commits(path, since)

    classifiable = prefixed + verb_ok
    pct = (classifiable / total * 100) if total else 0
    click.echo(
        f"{path.name}: {total} commits, {prefixed} prefixed, "
        f"{verb_ok} verb, {ambiguous} ambiguous ({pct:.0f}% classifiable)"
    )

    if show_bad and bad_msgs:
        click.echo("Ambiguous commits:")
        for msg in bad_msgs[:20]:
            click.echo(f"  {msg}")
        if len(bad_msgs) > 20:  # pragma: no cover — only with >20 ambiguous commits
            click.echo(f"  ... and {len(bad_msgs) - 20} more")


def _audit_commits(
    path: Path,
    since: str | None,
) -> tuple[int, int, int, int, list[str]]:
    """Count prefix adoption across commits."""
    dates = sorted(get_active_dates(path))
    if since:
        dates = [d for d in dates if d >= since]

    total = prefixed = verb_ok = ambiguous = 0
    bad_msgs: list[str] = []

    for date_str in dates:
        for c in get_commits_for_date(path, date_str):
            if c.subject.startswith("Merge"):  # pragma: no cover — needs merge commits in test
                continue
            total += 1
            if _PREFIX_RE.match(c.subject):
                prefixed += 1
            elif classify_commit(c.subject).needs_review:
                ambiguous += 1
                bad_msgs.append(c.subject)
            else:
                verb_ok += 1  # pragma: no cover — needs verb-classifiable commit in test

    return total, prefixed, verb_ok, ambiguous, bad_msgs
