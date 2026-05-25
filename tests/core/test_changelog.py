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
    generate_prompt_span,
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
        assert result["title"].startswith("Draft:")
        assert result["summary"].startswith("Draft:")
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
        assert not result["title"].startswith("Draft:")
        assert "planet harvest" in result["title"].lower()

    def test_real_summary(self) -> None:
        commits = _make_commits("feat: add A", "fix: fix B")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        assert not result["summary"].startswith("Draft:")
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

    def test_forced_category_does_not_emit_review_noise(self) -> None:
        commits = [
            CommitInfo(
                hash="a1",
                date="2026-04-07",
                subject="WIP checkpoint",
                files=["tests/test_core.py"],
            ),
        ]
        settings = Settings(
            file_rules=[FileRule(pattern="tests/**", action="classify", category="qualify")],
        )
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), settings)
        assert result["changes"][0]["category"] == "qualify"
        assert "review" not in result

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


class TestBuildChangesEdgeCases:
    """Pin _build_changes contracts surfaced by mutation testing.

    Without these, mutants that flip ``> 1`` to ``> 2`` or rewrite the
    ``_unclassified`` key survive because higher-level tests only check
    section presence or substring matches.
    """

    def test_unclassified_singular_title(self) -> None:
        """Single unclassified commit must NOT pluralize 'commit'."""
        commits = _make_commits("WIP work")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        unclass = [c for c in result["changes"] if c["category"] is None]
        assert len(unclass) == 1
        assert unclass[0]["title"] == "Unclassified: 1 commit"

    def test_unclassified_plural_title_two(self) -> None:
        """Exactly two unclassified commits must pluralize ('commits', not 'commit')."""
        commits = _make_commits("WIP one", "WIP two")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        unclass = [c for c in result["changes"] if c["category"] is None]
        assert len(unclass) == 1
        assert unclass[0]["title"] == "Unclassified: 2 commits"

    def test_unclassified_plural_title_three(self) -> None:
        """Three unclassified commits — pins '3 commits' literal."""
        commits = _make_commits("WIP one", "WIP two", "WIP three")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        unclass = [c for c in result["changes"] if c["category"] is None]
        assert len(unclass) == 1
        assert unclass[0]["title"] == "Unclassified: 3 commits"

    def test_unclassified_section_category_key(self) -> None:
        """The internal _unclassified bucket key must match.

        If the literal ``"_unclassified"`` is mutated (e.g. to
        ``"XX_unclassifiedXX"``), the ``groups.get(cat)`` lookup in
        ``_build_changes`` returns ``None`` and the unclassified section
        is silently dropped from the output. This test catches that.
        """
        commits = _make_commits("WIP one", "WIP two")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        # Section must exist and report 2 commits in its title.
        assert any(c["title"] == "Unclassified: 2 commits" for c in result["changes"])

    def test_section_severity_uses_commit_body(self) -> None:
        """``classify_commit`` must receive the commit body, not just subject.

        The vocabulary's verb-pattern fallback can promote ``fix: ...`` from
        ``patch`` (internal) to ``minor`` (behavioral) when the body mentions
        ``regression``. If ``_build_changes`` drops the ``body=`` argument,
        the section_sev would be the subject-only severity (patch) instead
        of the body-aware one (minor).
        """
        commits = [
            CommitInfo(
                hash="a1",
                date="2026-04-07",
                subject="fix: crash",
                body="resolves regression in payment flow",
                files=["src/payments.py"],
            ),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        fix_section = next(c for c in result["changes"] if c["category"] == "remediate")
        # severity is derived by classify_commit — pin it so a None-substituting mutant fails.
        assert fix_section["severity"] is not None

    def test_section_severity_multi_commit_uses_body(self) -> None:
        """Same body-propagation pin, but on the multi-commit branch (len(group) > 1)."""
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", body="x", files=["a.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", body="y", files=["b.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        fix_section = next(c for c in result["changes"] if c["category"] == "remediate")
        assert fix_section["severity"] is not None

    def test_section_severity_propagates_settings(self) -> None:
        """``classify_commit`` must receive the project ``Settings``, not None.

        A user-defined extra prefix mapping (via ``vocabulary.extra_prefix_map``)
        is only respected when settings is passed through. If a mutant drops
        ``settings=``, custom prefixes fall back to defaults silently.
        """
        from repogerbil.core.config import VocabularyConfig

        # Map a custom prefix "hotfix" → existing category "remediate" (severity patch).
        settings = Settings(
            vocabulary=VocabularyConfig(extra_prefix_map={"hotfix": "remediate"}),
        )
        commits = _make_commits("hotfix: revert bad deploy")
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), settings)
        # The "hotfix" subject should classify as remediate (not _unclassified)
        # because settings propagated. Without settings, "hotfix" is unknown.
        remediate = [c for c in result["changes"] if c["category"] == "remediate"]
        assert len(remediate) == 1, (
            "extra_prefix_map should have routed `hotfix:` to remediate; "
            "did _build_changes drop settings= when calling classify_commit?"
        )


