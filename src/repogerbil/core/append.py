# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Forward-only jsonl append.

Reads an existing ``.summaries.jsonl`` sidecar, walks the repo's current
HEAD history, and appends any commits not yet recorded. No LLM is invoked:
records are built verbatim from git data so forward-append is fast,
deterministic, and idempotent.

The record schema matches the one written by :mod:`repogerbil.core.snapshot`:

    {"hash": str, "date": "YYYY-MM-DD", "subjects": [str, ...],
     "body": str, "changes": [{"file": str, "description": str}, ...]}

For forward-append, ``subjects`` is always a single-element list (the commit
subject) and each ``changes`` entry has an empty ``description``, since no
LLM summary was generated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as date_type, timedelta
import json
from pathlib import Path
from typing import Any

from repogerbil.core.git import CommitInfo, _run_git


@dataclass(frozen=True)
class AppendResult:
    """Outcome of an append operation."""

    jsonl_path: str
    existing_entries: int
    new_entries: int
    skipped_dedup: int
    latest_hash: str | None


def read_recorded_hashes(jsonl_path: Path) -> set[str]:
    """Return the set of commit hashes already recorded in ``jsonl_path``."""
    hashes, _ = _read_recorded(jsonl_path)
    return hashes


def read_latest_date(jsonl_path: Path) -> str | None:
    """Return the max ``date`` (YYYY-MM-DD) seen in ``jsonl_path``, or ``None``."""
    _, latest = _read_recorded(jsonl_path)
    return latest


def _read_recorded(jsonl_path: Path) -> tuple[set[str], str | None]:
    """Single pass over the jsonl collecting hashes and the max date."""
    hashes: set[str] = set()
    latest: str | None = None
    if not jsonl_path.exists():
        return hashes, latest
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            h = rec.get("hash")
            if isinstance(h, str):
                hashes.add(h)
            d = rec.get("date")
            if isinstance(d, str) and (latest is None or d > latest):
                latest = d
    return hashes, latest


def count_jsonl_entries(jsonl_path: Path) -> int:
    """Return the number of non-empty lines in ``jsonl_path`` (0 if missing)."""
    if not jsonl_path.exists():
        return 0
    with jsonl_path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def _day_after(iso_date: str) -> str:
    """Return the next day in ISO format, or input unchanged if invalid."""
    try:
        return (date_type.fromisoformat(iso_date) + timedelta(days=1)).isoformat()
    except ValueError:
        return iso_date


def _scan_head_commits(
    repo_path: Path,
    since_ref: str | None = None,
    since_date: str | None = None,
) -> list[CommitInfo]:
    """Return HEAD commits (oldest first) with body + file list attached.

    When ``since_ref`` is given, restricts to ``<since_ref>..HEAD`` (exclusive
    of ``since_ref``). When ``since_date`` is given, restricts via git's
    ``--since=`` filter (committer-date based). Skips merge commits.
    """
    fmt = "%H%x00%as%x00%at%x00%s%x00%b%x00END"
    log_args = ["log", "--reverse", "--no-merges", f"--format={fmt}"]
    if since_date:
        log_args.append(f"--since={since_date}")
    if since_ref:
        log_args.append(f"{since_ref}..HEAD")
    output = _run_git(repo_path, *log_args, timeout=120)

    commits: list[CommitInfo] = []
    for block in output.split("\x00END"):
        parts = block.strip().split("\x00", 4)
        if len(parts) < 4:
            continue
        body = parts[4].strip() if len(parts) > 4 else ""
        try:
            ts = int(parts[2].strip())
        except ValueError:
            continue
        commits.append(
            CommitInfo(
                hash=parts[0].strip(),
                date=parts[1].strip(),
                subject=parts[3].strip(),
                body=body,
                timestamp=ts,
            )
        )

    # git log --reverse gives oldest-first topologically; preserve that order.
    if commits:
        commits = _attach_files(repo_path, commits, since_ref, since_date)
    return commits


def _attach_files(
    repo_path: Path,
    commits: list[CommitInfo],
    since_ref: str | None,
    since_date: str | None = None,
) -> list[CommitInfo]:
    """Attach per-commit file lists via a single ``git log --name-only`` pass."""
    log_args = ["log", "--reverse", "--no-merges", "--format=%H", "--name-only"]
    if since_date:
        log_args.append(f"--since={since_date}")
    if since_ref:
        log_args.append(f"{since_ref}..HEAD")
    output = _run_git(repo_path, *log_args, timeout=120)

    hash_files: dict[str, list[str]] = {}
    current: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) == 40 and all(c in "0123456789abcdef" for c in stripped):
            current = stripped
            hash_files[current] = []
        elif current is not None:
            hash_files[current].append(stripped)

    return [
        CommitInfo(
            hash=c.hash,
            date=c.date,
            subject=c.subject,
            files=hash_files.get(c.hash, []),
            body=c.body,
            refs=c.refs,
            timestamp=c.timestamp,
        )
        for c in commits
    ]


def build_record(commit: CommitInfo) -> dict[str, Any]:
    """Build a jsonl record for a single commit from git data only."""
    subjects = [commit.subject] if commit.subject else []
    changes = [{"file": f, "description": ""} for f in commit.files]
    return {
        "hash": commit.hash,
        "date": commit.date,
        "subjects": subjects,
        "body": commit.body,
        "changes": changes,
    }


def append_new_commits(
    repo_path: Path,
    jsonl_path: Path,
    since_ref: str | None = None,
    since_date: str | None = None,
    full_scan: bool = False,
    dry_run: bool = False,
) -> AppendResult:
    """Append any HEAD commits not yet recorded in ``jsonl_path``.

    Idempotent: runs twice produce the same jsonl, since each commit is
    keyed by its full SHA.

    Args:
        repo_path: Git repository to scan.
        jsonl_path: Path to the ``.summaries.jsonl`` sidecar to append to.
        since_ref: Optional ref used as exclusive lower bound (``<ref>..HEAD``).
        since_date: Optional date (YYYY-MM-DD) used as git ``--since=`` filter.
            Overrides the default date cutoff derived from the jsonl.
        full_scan: When ``True``, scan all HEAD history with no date/ref
            cutoff. Commits already in the jsonl are still skipped by hash.
            Useful for rebuilding a jsonl when history hashes are known to
            match.
        dry_run: When ``True``, report what would be appended without writing.

    Default behavior when none of ``since_ref``/``since_date``/``full_scan``
    are set: one day after the latest date found in ``jsonl_path`` is used as
    a git ``--since=`` cutoff. This avoids re-recording rewritten-history
    commits that share the same date as previously recorded entries.
    """
    hashes, latest_date = _read_recorded(jsonl_path)
    existing = len(hashes)

    effective_date = since_date
    if effective_date is None and since_ref is None and not full_scan:
        effective_date = _day_after(latest_date) if latest_date else None

    commits = _scan_head_commits(
        repo_path,
        since_ref=since_ref,
        since_date=effective_date,
    )
    new_commits = [c for c in commits if c.hash not in hashes]
    skipped = len(commits) - len(new_commits)

    if not dry_run and new_commits:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        with jsonl_path.open("a", encoding="utf-8") as fh:
            for commit in new_commits:
                fh.write(json.dumps(build_record(commit)) + "\n")

    latest = new_commits[-1].hash if new_commits else None
    return AppendResult(
        jsonl_path=str(jsonl_path),
        existing_entries=existing,
        new_entries=len(new_commits),
        skipped_dedup=skipped,
        latest_hash=latest,
    )
