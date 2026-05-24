# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for realign.py — re-keying legacy jsonl records to current SHAs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from repogerbil.core import realign as realign_mod
from repogerbil.core.realign import _LocalCommit, realign_jsonl


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    for cmd in [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.test"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
    ]:
        subprocess.run(cmd, cwd=repo, capture_output=True, check=False)


def _commit(
    repo: Path,
    files: dict[str, str],
    message: str,
    date: str | None = None,
) -> str:
    env = os.environ.copy()
    if date:
        env["GIT_COMMITTER_DATE"] = f"{date}T12:00:00"
        env["GIT_AUTHOR_DATE"] = f"{date}T12:00:00"
    for fname, content in files.items():
        (repo / fname).write_text(content)
    subprocess.run(["git", "add", "."], cwd=repo, env=env, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, env=env, capture_output=True, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class TestRealignBasic:
    def test_missing_jsonl_returns_empty_result(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)

        r = realign_jsonl(repo, tmp_path / "missing.jsonl")

        assert r.total_records == 0
        assert r.realigned == 0

    def test_already_verified_unchanged(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        sha = _commit(repo, {"a.txt": "1"}, "feat: one")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": sha,
                    "date": "2026-04-20",
                    "subjects": ["feat: one"],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                }
            ],
        )
        r = realign_jsonl(repo, jsonl)
        assert r.already_verified == 1
        assert r.realigned == 0

    def test_exact_match_realigns(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        sha = _commit(repo, {"a.txt": "1", "b.txt": "2"}, "feat: add", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,  # legacy hash, doesn't exist locally
                    "date": "2025-10-15",
                    "subjects": ["feat: better worded"],
                    "body": "body",
                    "changes": [
                        {"file": "a.txt", "description": "x"},
                        {"file": "b.txt", "description": "y"},
                    ],
                }
            ],
        )
        r = realign_jsonl(repo, jsonl)
        assert r.realigned == 1
        assert r.exact_matches == 1
        after = _read_jsonl(jsonl)
        assert after[0]["hash"] == sha
        assert after[0]["date"] == "2025-10-15"
        # Content preserved:
        assert after[0]["subjects"] == ["feat: better worded"]
        assert after[0]["body"] == "body"

    def test_fuzzy_match_within_one_day(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        sha = _commit(repo, {"a.txt": "1"}, "feat: one", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,
                    "date": "2025-10-16",  # off by one day
                    "subjects": ["legacy"],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                }
            ],
        )
        r = realign_jsonl(repo, jsonl)
        assert r.realigned == 1
        assert r.exact_matches == 0  # same fileset but different date
        after = _read_jsonl(jsonl)
        assert after[0]["hash"] == sha
        # Date updated to the matched commit's date:
        assert after[0]["date"] == "2025-10-15"

    def test_unalignable_preserved(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        _commit(repo, {"a.txt": "1"}, "feat: one", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,
                    "date": "1999-01-01",  # way out of window
                    "subjects": ["ancient"],
                    "body": "",
                    "changes": [{"file": "nonexistent.txt", "description": ""}],
                }
            ],
        )
        r = realign_jsonl(repo, jsonl)
        assert r.unalignable == 1
        assert r.realigned == 0
        after = _read_jsonl(jsonl)
        assert after[0]["hash"] == "f" * 40  # unchanged

    def test_record_without_file_evidence_not_realigned(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        _commit(repo, {"a.txt": "1"}, "feat: one", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,
                    "date": "2025-10-15",
                    "subjects": ["legacy"],
                    "body": "",
                    "changes": [],
                }
            ],
        )
        r = realign_jsonl(repo, jsonl)
        assert r.realigned == 0
        assert r.unalignable == 1

    def test_dry_run_no_write(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        _commit(repo, {"a.txt": "1"}, "feat: one", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,
                    "date": "2025-10-15",
                    "subjects": ["legacy"],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                }
            ],
        )
        original = jsonl.read_text()
        r = realign_jsonl(repo, jsonl, dry_run=True)
        assert r.realigned == 1
        assert jsonl.read_text() == original  # unchanged on disk

    def test_idempotent(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        _commit(repo, {"a.txt": "1"}, "feat: one", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,
                    "date": "2025-10-15",
                    "subjects": ["legacy"],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                }
            ],
        )
        first = realign_jsonl(repo, jsonl)
        assert first.realigned == 1
        second = realign_jsonl(repo, jsonl)
        assert second.realigned == 0
        assert second.already_verified == 1


