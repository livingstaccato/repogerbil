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

    def test_exact_markdown_structure(self) -> None:
        """Pin exact line structure of the markdown summary.

        Kills mutants that mutate header strings, blank lines, the join
        separator, the per-repo blank line, and section labels in
        ``generate_summary_markdown``.
        """
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
                    titles=["Add feature"],
                    categories={"instantiate": 1},
                ),
            ],
            total_commits=5,
            total_files=10,
        )
        md = generate_summary_markdown(data)
        lines = md.split("\n")
        # Lines [0..5] are the structural header — pinned exactly.
        assert lines[0] == "# Week 2026-W15 — Apr 6-12, 2026"
        assert lines[1] == ""
        assert lines[2] == "## Overview"
        # lines[3] is the overview paragraph
        assert lines[4] == ""
        assert lines[5] == "## Highlights"
        assert lines[6] == ""
        assert lines[7] == "### my-repo"
        # Last repo line is followed by an exact empty line ("" not "XXXX")
        assert lines[-1] == ""
        # The separator is exactly "\n" — concatenating lines back must
        # reproduce md, proving the join string is exactly "\n".
        assert "\n".join(lines) == md
        # The string "XXXX" must not appear anywhere.
        assert "XXXX" not in md

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


class TestCollectRepoWeekArithmetic:
    """Pin exact aggregation arithmetic in ``_collect_repo_week``.

    Uses asymmetric stats per-day so any mutation to accumulator behavior
    (init value, += vs =, += vs -=, default value swap) produces a
    distinguishable result.
    """

    def _write(
        self,
        path: Path,
        date_str: str,
        repo: str,
        title: str,
        commits: int,
        files: int,
        insertions: int,
        deletions: int,
        category: str = "instantiate",
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.dump(
                {
                    "date": date_str,
                    "repo": repo,
                    "title": title,
                    "summary": "s",
                    "stats": {
                        "commits": commits,
                        "files_changed": files,
                        "insertions": insertions,
                        "deletions": deletions,
                    },
                    "changes": [
                        {"title": title, "category": category, "severity": "behavioral", "points": []},
                    ],
                }
            )
        )

    def test_aggregates_across_two_days_exact(self, tmp_path: Path) -> None:
        """Two days of distinct stats produce exact sums.

        Kills init-mutations (`total_files = 1`, `total_ins = 1`,
        `total_dels = 1`), op-flips (`+= -> =`, `+= -> -=`), arg-drop on
        ``stats.get`` (kwarg name mutated to ``"FILES_CHANGED"`` etc., or
        default swapped 0->1), since any of these produce wrong totals.
        """
        cl_dir = tmp_path / "changelogs"
        self._write(
            cl_dir / "r" / "2026-04-07-r-changelog.yaml",
            "2026-04-07",
            "r",
            "T1",
            commits=3,
            files=7,
            insertions=100,
            deletions=40,
        )
        self._write(
            cl_dir / "r" / "2026-04-08-r-changelog.yaml",
            "2026-04-08",
            "r",
            "T2",
            commits=5,
            files=11,
            insertions=200,
            deletions=60,
        )
        data = collect_week_data(cl_dir, 2026, 15)
        repo = data.repos[0]
        # Each total has a unique sum and unique digit pattern so any
        # arithmetic mutation produces a different number.
        assert repo.total_commits == 8
        assert repo.total_files == 18
        assert repo.total_insertions == 300
        assert repo.total_deletions == 100
        # Top-level WeekSummaryData also aggregates files; pin it exactly
        # (kills `total_files = 1` init mutant in collect_week_data + the
        # `total_files = repo_data.total_files` overwrite mutant + the
        # `total_files=None` final-call mutant).
        assert data.total_files == 18
        assert data.total_commits == 8
        # ``total_files`` and ``total_insertions`` on the result must not
        # be None (kills `total_files=None` and `total_insertions=None`
        # constructor mutants).
        assert data.total_files is not None
        assert repo.total_insertions is not None
        assert repo.total_deletions is not None

    def test_categories_increment_by_exactly_one(self, tmp_path: Path) -> None:
        """Each occurrence of a category increments its count by exactly 1.

        Kills `categories.get(cat, 0) + 1 -> + 2` and `-> - 1`, plus
        `categories.get(cat, 0) -> categories.get(cat, 1)` (which would
        make the *first* occurrence count as 2).
        """
        cl_dir = tmp_path / "changelogs"
        # Day 1 has 1 'remediate'; day 2 has 1 'remediate' and 1 'instantiate'.
        d1 = cl_dir / "r" / "2026-04-07-r-changelog.yaml"
        d1.parent.mkdir(parents=True, exist_ok=True)
        d1.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "r",
                    "title": "T1",
                    "stats": {"commits": 1, "files_changed": 1, "insertions": 1, "deletions": 1},
                    "changes": [
                        {"title": "x", "category": "remediate"},
                    ],
                }
            )
        )
        d2 = cl_dir / "r" / "2026-04-08-r-changelog.yaml"
        d2.write_text(
            yaml.dump(
                {
                    "date": "2026-04-08",
                    "repo": "r",
                    "title": "T2",
                    "stats": {"commits": 1, "files_changed": 1, "insertions": 1, "deletions": 1},
                    "changes": [
                        {"title": "y", "category": "remediate"},
                        {"title": "z", "category": "instantiate"},
                    ],
                }
            )
        )
        data = collect_week_data(cl_dir, 2026, 15)
        cats = data.repos[0].categories
        assert cats == {"remediate": 2, "instantiate": 1}

    def test_titles_appended_unchanged(self, tmp_path: Path) -> None:
        """Real titles round-trip into ``titles`` exactly.

        Kills `titles.append(None)` mutant and `data.get("title", "XXXX")`
        (which would pollute titles with placeholder text since the
        default would only apply when key missing — but the *string*
        ``"title"`` -> ``"TITLE"`` / ``"XXtitleXX"`` mutants would yield
        a falsy lookup and skip the append).
        """
        cl_dir = tmp_path / "changelogs"
        self._write(
            cl_dir / "r" / "2026-04-07-r-changelog.yaml",
            "2026-04-07",
            "r",
            "Real Title One",
            commits=1,
            files=1,
            insertions=1,
            deletions=1,
        )
        data = collect_week_data(cl_dir, 2026, 15)
        # Exactly one real title — not None, not empty, not transformed.
        assert data.repos[0].titles == ["Real Title One"]

    def test_skips_outside_week_does_not_break_loop(self, tmp_path: Path) -> None:
        """A file outside the week (the *first* sorted file) must not abort
        the loop early.

        Kills mutant `_collect_repo_week__mutmut_23` (`continue` -> `break`).
        We arrange the out-of-week date to sort *before* an in-week date so
        a `break` would yield no data while a `continue` finds the in-week
        date.
        """
        cl_dir = tmp_path / "changelogs"
        # 2026-04-01 sorts before 2026-04-07 and is *outside* the W15 window.
        self._write(
            cl_dir / "r" / "2026-04-01-r-changelog.yaml",
            "2026-04-01",
            "r",
            "Old",
            commits=99,
            files=99,
            insertions=99,
            deletions=99,
        )
        self._write(
            cl_dir / "r" / "2026-04-07-r-changelog.yaml",
            "2026-04-07",
            "r",
            "New",
            commits=2,
            files=2,
            insertions=2,
            deletions=2,
        )
        data = collect_week_data(cl_dir, 2026, 15)
        # If `break` instead of `continue`, repos would be empty.
        assert len(data.repos) == 1
        assert data.repos[0].titles == ["New"]
        assert data.repos[0].total_commits == 2

    def test_missing_title_yields_no_titles(self, tmp_path: Path) -> None:
        """When the ``title`` key is missing, no title is appended.

        Kills mutant `_collect_repo_week__mutmut_78`
        (``data.get("title", "")`` -> ``data.get("title", "XXXX")``) — the
        default would be truthy and would be appended.
        """
        cl_dir = tmp_path / "changelogs"
        f = cl_dir / "r" / "2026-04-07-r-changelog.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        # No "title" key at all.
        f.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "r",
                    "stats": {"commits": 1, "files_changed": 1, "insertions": 1, "deletions": 1},
                    "changes": [],
                }
            )
        )
        data = collect_week_data(cl_dir, 2026, 15)
        assert data.repos[0].titles == []

    def test_missing_stats_uses_zero_default(self, tmp_path: Path) -> None:
        """When ``stats`` is absent, defaults to empty dict (`.get` defaults to 0).

        Kills `data.get("stats", None)` (would crash on .get), `data.get("stats", )`
        (TypeError: missing required positional), and `stats.get("commits", 1)`
        (would add 1 instead of 0 when stats present but key missing).
        """
        cl_dir = tmp_path / "changelogs"
        f = cl_dir / "r" / "2026-04-07-r-changelog.yaml"
        f.parent.mkdir(parents=True, exist_ok=True)
        # Note: no `stats` key at all.
        f.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "r",
                    "title": "Empty stats",
                    "changes": [],
                }
            )
        )
        data = collect_week_data(cl_dir, 2026, 15)
        repo = data.repos[0]
        # Everything zero because stats key missing.
        assert repo.total_commits == 0
        assert repo.total_files == 0
        assert repo.total_insertions == 0
        assert repo.total_deletions == 0


