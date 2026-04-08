# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Weekly summary generation from changelog data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class RepoWeekData:
    """Aggregated changelog data for one repo across a week."""

    repo: str
    dates: list[str]
    total_commits: int
    total_files: int
    total_insertions: int
    total_deletions: int
    titles: list[str]
    categories: dict[str, int]


@dataclass(frozen=True)
class WeekSummaryData:
    """All data needed to generate a weekly summary."""

    week_label: str
    week_start: str
    week_end: str
    repos: list[RepoWeekData]
    total_commits: int
    total_files: int


def iso_week_range(year: int, week: int) -> tuple[date, date]:
    """Return (monday, sunday) for an ISO week."""
    jan4 = date(year, 1, 4)
    start = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=week - 1)
    end = start + timedelta(days=6)
    return start, end


def collect_week_data(changelog_dir: Path, year: int, week: int) -> WeekSummaryData:
    """Collect all changelog data for an ISO week across all repos.

    Args:
        changelog_dir: Root directory containing per-repo changelog subdirectories.
        year: ISO year.
        week: ISO week number.

    Returns:
        WeekSummaryData with aggregated stats per repo.
    """
    start, end = iso_week_range(year, week)
    week_dates = set()
    d = start
    while d <= end:
        week_dates.add(d.isoformat())
        d += timedelta(days=1)

    repos: list[RepoWeekData] = []
    total_commits = 0
    total_files = 0

    for repo_dir in sorted(changelog_dir.iterdir()):
        if not repo_dir.is_dir() or repo_dir.name.startswith("."):
            continue

        repo_data = _collect_repo_week(repo_dir, week_dates)
        if repo_data is not None:
            repos.append(repo_data)
            total_commits += repo_data.total_commits
            total_files += repo_data.total_files

    week_label = f"{year}-W{week:02d}"
    return WeekSummaryData(
        week_label=week_label,
        week_start=start.isoformat(),
        week_end=end.isoformat(),
        repos=repos,
        total_commits=total_commits,
        total_files=total_files,
    )


def generate_summary_markdown(data: WeekSummaryData) -> str:
    """Generate a markdown summary from collected week data.

    Produces a structured summary with overview, per-repo highlights,
    and aggregate statistics. Designed as input for human review or
    LLM refinement.
    """
    lines: list[str] = [
        f"# Week {data.week_label} — {_format_date_range(data.week_start, data.week_end)}",
        "",
        "## Overview",
        _generate_overview(data),
        "",
        "## Highlights",
        "",
    ]

    for repo in data.repos:
        lines.append(f"### {repo.repo}")
        lines.extend(_repo_highlights(repo))
        lines.append("")

    return "\n".join(lines)


def generate_summary_prompt(data: WeekSummaryData) -> str:
    """Generate an LLM prompt for writing a polished weekly summary."""
    lines = [
        f"# Write a weekly summary for {data.week_label}",
        f"## Period: {data.week_start} to {data.week_end}",
        f"## Totals: {data.total_commits} commits across {len(data.repos)} repos, {data.total_files} files",
        "",
        "## Per-repo data:",
        "",
    ]
    for repo in data.repos:
        lines.append(f"### {repo.repo}")
        lines.append(
            f"- {repo.total_commits} commits, {repo.total_files} files, +{repo.total_insertions}/-{repo.total_deletions}"
        )
        lines.append(f"- Dates active: {', '.join(repo.dates)}")
        lines.append("- Titles:")
        for t in repo.titles:
            lines.append(f"  - {t}")
        lines.append(
            f"- Categories: {', '.join(f'{k}({v})' for k, v in sorted(repo.categories.items(), key=lambda x: -x[1]))}"
        )
        lines.append("")

    lines.extend(
        [
            "## Instructions",
            "",
            "Write a narrative weekly summary in markdown. Structure:",
            "1. Overview paragraph (2-4 sentences, what defined the week)",
            "2. Per-repo highlights (bullet points, not just listing titles)",
            "3. Cross-repo themes if any repos coordinated",
            "",
            "Use present tense. Be specific about what shipped, not just what was worked on.",
            f"Output format: markdown file titled '# Week {data.week_label}'",
        ]
    )
    return "\n".join(lines)


def _collect_repo_week(repo_dir: Path, week_dates: set[str]) -> RepoWeekData | None:
    """Collect changelog data for one repo across a week's dates."""
    dates_found: list[str] = []
    total_commits = 0
    total_files = 0
    total_ins = 0
    total_dels = 0
    titles: list[str] = []
    categories: dict[str, int] = {}

    for yaml_file in sorted(repo_dir.glob("*-changelog.yaml")):
        file_date = "-".join(yaml_file.name.split("-")[:3])
        if file_date not in week_dates:
            continue

        data = _load_yaml(yaml_file)
        if not data:  # pragma: no cover — only with corrupt yaml in changelog dir
            continue

        dates_found.append(file_date)
        stats = data.get("stats", {})
        total_commits += stats.get("commits", 0)
        total_files += stats.get("files_changed", 0)
        total_ins += stats.get("insertions", 0)
        total_dels += stats.get("deletions", 0)

        title = data.get("title", "")
        if title and not title.startswith("TODO"):
            titles.append(title)

        for change in data.get("changes") or []:
            cat = change.get("category")
            if cat:
                categories[cat] = categories.get(cat, 0) + 1

    if not dates_found:
        return None

    return RepoWeekData(
        repo=repo_dir.name,
        dates=dates_found,
        total_commits=total_commits,
        total_files=total_files,
        total_insertions=total_ins,
        total_deletions=total_dels,
        titles=titles,
        categories=categories,
    )


def _format_date_range(start: str, end: str) -> str:
    """Format a date range for display."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    if s.month == e.month:
        return f"{s.strftime('%b')} {s.day}-{e.day}, {s.year}"
    return f"{s.strftime('%b %d')} - {e.strftime('%b %d')}, {s.year}"


def _generate_overview(data: WeekSummaryData) -> str:
    """Generate a brief overview paragraph."""
    if not data.repos:
        return "No activity this week."

    active = len(data.repos)
    top_repos = sorted(data.repos, key=lambda r: r.total_commits, reverse=True)[:3]
    top_names = ", ".join(r.repo for r in top_repos)

    return (
        f"Week {data.week_label} saw {data.total_commits} commits across {active} repositories "
        f"touching {data.total_files} files. "
        f"Most active: {top_names}."
    )


def _repo_highlights(repo: RepoWeekData) -> list[str]:
    """Generate bullet-point highlights for a repo."""
    lines: list[str] = []
    lines.append(
        f"- **{repo.total_commits} commits**, {repo.total_files} files, "
        f"+{repo.total_insertions}/-{repo.total_deletions}"
    )
    for title in repo.titles[:5]:
        lines.append(f"- {title}")
    if len(repo.titles) > 5:
        lines.append(f"- ... and {len(repo.titles) - 5} more")
    return lines


def _load_yaml(path: Path) -> dict[str, Any] | None:
    """Load YAML file, return None on error."""
    try:
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover — corrupt yaml file
        return None
