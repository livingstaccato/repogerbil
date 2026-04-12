# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git analysis via subprocess — no GitPython dependency."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import subprocess

from repogerbil.core.errors import GitCommandError, NotAGitRepositoryError

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
    timestamp: int = 0  # unix epoch; 0 means only date available


@dataclass(frozen=True)
class DiffStats:
    """Aggregate diff statistics for a commit range."""

    commits: int
    files_changed: int
    insertions: int
    deletions: int


def _run_git(repo_path: str | Path, *args: str, timeout: int = 60) -> str:
    """Run a git command and return stdout.

    Raises:
        NotAGitRepositoryError: If the path is not a git repository.
        GitCommandError: If the git command fails.
    """
    result = subprocess.run(  # noqa: S603 — git is a trusted binary
        ["git", *args],  # noqa: S607 — partial path is intentional
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        stderr = result.stderr.strip()
        if "not a git repository" in stderr.lower():
            raise NotAGitRepositoryError(repo_path)
        raise GitCommandError(
            f"Git command failed: git {' '.join(args)}\n{stderr}",
            returncode=result.returncode,
            stderr=stderr,
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

    return CommitInfo(
        hash=commit.hash,
        date=commit.date,
        subject=commit.subject,
        files=files,
        body=commit.body,
        refs=commit.refs,
    )


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


def get_diff_stats(repo_path: str | Path, first_hash: str, last_hash: str) -> DiffStats:
    """Get aggregate diff stats between two commits.

    Uses ``first^..last`` to capture all changes in the range.  When
    ``first`` is the initial commit (no parent) git returns a non-zero exit
    code; in that case the function falls back to ``--root last``.
    When both hashes are identical, returns zero stats (no diff).
    """
    from repogerbil.core.errors import GitCommandError

    if first_hash == last_hash:
        return DiffStats(commits=0, files_changed=0, insertions=0, deletions=0)

    try:
        output = _run_git(repo_path, "diff", "--shortstat", f"{first_hash}^..{last_hash}", timeout=30)
    except GitCommandError:
        output = ""

    stat_line = output.strip()
    if not stat_line:  # pragma: no branch — first-commit fallback
        output = _run_git(repo_path, "diff", "--shortstat", "--root", last_hash, timeout=30)
        stat_line = output.strip()
    if not stat_line:
        return DiffStats(commits=0, files_changed=0, insertions=0, deletions=0)
    parsed = parse_shortstat(stat_line)
    return DiffStats(commits=0, **parsed)


def resolve_commit_trees(
    repo_path: str | Path,
    commits: list[CommitInfo],
    source_subdir: str | None = None,
) -> dict[str, str]:
    """Resolve tree SHA for each commit (monorepo subdir or full tree).

    Returns dict mapping commit hash → tree SHA.
    Falls back to full tree if subdir doesn't exist in commit.

    Args:
        repo_path: Path to git repository with all commits fetched.
        commits: List of commits to resolve trees for.
        source_subdir: Optional subdirectory for monorepo filtering.
    """
    tree_map: dict[str, str] = {}
    for commit in commits:
        try:
            if source_subdir:
                # Try subdir first (monorepo)
                tree_sha = _run_git(
                    repo_path, "rev-parse", f"{commit.hash}:{source_subdir}", timeout=10
                ).strip()
            else:
                # Full tree (standalone)
                tree_sha = _run_git(repo_path, "rev-parse", f"{commit.hash}^{{tree}}", timeout=10).strip()
        except GitCommandError:
            # Fall back to full tree if subdir doesn't exist
            tree_sha = _run_git(repo_path, "rev-parse", f"{commit.hash}^{{tree}}", timeout=10).strip()
        tree_map[commit.hash] = tree_sha
    return tree_map


def deduplicate_by_tree(
    commits: list[CommitInfo],
    tree_map: dict[str, str],
) -> list[CommitInfo]:
    """Deduplicate commits by tree SHA, keeping earliest of each unique state.

    Returns commits in chronological order with unique tree states only.

    Args:
        commits: List of commits (should be sorted chronologically).
        tree_map: Dict mapping commit hash → tree SHA.
    """
    # Map tree SHA → earliest commit with that state
    tree_to_commit: dict[str, CommitInfo] = {}
    for commit in commits:
        tree_sha = tree_map.get(commit.hash)
        if tree_sha and tree_sha not in tree_to_commit:
            tree_to_commit[tree_sha] = commit

    # Return unique commits in chronological order
    unique_commits = list(tree_to_commit.values())
    unique_commits.sort(key=lambda c: c.timestamp if c.timestamp else 0)
    return unique_commits
