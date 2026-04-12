# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for snapshot/distill CLI commands."""

from __future__ import annotations

from pathlib import Path
import subprocess

from click.testing import CliRunner
import yaml

from repogerbil.cli.main import cli


def _init_test_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with two commits on the same date."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / "f.py").write_text("x\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
    )
    (repo / "g.py").write_text("y\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: second"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
    )
    return repo


class TestMultiSnapshot:
    def test_basic_invocation(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "multi"
        result = CliRunner().invoke(cli, ["multi-snapshot", str(dest), "--repo", f"testrepo:{repo}"])
        assert result.exit_code == 0
        assert "Multi-snapshot created" in result.output

    def test_dry_run(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "multi"
        result = CliRunner().invoke(
            cli, ["multi-snapshot", str(dest), "--repo", f"testrepo:{repo}", "--dry-run"]
        )
        assert result.exit_code == 0
        assert "Would create" in result.output

    def test_dry_run_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "multi"
        result = CliRunner().invoke(
            cli,
            ["multi-snapshot", str(dest), "--repo", f"testrepo:{repo}", "--dry-run", "--since", "2026-04-07"],
        )
        assert result.exit_code == 0
        assert "Would create" in result.output

    def test_dry_run_many_dates(self, tmp_path: Path) -> None:
        """Dry run with > 10 dates shows overflow message."""
        repo = tmp_path / "many"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        for i in range(12):
            (repo / f"f{i}.py").write_text(f"x{i}\n")
            subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: change {i}"],
                cwd=repo,
                capture_output=True,
                check=True,
                env={
                    **env,
                    "GIT_AUTHOR_DATE": f"2026-01-{10 + i:02d}T12:00:00",
                    "GIT_COMMITTER_DATE": f"2026-01-{10 + i:02d}T12:00:00",
                },
            )
        dest = tmp_path / "multi"
        result = CliRunner().invoke(cli, ["multi-snapshot", str(dest), "--repo", f"many:{repo}", "--dry-run"])
        assert result.exit_code == 0
        assert "... and" in result.output

    def test_no_repos_errors(self, tmp_path: Path) -> None:
        dest = tmp_path / "multi"
        result = CliRunner().invoke(cli, ["multi-snapshot", str(dest)])
        assert result.exit_code == 1

    def test_bad_repo_format_errors(self, tmp_path: Path) -> None:
        dest = tmp_path / "multi"
        result = CliRunner().invoke(cli, ["multi-snapshot", str(dest), "--repo", "nocolon"])
        assert result.exit_code == 1

    def test_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "multi"
        result = CliRunner().invoke(
            cli, ["multi-snapshot", str(dest), "--repo", f"testrepo:{repo}", "--since", "2026-04-07"]
        )
        assert result.exit_code == 0
        assert "Multi-snapshot created" in result.output

    def test_with_changelog_dir(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl" / "testrepo"
        cl_dir.mkdir(parents=True)
        changelog = {
            "date": "2026-04-07",
            "repo": "testrepo",
            "title": "Daily update",
            "summary": "Two changes.",
        }
        (cl_dir / "2026-04-07-testrepo-changelog.yaml").write_text(yaml.dump(changelog))
        dest = tmp_path / "multi"
        result = CliRunner().invoke(
            cli,
            [
                "multi-snapshot",
                str(dest),
                "--repo",
                f"testrepo:{repo}",
                "--changelog-dir",
                str(tmp_path / "cl"),
            ],
        )
        assert result.exit_code == 0
        assert "Multi-snapshot created" in result.output


class TestSnapshot:
    def test_basic_snapshot(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest)])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output

    def test_snapshot_with_extra_source(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        extra = tmp_path / "extra"
        extra.mkdir()
        subprocess.run(["git", "init"], cwd=extra, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=extra, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=extra, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (extra / "old.py").write_text("old\n")
        subprocess.run(["git", "add", "."], cwd=extra, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: old era"],
            cwd=extra,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-01-01T10:00:00", "GIT_COMMITTER_DATE": "2026-01-01T10:00:00"},
        )
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest), "--extra-source", str(extra)])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output

    def test_snapshot_with_changelog_full_content(self, tmp_path: Path) -> None:
        """Changelog with changes/points produces rich commit messages."""
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl" / "repo"
        cl_dir.mkdir(parents=True)
        changelog = {
            "date": "2026-04-07",
            "repo": "repo",
            "title": "Widget system overhaul",
            "summary": "Refactored the widget pipeline.",
            "changes": [
                {
                    "title": "Core",
                    "points": [
                        {"text": "feat: add widget factory", "category": "instantiate"},
                        "fix: resolve widget leak",
                    ],
                }
            ],
        }
        (cl_dir / "2026-04-07-repo-changelog.yaml").write_text(yaml.dump(changelog))
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest), "--changelog-dir", str(cl_dir)])
        assert result.exit_code == 0
        log = subprocess.run(
            ["git", "log", "--format=%B", "-1"], cwd=dest, capture_output=True, text=True, check=True
        ).stdout
        assert "Widget system overhaul" in log
        assert "feat: add widget factory" in log
        assert "fix: resolve widget leak" in log

    def test_snapshot_with_commit_time(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        dest = tmp_path / "snap"
        result = CliRunner().invoke(
            cli,
            ["snapshot", str(repo), str(dest), "--commit-time", "20:00", "--timezone", "America/Los_Angeles"],
        )
        assert result.exit_code == 0
        assert "Snapshot created" in result.output
        # Verify timestamp
        log = subprocess.run(
            ["git", "log", "--format=%ai"], cwd=dest, capture_output=True, text=True, check=True
        )
        assert "20:00:00" in log.stdout

    def test_snapshot_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest)])
        assert "No commits" in result.output

    def test_snapshot_with_since(self, tmp_path: Path) -> None:
        """Since filters early commits on the branch path."""
        repo = tmp_path / "multi"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (repo / "a.py").write_text("a\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: early"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-01-01T10:00:00", "GIT_COMMITTER_DATE": "2026-01-01T10:00:00"},
        )
        (repo / "b.py").write_text("b\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: later"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
        )
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest), "--since", "2026-04-07"])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output

    def test_snapshot_with_changelog_dir(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl" / "repo"
        cl_dir.mkdir(parents=True)
        changelog = {
            "date": "2026-04-07",
            "repo": "repo",
            "title": "Daily update",
            "summary": "Two changes.",
            "stats": {"commits": 2, "files_changed": 2, "insertions": 2, "deletions": 0},
            "changes": [],
        }
        (cl_dir / "2026-04-07-repo-changelog.yaml").write_text(yaml.dump(changelog))
        dest = tmp_path / "snap"
        result = CliRunner().invoke(cli, ["snapshot", str(repo), str(dest), "--changelog-dir", str(cl_dir)])
        assert result.exit_code == 0
        assert "Snapshot created" in result.output


class TestExportCadence:
    def test_export_to_stdout(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo)])
        assert result.exit_code == 0
        assert "date" in result.output  # JSON contains date fields

    def test_export_to_file(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out_file = tmp_path / "cadence.json"
        result = CliRunner().invoke(cli, ["export-cadence", str(repo), "--output", str(out_file)])
        assert result.exit_code == 0
        assert out_file.exists()
        assert "Exported" in result.output

    def test_export_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo)])
        assert "No commits" in result.output

    def test_export_with_cadence(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo), "--cadence", "weekly"])
        assert result.exit_code == 0

    def test_export_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["export-cadence", str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0


class TestPreview:
    def _init_many_commits(self, tmp_path: Path) -> Path:
        """Create a repo with 4 commits on the same day to exercise the overflow line."""
        repo = tmp_path / "many"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        for i in range(4):
            (repo / f"f{i}.py").write_text(f"x{i}\n")
            subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"feat: change {i}"],
                cwd=repo,
                capture_output=True,
                check=True,
                env={
                    **env,
                    "GIT_AUTHOR_DATE": f"2026-04-07T1{i}:00:00",
                    "GIT_COMMITTER_DATE": f"2026-04-07T1{i}:00:00",
                },
            )
        return repo

    def test_preview_output(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo)])
        assert result.exit_code == 0
        assert "commits" in result.output
        assert "groups" in result.output

    def test_preview_many_commits_shows_overflow(self, tmp_path: Path) -> None:
        repo = self._init_many_commits(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo)])
        assert result.exit_code == 0
        assert "more" in result.output

    def test_preview_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["preview", str(repo)])
        assert "No commits" in result.output

    def test_preview_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0

    def test_preview_with_cadence(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["preview", str(repo), "--cadence", "weekly"])
        assert result.exit_code == 0
        assert "groups" in result.output


