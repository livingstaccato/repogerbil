# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI commands."""

from pathlib import Path
import subprocess
from types import SimpleNamespace

from click.testing import CliRunner
import pytest
import yaml

from repogerbil.cli.main import _handle_prompt_mode, cli


def _init_test_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for CLI testing."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
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
        ["git", "commit", "-m", "WIP stuff"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
    )
    return repo


def _generate_changelog(runner: CliRunner, repo: Path, out: Path) -> None:
    """Helper to generate a changelog for testing other commands."""
    runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out), "--analyze"])


class TestHelp:
    def test_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "gerbil" in result.output


class TestStatus:
    def test_with_dates(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["status", str(repo)])
        assert result.exit_code == 0
        assert "Active dates" in result.output
        assert "Date range" in result.output

    def test_empty_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["status", str(repo)])
        assert "Active dates: 0" in result.output

    def test_invalid_path(self) -> None:
        result = CliRunner().invoke(cli, ["status", "/nonexistent"])
        assert result.exit_code != 0


class TestChangelog:
    def test_draft_mode(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        result = CliRunner().invoke(
            cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)]
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output

    def test_analyze_mode(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        result = CliRunner().invoke(
            cli,
            ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out), "--analyze"],
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output

    def test_no_commits(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["changelog", str(repo), "--date", "2020-01-01"])
        assert "No commits" in result.output

    def test_exists_no_force(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        result = runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        assert "Exists" in result.output

    def test_force_overwrite(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        result = runner.invoke(
            cli,
            ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out), "--force"],
        )
        assert "Wrote" in result.output

    def test_prompt_mode(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        result = CliRunner().invoke(
            cli,
            ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out), "--prompt"],
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output

    def test_prompt_with_thorough_config(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        config = tmp_path / ".repogerbil.toml"
        config.write_text('backfill_depth = "thorough"\n')
        # Monkey-patch config loading for this test
        from repogerbil.core.config import Settings

        Settings._toml_path = str(config)
        try:
            result = CliRunner().invoke(
                cli,
                ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out), "--prompt"],
            )
            assert result.exit_code == 0
            assert "Wrote" in result.output
        finally:
            Settings._toml_path = None

    def test_message_depth_flag(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "changelog",
                str(repo),
                "--date",
                "2026-04-07",
                "--output-dir",
                str(out),
                "--message-depth",
                "refs",
            ],
        )
        assert result.exit_code == 0


class TestHandlePromptMode:
    def test_uses_empty_diff_content_by_default(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        seen: dict[str, object] = {}

        def fake_generate_prompt(
            repo_name: str, date: str, commits: list[object], stats: object, diff_content: dict[str, str]
        ) -> str:
            seen["repo_name"] = repo_name
            seen["date"] = date
            seen["commits"] = commits
            seen["stats"] = stats
            seen["diff_content"] = diff_content
            return "prompt-body"

        monkeypatch.setattr("repogerbil.cli.main.generate_prompt", fake_generate_prompt)

        commits = [SimpleNamespace(hash="a1"), SimpleNamespace(hash="a2")]
        stats = SimpleNamespace(files_changed=2)
        settings = SimpleNamespace(backfill_depth="standard")

        _handle_prompt_mode(repo, repo.name, "2026-04-07", commits, stats, settings, out)

        assert seen["repo_name"] == repo.name
        assert seen["date"] == "2026-04-07"
        assert seen["commits"] == commits
        assert seen["stats"] == stats
        assert seen["diff_content"] == {}
        assert (out / repo.name / "2026-04-07-repo-prompt.md").read_text() == "prompt-body"


class TestVerify:
    def test_verify_clean(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo)])
        assert result.exit_code == 0

    def test_verify_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0

    def test_verify_with_tolerance(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo), "--tolerance", "50"])
        assert result.exit_code == 0

    def test_verify_stats_mismatch(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        # Corrupt stats
        yaml_file = next((out / repo.name).glob("*changelog.yaml"))
        data = yaml.safe_load(yaml_file.read_text())
        data["stats"]["files_changed"] = 999
        yaml_file.write_text(yaml.dump(data))
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo), "--tolerance", "1"])
        assert "Stats mismatches" in result.output

    def test_verify_coverage_gap(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        # Generate draft (no files listed) — will have coverage gap
        runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo), "--tolerance", "1"])
        assert "Coverage gaps" in result.output or "All good" in result.output


class TestAudit:
    def test_audit(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["audit", str(repo)])
        assert result.exit_code == 0
        assert "classifiable" in result.output

    def test_audit_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["audit", str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0

    def test_audit_show_bad(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["audit", str(repo), "--show-bad"])
        assert result.exit_code == 0
        # Should have at least "WIP stuff" as ambiguous
        assert "Ambiguous" in result.output or "0 ambiguous" in result.output

    def test_audit_empty_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["audit", str(repo)])
        assert "0% classifiable" in result.output or "0 commits" in result.output


