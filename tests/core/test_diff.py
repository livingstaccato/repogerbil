# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for diff reading and parsing."""

from pathlib import Path
import subprocess

from repogerbil.core.diff import get_diff_content, parse_diff


class TestParseDiff:
    def test_basic(self) -> None:
        raw = "diff --git a/src/a.py b/src/a.py\n+line1\n+line2\ndiff --git a/src/b.py b/src/b.py\n-removed\n"
        result = parse_diff(raw)
        assert "src/a.py" in result
        assert "src/b.py" in result
        assert "+line1" in result["src/a.py"]

    def test_empty(self) -> None:
        assert parse_diff("") == {}

    def test_malformed_header(self) -> None:
        raw = "diff --git malformed\n+content\n"
        assert parse_diff(raw) == {}

    def test_skips_lock_files(self) -> None:
        raw = (
            "diff --git a/package-lock.json b/package-lock.json\n"
            "+huge lock content\n"
            "diff --git a/src/real.py b/src/real.py\n"
            "+real code\n"
        )
        result = parse_diff(raw)
        assert "package-lock.json" not in result
        assert "src/real.py" in result

    def test_skips_pyc(self) -> None:
        raw = "diff --git a/cache.pyc b/cache.pyc\n+binary\n"
        assert parse_diff(raw) == {}

    def test_skips_node_modules(self) -> None:
        raw = "diff --git a/node_modules/x.js b/node_modules/x.js\n+x\n"
        assert parse_diff(raw) == {}

    def test_max_files(self) -> None:
        lines = []
        for i in range(10):
            lines.append(f"diff --git a/f{i}.py b/f{i}.py")
            lines.append(f"+content{i}")
        raw = "\n".join(lines)
        result = parse_diff(raw, max_files=3)
        assert len(result) == 3

    def test_max_lines_per_file(self) -> None:
        lines = ["diff --git a/big.py b/big.py"]
        for i in range(100):
            lines.append(f"+line{i}")
        raw = "\n".join(lines)
        result = parse_diff(raw, max_lines_per_file=5)
        assert result["big.py"].count("\n") == 4  # 5 lines = 4 newlines


class TestGetDiffContent:
    def test_real_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "T"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo, capture_output=True, check=True)
        env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/local/bin"}
        (repo / "a.py").write_text("x\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T10:00:00", "GIT_COMMITTER_DATE": "2026-04-07T10:00:00"},
        )
        (repo / "b.py").write_text("y\n")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-m", "add b"],
            cwd=repo,
            capture_output=True,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": "2026-04-07T11:00:00", "GIT_COMMITTER_DATE": "2026-04-07T11:00:00"},
        )
        hashes = (
            subprocess.run(
                ["git", "log", "--format=%H"],
                cwd=repo,
                capture_output=True,
                text=True,
                check=True,
            )
            .stdout.strip()
            .splitlines()
        )
        # hashes[0] is newest, hashes[1] is oldest
        first, last = hashes[1], hashes[0]
        result = get_diff_content(repo, first, last)
        assert "b.py" in result


class TestParseDiffEdgeCases:
    def test_empty_diff_for_file(self) -> None:
        raw = "diff --git a/empty.py b/empty.py\ndiff --git a/real.py b/real.py\n+content\n"
        result = parse_diff(raw)
        assert "empty.py" not in result
        assert "real.py" in result