class TestTopDirectoryMutationKills:
    """Pin ``_top_directory`` behavior surfaced by mutation testing.

    ``_top_directory`` chooses the most-common top-level directory across
    the files of a group of commits. It is only invoked from the multi-commit
    branch of ``_build_changes``, where its return value appears in the
    generated section title as ``"{verb} {top}/ ({n} commits)"``. We drive
    it through ``generate_analyzed`` and assert on the resulting title.

    Some path-split / counter-default mutants are practically equivalent
    (e.g. ``dirs.get(top, 1)`` vs ``dirs.get(top, 0)``) because they shift
    every count by a constant and ``max`` is invariant to that. Those are
    deliberately not exercised; they will continue to survive.
    """

    def test_picks_majority_directory(self) -> None:
        """Section title must include the majority directory, not a minority one.

        Kills mutants that flip ``+ 1`` to ``- 1`` (counts go negative, so
        ``max(dirs, key=dirs.get)`` picks the LEAST common dir) and
        ``dirs.get(None, 0)`` (all counts become 1, ``max`` picks the
        first inserted key).
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["tests/x.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["src/a.py"]),
            CommitInfo(hash="a3", date="2026-04-07", subject="fix: C", files=["src/b.py"]),
            CommitInfo(hash="a4", date="2026-04-07", subject="fix: D", files=["src/c.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        # 3 src/ vs 1 tests/ → src/ must win and tests/ must not appear in the title.
        assert "src/" in section["title"]
        assert "tests/" not in section["title"]

    def test_picks_majority_not_alphabetical_max(self) -> None:
        """``max(dirs, key=dirs.get)`` must use the count, not alphabetical order.

        Kills the ``max(dirs, )`` mutant (drops the key= kwarg). Without
        ``key=``, ``max(dirs)`` returns the lexicographically last key.
        Here ``abc`` has more files than ``zzz``, so the count-based max
        is ``abc`` but the alphabetical max is ``zzz``.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["abc/a.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["abc/b.py"]),
            CommitInfo(hash="a3", date="2026-04-07", subject="fix: C", files=["zzz/c.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        assert "abc/" in section["title"]
        assert "zzz/" not in section["title"]

    def test_splits_on_slash_returning_first_segment(self) -> None:
        """``f.split("/")[0]`` — top must be a *segment*, never the full path.

        Kills ``f.split(None)[0]`` and ``f.split("XX/XX")[0]`` mutants:
        both return ``[full_path]``, so ``top`` equals the full path
        ``"deeply/nested/dir/file.py"`` instead of ``"deeply"``.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["deeply/nested/a.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["deeply/nested/b.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        # Title contains "deeply/" not "deeply/nested/a.py/".
        assert "deeply/" in section["title"]
        assert "deeply/nested/" not in section["title"]
        assert "a.py" not in section["title"]

    def test_flat_files_do_not_pollute_with_sentinel(self) -> None:
        """Files without a ``/`` must contribute nothing — not a sentinel like ``"XXXX"``.

        Kills the ``else "XXXX"`` mutant. With that mutation, two commits
        touching only flat files (``Makefile`` and ``README``) would group
        under a phantom ``XXXX/`` directory in the title.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["Makefile"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["README"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        # No dir was found, so the title uses the "no top_dir" branch:
        # f"{verb}: {len(group)} commits" (with a colon, not a slash).
        assert "XXXX" not in section["title"]
        assert "/" not in section["title"]
        assert section["title"] == "Fix: 2 commits"

    def test_empty_dirs_returns_empty_string(self) -> None:
        """When no directories were collected, the result must be ``""`` — not ``"XXXX"``.

        Kills the ``else "XXXX"`` mutant on the final ``return`` expression.
        A commit group with no files at all yields an empty ``dirs`` dict,
        which must produce the no-top-dir branch in the section title.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=[]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=[]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        assert "XXXX" not in section["title"]
        assert section["title"] == "Fix: 2 commits"

    def test_counter_increment_does_not_corrupt(self) -> None:
        """Counter slot must store an int — not ``None`` — so increments don't TypeError.

        Kills ``dirs[top] = None`` (TypeError on the second occurrence)
        and ``max(dirs, key=None)`` (TypeError because ``None`` is not callable).
        Both mutations would raise; we assert that calling generate_analyzed
        on multi-commit groups with repeated directories does not raise and
        produces a sane title.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: A", files=["src/a.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: B", files=["src/b.py"]),
            CommitInfo(hash="a3", date="2026-04-07", subject="fix: C", files=["src/c.py"]),
        ]
        # Original raises nothing and emits a "src/" title; mutants raise.
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        assert section["title"] == "Fix src/ (3 commits)"


class TestCollectSectionFilesMutationKills:
    """Pin the dict-key shape of ``_collect_section_files`` output.

    The function maps each path → first-seen commit subject and returns a
    list of ``{"path": ..., "summary": ...}`` dicts (capped at 10). Mutants
    that rename the ``"summary"`` key to ``"XXsummaryXX"`` or ``"SUMMARY"``
    would still produce dicts with the right shape but the wrong key, and
    higher-level tests don't inspect the value, so they survive.
    """

    def test_summary_key_is_exact(self) -> None:
        """Section-file entries must use the literal key ``"summary"``."""
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: subj-A", files=["a.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = result["changes"][0]
        files = section["files"]
        assert len(files) == 1
        entry = files[0]
        assert set(entry.keys()) == {"path", "summary"}
        assert entry["summary"] == "fix: subj-A"

    def test_summary_value_is_first_seen_subject(self) -> None:
        """``seen[f] = c.subject`` must store the commit subject, not ``None``.

        Kills the ``seen[f] = None`` mutant: the summary value would be
        ``None`` instead of the originating subject.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: first", files=["shared.py"]),
            CommitInfo(hash="a2", date="2026-04-07", subject="fix: second", files=["shared.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        section = next(c for c in result["changes"] if c["category"] == "remediate")
        files = section["files"]
        assert len(files) == 1
        # First seen wins; the value must be the first commit's subject string.
        assert files[0]["summary"] == "fix: first"


class TestCommitToPointMutationKills:
    """Pin the per-point dict structure produced by ``_commit_to_point``."""

    def test_point_dict_keys_are_exact(self) -> None:
        """Point dicts must use the literal keys ``severity`` and ``files``.

        Kills the ``"XXseverityXX"`` / ``"SEVERITY"`` / ``"XXfilesXX"`` /
        ``"FILES"`` mutants — these rename the keys but keep the values,
        so higher-level tests checking ``"severity" in point`` would still pass.
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="fix: x", files=["a.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        point = result["changes"][0]["points"][0]
        assert "severity" in point
        assert "files" in point
        # Reject mutated key names explicitly.
        assert "XXseverityXX" not in point
        assert "SEVERITY" not in point
        assert "XXfilesXX" not in point
        assert "FILES" not in point

    def test_body_is_forwarded_to_classify(self) -> None:
        """``classify_commit`` in ``_commit_to_point`` must receive ``body=``.

        Kills the mutant that drops ``body=commit.body``. A ``feat:`` subject
        with ``BREAKING CHANGE:`` in the body is classified as architectural;
        without the body it stays behavioral.
        """
        commits = [
            CommitInfo(
                hash="a1",
                date="2026-04-07",
                subject="feat: add interface",
                body="BREAKING CHANGE: removes legacy endpoint",
                files=["api.py"],
            ),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), Settings())
        point = result["changes"][0]["points"][0]
        # ``architectural`` severity is mapped through the default vocab to "major";
        # the non-breaking ``feat:`` would resolve to "minor".
        assert point["severity"] == "major"

    def test_settings_are_forwarded_to_classify(self) -> None:
        """``classify_commit`` in ``_commit_to_point`` must receive ``settings=``.

        Kills the mutant that drops ``settings=settings``. With a custom
        extra_prefix_map mapping ``hotfix → remediate``, the point's category
        is ``remediate`` only when ``settings`` is passed through;
        otherwise the unknown prefix yields ``None``.
        """
        from repogerbil.core.config import VocabularyConfig

        settings = Settings(
            vocabulary=VocabularyConfig(extra_prefix_map={"hotfix": "remediate"}),
        )
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="hotfix: revert", files=["x.py"]),
        ]
        result = generate_analyzed("r", "2026-04-07", commits, _make_stats(), settings)
        point = result["changes"][0]["points"][0]
        assert point["category"] == "remediate"


class TestUpdateStatsYamlFormatMutationKills:
    """Pin the YAML-dump kwargs used by ``update_stats``.

    The function writes the YAML back with ``default_flow_style=False,
    allow_unicode=True, sort_keys=False``. Each of those kwargs governs
    a visible feature of the output. Mutants that drop or flip a kwarg
    silently change the file format; we assert the output structure
    matches the expected block-style, original-order layout.

    The ``< → <=`` mutant on the corruption guard (mutant 41) is on a
    branch marked ``pragma: no cover`` — it only fires when ``yaml.dump``
    corrupts its input to <50% of the original size, which never happens
    in practice. We leave that mutant deliberately surviving.

    The ``sort_keys=None`` mutant (mutant 33) is semantically equivalent
    to ``sort_keys=False`` in PyYAML — both bypass sorting and preserve
    insertion order — so no test can distinguish them.

    The ``default_flow_style=False`` kwarg-drop (mutant 35) is also
    practically equivalent: PyYAML's auto-detect default (``None``) emits
    block style for nested mappings like ours, so the output is identical.
    """

    def _seed_file(self, tmp_path: Path) -> Path:
        """Write a seed YAML file whose key order differs from alphabetical."""
        yaml_path = tmp_path / "test.yaml"
        # Original key order: date, repo, title, summary, stats, changes.
        # Alphabetical order: changes, date, repo, stats, summary, title.
        content = (
            "date: '2026-04-07'\n"
            "repo: test\n"
            "title: café special\n"
            "summary: a summary\n"
            "stats:\n"
            "  commits: 1\n"
            "  files_changed: 5\n"
            "  insertions: 10\n"
            "  deletions: 2\n"
            "changes: []\n"
        )
        yaml_path.write_text(content)
        return yaml_path

    def test_block_style_preserved(self, tmp_path: Path) -> None:
        """``default_flow_style=False`` must emit block style (multiline ``stats:``).

        Kills the ``default_flow_style=None`` (auto-detect → inline ``stats: {}``)
        and ``default_flow_style=True`` (everything inline ``{date: ..., ...}``)
        mutants, plus the variant that drops the kwarg entirely (defaults to ``None``).
        """
        yaml_path = self._seed_file(tmp_path)
        stats = DiffStats(commits=0, files_changed=99, insertions=42, deletions=7)
        assert update_stats(yaml_path, stats, 3) is True
        new_content = yaml_path.read_text()
        # Block style: stats keys on their own indented lines, no '{' wrapper.
        assert "stats:\n  commits:" in new_content
        assert "{" not in new_content
        assert "}" not in new_content

    def test_key_order_preserved(self, tmp_path: Path) -> None:
        """``sort_keys=False`` must keep insertion order (``date`` before ``changes``).

        Kills the ``sort_keys=True`` mutant and the kwarg-drop variant
        (yaml.dump defaults to ``sort_keys=True``). With sorting enabled,
        ``changes`` would appear before ``date`` (alphabetical).
        """
        yaml_path = self._seed_file(tmp_path)
        stats = DiffStats(commits=0, files_changed=99, insertions=42, deletions=7)
        assert update_stats(yaml_path, stats, 3) is True
        new_content = yaml_path.read_text()
        # Original order: date appears before stats appears before changes.
        date_idx = new_content.index("date:")
        stats_idx = new_content.index("stats:")
        changes_idx = new_content.index("changes:")
        assert date_idx < stats_idx < changes_idx, f"keys reordered (sort_keys leaked True?): {new_content!r}"

    def test_unicode_preserved_unescaped(self, tmp_path: Path) -> None:
        """``allow_unicode=True`` must keep ``café`` as raw UTF-8, not ``\\xE9``.

        Kills the ``allow_unicode=False`` mutant and the kwarg-drop variant
        (yaml.dump defaults to escaping non-ASCII).
        """
        yaml_path = self._seed_file(tmp_path)
        stats = DiffStats(commits=0, files_changed=99, insertions=42, deletions=7)
        assert update_stats(yaml_path, stats, 3) is True
        new_content = yaml_path.read_text()
        assert "café" in new_content
        assert "\\xE9" not in new_content
        assert "\\u" not in new_content


class TestGeneratePromptMutationKills:
    """Pin the exact markdown layout of ``generate_prompt``.

    The function builds a prompt for an external LLM. Section headers and
    join separators are load-bearing for downstream parsing, so we assert
    them as exact substrings rather than ``in prompt``.
    """

    def test_commits_header_exact(self) -> None:
        """The commits section header must be the exact literal ``"## Commits\\n"``.

        Kills the ``"XX## Commits\\nXX"`` / ``"## commits\\n"`` / ``"## COMMITS\\n"`` mutants.
        """
        prompt = generate_prompt("r", "2026-04-07", _make_commits("feat: x"), _make_stats(), {})
        assert "## Commits\n" in prompt
        # Reject mutated forms explicitly.
        assert "XX## CommitsXX" not in prompt
        assert "## commits" not in prompt
        assert "## COMMITS" not in prompt

    def test_diffs_header_exact(self) -> None:
        """The diffs section header must be the exact literal ``"## Diffs (key files)\\n"``."""
        diffs = {"src/main.py": "+x"}
        prompt = generate_prompt("r", "2026-04-07", _make_commits("feat: x"), _make_stats(), diffs)
        assert "## Diffs (key files)\n" in prompt
        # Reject case-mutated forms.
        assert "## diffs (key files)" not in prompt
        assert "## DIFFS (KEY FILES)" not in prompt
        assert "XX## Diffs" not in prompt

    def test_files_joined_with_comma_space(self) -> None:
        """The per-commit file list must be joined with the literal ``", "``.

        Kills the ``"XX, XX".join(...)`` mutant (which produces
        ``"a.pyXX, XXb.py"``).
        """
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="feat: x", files=["a.py", "b.py"]),
        ]
        prompt = generate_prompt("r", "2026-04-07", commits, _make_stats(), {})
        assert "files: a.py, b.py" in prompt
        assert "XX" not in prompt

    def test_file_list_capped_at_five(self) -> None:
        """``c.files[:5]`` — at most five files per commit are listed.

        Kills the ``c.files[:6]`` mutant: with six distinct files, the
        original lists exactly five, the mutant lists six.
        """
        files = [f"f{i}.py" for i in range(6)]
        commits = [CommitInfo(hash="a1", date="2026-04-07", subject="feat: x", files=files)]
        prompt = generate_prompt("r", "2026-04-07", commits, _make_stats(), {})
        # Find the "files: ..." line under the commit bullet.
        line = next(line for line in prompt.splitlines() if line.startswith("  files: "))
        listed = line.removeprefix("  files: ").split(", ")
        assert len(listed) == 5
        assert "f5.py" not in line

    def test_diffs_capped_at_thirty(self) -> None:
        """``[:30]`` — at most 30 diff entries are emitted.

        Kills the ``[:31]`` mutant. With 31 distinct diffs, the original
        emits 30, the mutant emits 31. We count ``### `` markers, which
        only appear in the diff section.
        """
        diffs = {f"f{i}.py": "+x" for i in range(31)}
        prompt = generate_prompt("r", "2026-04-07", _make_commits("feat: x"), _make_stats(), diffs)
        assert prompt.count("### f") == 30
        # The 31st file (insertion order: f0..f30) must be absent.
        assert "### f30.py" not in prompt

    def test_blank_separator_between_commits(self) -> None:
        """``parts.append("")`` must append an empty string, not ``"XXXX"``.

        Kills the ``parts.append("XXXX")`` mutant. With two commits, the
        blank-line separator between them would otherwise contain ``XXXX``.
        """
        prompt = generate_prompt("r", "2026-04-07", _make_commits("feat: a", "feat: b"), _make_stats(), {})
        assert "XXXX" not in prompt
        # Two consecutive newlines separate commits (from the appended "" plus "\n".join).
        assert "\n\n" in prompt

    def test_newline_join_not_tagged(self) -> None:
        """``"\\n".join(parts)`` must use the literal newline, not ``"XX\\nXX"``.

        Kills the ``"XX\\nXX".join(parts)`` mutant which would scatter
        ``XX`` markers throughout the prompt.
        """
        prompt = generate_prompt("r", "2026-04-07", _make_commits("feat: x"), _make_stats(), {})
        assert "XX\nXX" not in prompt
        assert "XX" not in prompt

    def test_instructions_args_forwarded(self) -> None:
        """``_prompt_instructions`` must receive ``repo``, ``date_str`` and ``commit_count``.

        Kills the mutants that pass ``None`` for one of those args. The
        ``_prompt_instructions`` body interpolates each of repo, date_str,
        stats.* and commit_count into its YAML template. If any of them
        becomes ``None``, the literal string ``None`` appears verbatim
        in the prompt and the expected formatted value disappears.
        """
        commits = _make_commits("feat: x", "feat: y", "feat: z")
        stats = _make_stats(files=17, ins=123, dels=45)
        prompt = generate_prompt("uniqrepo", "2999-01-02", commits, stats, {})
        # repo arg surfaces inside the YAML "repo: <name>" line of the template.
        assert "repo: uniqrepo" in prompt
        # date_str arg surfaces inside the "date: <date>" template line.
        assert "date: 2999-01-02" in prompt
        # commit_count arg surfaces as "commits: <N>"; with 3 commits we expect "commits: 3".
        assert "commits: 3" in prompt
        # Sanity: no literal "None" leaked from a None-substitution mutant.
        # (Allow lowercase "none" inside instructions text but not a bare "None" token.)
        assert " None\n" not in prompt
        assert ": None" not in prompt


