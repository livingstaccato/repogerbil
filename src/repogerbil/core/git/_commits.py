# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Commit retrieval and parsing functions."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from repogerbil.core.errors import GitCommandError

from ._runner import _run_git
from ._types import _REF_RE, CommitInfo


def get_active_dates(repo_path: str | Path) -> set[str]:
    """Return all YYYY-MM-DD strings with commits (author date)."""
    output = _run_git(repo_path, "log", "--format=%as", "--all")
    return set(output.strip().splitlines()) if output.strip() else set()


def resolve_head_branch(repo_path: str | Path) -> str:
    """Return the current local branch name pointed to by HEAD.

    Raises:
        GitCommandError: If HEAD is detached or branch resolution fails.
    """
    try:
        branch = _run_git(repo_path, "symbolic-ref", "--short", "HEAD", timeout=10).strip()
    except GitCommandError as e:
        msg = f"Unable to resolve source branch from HEAD in {repo_path}."
        raise GitCommandError(msg, returncode=e.returncode, stderr=e.stderr) from e
    if not branch:
        msg = f"Unable to resolve source branch from HEAD in {repo_path}."
        raise GitCommandError(msg, returncode=1, stderr="empty branch name")
    return branch


def get_hidden_ref_hashes(repo_path: str | Path) -> list[str]:
    """Return commit hashes for unreachable objects in the repository."""
    try:
        output = _run_git(
            repo_path,
            "fsck",
            "--full",
            "--no-reflogs",
            "--unreachable",
            "--no-progress",
        )
    except GitCommandError:
        return []

    hashes: list[str] = []
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) >= 3 and parts[0] == "unreachable" and parts[1] == "commit":
            hashes.append(parts[2])
    return hashes


def get_hidden_ref_dates(repo_path: str | Path) -> set[str]:
    """Return author dates for unreachable commits in the repository."""
    dates: set[str] = set()
    for commit_hash in get_hidden_ref_hashes(repo_path):
        try:
            output = _run_git(repo_path, "show", "--no-patch", "--format=%as", commit_hash, timeout=10)
        except GitCommandError:
            continue
        date_str = output.strip()
        if date_str:
            dates.add(date_str)
    return dates


def get_commit_for_hash(
    repo_path: str | Path,
    commit_hash: str,
    message_depth: str = "subject",
    include_files: bool = False,
) -> CommitInfo:
    """Return commit info for a specific hash."""
    fmt = "%H%x00%as%x00%at%x00%s%x00%b"
    output = _run_git(repo_path, "show", "--no-patch", f"--format={fmt}", commit_hash, timeout=20)
    parts = output.strip().split("\x00", 4)
    if len(parts) < 5:
        raise GitCommandError(
            f"Git command failed: git show --no-patch --format={fmt} {commit_hash}",
            returncode=1,
            stderr="unexpected commit output",
        )

    body = parts[4].strip()
    refs = [f"#{r}" for r in _REF_RE.findall(body)]
    commit = CommitInfo(
        hash=parts[0].strip(),
        date=parts[1].strip(),
        subject=parts[3].strip(),
        body=body if message_depth == "full" else "",
        refs=refs if message_depth in ("refs", "full") else [],
        timestamp=int(parts[2].strip()),
    )

    if not include_files:
        return commit

    files_output = _run_git(
        repo_path,
        "diff-tree",
        "--root",
        "--no-commit-id",
        "--name-only",
        "-r",
        "--no-renames",
        "--no-ext-diff",
        commit_hash,
        timeout=20,
    )
    files: list[str] = []
    for line in files_output.splitlines():
        stripped = line.strip()
        if stripped:
            files.append(stripped)

    return replace(commit, files=files)


def get_commits_for_hashes(
    repo_path: str | Path,
    hashes: list[str],
    message_depth: str = "subject",
    include_files: bool = False,
) -> list[CommitInfo]:
    """Return commit info objects for an explicit list of hashes."""
    commits: list[CommitInfo] = []
    for commit_hash in hashes:
        commits.append(
            get_commit_for_hash(
                repo_path,
                commit_hash,
                message_depth=message_depth,
                include_files=include_files,
            )
        )
    commits.sort(key=lambda c: c.date)
    return commits


