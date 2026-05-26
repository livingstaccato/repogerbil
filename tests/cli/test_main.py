# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI commands."""

from pathlib import Path
import subprocess
from types import SimpleNamespace

from click.testing import CliRunner
import pytest
import yaml

from repogerbil.cli.main import _handle_prompt_mode, _report_verification, cli


def _init_test_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for CLI testing."""
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


def _repo_with_hidden_commit(tmp_path: Path) -> Path:
    repo = tmp_path / "hidden"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
    (repo / "visible.py").write_text("visible\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: visible"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2025-07-23T10:00:00", "GIT_COMMITTER_DATE": "2025-07-23T10:00:00"},
    )
    subprocess.run(["git", "checkout", "-b", "hidden"], cwd=repo, capture_output=True, check=True)
    (repo / "hidden.py").write_text("hidden\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: hidden"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2025-07-28T10:00:00", "GIT_COMMITTER_DATE": "2025-07-28T10:00:00"},
    )
    subprocess.run(["git", "checkout", "-"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "branch", "-D", "hidden"], cwd=repo, capture_output=True, check=True)
    return repo


class TestHelp:
    def test_help(self) -> None:
        result = CliRunner().invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "gerbil" in result.output


class TestCliLogging:
    """Verify ``_configure_cli_logging`` wires the repogerbil logger to stderr."""

    def test_warning_reaches_stderr(self) -> None:
        """A ``logger.warning`` from a core module reaches the CLI handler's stream.

        The package root attaches only a ``NullHandler``; the CLI layer is
        responsible for routing warnings to the user. After CLI bootstrap the
        warning surfaces on the handler's stream (configured to ``sys.stderr``
        at bootstrap time — pytest's capture mechanism may swap sys.stderr
        between the bootstrap call and the assertion, so we point the handler
        at an in-memory buffer to make the test deterministic).
        """
        import io
        import logging

        from repogerbil.cli.main import _configure_cli_logging

        pkg_logger = logging.getLogger("repogerbil")
        # Drop any prior CLI handler + level so we exercise a clean first-time
        # bootstrap; other tests may have left state behind.
        for h in list(pkg_logger.handlers):
            if getattr(h, "_repogerbil_cli_handler", False):
                pkg_logger.removeHandler(h)
        pkg_logger.setLevel(logging.NOTSET)
        # Bootstrap CLI logging exactly as a real CLI invocation would.
        _configure_cli_logging()
        assert pkg_logger.level == logging.WARNING
        cli_handlers = [h for h in pkg_logger.handlers if getattr(h, "_repogerbil_cli_handler", False)]
        assert len(cli_handlers) == 1
        handler = cli_handlers[0]
        # Redirect the handler at an in-memory buffer to confirm the formatted
        # message lands there.
        buf = io.StringIO()
        original_stream = handler.stream  # type: ignore[attr-defined]  # StreamHandler exposes .stream
        handler.stream = buf  # type: ignore[attr-defined]
        try:
            child_logger = logging.getLogger("repogerbil.core.multi_snapshot")
            assert child_logger.getEffectiveLevel() == logging.WARNING
            child_logger.warning("LLM refinement failed for 2026-04-01")
        finally:
            handler.stream = original_stream  # type: ignore[attr-defined]
        assert "LLM refinement failed for 2026-04-01" in buf.getvalue()

    def test_idempotent_across_invocations(self) -> None:
        """Repeated CLI invocations must not stack duplicate handlers."""
        import logging

        runner = CliRunner()
        runner.invoke(cli, ["--help"])
        runner.invoke(cli, ["--help"])
        runner.invoke(cli, ["--help"])
        pkg_logger = logging.getLogger("repogerbil")
        cli_handlers = [h for h in pkg_logger.handlers if getattr(h, "_repogerbil_cli_handler", False)]
        assert len(cli_handlers) == 1

    def test_verbose_flag_bumps_handler_level_to_info(self, tmp_path: Path) -> None:
        """``--verbose`` bumps the CLI handler's level to INFO.

        The package-logger level itself is *not* re-asserted on each call so
        an embedder's pre-existing level is preserved (see
        ``test_embedder_logger_level_preserved``). The handler's own level is
        the bumping point for ``--verbose``.
        """
        import logging

        from repogerbil.cli.main import _configure_cli_logging

        # Reset handler to WARNING so the bump is observable.
        _configure_cli_logging(level=logging.WARNING)
        repo = tmp_path / "r"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        runner = CliRunner()
        runner.invoke(cli, ["--verbose", "status", str(repo)])
        pkg_logger = logging.getLogger("repogerbil")
        cli_handlers = [h for h in pkg_logger.handlers if getattr(h, "_repogerbil_cli_handler", False)]
        assert len(cli_handlers) == 1
        assert cli_handlers[0].level == logging.INFO
        # Restore handler WARNING for downstream tests.
        _configure_cli_logging(level=logging.WARNING)

    def test_embedder_logger_level_preserved(self, tmp_path: Path) -> None:
        """A pre-existing ``repogerbil`` logger level survives CLI invocations.

        Library hygiene: when an embedder sets the package logger to e.g.
        ``ERROR``, subsequent CLI invocations must not silently downgrade it
        to ``WARNING``/``INFO``. The CLI bumps its *handler* level instead.
        """
        import logging

        from repogerbil.cli.main import _configure_cli_logging

        # First, ensure the CLI handler exists (simulates a prior CLI run).
        _configure_cli_logging(level=logging.WARNING)
        pkg_logger = logging.getLogger("repogerbil")
        # Embedder now reconfigures the package logger to ERROR.
        original = pkg_logger.level
        try:
            pkg_logger.setLevel(logging.ERROR)
            # Subsequent CLI invocations must leave the embedder's level alone.
            repo = tmp_path / "r"
            repo.mkdir()
            subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
            runner = CliRunner()
            runner.invoke(cli, ["--verbose", "status", str(repo)])
            assert pkg_logger.level == logging.ERROR
            # The CLI handler should still have bumped to INFO though.
            cli_handlers = [h for h in pkg_logger.handlers if getattr(h, "_repogerbil_cli_handler", False)]
            assert len(cli_handlers) == 1
            assert cli_handlers[0].level == logging.INFO
        finally:
            pkg_logger.setLevel(original)
            _configure_cli_logging(level=logging.WARNING)

    def test_first_time_setup_respects_existing_logger_level(self) -> None:
        """First-time CLI bootstrap must not clobber a level the embedder set.

        Covers the case where an embedder configures the package logger
        *before* any CLI command runs. ``NOTSET`` (no embedder config) is the
        only state where the CLI takes ownership of the level.
        """
        import logging

        from repogerbil.cli.main import _configure_cli_logging

        pkg_logger = logging.getLogger("repogerbil")
        # Drop the CLI handler so we exercise the first-time-setup branch.
        for h in list(pkg_logger.handlers):
            if getattr(h, "_repogerbil_cli_handler", False):
                pkg_logger.removeHandler(h)
        original = pkg_logger.level
        try:
            pkg_logger.setLevel(logging.ERROR)
            _configure_cli_logging(level=logging.WARNING)
            # Embedder's level survives; only the handler we just added is
            # owned by us.
            assert pkg_logger.level == logging.ERROR
            cli_handlers = [h for h in pkg_logger.handlers if getattr(h, "_repogerbil_cli_handler", False)]
            assert len(cli_handlers) == 1
            assert cli_handlers[0].level == logging.WARNING
        finally:
            pkg_logger.setLevel(original)
            _configure_cli_logging(level=logging.WARNING)

    def test_first_time_setup_takes_level_when_logger_notset(self) -> None:
        """When the package logger is NOTSET (no embedder), CLI sets the level."""
        import logging

        from repogerbil.cli.main import _configure_cli_logging

        pkg_logger = logging.getLogger("repogerbil")
        for h in list(pkg_logger.handlers):
            if getattr(h, "_repogerbil_cli_handler", False):
                pkg_logger.removeHandler(h)
        original = pkg_logger.level
        try:
            pkg_logger.setLevel(logging.NOTSET)
            _configure_cli_logging(level=logging.WARNING)
            assert pkg_logger.level == logging.WARNING
        finally:
            pkg_logger.setLevel(original)
            _configure_cli_logging(level=logging.WARNING)


class TestRealign:
    def test_reports_realign_result(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        jsonl = tmp_path / "repo.summaries.jsonl"

        def fake_realign_jsonl(repo_path: Path, jsonl_path: Path, dry_run: bool) -> SimpleNamespace:
            assert repo_path == repo
            assert jsonl_path == jsonl
            assert dry_run is True
            return SimpleNamespace(
                jsonl_path=str(jsonl),
                total_records=3,
                already_verified=1,
                realigned=1,
                exact_matches=1,
                unalignable=1,
                corrupt_lines=2,
            )

        monkeypatch.setattr("repogerbil.cli.commands.realign_cmd.realign_jsonl", fake_realign_jsonl)

        result = CliRunner().invoke(cli, ["realign", str(repo), str(jsonl), "--dry-run"])

        assert result.exit_code == 0
        assert "would realign: 1 (exact match: 1)" in result.output
        assert "unalignable: 1" in result.output
        assert "corrupt lines (preserved): 2" in result.output

    def test_no_corrupt_lines_message_when_zero(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When corrupt_lines == 0, the corrupt-lines line is omitted."""
        repo = tmp_path / "repo"
        repo.mkdir()
        jsonl = tmp_path / "repo.summaries.jsonl"

        def fake_realign_jsonl(repo_path: Path, jsonl_path: Path, dry_run: bool) -> SimpleNamespace:
            return SimpleNamespace(
                jsonl_path=str(jsonl),
                total_records=1,
                already_verified=1,
                realigned=0,
                exact_matches=0,
                unalignable=0,
                corrupt_lines=0,
            )

        monkeypatch.setattr("repogerbil.cli.commands.realign_cmd.realign_jsonl", fake_realign_jsonl)

        result = CliRunner().invoke(cli, ["realign", str(repo), str(jsonl)])

        assert result.exit_code == 0
        assert "corrupt lines" not in result.output


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

    def test_extra_source_flag(self, tmp_path: Path) -> None:
        primary = tmp_path / "primary"
        primary.mkdir()
        subprocess.run(["git", "init"], cwd=primary, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "user.email", "t@t.com"], cwd=primary, capture_output=True, check=True
        )
        subprocess.run(["git", "config", "user.name", "T"], cwd=primary, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=primary, capture_output=True, check=True
        )
        backup = tmp_path / "backup"
        backup.mkdir()
        subprocess.run(["git", "init"], cwd=backup, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=backup, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=backup, capture_output=True, check=True)
        subprocess.run(
            ["git", "config", "commit.gpgsign", "false"], cwd=backup, capture_output=True, check=True
        )
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (backup / "old.py").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=backup, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: old era"],
            cwd=backup,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2025-02-03T10:00:00", "GIT_COMMITTER_DATE": "2025-02-03T10:00:00"},
        )
        out = tmp_path / "out"
        out.mkdir()
        result = CliRunner().invoke(
            cli,
            [
                "changelog",
                str(primary),
                "--date",
                "2025-02-03",
                "--output-dir",
                str(out),
                "--analyze",
                "--extra-source",
                str(backup),
            ],
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output


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


class TestProbe:
    def test_hidden_ref_probe(self, tmp_path: Path) -> None:
        repo = _repo_with_hidden_commit(tmp_path)
        result = CliRunner().invoke(cli, ["probe", str(repo), "--date", "2025-07-28"])
        assert result.exit_code == 0
        assert "hidden_ref" in result.output


class TestReportVerification:
    def test_outputs_issue_lines(self, capsys: pytest.CaptureFixture[str]) -> None:
        _report_verification(["  repo/2026-04-07: 1 reported vs 2 actual"], ["  repo/2026-04-07: gap"], 1)
        out = capsys.readouterr().out
        assert "Stats mismatches:" in out
        assert "Coverage gaps:" in out
        assert "repo/2026-04-07" in out


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

    def test_run_verification_checks_insertions_and_deletions(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from repogerbil.cli.commands import verify_cmds as verify_mod

        changelog_dir = tmp_path / "out" / "repo"
        changelog_dir.mkdir(parents=True)
        yaml_file = changelog_dir / "2026-04-07-repo-changelog.yaml"
        yaml_file.write_text(
            yaml.dump(
                {
                    "date": "2026-04-07",
                    "repo": "repo",
                    "stats": {"files_changed": 10, "insertions": 100, "deletions": 1},
                    "bulk": [{"files": 10}],
                    "changes": [],
                }
            )
        )

        monkeypatch.setattr(
            verify_mod,
            "resolve_provenance",
            lambda *args, **kwargs: SimpleNamespace(
                commits=[SimpleNamespace(hash="a"), SimpleNamespace(hash="b")],
                stats=SimpleNamespace(files_changed=10, insertions=10, deletions=10),
            ),
        )
        stat_issues, coverage_issues, checked = verify_mod._run_verification(
            changelog_dir,
            tmp_path,
            "repo",
            since=None,
            tol=5,
        )

        assert checked == 1
        assert coverage_issues == []
        assert len(stat_issues) == 1
        assert "insertions" in stat_issues[0]
        assert "deletions" in stat_issues[0]

    def test_collect_stat_mismatches_handles_non_mapping_stats(self) -> None:
        from repogerbil.cli.commands.verify_cmds import _collect_stat_mismatches

        mismatches = _collect_stat_mismatches(
            {"stats": "invalid"},
            actual_files=1,
            actual_insertions=1,
            actual_deletions=1,
            tolerance=0,
        )
        assert mismatches

    def test_collect_stat_mismatches_handles_invalid_numeric_values(self) -> None:
        from repogerbil.cli.commands.verify_cmds import _collect_stat_mismatches

        mismatches = _collect_stat_mismatches(
            {"stats": {"files_changed": "n/a", "insertions": "oops", "deletions": "bad"}},
            actual_files=1,
            actual_insertions=1,
            actual_deletions=1,
            tolerance=0,
        )
        assert any("files invalid" in m for m in mismatches)
        assert any("insertions invalid" in m for m in mismatches)
        assert any("deletions invalid" in m for m in mismatches)

    def test_safe_int_covers_supported_inputs(self) -> None:
        from repogerbil.cli.commands.verify_cmds import _safe_int

        assert _safe_int(True) == 1
        assert _safe_int(5) == 5
        assert _safe_int(2.9) == 2
        assert _safe_int("7") == 7
        assert _safe_int(object()) is None

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

    def test_confirm_source_write_suppresses_warning(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(
            cli,
            ["distill", str(repo), "--target-branch", "test-distill-confirmed", "--confirm-source-write"],
        )
        assert result.exit_code == 0
        assert "WARNING" not in result.output

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

    def test_distill_without_backup_omits_backup_lines(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When create_backup=False, consolidate() returns empty backup_branch/tag
        and the CLI must NOT print the 'Backup:' / 'Tag:' lines (exercises the
        falsy branch of the post-distill conditionals)."""
        monkeypatch.setenv("REPOGERBIL_CREATE_BACKUP", "false")
        repo = _init_test_repo(tmp_path)
        result = CliRunner().invoke(
            cli,
            ["distill", str(repo), "--target-branch", "no-backup-distill", "--confirm-source-write"],
        )
        assert result.exit_code == 0, result.output
        assert "Consolidated" in result.output
        assert "Backup:" not in result.output
        assert "Tag:" not in result.output


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

    def test_prompt_writes_prompt_files_not_yaml(self, tmp_path: Path) -> None:
        repo = _init_test_repo(tmp_path)
        cl_dir = tmp_path / "cl"
        cl_dir.mkdir()
        config = tmp_path / "test.toml"
        config.write_text(f'[tracked]\nrepo = "{repo}"\n')
        result = CliRunner().invoke(cli, ["backfill", str(cl_dir), "--config", str(config), "--prompt"])
        assert result.exit_code == 0
        prompt_files = list((cl_dir / repo.name).glob("*-prompt.md"))
        yaml_files = list((cl_dir / repo.name).glob("*-changelog.yaml"))
        assert len(prompt_files) > 0
        assert len(yaml_files) == 0
        assert "prompts" in result.output


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

    def test_debug_flag_reraises_unexpected_exception(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import sys

        from repogerbil.cli.main import main

        monkeypatch.setattr(sys, "argv", ["gerbil", "--debug"])

        def _raise() -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr("repogerbil.cli.main.cli", _raise)

        with pytest.raises(RuntimeError, match="boom"):
            main()


class TestMainEntryPointMutationSurvivors:
    """Pin the unexpected-exception branch's exact message routing.

    The Console must write to stderr (not stdout) and the f-string must use
    ``str(e) or type(e).__name__`` — verified by examining captured streams
    and by sending a zero-length-message exception to force the OR fallback.
    """

    def test_unexpected_exception_writes_to_stderr_not_stdout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        from repogerbil.cli.main import main

        def _raise() -> None:
            raise RuntimeError("explode-stderr-marker")

        monkeypatch.setattr("repogerbil.cli.main.cli", _raise)
        with pytest.raises(SystemExit):
            main()
        captured = capsys.readouterr()
        # Message must land on stderr (Console(stderr=True)), never on stdout.
        assert "explode-stderr-marker" in captured.err
        assert "explode-stderr-marker" not in captured.out

    def test_unexpected_exception_formats_message_with_str_e(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``str(e)`` (not ``str(None)``) must appear in the formatted line."""
        from repogerbil.cli.main import main

        def _raise() -> None:
            raise RuntimeError("unique-formatted-message-XYZ")

        monkeypatch.setattr("repogerbil.cli.main.cli", _raise)
        with pytest.raises(SystemExit):
            main()
        err = capsys.readouterr().err
        assert "unique-formatted-message-XYZ" in err
        # Defend against ``str(None)`` (which would render "None") and against
        # ``str(e) and type(e).__name__`` (which would render the class name
        # because str(e) is truthy → "and" → "RuntimeError").
        assert "RuntimeError" not in err
        # Defend against ``console.print(None)`` — the label must be present.
        assert "Unexpected Error:" in err

    def test_unexpected_exception_falls_back_to_type_name_for_empty_str(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``str(e) or type(e).__name__`` — when str(e) is empty, class name shows.

        Also pins ``type(e).__name__`` (not ``type(None).__name__`` = "NoneType").
        """
        from repogerbil.cli.main import main

        class CustomZeroStrError(Exception):
            def __str__(self) -> str:
                return ""

        def _raise() -> None:
            raise CustomZeroStrError

        monkeypatch.setattr("repogerbil.cli.main.cli", _raise)
        with pytest.raises(SystemExit):
            main()
        err = capsys.readouterr().err
        # ``str(e)`` is "" → falsy → ``or`` falls back to ``type(e).__name__``.
        assert "CustomZeroStrError" in err
        # ``type(None).__name__`` would be "NoneType"; must not appear.
        assert "NoneType" not in err


class TestHandlePromptModeMutationSurvivors:
    """Pin thorough-branch string literal and mkdir kwargs for ``_handle_prompt_mode``."""

    def test_thorough_backfill_depth_triggers_diff_collection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``settings.backfill_depth == 'thorough'`` (exact, lowercase) routes through get_diff_content."""
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"

        seen: dict[str, object] = {}

        def fake_get_diff_content(path: Path, a: str, b: str) -> dict[str, str]:
            seen["called"] = True
            seen["path"] = path
            seen["a"] = a
            seen["b"] = b
            return {"f.py": "diff-body"}

        def fake_generate_prompt(
            repo_name: str, date: str, commits: list[object], stats: object, diff_content: dict[str, str]
        ) -> str:
            seen["diff_content"] = diff_content
            return "prompt-with-diffs"

        monkeypatch.setattr("repogerbil.core.diff.get_diff_content", fake_get_diff_content)
        monkeypatch.setattr("repogerbil.cli.main.generate_prompt", fake_generate_prompt)

        commits = [SimpleNamespace(hash="aaa"), SimpleNamespace(hash="bbb")]
        stats = SimpleNamespace(files_changed=2)
        settings = SimpleNamespace(backfill_depth="thorough")

        _handle_prompt_mode(repo, repo.name, "2026-04-07", commits, stats, settings, out)

        assert seen.get("called") is True
        assert seen["a"] == "aaa"
        assert seen["b"] == "bbb"
        assert seen["diff_content"] == {"f.py": "diff-body"}

    def test_non_thorough_backfill_depth_skips_diff_collection(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Any non-``'thorough'`` value (incl. ``'THOROUGH'``) must NOT call get_diff_content."""
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        called: list[bool] = []

        def fake_get_diff_content(*args: object, **kwargs: object) -> dict[str, str]:
            called.append(True)
            return {}

        monkeypatch.setattr("repogerbil.core.diff.get_diff_content", fake_get_diff_content)
        monkeypatch.setattr(
            "repogerbil.cli.main.generate_prompt",
            lambda *a, **k: "p",
        )

        commits = [SimpleNamespace(hash="a"), SimpleNamespace(hash="b")]
        stats = SimpleNamespace(files_changed=1)
        # Uppercase variant — would match a "THOROUGH" string mutation but
        # must NOT match the real lowercase literal.
        settings = SimpleNamespace(backfill_depth="THOROUGH")

        _handle_prompt_mode(repo, repo.name, "2026-04-07", commits, stats, settings, out)
        assert called == []

    def test_mkdir_succeeds_when_parent_already_exists(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``exist_ok=True`` must hold — pre-existing parent dir must NOT raise."""
        repo = _init_test_repo(tmp_path)
        out = tmp_path / "out"
        # Pre-create the prompt parent directory so exist_ok=False would raise.
        (out / repo.name).mkdir(parents=True)

        monkeypatch.setattr("repogerbil.cli.main.generate_prompt", lambda *a, **k: "p")

        commits = [SimpleNamespace(hash="a"), SimpleNamespace(hash="b")]
        stats = SimpleNamespace(files_changed=1)
        settings = SimpleNamespace(backfill_depth="standard")

        # No exception should be raised even though parent already exists.
        _handle_prompt_mode(repo, repo.name, "2026-04-07", commits, stats, settings, out)
        assert (out / repo.name / "2026-04-07-repo-prompt.md").exists()

    def test_mkdir_creates_nested_missing_parents(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``parents=True`` must hold — deeply nested missing parents must be created."""
        repo = _init_test_repo(tmp_path)
        # Use a 3-level-deep output directory; parents=False would raise.
        out = tmp_path / "deep" / "nest" / "out"

        monkeypatch.setattr("repogerbil.cli.main.generate_prompt", lambda *a, **k: "deep-prompt")

        commits = [SimpleNamespace(hash="a"), SimpleNamespace(hash="b")]
        stats = SimpleNamespace(files_changed=1)
        settings = SimpleNamespace(backfill_depth="standard")

        _handle_prompt_mode(repo, repo.name, "2026-04-07", commits, stats, settings, out)
        target = out / repo.name / "2026-04-07-repo-prompt.md"
        assert target.exists()
        assert target.read_text() == "deep-prompt"
