# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Multi-repo snapshot — merge multiple repos into a single distilled daily history."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date, datetime
import os
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

import yaml

from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git


@dataclass(frozen=True)
class MultiSnapshotResult:
    """Result of a multi-repo snapshot operation."""

    dest_path: Path
    commits_created: int
    repos_included: list[str]


def create_multi_snapshot(
    source_repos: dict[str, Path],
    dest_path: Path,
    *,
    since: date | None = None,
    commit_time: str = "20:00",
    timezone: str = "America/Los_Angeles",
    changelog_dir: Path | None = None,
) -> MultiSnapshotResult:
    """Create an independent repo with one daily commit merging multiple source repos.

    Each source repo gets its own subdirectory in the destination. Commits are
    timestamped at commit_time in the specified timezone. Commit messages are
    assembled from changelog YAMLs when available.

    Args:
        source_repos: Mapping of name → path for source repositories.
        dest_path: Path for the new snapshot repository (must not exist or be empty).
        since: Only include dates on or after this date.
        commit_time: Time for daily commits (HH:MM format).
        timezone: IANA timezone name for commit timestamps.
        changelog_dir: Directory containing <repo>/<date>-<repo>-changelog.yaml files.

    Returns:
        MultiSnapshotResult with path and counts.
    """
    if dest_path.exists() and any(dest_path.iterdir()):
        msg = f"Destination already exists and is not empty: {dest_path}"
        raise RuntimeError(msg)

    # Collect active dates across all repos
    active_dates = _collect_all_active_dates(source_repos)
    if since:
        active_dates = [d for d in active_dates if d >= since]

    if not active_dates:
        dest_path.mkdir(parents=True, exist_ok=True)
        _run_git(dest_path, "init")
        return MultiSnapshotResult(dest_path=dest_path, commits_created=0, repos_included=[])

    # Initialize destination repo and fetch sources
    _init_dest_repo(dest_path, source_repos)

    # Load changelog messages
    changelog_messages = _load_multi_changelog_messages(changelog_dir) if changelog_dir else {}

    # Create daily commits
    repo_first_dates = _get_first_commit_dates(source_repos)
    repos_included: set[str] = set()
    commits_created = _create_daily_commits(
        dest_path,
        source_repos,
        active_dates,
        repo_first_dates,
        repos_included,
        changelog_messages,
        commit_time,
        timezone,
    )

    # Cleanup remotes
    for name in source_repos:
        with contextlib.suppress(GitCommandError):
            _run_git(dest_path, "remote", "remove", f"source-{name}")

    # Checkout main so working directory has files
    if commits_created > 0:  # pragma: no branch — active_dates guarantees ≥1 commit
        _run_git(dest_path, "checkout", "main", timeout=30)

    return MultiSnapshotResult(
        dest_path=dest_path,
        commits_created=commits_created,
        repos_included=sorted(repos_included),
    )


def _init_dest_repo(dest_path: Path, source_repos: dict[str, Path]) -> None:
    """Initialize the destination repo and add source remotes."""
    dest_path.mkdir(parents=True, exist_ok=True)
    _run_git(dest_path, "init")
    _run_git(dest_path, "config", "user.email", "repogerbil@localhost")
    _run_git(dest_path, "config", "user.name", "repogerbil")

    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        source_uri = path.resolve().as_uri()
        _run_git(dest_path, "remote", "add", f"source-{name}", source_uri)
        with contextlib.suppress(GitCommandError):
            _run_git(dest_path, "fetch", f"source-{name}", "--tags", timeout=120)


def _create_daily_commits(
    dest_path: Path,
    source_repos: dict[str, Path],
    active_dates: list[date],
    repo_first_dates: dict[str, date],
    repos_included: set[str],
    changelog_messages: dict[str, dict[str, str]],
    commit_time: str,
    timezone: str,
) -> int:
    """Create one commit per active day in the destination repo."""
    commits_created = 0
    for day in active_dates:
        repo_trees = _collect_repo_trees_for_day(
            dest_path,
            source_repos,
            day,
            repo_first_dates,
            repos_included,
        )
        if not repo_trees:  # pragma: no cover — dates come from repos that have commits
            continue

        combined_tree = _build_merged_tree(dest_path, repo_trees)
        message = _build_message(day, repo_trees, changelog_messages)
        timestamp = _make_timestamp(day, commit_time, timezone)
        _commit_tree(dest_path, combined_tree, message, timestamp)
        commits_created += 1

    return commits_created


def _collect_repo_trees_for_day(
    dest_path: Path,
    source_repos: dict[str, Path],
    day: date,
    repo_first_dates: dict[str, date],
    repos_included: set[str],
) -> dict[str, str]:
    """Collect tree SHAs for all repos that should appear on this day."""
    repo_trees: dict[str, str] = {}
    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        first_date = repo_first_dates.get(name)
        if first_date is None or day < first_date:
            continue
        tree_sha = _get_tree_at_date(dest_path, name, day)
        if tree_sha:  # pragma: no branch — tree always exists for fetched commits
            repo_trees[name] = tree_sha
            repos_included.add(name)
    return repo_trees


