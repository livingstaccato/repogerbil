# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for distill-ecosystem command."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

from click.testing import CliRunner

from repogerbil.cli.commands.distill_cmds import _find_source_repo
from repogerbil.cli.main import cli
from repogerbil.core.errors import GitCommandError


def _init_test_repo(repo_path: Path, commits: list[str]) -> None:
    """Create a test git repo with specified commits on the same date."""
    repo_path.mkdir(exist_ok=True)
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo_path,
        check=True,
        capture_output=True,
    )

    # Create commits on 2026-04-05
    for i, msg in enumerate(commits):
        (repo_path / f"file{i}.txt").write_text(f"content {i}")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        env = {
            "GIT_AUTHOR_DATE": "2026-04-05 10:00:00 +0000",
            "GIT_COMMITTER_DATE": "2026-04-05 10:00:00 +0000",
        }
        subprocess.run(
            ["git", "commit", "-m", msg],
            cwd=repo_path,
            check=True,
            capture_output=True,
            env=env,
        )


def _make_changelog_yaml(changelog_dir: Path, date: str, title: str, category: str) -> None:
    """Create a changelog YAML file."""
    repo_name = changelog_dir.name
    yaml_content = f"""date: {date}
repository: {repo_name}
title: "{title}"
summary: "Test changelog"
changes:
  - category: {category}
    description: "Test change"
    points:
      - "Item 1"
"""
    changelog_dir.mkdir(parents=True, exist_ok=True)
    (changelog_dir / f"{date}-{repo_name}-changelog.yaml").write_text(yaml_content)