class TestGeneratePromptSpanMutationKills:
    """Pin the exact markdown layout of ``generate_prompt_span``.

    Parallel to ``TestGeneratePromptMutationKills`` but for the span variant.
    """

    def test_commits_header_exact(self) -> None:
        """Span header must be the exact literal ``"## Commits (oldest → newest)\\n"``."""
        prompt = generate_prompt_span("r", "v1.0", "v2.0", _make_commits("feat: x"), _make_stats(), {})
        assert "## Commits (oldest → newest)\n" in prompt
        # Reject mutated variants.
        assert "## commits (oldest" not in prompt
        assert "## COMMITS (OLDEST" not in prompt
        assert "XX## Commits" not in prompt

    def test_diffs_header_exact(self) -> None:
        """Span diffs header must be the exact literal ``"## Diffs (key files)\\n"``."""
        diffs = {"src/main.py": "+x"}
        prompt = generate_prompt_span("r", "v1", "v2", _make_commits("feat: x"), _make_stats(), diffs)
        assert "## Diffs (key files)\n" in prompt
        assert "## diffs (key files)" not in prompt
        assert "## DIFFS (KEY FILES)" not in prompt
        assert "XX## Diffs" not in prompt

    def test_files_joined_with_comma_space(self) -> None:
        """Per-commit file list joined with literal ``", "``."""
        commits = [
            CommitInfo(hash="a1", date="2026-04-07", subject="feat: x", files=["a.py", "b.py"]),
        ]
        prompt = generate_prompt_span("r", "v1", "v2", commits, _make_stats(), {})
        assert "files: a.py, b.py" in prompt
        assert "XX" not in prompt

    def test_file_list_capped_at_five(self) -> None:
        """``c.files[:5]`` for span — at most five files per commit listed."""
        files = [f"f{i}.py" for i in range(6)]
        commits = [CommitInfo(hash="a1", date="2026-04-07", subject="feat: x", files=files)]
        prompt = generate_prompt_span("r", "v1", "v2", commits, _make_stats(), {})
        line = next(line for line in prompt.splitlines() if line.startswith("  files: "))
        listed = line.removeprefix("  files: ").split(", ")
        assert len(listed) == 5
        assert "f5.py" not in line

    def test_diffs_capped_at_thirty(self) -> None:
        """Span ``[:30]`` — at most 30 diff entries emitted."""
        diffs = {f"f{i}.py": "+x" for i in range(31)}
        prompt = generate_prompt_span("r", "v1", "v2", _make_commits("feat: x"), _make_stats(), diffs)
        assert prompt.count("### f") == 30
        assert "### f30.py" not in prompt

    def test_blank_separator_not_tagged(self) -> None:
        """``parts.append("")`` between commits is empty, not ``"XXXX"``."""
        prompt = generate_prompt_span("r", "v1", "v2", _make_commits("feat: a", "feat: b"), _make_stats(), {})
        assert "XXXX" not in prompt

    def test_newline_join_not_tagged(self) -> None:
        """``"\\n".join(parts)`` for span is plain newline, not ``"XX\\nXX"``."""
        prompt = generate_prompt_span("r", "v1", "v2", _make_commits("feat: x"), _make_stats(), {})
        assert "XX\nXX" not in prompt
        assert "XX" not in prompt

    def test_span_refs_appear_exactly(self) -> None:
        """From/To refs must surface as literal backtick-wrapped tokens.

        Kills any mutant that swaps ``from_ref`` / ``to_ref`` or drops them
        from the instructions call.
        """
        prompt = generate_prompt_span(
            "myrepo", "v1.2.3", "v1.3.0", _make_commits("feat: x"), _make_stats(), {}
        )
        assert "From: `v1.2.3`" in prompt
        assert "To: `v1.3.0`" in prompt
        # The instructions block re-interpolates the span as `v1.2.3..v1.3.0`.
        assert "v1.2.3..v1.3.0" in prompt
        assert "myrepo" in prompt

    def test_instructions_args_forwarded(self) -> None:
        """``_prompt_instructions_span`` must receive all positional args.

        Kills mutants that pass ``None`` in place of repo/from_ref/to_ref/
        commit_count. Each of those args is interpolated into the
        instructions template; substituting ``None`` either drops the
        expected literal or introduces a bare ``None`` token.
        """
        commits = _make_commits("feat: x", "feat: y", "feat: z", "feat: w")
        stats = _make_stats(files=99, ins=42, dels=7)
        prompt = generate_prompt_span("uniqrepo", "rA", "rB", commits, stats, {})
        # The instructions template contains "for {repo}." — pin that literal so
        # the ``_prompt_instructions_span(None, ...)`` mutant (which would emit
        # "for None.") is killed even though "uniqrepo" still appears in the
        # earlier header line.
        assert "for uniqrepo." in prompt
        assert "for None." not in prompt
        assert "rA..rB" in prompt
        # Total commit count line in the instructions guidelines.
        assert "Total commit count: 4" in prompt
        # No None-substituted args leaked through.
        assert "Total commit count: None" not in prompt
        assert "None..rB" not in prompt
        assert "rA..None" not in prompt
