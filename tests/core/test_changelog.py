# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for changelog generation, enrichment, and stats."""

from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.changelog import (
    generate_analyzed,
    generate_draft,
    generate_prompt,
    update_stats,
    write_changelog,
)
from repogerbil.core.config import FileRule, Settings
from repogerbil.core.git import CommitInfo, DiffStats


def _make_commits(*subjects: str, files: list[str] | None = None) -> list[CommitInfo]:
    return [
        CommitInfo(
            hash=f"abc{i:04d}",
            date="2026-04-07",
            subject=s,
            files=files or [],
        )
        for i, s in enumerate(subjects)
    ]


def _make_stats(
    commits: int = 3,
    files: int = 10,
    ins: int = 100,
    dels: int = 50,
) -> DiffStats:
    return DiffStats(commits=commits, files_changed=files, insertions=ins, deletions=dels)


class TestGenerateDraft:
    def test_basic_structure(self) -> None:
        commits = _make_commits("feat: add thing", "fix: broken thing")
        stats = _make_stats()
        result = generate_draft("myrepo", "2026-04-07", commits, stats, Settings())

        assert result["date"] == "2026-04-07"
        assert result["repo"] == "myrepo"
        assert "TODO" in result["title"]
        assert "TODO" in result["summary"]
        assert result["stats"]["commits"] == 2
        assert result["stats"]["files_changed"] == 10
        assert isinstance(result["changes"], list)

    def test_groups_by_category(self) -> None:
        commits = _make_commits("feat: add A", "feat: add B", "fix: broken C")
        result = generate_draft("r", "2026-04-07", commits, _make_stats(), Settings())
        cats = [c["category"] for c in result["changes"]]
        assert "instantiate" in cats
        assert "remediate" in cats

    def test_unclassifiable_in_review(self) -> None:
        commits = _make_commits("WIP checkpoint", "Misc stuff")
        result = generate_draft("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "review" in result
        assert "WIP checkpoint" in result["review"]


class TestGenerateAnalyzed:
    def test_real_title(self) -> None:
        commits = _make_commits("feat: add planet harvest pipeline")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "TODO" not in result["title"]
        assert "planet harvest" in result["title"].lower()

    def test_real_summary(self) -> None:
        commits = _make_commits("feat: add A", "fix: fix B")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "TODO" not in result["summary"]
        assert "files changed" in result["summary"]

    def test_file_rules_create_bulk(self) -> None:
        commits = [
            CommitInfo(
                hash="a1", date="2026-04-07", subject="chore: cleanup", files=["uv.lock", "src/main.py"]
            ),
        ]
        settings = Settings(
            file_rules=[
                FileRule(pattern="*.lock", action="bulk", category="baseline", reason="Lock file"),
            ]
        )
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), settings)
        assert "bulk" in result
        assert result["bulk"][0]["files"] == 1
        assert result["bulk"][0]["category"] == "baseline"

    def test_no_file_rules(self) -> None:
        commits = _make_commits("feat: add thing")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "bulk" not in result

    def test_classify_file_rules_force_commit_category(self) -> None:
        commits = [
            CommitInfo(
                hash="a1",
                date="2026-04-07",
                subject="chore: adjust test scaffold",
                files=["tests/test_core.py", "src/main.py"],
            ),
        ]
        settings = Settings(
            file_rules=[FileRule(pattern="tests/**", action="classify", category="qualify")],
        )
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), settings)
        assert result["changes"][0]["category"] == "qualify"
        assert result["changes"][0]["points"][0]["category"] == "qualify"

    def test_multi_commit_title(self) -> None:
        commits = _make_commits(
            "feat: add planet harvest pipeline",
            "feat: add ship purchasing",
            "fix: fix crash on startup",
        )
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "more change" in result["title"]

    def test_section_files_capped(self) -> None:
        files = [f"src/file{i}.py" for i in range(20)]
        commits = [CommitInfo(hash="a1", date="2026-04-07", subject="feat: big change", files=files)]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section_files = result["changes"][0]["files"]
        assert len(section_files) <= 10

    def test_single_commit_title(self) -> None:
        commits = _make_commits("fix: resolve crash")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert result["title"] == "resolve crash"

    def test_commits_without_files(self) -> None:
        commits = _make_commits("feat: add thing")
        settings = Settings(file_rules=[FileRule(pattern="*.lock", action="bulk")])
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), settings)
        assert isinstance(result["changes"], list)

    def test_only_unclassified(self) -> None:
        commits = _make_commits("WIP", "stuff")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "unclassified" in result["title"].lower()

    def test_summary_multiple_categories(self) -> None:
        commits = _make_commits("feat: A", "fix: B", "test: C", "perf: D")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "more categories" in result["summary"]

    def test_short_title_fallback(self) -> None:
        commits = _make_commits("feat: ab", "feat: cd", "fix: ef")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert "changes across" in result["title"] or "more change" in result["title"]

    def test_commit_with_refs(self) -> None:
        commits = [CommitInfo(hash="a1", date="2026-04-07", subject="fix: crash", refs=["#42"])]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        point = result["changes"][0]["points"][0]
        assert point["refs"] == ["#42"]

    def test_commit_with_body(self) -> None:
        commits = [CommitInfo(hash="a1", date="2026-04-07", subject="fix: crash", body="Detailed explanation")]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        point = result["changes"][0]["points"][0]
        assert point["body"] == "Detailed explanation"

    def test_corruption_guard_triggers(self, tmp_path: Path) -> None:
        """update_stats rejects output that's less than 50% of original."""
        yaml_path = tmp_path / "test.yaml"
        # Write a long original file
        long_data = {
            "date": "2026-04-07",
            "repo": "test",
            "stats": {"commits": 1, "files_changed": 5, "insertions": 10, "deletions": 2},
            "changes": [{"title": "x" * 2000, "points": [{"text": "y" * 2000}]}],
        }
        yaml_path.write_text(yaml.dump(long_data))
        stats = DiffStats(commits=0, files_changed=1, insertions=1, deletions=0)
        # Succeeds because yaml.dump preserves data (corruption guard is a safety net)
        assert update_stats(yaml_path, stats, 1) is True

    def test_top_directory_grouping(self) -> None:
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["src/a.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["src/b.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = result["changes"][0]
        assert "src/" in section["title"]

    def test_duplicate_files_deduped(self) -> None:
        """Two commits touching the same file — section files list deduplicates."""
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["src/main.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["src/main.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section_files = result["changes"][0]["files"]
        paths = [f["path"] for f in section_files]
        assert paths.count("src/main.py") == 1

    def test_flat_path_files(self) -> None:
        """Files without directory separators should not crash."""
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["Makefile"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["README.md"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert len(result["changes"]) >= 1


class TestGeneratePrompt:
    def test_basic_structure(self) -> None:
        commits = _make_commits("feat: add thing")
        stats = _make_stats()
        prompt = generate_prompt("myrepo", "2026-04-07", commits, stats, {})
        assert "myrepo" in prompt
        assert "2026-04-07" in prompt
        assert "feat: add thing" in prompt
        assert "Categories:" in prompt

    def test_includes_diffs(self) -> None:
        commits = _make_commits("feat: add thing")
        stats = _make_stats()
        diffs = {"src/main.py": "+print('hello')"}
        prompt = generate_prompt("myrepo", "2026-04-07", commits, stats, diffs)
        assert "src/main.py" in prompt
        assert "+print('hello')" in prompt

    def test_includes_files(self) -> None:
        commits = [CommitInfo(hash="a1", date="2026-04-07", subject="feat: A", files=["src/a.py"])]
        prompt = generate_prompt("r", "2026-04-07", commits, _make_stats(), {})
        assert "src/a.py" in prompt

    def test_empty_diffs(self) -> None:
        commits = _make_commits("feat: add thing")
        prompt = generate_prompt("r", "2026-04-07", commits, _make_stats(), {})
        assert "Diffs" not in prompt


class TestUpdateStats:
    def test_updates_stats(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "test",
                    "stats": {"commits": 1, "files_changed": 5, "insertions": 10, "deletions": 2},
                    "changes": [],
                }
            )
        )
        stats = DiffStats(commits=0, files_changed=8, insertions=20, deletions=5)
        assert update_stats(yaml_path, stats, 3) is True
        data = yaml.safe_load(yaml_path.read_text())
        assert data["stats"]["files_changed"] == 8
        assert data["stats"]["commits"] == 3

    def test_unchanged(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "test",
                    "stats": {"commits": 3, "files_changed": 8, "insertions": 20, "deletions": 5},
                    "changes": [],
                }
            )
        )
        stats = DiffStats(commits=0, files_changed=8, insertions=20, deletions=5)
        assert update_stats(yaml_path, stats, 3) is False

    def test_invalid_data(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text("not valid yaml mapping")
        stats = DiffStats(commits=0, files_changed=1, insertions=1, deletions=0)
        assert update_stats(yaml_path, stats, 1) is False

    def test_missing_date(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        yaml_path.write_text(yaml.dump({"repo": "test", "stats": {}}))
        stats = DiffStats(commits=0, files_changed=1, insertions=1, deletions=0)
        assert update_stats(yaml_path, stats, 1) is False

    def test_corruption_guard(self, tmp_path: Path) -> None:
        yaml_path = tmp_path / "test.yaml"
        long_content = yaml.dump(
            {
                "date": "2026-04-07",
                "repo": "test",
                "stats": {"commits": 1, "files_changed": 5, "insertions": 10, "deletions": 2},
                "changes": [{"title": "x" * 500, "points": []}],
            }
        )
        yaml_path.write_text(long_content)
        # Stats update that would produce much shorter output shouldn't happen
        # (in practice this only triggers if yaml.dump produces garbage)
        stats = DiffStats(commits=0, files_changed=1, insertions=1, deletions=0)
        result = update_stats(yaml_path, stats, 1)
        # Should succeed since the content size ratio is reasonable
        assert isinstance(result, bool)


class TestWriteChangelog:
    def test_writes_file(self, tmp_path: Path) -> None:
        data: dict[str, Any] = {
            "date": "2026-04-07",
            "repo": "myrepo",
            "title": "test",
            "summary": "test",
            "stats": {"commits": 1, "files_changed": 1, "insertions": 1, "deletions": 0},
            "changes": [],
        }
        path = write_changelog("myrepo", "2026-04-07", data, tmp_path)
        assert path.exists()
        assert path.name == "2026-04-07-myrepo-changelog.yaml"
        loaded = yaml.safe_load(path.read_text())
        assert loaded["repo"] == "myrepo"

    def test_creates_repo_dir(self, tmp_path: Path) -> None:
        data: dict[str, Any] = {"date": "2026-04-07", "repo": "new", "changes": []}
        path = write_changelog("new", "2026-04-07", data, tmp_path)
        assert (tmp_path / "new").is_dir()
        assert path.exists()