class TestDistillEcosystem:
    def test_finds_source_in_repo_bak(self, tmp_path: Path) -> None:
        """Fallback lookup checks repo-bak when the primary root is absent."""
        source_base = tmp_path / "source"
        repo_bak = source_base / "repo-bak" / "repo1"
        repo_bak.mkdir(parents=True)

        assert _find_source_repo("repo1", source_base) == repo_bak

    def test_dry_run_lists_targets(self, tmp_path: Path) -> None:
        """Dry run prints target names without creating repos."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        # Create source repos
        source_base.mkdir()
        _init_test_repo(source_base / "repo1", ["Initial commit"])
        _init_test_repo(source_base / "repo2", ["Initial commit"])

        # Create changelog dirs with YAML
        report_base.mkdir(parents=True, exist_ok=True)
        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Add feature", "instantiate")
        _make_changelog_yaml(report_base / "repo2", "2026-04-05", "Fix bug", "remediate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "1",
                "--dry-run",
            ],
        )

        assert result.exit_code == 0
        assert "repo1" in result.output
        assert "repo2" in result.output
        assert "DRY RUN" in result.output
        assert not (dest_base / "repo1").exists()

    def test_distills_two_repos_in_parallel(self, tmp_path: Path) -> None:
        """Distill two repos, verify output dirs created."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Initial commit"])
        _init_test_repo(source_base / "repo2", ["Fix issue"])

        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Add widget", "instantiate")
        _make_changelog_yaml(report_base / "repo2", "2026-04-05", "Resolve bug", "remediate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "1",
                "--parallel",
                "2",
            ],
        )

        assert result.exit_code == 0
        assert (dest_base / "repo1").exists()
        assert (dest_base / "repo2").exists()

        # Verify commits exist
        repo1_commits = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=dest_base / "repo1",
            capture_output=True,
            text=True,
        ).stdout.strip()
        assert "Add widget" in repo1_commits or "feat:" in repo1_commits

    def test_skips_missing_source(self, tmp_path: Path) -> None:
        """One source missing, other distilled successfully."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Commit"])

        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title 1", "instantiate")
        _make_changelog_yaml(report_base / "repo2", "2026-04-05", "Title 2", "remediate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "1",
            ],
        )

        assert result.exit_code == 0
        assert "source not found" in result.output
        assert (dest_base / "repo1").exists()
        assert not (dest_base / "repo2").exists()

    def test_min_changelogs_filter(self, tmp_path: Path) -> None:
        """Only repos with >= min changelogs are distilled."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Commit"])
        _init_test_repo(source_base / "repo2", ["Commit"])

        # repo1 has 2 changelogs, repo2 has 1
        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title", "instantiate")
        _make_changelog_yaml(report_base / "repo1", "2026-04-06", "Title 2", "instantiate")
        _make_changelog_yaml(report_base / "repo2", "2026-04-05", "Title", "instantiate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "2",  # Only repo1 qualifies
            ],
        )

        assert result.exit_code == 0
        assert (dest_base / "repo1").exists()
        assert not (dest_base / "repo2").exists()

    def test_prefixed_count_in_result(self, tmp_path: Path) -> None:
        """Result includes prefixed commit count."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Commit 1", "Commit 2"])

        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Feature A", "instantiate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "1",
            ],
        )

        assert result.exit_code == 0
        # Should report commits and prefixed count
        assert "commits" in result.output.lower()

    def test_dest_already_exists_error(self, tmp_path: Path) -> None:
        """Non-empty dest repo is skipped with error."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Commit"])

        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title", "instantiate")

        # Create a non-empty dest
        dest_base.mkdir()
        (dest_base / "repo1").mkdir()
        (dest_base / "repo1" / ".git").mkdir()

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "1",
            ],
        )

        assert result.exit_code == 0
        # Should report an error for repo1 (already exists)
        assert "✗" in result.output

    def test_no_repos_found_when_no_directory_meets_threshold(self, tmp_path: Path) -> None:
        """Non-directories are ignored and low-changelog repos are skipped."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        (report_base / "README.txt").write_text("ignore me")
        _init_test_repo(source_base / "repo1", ["Commit"])
        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title", "instantiate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "2",
            ],
        )

        assert result.exit_code == 0
        assert "No repos found matching criteria" in result.output

    def test_no_commits_found_leads_to_no_valid_targets(self, tmp_path: Path) -> None:
        """An empty source repo is reported and produces no distillation targets."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        (source_base / "repo1").mkdir()
        subprocess.run(["git", "init"], cwd=source_base / "repo1", check=True, capture_output=True)
        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title", "instantiate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--min-changelogs",
                "1",
            ],
        )

        assert result.exit_code == 0
        assert "no commits found" in result.output
        assert "No valid targets to distill" in result.output

    def test_targets_flag_overrides_discovery(self, tmp_path: Path) -> None:
        """--targets flag restricts to specified repos only."""
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"

        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Commit"])
        _init_test_repo(source_base / "repo2", ["Commit"])

        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title 1", "instantiate")
        _make_changelog_yaml(report_base / "repo2", "2026-04-05", "Title 2", "instantiate")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "distill-ecosystem",
                "--source-base",
                str(source_base),
                "--report-base",
                str(report_base),
                "--dest-base",
                str(dest_base),
                "--targets",
                "repo1",  # Only repo1
                "--min-changelogs",
                "1",
            ],
        )

        assert result.exit_code == 0
        assert (dest_base / "repo1").exists()
        assert not (dest_base / "repo2").exists()

    def test_branch_resolution_failure_skips_repo(self, tmp_path: Path) -> None:
        source_base = tmp_path / "source"
        report_base = tmp_path / "reports"
        dest_base = tmp_path / "dest"
        source_base.mkdir()
        report_base.mkdir(parents=True, exist_ok=True)
        _init_test_repo(source_base / "repo1", ["Commit"])
        _make_changelog_yaml(report_base / "repo1", "2026-04-05", "Title", "instantiate")

        with patch(
            "repogerbil.cli.commands.distill_cmds._ecosystem.resolve_head_branch",
            side_effect=GitCommandError("no-branch", returncode=1, stderr="no-branch"),
        ):
            result = CliRunner().invoke(
                cli,
                [
                    "distill-ecosystem",
                    "--source-base",
                    str(source_base),
                    "--report-base",
                    str(report_base),
                    "--dest-base",
                    str(dest_base),
                    "--min-changelogs",
                    "1",
                ],
            )
        assert result.exit_code == 0
        assert "unable to resolve HEAD branch" in result.output
        assert "No valid targets to distill" in result.output