def _commit_tree(dest_path: Path, tree_sha: str, message: str, timestamp: str) -> None:
    """Create a commit on the tree with the given timestamp."""
    cmd = ["commit-tree", tree_sha, "-m", message]

    try:
        head = _run_git(dest_path, "rev-parse", "--verify", "HEAD", timeout=5).strip()
    except GitCommandError:
        head = ""
    if head:
        cmd.extend(["-p", head])

    env = dict(os.environ)
    env["GIT_AUTHOR_DATE"] = timestamp
    env["GIT_COMMITTER_DATE"] = timestamp

    result = subprocess.run(  # noqa: S603
        ["git", *cmd],  # noqa: S607
        cwd=str(dest_path),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    new_commit = result.stdout.strip()
    _run_git(dest_path, "update-ref", "refs/heads/main", new_commit)


def _collect_all_active_dates(source_repos: dict[str, Path]) -> list[date]:
    """Get the union of all active commit dates across repos."""
    all_dates: set[date] = set()
    for path in source_repos.values():
        if not path.exists() or not (path / ".git").exists():
            continue
        try:
            output = _run_git(path, "log", "--format=%as", timeout=30)
        except GitCommandError:
            continue
        for line in output.strip().split("\n"):
            if line:  # pragma: no branch — git log %as produces no blank lines
                all_dates.add(date.fromisoformat(line))
    return sorted(all_dates)


def _get_first_commit_dates(source_repos: dict[str, Path]) -> dict[str, date]:
    """Get the first commit date for each repo."""
    result: dict[str, date] = {}
    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        try:
            output = _run_git(path, "log", "--format=%as", "--reverse", timeout=30)
        except GitCommandError:
            continue
        first_line = output.strip().split("\n")[0] if output.strip() else ""
        if first_line:  # pragma: no branch — repos with commits always have output
            result[name] = date.fromisoformat(first_line)
    return result


def _get_tree_at_date(dest_path: Path, remote_name: str, day: date) -> str | None:
    """Get the tree SHA for a repo's state at end of a given day."""
    date_str = day.isoformat()
    try:
        output = _run_git(
            dest_path,
            "log",
            f"--until={date_str}T23:59:59",
            "--format=%H",
            "-1",
            f"--remotes=source-{remote_name}",
            timeout=10,
        )
        commit_hash = output.strip()
        if not commit_hash:  # pragma: no cover — day comes from same repo's history
            return None
        tree_sha = _run_git(dest_path, "rev-parse", f"{commit_hash}^{{tree}}", timeout=10).strip()
        return tree_sha
    except GitCommandError:  # pragma: no cover — fetched objects are always resolvable
        return None


def _build_merged_tree(dest_path: Path, repo_trees: dict[str, str]) -> str:
    """Build a combined tree with each repo as a subdirectory."""
    with tempfile.NamedTemporaryFile(prefix="multi-snap-idx-", delete=False) as tmp:
        index_file = tmp.name

    try:
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = index_file

        subprocess.run(
            ["git", "read-tree", "--empty"],  # noqa: S607
            cwd=str(dest_path),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )

        for name, tree_sha in sorted(repo_trees.items()):
            subprocess.run(  # noqa: S603
                ["git", "read-tree", f"--prefix={name}/", tree_sha],  # noqa: S607
                cwd=str(dest_path),
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )

        result = subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=str(dest_path),
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
        return result.stdout.strip()
    finally:
        Path(index_file).unlink(missing_ok=True)


def _make_timestamp(day: date, commit_time: str, tz_name: str) -> str:
    """Create an ISO8601 timestamp at the given time in the given timezone."""
    h, m = map(int, commit_time.split(":"))
    tz = ZoneInfo(tz_name)
    dt = datetime(day.year, day.month, day.day, h, m, 0, tzinfo=tz)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def _build_message(
    day: date,
    repo_trees: dict[str, str],
    changelog_messages: dict[str, dict[str, str]],
) -> str:
    """Build commit message from changelog YAMLs or fallback."""
    date_str = day.isoformat()
    lines = [f"{date_str} pyvider ecosystem", ""]

    has_changelog = False
    for name in sorted(repo_trees.keys()):
        if name in changelog_messages and date_str in changelog_messages[name]:
            msg = changelog_messages[name][date_str]
            lines.append(f"{name}: {msg}")
            has_changelog = True
        else:
            lines.append(f"{name}: [activity, no changelog]")

    if not has_changelog and len(repo_trees) == 1:
        name = next(iter(repo_trees))
        return f"{date_str} {name}"

    return "\n".join(lines)


def _load_multi_changelog_messages(changelog_dir: Path) -> dict[str, dict[str, str]]:
    """Load changelog titles+summaries for all repos in a changelog directory.

    Returns:
        Nested dict: {repo_name: {date_str: "title\\nsummary"}}
    """
    messages: dict[str, dict[str, str]] = {}

    if not changelog_dir.exists():
        return messages

    for repo_dir in changelog_dir.iterdir():
        if not repo_dir.is_dir():
            continue
        repo_name = repo_dir.name
        for yaml_file in repo_dir.glob("*-changelog.yaml"):
            try:
                data = yaml.safe_load(yaml_file.read_text())
            except (yaml.YAMLError, OSError):
                continue
            if not isinstance(data, dict) or not data.get("date") or not data.get("title"):
                continue
            date_key = str(data["date"])[:10]
            title = data["title"]
            summary = data.get("summary", "")
            if repo_name not in messages:
                messages[repo_name] = {}
            messages[repo_name][date_key] = f"{title}\n  {summary}" if summary else title

    return messages