class TestDeriveCommitType:
    def test_known_categories_map_to_conventional_types(self) -> None:
        from repogerbil.cli.commands.distill_cmds import _derive_commit_type

        cases = {
            "instantiate": "feat",
            "interface": "feat",
            "remediate": "fix",
            "margin": "fix",
            "harden": "fix",
            "decouple": "refactor",
            "deprecate": "refactor",
            "specify": "docs",
            "qualify": "test",
            "streamline": "perf",
            "baseline": "chore",
        }
        for category, expected in cases.items():
            data = {"changes": [{"category": category}]}
            assert _derive_commit_type(data) == expected, f"{category} → {expected}"

    def test_unknown_category_returns_empty(self) -> None:
        from repogerbil.cli.commands.distill_cmds import _derive_commit_type

        assert _derive_commit_type({"changes": [{"category": "unknown-xyz"}]}) == ""

    def test_empty_changes_returns_empty(self) -> None:
        from repogerbil.cli.commands.distill_cmds import _derive_commit_type

        assert _derive_commit_type({"changes": []}) == ""
        assert _derive_commit_type({}) == ""

    def test_non_dict_change_skipped(self) -> None:
        from repogerbil.cli.commands.distill_cmds import _derive_commit_type

        # Non-dict entries are skipped; falls through to next entry
        data = {"changes": ["not-a-dict", {"category": "instantiate"}]}
        assert _derive_commit_type(data) == "feat"

    def test_changelog_to_message_adds_prefix(self) -> None:
        from repogerbil.cli.commands.distill_cmds import _changelog_to_message

        data = {
            "title": "Add widget factory",
            "summary": "New factory pattern.",
            "changes": [{"category": "instantiate", "points": ["Create factory"]}],
        }
        msg = _changelog_to_message(data)
        assert msg.startswith("feat: Add widget factory")

    def test_changelog_to_message_no_double_prefix(self) -> None:
        from repogerbil.cli.commands.distill_cmds import _changelog_to_message

        data = {
            "title": "feat: Add widget factory",
            "summary": "New factory.",
            "changes": [{"category": "instantiate", "points": ["Create factory"]}],
        }
        msg = _changelog_to_message(data)
        assert msg.startswith("feat: Add widget factory")
        assert not msg.startswith("feat: feat:")