class TestRealignPicking:
    def test_picks_exact_over_fuzzy(self, tmp_path: Path) -> None:
        """When one candidate is exact and another is date-match only, exact wins."""
        repo = tmp_path / "repo"
        _init_repo(repo)
        _commit(repo, {"a.txt": "1"}, "c1", date="2025-10-15")  # fileset differs
        sha_exact = _commit(repo, {"b.txt": "1", "c.txt": "2"}, "c2", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": "f" * 40,
                    "date": "2025-10-15",
                    "subjects": [],
                    "body": "",
                    "changes": [
                        {"file": "b.txt", "description": ""},
                        {"file": "c.txt", "description": ""},
                    ],
                }
            ],
        )
        realign_jsonl(repo, jsonl)
        after = _read_jsonl(jsonl)
        assert after[0]["hash"] == sha_exact

    def test_mixed_records(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        sha1 = _commit(repo, {"a.txt": "1"}, "c1", date="2025-10-15")
        sha2 = _commit(repo, {"b.txt": "1"}, "c2", date="2025-10-16")
        jsonl = tmp_path / "s.jsonl"
        _write_jsonl(
            jsonl,
            [
                {
                    "hash": sha1,
                    "date": "2025-10-15",
                    "subjects": [],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                },
                {
                    "hash": "f" * 40,
                    "date": "2025-10-16",
                    "subjects": [],
                    "body": "",
                    "changes": [{"file": "b.txt", "description": ""}],
                },
                {
                    "hash": "e" * 40,
                    "date": "1999-01-01",
                    "subjects": [],
                    "body": "",
                    "changes": [{"file": "zzz.txt", "description": ""}],
                },
            ],
        )
        r = realign_jsonl(repo, jsonl)
        assert r.total_records == 3
        assert r.already_verified == 1
        assert r.realigned == 1
        assert r.unalignable == 1
        after = _read_jsonl(jsonl)
        assert after[0]["hash"] == sha1
        assert after[1]["hash"] == sha2
        assert after[2]["hash"] == "e" * 40  # unchanged

    def test_blank_jsonl_lines_are_ignored(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        _init_repo(repo)
        sha = _commit(repo, {"a.txt": "1"}, "c1", date="2025-10-15")
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            "\n"
            + json.dumps(
                {
                    "hash": sha,
                    "date": "2025-10-15",
                    "subjects": [],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                }
            )
            + "\n\n"
        )

        r = realign_jsonl(repo, jsonl)

        assert r.total_records == 1
        assert r.already_verified == 1


class TestRealignInternals:
    def test_jaccard_empty_sets(self) -> None:
        assert realign_mod._jaccard(frozenset(), frozenset()) == 0.0

    def test_date_window_invalid_date(self) -> None:
        assert realign_mod._date_window("not-a-date", 7) == set()

    def test_pick_best_empty_and_no_overlap(self) -> None:
        candidate = _LocalCommit(hash="a" * 40, date="2025-10-15", timestamp=1, files=frozenset({"a.py"}))

        assert realign_mod._pick_best([], frozenset({"a.py"}), "2025-10-15") is None
        assert realign_mod._pick_best([candidate], frozenset({"b.py"}), "2025-10-15") is None

    def test_pick_best_handles_invalid_record_date(self) -> None:
        candidate = _LocalCommit(hash="a" * 40, date="2025-10-15", timestamp=1, files=frozenset())

        assert realign_mod._pick_best([candidate], frozenset(), "not-a-date") == candidate

    def test_find_match_falls_through_non_exact_same_day(self) -> None:
        candidate = _LocalCommit(hash="a" * 40, date="2025-10-15", timestamp=1, files=frozenset({"a.py"}))

        match, is_exact = realign_mod._find_match(
            {"2025-10-15": [candidate]}, "2025-10-15", frozenset({"a.py", "b.py"})
        )

        assert match == candidate
        assert is_exact is False

    def test_scan_local_commits_skips_malformed_metadata(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def fake_run_git(repo_path: Path, *args: str, timeout: int) -> str:
            if "--name-only" in args:
                return "orphan.py\n" + "a" * 40 + "\ntracked.py\n"
            return "\n".join(
                [
                    "malformed",
                    "b" * 40 + "\x002025-10-15\x00not-an-int",
                    "a" * 40 + "\x002025-10-15\x00123",
                ]
            )

        monkeypatch.setattr(realign_mod, "_run_git", fake_run_git)

        commits = realign_mod._scan_local_commits(tmp_path)

        assert commits == [
            _LocalCommit(hash="a" * 40, date="2025-10-15", timestamp=123, files=frozenset({"tracked.py"}))
        ]
