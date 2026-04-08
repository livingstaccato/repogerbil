# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""End-to-end integration test: create repo → generate changelog → verify → distill."""

from pathlib import Path
import subprocess

from click.testing import CliRunner
import yaml

from repogerbil.cli.main import cli


def _create_test_repo(tmp_path: Path) -> Path:
    """Create a repo with 2 days of commits."""
    repo = tmp_path / "project"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "dev@example.com"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(["git", "config", "user.name", "Developer"], cwd=repo, capture_output=True, check=True)
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}

    # Day 1: two commits
    (repo / "src").mkdir()
    (repo / "src" / "main.py").write_text("def main():\n    pass\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: initial project scaffold"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T09:00:00", "GIT_COMMITTER_DATE": "2026-04-07T09:00:00"},
    )

    (repo / "src" / "utils.py").write_text("def helper():\n    return 42\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add utility module"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-07T14:00:00", "GIT_COMMITTER_DATE": "2026-04-07T14:00:00"},
    )

    # Day 2: one commit
    (repo / "src" / "main.py").write_text("from .utils import helper\n\ndef main():\n    return helper()\n")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "fix: wire utils into main"],
        cwd=repo,
        capture_output=True,
        check=True,
        env={**env, "GIT_AUTHOR_DATE": "2026-04-08T10:00:00", "GIT_COMMITTER_DATE": "2026-04-08T10:00:00"},
    )

    return repo


class TestEndToEnd:
    def test_full_pipeline(self, tmp_path: Path) -> None:
        """Create repo → status → changelog → verify → distill."""
        repo = _create_test_repo(tmp_path)
        out = tmp_path / "changelogs"
        out.mkdir()
        runner = CliRunner()

        # Step 1: Status
        result = runner.invoke(cli, ["status", str(repo)])
        assert result.exit_code == 0
        assert "Active dates: 2" in result.output

        # Step 2: Generate changelogs for both days
        result = runner.invoke(
            cli,
            ["changelog", str(repo), "--date", "2026-04-07", "--output-dir", str(out), "--analyze"],
        )
        assert result.exit_code == 0
        assert "Wrote" in result.output

        result = runner.invoke(
            cli,
            ["changelog", str(repo), "--date", "2026-04-08", "--output-dir", str(out), "--analyze"],
        )
        assert result.exit_code == 0

        # Verify changelog files exist and are valid YAML
        cl_dir = out / repo.name
        files = list(cl_dir.glob("*changelog.yaml"))
        assert len(files) == 2

        for f in files:
            data = yaml.safe_load(f.read_text())
            assert "date" in data
            assert "repo" in data
            assert "stats" in data
            assert "changes" in data
            assert data["stats"]["commits"] >= 1

        # Step 3: Audit commit messages
        result = runner.invoke(cli, ["audit", str(repo)])
        assert result.exit_code == 0
        assert "classifiable" in result.output

        # Step 4: Distill (dry-run)
        result = runner.invoke(cli, ["distill", str(repo), "--dry-run"])
        assert result.exit_code == 0
        assert "2 daily groups" in result.output

        # Step 5: Distill (real) with changelog messages
        result = runner.invoke(
            cli,
            ["distill", str(repo), "--target-branch", "clean", "--changelog-dir", str(cl_dir)],
        )
        assert result.exit_code == 0
        assert "Consolidated" in result.output

        # Verify the consolidated branch has 2 commits (one per day)
        log = (
            subprocess.run(
                ["git", "log", "--oneline", "clean"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        assert len(log) == 2