class TestCollectWeekDataBoundaries:
    """Boundary tests for ``collect_week_data``."""

    def test_includes_sunday_end_of_week(self, tmp_path: Path) -> None:
        """The week-dates range must include the Sunday end-of-week.

        Kills mutant `collect_week_data__mutmut_8` (`d <= end` -> `d < end`),
        which would drop Sunday from ``week_dates`` and make a Sunday
        changelog appear out-of-week.
        """
        cl_dir = tmp_path / "changelogs"
        # 2026-04-12 is the Sunday of ISO week 2026-W15.
        _write_changelog(
            cl_dir / "r" / "2026-04-12-r-changelog.yaml",
            "2026-04-12",
            "r",
            "Sunday work",
        )
        data = collect_week_data(cl_dir, 2026, 15)
        assert len(data.repos) == 1
        assert data.repos[0].dates == ["2026-04-12"]

    def test_hidden_dir_with_real_changelog_skipped(self, tmp_path: Path) -> None:
        """A dotted directory must be skipped *even when* it contains a
        valid changelog file inside the week.

        Kills:
          * mutant 20 (`not is_dir() or startswith(".")` -> `not is_dir() and
            startswith(".")`) — would no longer skip dot-dirs;
          * mutant 23 (``startswith(".")`` -> ``startswith("XX.XX")``) —
            the literal ``XX.XX`` is never a real prefix, so dot-dirs leak
            through and contribute data; and
          * mutant 24 (``continue`` -> ``break``) — would abort iteration
            after the first dot-dir, missing later real repos.
        """
        cl_dir = tmp_path / "changelogs"
        # Hidden dir with a valid in-week changelog.
        _write_changelog(
            cl_dir / ".hidden" / "2026-04-07-.hidden-changelog.yaml",
            "2026-04-07",
            ".hidden",
            "Should be skipped",
        )
        # Real repo sorted *after* the hidden dir alphabetically (`.` < letters).
        _write_changelog(
            cl_dir / "real" / "2026-04-08-real-changelog.yaml",
            "2026-04-08",
            "real",
            "Should appear",
        )
        data = collect_week_data(cl_dir, 2026, 15)
        repo_names = [r.repo for r in data.repos]
        # Only "real" must appear, never ".hidden".
        assert repo_names == ["real"]