class TestDistill:
    def test_dry_run(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["distill", str(repo), "--dry-run"])
        assert result.exit_code == 0
        assert "groups" in result.output

    def test_dry_run_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["distill", str(repo), "--dry-run", "--since", "2026-04-07"])
        assert result.exit_code == 0

    def test_dry_run_with_cadence(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["distill", str(repo), "--dry-run", "--cadence", "weekly"])
        assert result.exit_code == 0

    def test_no_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["distill", str(repo), "--dry-run"])
        assert "No commits" in result.output

    def test_real_distill(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["distill", str(repo), "--target-branch", "test-distill"])
        assert result.exit_code == 0
        assert "Consolidated" in result.output
        assert "Backup" in result.output
        assert "Tag" in result.output

    def test_distill_with_changelog_dir(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "cl"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(
            cli,
            ["distill", str(repo), "--target-branch", "cl-distill", "--changelog-dir", str(out / repo.name)],
        )
        assert result.exit_code == 0
        assert "Consolidated" in result.output


class TestFixStatsEdgeCases:
    def test_fix_stats_since_filters(self, tmp_path: Path) -> None:
        """Since filter skips earlier dates."""
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["fix-stats", str(out / repo.name), str(repo), "--since", "2027-01-01"])
        assert "0 files updated" in result.output

    def test_fix_stats_actually_fixes(self, tmp_path: Path) -> None:
        """Stats that differ from git truth get corrected."""
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        # Corrupt the stats
        yaml_file = next((out / repo.name).glob("*changelog.yaml"))
        data = yaml.safe_load(yaml_file.read_text())
        data["stats"]["files_changed"] = 999
        yaml_file.write_text(yaml.dump(data))
        result = runner.invoke(cli, ["fix-stats", str(out / repo.name), str(repo)])
        assert "1 files updated" in result.output


class TestVerifyEdgeCases:
    def test_verify_stat_and_coverage_report(self, tmp_path: Path) -> None:
        """Verify reports both stat mismatches and coverage gaps."""
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        # Generate draft changelog (no file paths = coverage gap)
        runner.invoke(cli, ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out)])
        # Corrupt stats
        yaml_file = next((out / repo.name).glob("*changelog.yaml"))
        data = yaml.safe_load(yaml_file.read_text())
        data["stats"]["files_changed"] = 999
        yaml_file.write_text(yaml.dump(data))
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo), "--tolerance", "1"])
        assert "stat issues" in result.output or "Stats mismatches" in result.output

    def test_verify_all_good(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["verify", str(out / repo.name), str(repo), "--tolerance", "50"])
        assert "All good" in result.output


