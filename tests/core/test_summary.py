# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for weekly summary generation."""

from pathlib import Path

import yaml

from repogerbil.core.summary import (
    RepoWeekData,
    WeekSummaryData,
    collect_week_data,
    generate_summary_markdown,
    generate_summary_prompt,
    iso_week_range,
)


def _write_changelog(path: Path, date_str: str, repo: str, title: str, commits: int = 3) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "date": date_str,
                "repo": repo,
                "title": title,
                "summary": f"Summary for {date_str}",
                "stats": {"commits": commits, "files_changed": 10, "insertions": 100, "deletions": 50},
                "changes": [
                    {"title": title, "category": "instantiate", "severity": "behavioral", "points": []},
                ],
            }
        )
    )


class TestIsoWeekRange:
    def test_week_15_2026(self) -> None:
        start, end = iso_week_range(2026, 15)
        assert start.isoformat() == "2026-04-06"
        assert end.isoformat() == "2026-04-12"

    def test_week_1_2026(self) -> None:
        start, end = iso_week_range(2026, 1)
        assert start.weekday() == 0  # Monday
        assert end.weekday() == 6  # Sunday


class TestCollectWeekData:
    def test_collects_from_multiple_repos(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml",
            "2026-04-07",
            "repo-a",
            "Add feature A",
        )
        _write_changelog(
            cl_dir / "repo-b" / "2026-04-08-repo-b-changelog.yaml",
            "2026-04-08",
            "repo-b",
            "Fix bug B",
        )

        data = collect_week_data(cl_dir, 2026, 15)
        assert data.week_label == "2026-W15"
        assert len(data.repos) == 2
        assert data.total_commits == 6

    def test_skips_outside_week(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-01-repo-a-changelog.yaml",
            "2026-04-01",
            "repo-a",
            "Old work",
        )
        data = collect_week_data(cl_dir, 2026, 15)
        assert len(data.repos) == 0

    def test_empty_dir(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "empty"
        cl_dir.mkdir()
        data = collect_week_data(cl_dir, 2026, 15)
        assert data.repos == []
        assert data.total_commits == 0

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        cl_dir.mkdir()
        (cl_dir / ".git").mkdir()
        data = collect_week_data(cl_dir, 2026, 15)
        assert data.repos == []

    def test_skips_draft_placeholder_titles(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml",
            "2026-04-07",
            "repo-a",
            "Draft: summarize 3 commits",
        )
        data = collect_week_data(cl_dir, 2026, 15)
        assert data.repos[0].titles == []

    def test_skips_legacy_todo_placeholder_titles(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml",
            "2026-04-07",
            "repo-a",
            "TODO: summarize 3 commits",
        )
        data = collect_week_data(cl_dir, 2026, 15)
        assert data.repos[0].titles == []

    def test_aggregates_categories(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "changelogs"
        _write_changelog(
            cl_dir / "repo-a" / "2026-04-07-repo-a-changelog.yaml",
            "2026-04-07",
            "repo-a",
            "Work",
        )
        data = collect_week_data(cl_dir, 2026, 15)
        assert "instantiate" in data.repos[0].categories


class TestGenerateSummaryMarkdown:
    def test_basic(self) -> None:
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="my-repo",
                    dates=["2026-04-07"],
                    total_commits=5,
                    total_files=10,
                    total_insertions=100,
                    total_deletions=50,
                    titles=["Add feature", "Fix bug"],
                    categories={"instantiate": 1, "remediate": 1},
                ),
            ],
            total_commits=5,
            total_files=10,
        )
        md = generate_summary_markdown(data)
        assert "Week 2026-W15" in md
        assert "my-repo" in md
        assert "Add feature" in md
        assert "5 commits" in md

    def test_no_repos(self) -> None:
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[],
            total_commits=0,
            total_files=0,
        )
        md = generate_summary_markdown(data)
        assert "No activity" in md

    def test_many_titles_truncated(self) -> None:
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="big-repo",
                    dates=["2026-04-07"],
                    total_commits=20,
                    total_files=50,
                    total_insertions=500,
                    total_deletions=200,
                    titles=[f"Title {i}" for i in range(10)],
                    categories={"instantiate": 10},
                ),
            ],
            total_commits=20,
            total_files=50,
        )
        md = generate_summary_markdown(data)
        assert "... and 5 more" in md

    def test_cross_month_date_range(self) -> None:
        data = WeekSummaryData(
            week_label="2026-W14",
            week_start="2026-03-30",
            week_end="2026-04-05",
            repos=[],
            total_commits=0,
            total_files=0,
        )
        md = generate_summary_markdown(data)
        assert "Mar 30" in md
        assert "Apr 05" in md or "Apr 5" in md


class TestGenerateSummaryPrompt:
    def test_basic(self) -> None:
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="my-repo",
                    dates=["2026-04-07", "2026-04-08"],
                    total_commits=5,
                    total_files=10,
                    total_insertions=100,
                    total_deletions=50,
                    titles=["Feature A", "Fix B"],
                    categories={"instantiate": 1, "remediate": 1},
                ),
            ],
            total_commits=5,
            total_files=10,
        )
        prompt = generate_summary_prompt(data)
        assert "2026-W15" in prompt
        assert "my-repo" in prompt
        assert "Feature A" in prompt
        assert "Instructions" in prompt
        assert "narrative" in prompt.lower()

    def test_exact_structure_and_spacing(self) -> None:
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="my-repo",
                    dates=["2026-04-07", "2026-04-08"],
                    total_commits=5,
                    total_files=10,
                    total_insertions=100,
                    total_deletions=50,
                    titles=["Feature A", "Fix B"],
                    categories={"remediate": 1, "instantiate": 2},
                ),
            ],
            total_commits=5,
            total_files=10,
        )

        prompt = generate_summary_prompt(data)

        assert prompt.splitlines() == [
            "# Write a weekly summary for 2026-W15",
            "## Period: 2026-04-06 to 2026-04-12",
            "## Totals: 5 commits across 1 repos, 10 files",
            "",
            "## Per-repo data:",
            "",
            "### my-repo",
            "- 5 commits, 10 files, +100/-50",
            "- Dates active: 2026-04-07, 2026-04-08",
            "- Titles:",
            "  - Feature A",
            "  - Fix B",
            "- Categories: instantiate(2), remediate(1)",
            "",
            "## Instructions",
            "",
            "Write a narrative weekly summary in markdown. Structure:",
            "1. Overview paragraph (2-4 sentences, what defined the week)",
            "2. Per-repo highlights (bullet points, not just listing titles)",
            "3. Cross-repo themes if any repos coordinated",
            "",
            "Use present tense. Be specific about what shipped, not just what was worked on.",
            "Output format: markdown file titled '# Week 2026-W15'",
        ]