class TestGenerateOverviewExact:
    """Pin exact behavior of ``_generate_overview``."""

    def test_no_repos_exact_message(self) -> None:
        """Empty week returns exactly ``"No activity this week."``.

        Kills mutant `_generate_overview__mutmut_2` (string -> ``"XXNo
        activity this week.XX"``).
        """
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[],
            total_commits=0,
            total_files=0,
        )
        md = generate_summary_markdown(data)
        # The overview line is at index 3 (header, blank, "## Overview", overview).
        assert "No activity this week." in md
        assert "XXNo activity this week.XX" not in md

    def test_top_three_in_descending_order(self) -> None:
        """The top-3 repos are sorted by commits *descending* and capped at 3.

        Kills:
          * `key=None` (8) — sorted() would fail or yield arbitrary order;
          * `reverse=None` (9) — TypeError;
          * dropping kwargs (11, 12) — wrong order;
          * `reverse=False` (14) — ascending order;
          * `[:3] -> [:4]` (15) — would include a 4th repo name;
          * `key=lambda r: None` (13) — all keys equal, order undefined.
        """
        # Four repos with strictly decreasing commit counts.
        repos = [
            RepoWeekData(
                repo=f"repo-{name}",
                dates=["2026-04-07"],
                total_commits=count,
                total_files=1,
                total_insertions=1,
                total_deletions=1,
                titles=[],
                categories={},
            )
            for name, count in [("a", 1), ("b", 10), ("c", 5), ("d", 20)]
        ]
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=repos,
            total_commits=36,
            total_files=4,
        )
        md = generate_summary_markdown(data)
        # Extract the "Most active: ..." segment.
        marker = "Most active: "
        idx = md.index(marker) + len(marker)
        rest = md[idx:].split(".", 1)[0]
        # The exact descending top-3, joined by exactly ", ".
        assert rest == "repo-d, repo-b, repo-c"
        # Confirm 4th repo not present in the top-names listing
        # (`[:3] -> [:4]` would add "repo-a").
        assert "repo-a" not in rest

    def test_overview_exact_format(self) -> None:
        """The overview sentence pins exact wording, including commas and ``Most active:``.

        Kills mutants that change the separator or active-len reference,
        e.g. `top_names = None` (16) — TypeError on format — and
        `", ".join` -> `"XX, XX".join` (18).
        """
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="repo-x",
                    dates=["2026-04-07"],
                    total_commits=7,
                    total_files=3,
                    total_insertions=10,
                    total_deletions=5,
                    titles=[],
                    categories={},
                ),
                RepoWeekData(
                    repo="repo-y",
                    dates=["2026-04-08"],
                    total_commits=3,
                    total_files=2,
                    total_insertions=4,
                    total_deletions=1,
                    titles=[],
                    categories={},
                ),
            ],
            total_commits=10,
            total_files=5,
        )
        md = generate_summary_markdown(data)
        expected = (
            "Week 2026-W15 saw 10 commits across 2 repositories touching 5 files. Most active: repo-x, repo-y."
        )
        assert expected in md
        # ``"XX, XX"`` separator must never appear.
        assert "XX, XX" not in md