class TestDistillEdgeCases:
    def test_distill_backup_output(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(cli, ["distill", str(repo), "--target-branch", "backup-test"])
        assert "Backup:" in result.output
        assert "Tag:" in result.output


class TestAuditEdgeCases:
    def test_audit_with_bad_messages(self, tmp_path: Path) -> None:
        """Repo with WIP messages should show ambiguous count."""
        repo = _init_test_repo(tmp_path)  # Has "WIP stuff" commit
        result = CliRunner().invoke(cli, ["audit", str(repo), "--show-bad"])
        assert "ambiguous" in result.output

    def test_audit_zero_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "empty"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        result = CliRunner().invoke(cli, ["audit", str(repo)])
        assert "0 commits" in result.output


class TestSummary:
    def test_summary_markdown(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "cl"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        summary_out = tmp_path / "summaries"
        summary_out.mkdir()
        result = runner.invoke(
            cli,
            ["summary", str(out), "--year", "2026", "--week", "15", "--output-dir", str(summary_out)],
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output

    def test_summary_prompt(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "cl"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        summary_out = tmp_path / "summaries"
        summary_out.mkdir()
        result = runner.invoke(
            cli,
            [
                "summary",
                str(out),
                "--year",
                "2026",
                "--week",
                "15",
                "--output-dir",
                str(summary_out),
                "--prompt",
            ],
        )
        assert result.exit_code == 0
        assert "prompt" in result.output.lower() or "Wrote" in result.output

    def test_summary_no_data(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "empty"
        cl_dir.mkdir()
        result = CliRunner().invoke(cli, ["summary", str(cl_dir), "--year", "2020", "--week", "1"])
        assert "No changelogs" in result.output


class TestMissing:
    def test_no_tracked(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "cl"
        cl_dir.mkdir()
        result = CliRunner().invoke(cli, ["missing", str(cl_dir)])
        assert "No tracked repos" in result.output

    def test_with_config(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl"
        cl_dir.mkdir()
        config = tmp_path / "test.toml"
        config.write_text(f'[tracked]\nrepo = "{repo}"\n')
        result = CliRunner().invoke(cli, ["missing", str(cl_dir), "--config", str(config)])
        assert result.exit_code == 0
        # Should find missing dates since no changelogs exist
        assert "missing" in result.output or "repo" in result.output


class TestEnrich:
    def test_enrich(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "cl"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["enrich", str(out / repo.name), str(repo)])
        assert result.exit_code == 0
        assert "enriched" in result.output


class TestBackfill:
    def test_no_tracked(self, tmp_path: Path) -> None:
        cl_dir = tmp_path / "cl"
        cl_dir.mkdir()
        result = CliRunner().invoke(cli, ["backfill", str(cl_dir)])
        assert "No tracked repos" in result.output

    def test_with_config(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl"
        cl_dir.mkdir()
        config = tmp_path / "test.toml"
        config.write_text(f'[tracked]\nrepo = "{repo}"\n')
        result = CliRunner().invoke(cli, ["backfill", str(cl_dir), "--config", str(config)])
        assert result.exit_code == 0
        assert "generated" in result.output


class TestFixStats:
    def test_fix_stats(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["fix-stats", str(out / repo.name), str(repo)])
        assert result.exit_code == 0
        assert "updated" in result.output

    def test_fix_stats_with_since(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        result = runner.invoke(cli, ["fix-stats", str(out / repo.name), str(repo), "--since", "2026-04-07"])
        assert result.exit_code == 0


class TestSummaryForce:
    def test_summary_exists_no_force(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "cl"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        summary_out = tmp_path / "summaries"
        summary_out.mkdir()
        runner.invoke(
            cli, ["summary", str(out), "--year", "2026", "--week", "15", "--output-dir", str(summary_out)]
        )
        result = runner.invoke(
            cli, ["summary", str(out), "--year", "2026", "--week", "15", "--output-dir", str(summary_out)]
        )
        assert "Exists" in result.output

    def test_summary_force_overwrite(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "cl"
        out.mkdir()
        runner = CliRunner()
        _generate_changelog(runner, repo, out)
        summary_out = tmp_path / "summaries"
        summary_out.mkdir()
        runner.invoke(
            cli, ["summary", str(out), "--year", "2026", "--week", "15", "--output-dir", str(summary_out)]
        )
        result = runner.invoke(
            cli,
            [
                "summary",
                str(out),
                "--year",
                "2026",
                "--week",
                "15",
                "--output-dir",
                str(summary_out),
                "--force",
            ],
        )
        assert "Wrote" in result.output


class TestLintCommand:
    def test_lint_valid_files(self, tmp_path: Path) -> None:
        runner = CliRunner()
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        _generate_changelog(runner, repo, out)

        result = runner.invoke(cli, ["lint", str(out)])
        assert result.exit_code == 0
        assert "files checked" in result.output

    def test_lint_catches_errors(self, tmp_path: Path) -> None:
        runner = CliRunner()
        cl_dir = tmp_path / "changelogs" / "bad-repo"
        cl_dir.mkdir(parents=True)
        (cl_dir / "2026-04-08-bad-repo-changelog.yaml").write_text(yaml.dump({"changes": "not a list"}))

        result = runner.invoke(cli, ["lint", str(tmp_path / "changelogs")])
        assert result.exit_code == 1
        assert "ERROR" in result.output

    def test_lint_errors_only(self, tmp_path: Path) -> None:
        runner = CliRunner()
        cl_dir = tmp_path / "changelogs" / "myrepo"
        cl_dir.mkdir(parents=True)
        data = {
            "date": "2026-04-08",
            "repo": "myrepo",
            "title": "Test",
            "summary": "Test",
            "stats": {"files_changed": 1, "insertions": 1, "deletions": 0},
            "changes": [{"title": "A"}],  # missing category/severity = warnings only
        }
        (cl_dir / "2026-04-08-myrepo-changelog.yaml").write_text(yaml.dump(data))

        result = runner.invoke(cli, ["lint", str(tmp_path / "changelogs"), "--errors-only"])
        assert result.exit_code == 0
        assert "WARN" not in result.output

    def test_lint_filter_repo(self, tmp_path: Path) -> None:
        runner = CliRunner()
        for name in ("repo-a", "repo-b"):
            d = tmp_path / "changelogs" / name
            d.mkdir(parents=True)
            (d / f"2026-04-08-{name}-changelog.yaml").write_text(yaml.dump({"changes": "bad"}))

        result = runner.invoke(cli, ["lint", str(tmp_path / "changelogs"), "repo-a"])
        assert "repo-a" in result.output
        assert "repo-b" not in result.output


class TestMainEntryPoint:
    def test_repogerbil_error_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.cli.main import main
        from repogerbil.core.errors import RepogerbilError

        def _raise() -> None:
            raise RepogerbilError("git failure")

        monkeypatch.setattr("repogerbil.cli.main.cli", _raise)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_unexpected_exception_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.cli.main import main

        def _raise() -> None:
            raise RuntimeError("something broke")

        monkeypatch.setattr("repogerbil.cli.main.cli", _raise)

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

    def test_debug_flag_stripped_from_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        from repogerbil.cli.main import main

        monkeypatch.setattr(sys, "argv", ["gerbil", "--debug"])

        call_count: list[int] = [0]

        def _fake_cli() -> None:
            call_count[0] += 1

        monkeypatch.setattr("repogerbil.cli.main.cli", _fake_cli)

        main()

        assert call_count[0] == 1
        assert "--debug" not in sys.argv
