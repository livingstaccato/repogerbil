# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for forward-only JSONL metadata catch-up."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess

import pytest

from repogerbil.core.catch_up import (
    _commit_signature,
    _read_signatures_for_date,
    _record_signature,
    append_new_commits,
    build_record,
    count_jsonl_entries,
    read_latest_date,
    read_recorded_hashes,
    record_missing_commits,
)
from repogerbil.core.git import CommitInfo


def _init_repo(repo: Path) -> None:
    for cmd in [
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "t@t.test"],
        ["git", "config", "user.name", "T"],
        ["git", "config", "commit.gpgsign", "false"],
    ]:
        subprocess.run(cmd, cwd=repo, capture_output=True, check=False)


def _commit(repo: Path, file: str, content: str, message: str, date: str = "2026-04-07T10:00:00") -> str:
    (repo / file).write_text(content)
    subprocess.run(["git", "add", file], cwd=repo, capture_output=True, check=True)
    env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, capture_output=True, check=True, env=env)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    return sha


class TestReadRecordedHashes:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_recorded_hashes(tmp_path / "nope.jsonl") == set()

    def test_reads_hashes(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "r.jsonl"
        jsonl.write_text(
            json.dumps({"hash": "a" * 40, "date": "2026-01-01"})
            + "\n"
            + json.dumps({"hash": "b" * 40, "date": "2026-01-02"})
            + "\n"
        )
        assert read_recorded_hashes(jsonl) == {"a" * 40, "b" * 40}

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "r.jsonl"
        jsonl.write_text(
            "not json\n"
            + json.dumps({"hash": "a" * 40})
            + "\n"
            + "\n"  # blank
            + json.dumps({"date": "2026-01-01"})
            + "\n"  # no hash
        )
        assert read_recorded_hashes(jsonl) == {"a" * 40}


class TestCountJsonlEntries:
    def test_missing_returns_zero(self, tmp_path: Path) -> None:
        assert count_jsonl_entries(tmp_path / "nope.jsonl") == 0

    def test_counts_non_empty_lines(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "r.jsonl"
        jsonl.write_text('{"hash":"a"}\n\n{"hash":"b"}\n')
        assert count_jsonl_entries(jsonl) == 2


class TestBuildRecord:
    def test_basic_shape(self) -> None:
        c = CommitInfo(
            hash="x" * 40,
            date="2026-04-20",
            subject="feat: add thing",
            files=["src/a.py", "src/b.py"],
            body="Some body\ntext.",
            timestamp=1700000000,
        )
        rec = build_record(c)
        assert rec == {
            "hash": "x" * 40,
            "date": "2026-04-20",
            "subjects": ["feat: add thing"],
            "body": "Some body\ntext.",
            "changes": [
                {"file": "src/a.py", "description": ""},
                {"file": "src/b.py", "description": ""},
            ],
        }

    def test_empty_subject_yields_empty_subjects(self) -> None:
        c = CommitInfo(hash="y" * 40, date="2026-04-20", subject="", timestamp=0)
        assert build_record(c)["subjects"] == []


class TestRecordMissingCommits:
    def test_fresh_repo_creates_jsonl(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        _commit(repo, "b.txt", "2", "fix: two")

        jsonl = tmp_path / "repo.summaries.jsonl"
        result = record_missing_commits(repo, jsonl)

        assert result.new_entries == 2
        assert result.existing_entries == 0
        assert result.skipped_dedup == 0
        assert jsonl.exists()
        lines = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
        assert [r["subjects"][0] for r in lines] == ["feat: one", "fix: two"]

    def test_idempotent(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        first = record_missing_commits(repo, jsonl)
        assert first.new_entries == 1

        second = record_missing_commits(repo, jsonl)
        assert second.new_entries == 0
        assert second.skipped_dedup == 1
        assert count_jsonl_entries(jsonl) == 1

    def test_catch_up_adds_only_new_commits(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        record_missing_commits(repo, jsonl)
        assert count_jsonl_entries(jsonl) == 1

        _commit(repo, "b.txt", "2", "fix: two")
        _commit(repo, "c.txt", "3", "docs: three")
        result = record_missing_commits(repo, jsonl, full_scan=True)
        assert result.new_entries == 2
        assert count_jsonl_entries(jsonl) == 3

        lines = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
        assert [r["subjects"][0] for r in lines] == ["feat: one", "fix: two", "docs: three"]

    def test_scan_skips_malformed_timestamps(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core import catch_up as catch_up_mod

        def fake_run_git(repo_path: Path, *args: str, timeout: int) -> str:
            if "--name-only" in args:
                return ""
            return "a" * 40 + "\x002026-04-20\x00not-an-int\x00bad\x00body\x00END"

        monkeypatch.setattr(catch_up_mod, "_run_git", fake_run_git)

        assert catch_up_mod._scan_head_commits(tmp_path) == []

    def test_attach_files_ignores_lines_before_first_hash(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from repogerbil.core import catch_up as catch_up_mod

        def fake_run_git(repo_path: Path, *args: str, timeout: int) -> str:
            return "orphan.txt\n\x00" + "a" * 40 + "\ntracked.txt\n"

        monkeypatch.setattr(catch_up_mod, "_run_git", fake_run_git)
        commit = CommitInfo(hash="a" * 40, date="2026-04-20", subject="feat: one", timestamp=1)

        [attached] = catch_up_mod._attach_files(tmp_path, [commit], since_ref=None)
        assert attached.files == ["tracked.txt"]

    def test_attach_files_handles_hex_like_filename(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A file whose name is 40 lowercase hex chars must not be treated as a hash."""
        from repogerbil.core import catch_up as catch_up_mod

        hex_filename = "0" * 40  # exactly 40 lowercase-hex chars — looks like SHA-1
        commit_hash = "a" * 40

        def fake_run_git(repo_path: Path, *args: str, timeout: int) -> str:
            return f"\x00{commit_hash}\n{hex_filename}\nreal.txt\n"

        monkeypatch.setattr(catch_up_mod, "_run_git", fake_run_git)
        commit = CommitInfo(hash=commit_hash, date="2026-04-20", subject="feat: one", timestamp=1)

        [attached] = catch_up_mod._attach_files(tmp_path, [commit], since_ref=None)
        assert attached.files == [hex_filename, "real.txt"]

    def test_attach_files_handles_sha256_hash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Parser must accept 64-char SHA-256 hashes via the NUL sentinel."""
        from repogerbil.core import catch_up as catch_up_mod

        commit_hash = "b" * 64  # SHA-256 length

        def fake_run_git(repo_path: Path, *args: str, timeout: int) -> str:
            return f"\x00{commit_hash}\nfile.py\n"

        monkeypatch.setattr(catch_up_mod, "_run_git", fake_run_git)
        commit = CommitInfo(hash=commit_hash, date="2026-04-20", subject="feat: one", timestamp=1)

        [attached] = catch_up_mod._attach_files(tmp_path, [commit], since_ref=None)
        assert attached.files == ["file.py"]

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = record_missing_commits(repo, jsonl, dry_run=True)
        assert result.new_entries == 1  # would-be count
        assert not jsonl.exists()

    def test_records_body_and_files(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "a.txt").write_text("hello")
        (repo / "b.txt").write_text("world")
        subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: multi\n\nBody line 1\nBody line 2\n"],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        jsonl = tmp_path / "r.summaries.jsonl"
        record_missing_commits(repo, jsonl)

        rec = json.loads(jsonl.read_text().strip())
        assert rec["subjects"] == ["feat: multi"]
        assert "Body line 1" in rec["body"]
        assert sorted(c["file"] for c in rec["changes"]) == ["a.txt", "b.txt"]

    def test_since_ref_limits_range(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        sha_old = _commit(repo, "a.txt", "1", "feat: one")
        _commit(repo, "b.txt", "2", "fix: two")
        _commit(repo, "c.txt", "3", "docs: three")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = record_missing_commits(repo, jsonl, since_ref=sha_old)
        assert result.new_entries == 2  # two commits after sha_old

    def test_preexisting_jsonl_hashes_skipped(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        sha = _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"
        # Pre-seed jsonl with the existing commit's hash (simulates prior recording)
        jsonl.write_text(json.dumps({"hash": sha, "date": "2026-04-20"}) + "\n")

        result = record_missing_commits(repo, jsonl)
        assert result.new_entries == 0
        assert result.existing_entries == 1
        assert count_jsonl_entries(jsonl) == 1

    def test_legacy_append_new_commits_alias(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"

        result = append_new_commits(repo, jsonl)
        assert result.new_entries == 1


class TestReadLatestDate:
    def test_missing_returns_none(self, tmp_path: Path) -> None:
        assert read_latest_date(tmp_path / "nope.jsonl") is None

    def test_returns_max_date(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "r.jsonl"
        jsonl.write_text(
            json.dumps({"hash": "a", "date": "2026-01-01"})
            + "\n"
            + json.dumps({"hash": "b", "date": "2026-04-20"})
            + "\n"
            + json.dumps({"hash": "c", "date": "2026-03-15"})
            + "\n"
        )
        assert read_latest_date(jsonl) == "2026-04-20"


class TestDefaultDateCutoff:
    def test_jsonl_date_used_as_default_cutoff(self, tmp_path: Path) -> None:
        """When jsonl has a latest date, default scan uses it as git --since=."""
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        # Commit with committer-date in the past (before jsonl's latest date).
        import os

        env = os.environ.copy()
        env["GIT_COMMITTER_DATE"] = "2025-01-01T12:00:00"
        env["GIT_AUTHOR_DATE"] = "2025-01-01T12:00:00"
        (repo / "old.txt").write_text("x")
        subprocess.run(["git", "add", "old.txt"], cwd=repo, env=env, capture_output=True, check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat: old"], cwd=repo, env=env, capture_output=True, check=True
        )
        # Commit today (will be after any jsonl date we plant).
        _commit(repo, "new.txt", "y", "feat: new")

        jsonl = tmp_path / "r.summaries.jsonl"
        # Plant a record whose date sits between the two commits.
        jsonl.write_text(json.dumps({"hash": "f" * 40, "date": "2025-06-01"}) + "\n")

        result = record_missing_commits(repo, jsonl)
        # The 2025-01-01 commit is before the 2025-06-01 cutoff and is skipped.
        # The today commit is after and is recorded.
        assert result.new_entries == 1
        rec = json.loads(jsonl.read_text().splitlines()[-1])
        assert rec["subjects"] == ["feat: new"]

    def test_default_cutoff_uses_latest_date(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core import catch_up as catch_up_mod

        seen: dict[str, str | None] = {"since_date": None}

        def fake_scan_head_commits(
            repo_path: Path,
            since_ref: str | None = None,
            since_date: str | None = None,
        ) -> list[CommitInfo]:
            seen["since_date"] = since_date
            return []

        monkeypatch.setattr(catch_up_mod, "_scan_head_commits", fake_scan_head_commits)

        repo = tmp_path / "repo"
        repo.mkdir()
        jsonl = tmp_path / "r.summaries.jsonl"
        jsonl.write_text(json.dumps({"hash": "f" * 40, "date": "2025-06-01"}) + "\n")
        catch_up_mod.record_missing_commits(repo, jsonl)
        assert seen["since_date"] == "2025-06-01"

    def test_full_scan_flag_bypasses_date_cutoff(self, tmp_path: Path) -> None:
        from repogerbil.core import catch_up as catch_up_mod

        seen: list[str | None] = []

        def fake_scan_head_commits(
            repo_path: Path,
            since_ref: str | None = None,
            since_date: str | None = None,
        ) -> list[CommitInfo]:
            seen.append(since_date)
            return []

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(catch_up_mod, "_scan_head_commits", fake_scan_head_commits)
        try:
            repo = tmp_path / "repo"
            repo.mkdir()
            jsonl = tmp_path / "r.summaries.jsonl"
            jsonl.write_text(json.dumps({"hash": "f" * 40, "date": "2099-12-31"}) + "\n")
            catch_up_mod.record_missing_commits(repo, jsonl)
            catch_up_mod.record_missing_commits(repo, jsonl, full_scan=True)
        finally:
            monkeypatch.undo()

        assert seen[0] == "2099-12-31"
        assert seen[1] is None


class TestSchemaCompat:
    """Record shape matches what core.snapshot writes."""

    def test_all_expected_keys_present(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        jsonl = tmp_path / "r.summaries.jsonl"
        record_missing_commits(repo, jsonl)
        rec = json.loads(jsonl.read_text().strip())
        assert set(rec.keys()) == {"hash", "date", "subjects", "body", "changes"}
        assert isinstance(rec["subjects"], list)
        assert isinstance(rec["changes"], list)
        for ch in rec["changes"]:
            assert set(ch.keys()) == {"file", "description"}


class TestSignatures:
    def test_record_signature_and_commit_signature_match(self) -> None:
        commit = CommitInfo(
            hash="a" * 40,
            date="2026-05-24",
            subject="feat: one",
            body="body",
            files=["b.py", "a.py", "a.py"],
            timestamp=1,
        )
        rec = build_record(commit)
        assert _record_signature(rec) == _commit_signature(commit)

    def test_read_signatures_for_date(self, tmp_path: Path) -> None:
        jsonl = tmp_path / "r.summaries.jsonl"
        jsonl.write_text(
            json.dumps(
                {
                    "hash": "a" * 40,
                    "date": "2026-05-24",
                    "subjects": ["feat: one"],
                    "body": 123,
                    "changes": [{"file": "a.py", "description": ""}],
                }
            )
            + "\n"
            + "\n"
            + "{not-json}\n"
            + json.dumps({"hash": "b" * 40, "date": "2026-05-25", "subjects": ["feat: two"], "changes": []})
            + "\n"
        )
        sigs = _read_signatures_for_date(jsonl, "2026-05-24")
        assert len(sigs) == 1

    def test_read_signatures_for_date_missing_file(self, tmp_path: Path) -> None:
        assert _read_signatures_for_date(tmp_path / "missing.jsonl", "2026-05-24") == set()

    def test_record_signature_ignores_non_dict_changes(self) -> None:
        rec = {
            "subjects": ["feat: one"],
            "body": "b",
            "changes": ["not-a-dict", {"description": ""}, {"file": ""}, {"file": "x.py"}],
        }
        assert _record_signature(rec) == ("feat: one", "b", ("x.py",))

    def test_same_day_signature_dedup_skips_rewritten_hash(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        _commit(repo, "a.txt", "1", "feat: one")
        commit_date = subprocess.run(
            ["git", "show", "-s", "--format=%as", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        jsonl = tmp_path / "r.summaries.jsonl"
        # Different hash, same date/subject/body/files signature.
        jsonl.write_text(
            json.dumps(
                {
                    "hash": "f" * 40,
                    "date": commit_date,
                    "subjects": ["feat: one"],
                    "body": "",
                    "changes": [{"file": "a.txt", "description": ""}],
                }
            )
            + "\n"
        )

        result = record_missing_commits(repo, jsonl)
        assert result.new_entries == 0

    def test_same_day_signature_dedup_branch_covered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Exercise same-day signature skip path in the main loop."""
        from repogerbil.core import catch_up as catch_up_mod

        jsonl = tmp_path / "r.summaries.jsonl"
        jsonl.write_text(json.dumps({"hash": "f" * 40, "date": "2026-05-24"}) + "\n")
        commit = CommitInfo(
            hash="a" * 40,
            date="2026-05-24",
            subject="feat: one",
            body="",
            files=["a.py"],
            timestamp=1,
        )
        monkeypatch.setattr(catch_up_mod, "_scan_head_commits", lambda *args, **kwargs: [commit])
        monkeypatch.setattr(
            catch_up_mod, "_read_signatures_for_date", lambda *args, **kwargs: {_commit_signature(commit)}
        )

        result = catch_up_mod.record_missing_commits(tmp_path, jsonl)
        assert result.new_entries == 0
        assert result.skipped_dedup == 1

    def test_same_day_new_commit_not_missed(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        (repo / "a.txt").write_text("1")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: one"], cwd=repo, capture_output=True, check=True)
        first_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()
        first_date = subprocess.run(
            ["git", "show", "-s", "--format=%as", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

        jsonl = tmp_path / "r.summaries.jsonl"
        jsonl.write_text(json.dumps({"hash": first_sha, "date": first_date}) + "\n")

        (repo / "b.txt").write_text("2")
        subprocess.run(["git", "add", "b.txt"], cwd=repo, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: two"], cwd=repo, capture_output=True, check=True)

        result = record_missing_commits(repo, jsonl)
        assert result.new_entries == 1