class TestRepoHighlightsBoundaries:
    """Boundary tests for ``_repo_highlights``."""

    def test_exactly_five_titles_no_more_line(self) -> None:
        """With exactly 5 titles, the ``... and N more`` line must NOT appear.

        Kills `len(repo.titles) > 5` -> `>= 5` (mutant 5), which would
        produce ``"- ... and 0 more"`` for a 5-title repo.
        """
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="r",
                    dates=["2026-04-07"],
                    total_commits=5,
                    total_files=5,
                    total_insertions=5,
                    total_deletions=5,
                    titles=[f"Title {i}" for i in range(5)],
                    categories={},
                ),
            ],
            total_commits=5,
            total_files=5,
        )
        md = generate_summary_markdown(data)
        assert "more" not in md
        assert "... and 0 more" not in md

    def test_six_titles_emits_one_more(self) -> None:
        """With 6 titles, exactly the first 5 are listed and ``and 1 more``
        appears.

        Kills:
          * `repo.titles[:5]` -> `[:6]` (mutant 3) — would list all 6 titles;
          * `len(repo.titles) > 6` (mutant 6) — would not emit the ``more``
            line for 6 titles.
        """
        titles = [f"Title {i}" for i in range(6)]
        data = WeekSummaryData(
            week_label="2026-W15",
            week_start="2026-04-06",
            week_end="2026-04-12",
            repos=[
                RepoWeekData(
                    repo="r",
                    dates=["2026-04-07"],
                    total_commits=6,
                    total_files=6,
                    total_insertions=6,
                    total_deletions=6,
                    titles=titles,
                    categories={},
                ),
            ],
            total_commits=6,
            total_files=6,
        )
        md = generate_summary_markdown(data)
        # ``Title 0`` ... ``Title 4`` must appear; ``Title 5`` must NOT.
        for i in range(5):
            assert f"- Title {i}" in md
        assert "- Title 5" not in md
        # Exactly the "and 1 more" trailer (not 0 more, not absent).
        assert "- ... and 1 more" in md
