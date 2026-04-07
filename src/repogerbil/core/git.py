# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git analysis via subprocess — no GitPython dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess

_SHORTSTAT_FILE_RE = re.compile(r"(\d+)\s+file")
_SHORTSTAT_INS_RE = re.compile(r"(\d+)\s+insertion")
_SHORTSTAT_DEL_RE = re.compile(r"(\d+)\s+deletion")

_REF_RE = re.compile(r"(?:Fix(?:es)?|Clos(?:e[ds]?|ing)|Ref(?:s)?)\s+#(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class CommitInfo:
    """Immutable representation of a single git commit."""

    hash: str
    date: str
    subject: str
    files: list[str] = field(default_factory=list)
    body: str = ""
    refs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DiffStats:
    """Aggregate diff statistics for a commit range."""

    commits: int
    files_changed: int
    insertions: int
    deletions: int


def _run_git(repo_path: str | Path, *args: str, timeout: int = 60) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(  # noqa: S603 — git is a trusted binary
        ["git", *args],  # noqa: S607 — partial path is intentional
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout


def parse_shortstat(stat_line: str) -> dict[str, int]:
    """Parse a git diff --shortstat line into files/insertions/deletions."""
    stats: dict[str, int] = {"files_changed": 0, "insertions": 0, "deletions": 0}
    m = _SHORTSTAT_FILE_RE.search(stat_line)
    if m:
        stats["files_changed"] = int(m.group(1))
    m = _SHORTSTAT_INS_RE.search(stat_line)
    if m:
        stats["insertions"] = int(m.group(1))
    m = _SHORTSTAT_DEL_RE.search(stat_line)
    if m:
        stats["deletions"] = int(m.group(1))
    return stats


def get_active_dates(repo_path: str | Path) -> set[str]:
    """Return all YYYY-MM-DD strings with commits (author date)."""
    output = _run_git(repo_path, "log", "--format=%as", "--all")
    return set(output.strip().splitlines()) if output.strip() else set()


def _parse_commits_with_body(repo_path: str | Path, date_str: str, message_depth: str) -> list[CommitInfo]:
    """Parse commits using full message format (body + refs)."""
    fmt = "%H%x00%as%x00%s%x00%b%x00END"
    output = _run_git(repo_path, "log", f"--format={fmt}", "--all")
    commits: list[CommitInfo] = []
    for block in output.split("\x00END"):
        parts = block.strip().split("\x00", 3)
        if len(parts) >= 3 and parts[1].strip() == date_str:
            body = parts[3].strip() if len(parts) > 3 else ""
            refs = [f"#{r}" for r in _REF_RE.findall(body)]
            commits.append(
                CommitInfo(
                    hash=parts[0].strip(),
                    date=parts[1].strip(),
                    subject=parts[2].strip(),
                    body=body if message_depth == "full" else "",
                    refs=refs,
                )
            )
    return commits


def _parse_commits_subject_only(repo_path: str | Path, date_str: str) -> list[CommitInfo]:
    """Parse commits using subject-only format."""
    output = _run_git(repo_path, "log", "--format=%H\t%as\t%s", "--all")
    commits: list[CommitInfo] = []
    for line in output.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[1] == date_str:
            commits.append(CommitInfo(hash=parts[0], date=parts[1], subject=parts[2]))
    return commits


def _attach_file_lists(repo_path: str | Path, commits: list[CommitInfo]) -> list[CommitInfo]:
    """Attach per-commit file lists by parsing --name-only output."""
    output = _run_git(repo_path, "log", "--format=%H", "--name-only", "--all")
    hash_files: dict[str, list[str]] = {}
    current_hash: str | None = None
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) == 40 and all(c in "0123456789abcdef" for c in stripped):
            current_hash = stripped
            hash_files[current_hash] = []
        elif current_hash:  # pragma: no branch — always true after first hash line
            hash_files[current_hash].append(stripped)

    return [
        CommitInfo(
            hash=c.hash,
            date=c.date,
            subject=c.subject,
            files=hash_files.get(c.hash, []),
            body=c.body,
            refs=c.refs,
        )
        for c in commits
    ]


def get_commits_for_date(
    repo_path: str | Path,
    date_str: str,
    message_depth: str = "subject",
    include_files: bool = False,
) -> list[CommitInfo]:
    """Get commits for a date using author date (%as).

    Args:
        repo_path: Path to the git repository.
        date_str: YYYY-MM-DD date string.
        message_depth: "subject", "refs" (extract issue refs), or "full" (include body).
        include_files: Attach per-commit file lists.
    """
    if message_depth in ("refs", "full"):
        commits = _parse_commits_with_body(repo_path, date_str, message_depth)
    else:
        commits = _parse_commits_subject_only(repo_path, date_str)

    commits.reverse()

    if include_files and commits:
        commits = _attach_file_lists(repo_path, commits)

    return commits


def get_diff_stats(repo_path: str | Path, first_hash: str, last_hash: str) -> DiffStats:
    """Get aggregate diff stats between two commits."""
    output = _run_git(repo_path, "diff", "--shortstat", f"{first_hash}^..{last_hash}", timeout=30)
    stat_line = output.strip()
    if not stat_line:  # pragma: no branch — first commit fallback
        output = _run_git(repo_path, "diff", "--shortstat", "--root", last_hash, timeout=30)
        stat_line = output.strip()
    if not stat_line:
        return DiffStats(commits=0, files_changed=0, insertions=0, deletions=0)
    parsed = parse_shortstat(stat_line)
    return DiffStats(commits=0, **parsed)