def _parse_commits_with_body(repo_path: str | Path, date_str: str, message_depth: str) -> list[CommitInfo]:
    """Parse commits using full message format (body + refs)."""
    fmt = "%H%x00%as%x00%at%x00%s%x00%b%x00END"
    output = _run_git(repo_path, "log", f"--format={fmt}", "--all")
    commits: list[CommitInfo] = []
    for block in output.split("\x00END"):
        parts = block.strip().split("\x00", 4)
        if len(parts) >= 3 and parts[1].strip() == date_str:
            body = parts[4].strip() if len(parts) > 4 else ""
            refs = [f"#{r}" for r in _REF_RE.findall(body)]
            commits.append(
                CommitInfo(
                    hash=parts[0].strip(),
                    date=parts[1].strip(),
                    subject=parts[3].strip(),
                    body=body if message_depth == "full" else "",
                    refs=refs,
                    timestamp=int(parts[2].strip()),
                )
            )
    return commits


def _parse_commits_subject_only(repo_path: str | Path, date_str: str) -> list[CommitInfo]:
    """Parse commits using subject-only format."""
    output = _run_git(repo_path, "log", "--format=%H\t%as\t%at\t%s", "--all")
    commits: list[CommitInfo] = []
    for line in output.strip().splitlines():
        parts = line.split("\t", 3)
        if len(parts) >= 3 and parts[1] == date_str:
            commits.append(
                CommitInfo(
                    hash=parts[0],
                    date=parts[1],
                    subject=parts[3] if len(parts) > 3 else "",
                    timestamp=int(parts[2]),
                )
            )
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
            timestamp=c.timestamp,
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


def get_commits_for_path(
    repo_path: str | Path,
    subpath: str,
    all_branches: bool = True,
    include_files: bool = False,
    message_depth: str = "subject",
) -> list[CommitInfo]:
    """Get commits that touched a subdirectory (path-scoped commit collection).

    Args:
        repo_path: Path to the git repository.
        subpath: Subdirectory path to filter by (e.g., "pyvider-cty").
        all_branches: If True, use --all to search all branches.
        include_files: Attach per-commit file lists.
        message_depth: "subject", "refs" (extract issue refs), or "full" (include body).

    Returns:
        List of CommitInfo for commits that touched the subpath, sorted oldest first.
    """
    fmt = (
        "%H%x00%as%x00%at%x00%s%x00%b%x00END"
        if message_depth in ("refs", "full")
        else "%H%x00%as%x00%at%x00%s"
    )

    cmd = ["log", f"--format={fmt}"]
    if all_branches:
        cmd.append("--all")
    cmd.extend(["--", f"{subpath}/"])

    output = _run_git(repo_path, *cmd)
    commits: list[CommitInfo] = []

    if message_depth in ("refs", "full"):
        for block in output.split("\x00END"):
            parts = block.strip().split("\x00", 4)
            if len(parts) >= 3:
                body = parts[4].strip() if len(parts) > 4 else ""
                refs = [f"#{r}" for r in _REF_RE.findall(body)]
                commits.append(
                    CommitInfo(
                        hash=parts[0].strip(),
                        date=parts[1].strip(),
                        subject=parts[3].strip() if len(parts) > 3 else "",
                        body=body if message_depth == "full" else "",
                        refs=refs,
                        timestamp=int(parts[2].strip()),
                    )
                )
    else:
        for line in output.strip().splitlines():
            parts = line.split("\x00", 3)
            if len(parts) >= 3:  # pragma: no cover — false branch unreachable with valid git output
                commits.append(
                    CommitInfo(
                        hash=parts[0],
                        date=parts[1],
                        subject=parts[3] if len(parts) > 3 else "",
                        timestamp=int(parts[2]),
                    )
                )

    commits.sort(key=lambda c: c.timestamp)

    if include_files and commits:
        commits = _attach_file_lists(repo_path, commits)

    return commits
