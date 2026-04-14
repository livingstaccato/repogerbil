# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Multi-repo snapshot — merge multiple repos into a single distilled daily history."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import yaml

from repogerbil.core._multi_snapshot_git import (
    _build_merged_tree,
    _collect_repo_trees_for_day,
    _commit_tree,
    _init_dest_repo,
)
from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git
from repogerbil.core.tree_filter import exclude_files

if TYPE_CHECKING:
    from repogerbil.llm.generator import MessageGenerator


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
    exclude_paths: list[str] | None = None,
    llm_generator: MessageGenerator | None = None,
) -> MultiSnapshotResult:
    """Create an independent repo with one daily commit merging multiple source repos.

    Each source repo gets its own subdirectory in the destination. Commits are
    timestamped at commit_time in the specified timezone. Commit messages are
    assembled from changelog YAMLs when available, or refined by an LLM.

    Args:
        source_repos: Mapping of name → path for source repositories.
        dest_path: Path for the new snapshot repository (must not exist or be empty).
        since: Only include dates on or after this date.
        commit_time: Time for daily commits (HH:MM format).
        timezone: IANA timezone name for commit timestamps.
        changelog_dir: Directory containing <repo>/<date>-<repo>-changelog.yaml files.
        exclude_paths: Regex patterns stripped from every committed tree (via re.search).
        llm_generator: When set, refine each commit message using the LLM.

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
    per_repo_dates = _collect_per_repo_dates(source_repos)
    summaries_path = dest_path.parent / f"{dest_path.name}.summaries.jsonl" if llm_generator else None
    repos_included: set[str] = set()
    commits_created = _create_daily_commits(
        dest_path,
        source_repos,
        active_dates,
        repo_first_dates,
        per_repo_dates,
        repos_included,
        changelog_messages,
        commit_time,
        timezone,
        exclude_paths=exclude_paths,
        llm_generator=llm_generator,
        summaries_path=summaries_path,
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


def _create_daily_commits(
    dest_path: Path,
    source_repos: dict[str, Path],
    active_dates: list[date],
    repo_first_dates: dict[str, date],
    per_repo_dates: dict[str, set[date]],
    repos_included: set[str],
    changelog_messages: dict[str, dict[str, str]],
    commit_time: str,
    timezone: str,
    *,
    exclude_paths: list[str] | None = None,
    llm_generator: MessageGenerator | None = None,
    summaries_path: Path | None = None,
) -> int:
    """Create one commit per active day in the destination repo."""
    import json
    import sys

    commits_created = 0
    total = len(active_dates)
    width = len(str(total))

    for idx, day in enumerate(active_dates, 1):
        repo_trees = _collect_repo_trees_for_day(
            dest_path,
            source_repos,
            day,
            repo_first_dates,
            repos_included,
            exclude_paths=exclude_paths,
        )
        if not repo_trees:  # pragma: no cover — dates come from repos that have commits
            continue

        active_repos = {name for name, dates in per_repo_dates.items() if day in dates}
        combined_tree = _build_merged_tree(dest_path, repo_trees)

        generated = None
        if llm_generator is not None:
            files, subjects, bodies = _collect_day_context(source_repos, active_repos, day, exclude_paths)
            try:
                generated = llm_generator.generate(
                    date_str=day.isoformat(),
                    files=files,
                    commit_count=len(subjects),
                    original_subjects=subjects,
                    original_bodies=bodies,
                )
                message = generated.message
            except Exception:
                message = _build_message(day, active_repos, changelog_messages)
        else:
            message = _build_message(day, active_repos, changelog_messages)

        timestamp = _make_timestamp(day, commit_time, timezone)
        first_line = message.splitlines()[0][:72]
        print(f"[{idx:{width}}/{total}] {day.isoformat()}  {first_line}", file=sys.stderr, flush=True)
        commit_hash = _commit_tree(dest_path, combined_tree, message, timestamp)
        commits_created += 1

        if generated is not None and summaries_path is not None:
            record = {
                "hash": commit_hash,
                "date": day.isoformat(),
                "subjects": message.splitlines(),
                "body": generated.body,
                "changes": generated.changes,
            }
            with summaries_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")

    return commits_created


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


def _collect_per_repo_dates(source_repos: dict[str, Path]) -> dict[str, set[date]]:
    """Get the set of active commit dates per repo."""
    result: dict[str, set[date]] = {}
    for name, path in source_repos.items():
        if not path.exists() or not (path / ".git").exists():
            continue
        try:
            output = _run_git(path, "log", "--format=%as", timeout=30)
        except GitCommandError:
            continue
        dates: set[date] = set()
        for line in output.strip().split("\n"):
            if line:  # pragma: no branch
                dates.add(date.fromisoformat(line))
        result[name] = dates
    return result


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


def _make_timestamp(day: date, commit_time: str, tz_name: str) -> str:
    """Create an ISO8601 timestamp at the given time in the given timezone."""
    h, m = map(int, commit_time.split(":"))
    tz = ZoneInfo(tz_name)
    dt = datetime(day.year, day.month, day.day, h, m, 0, tzinfo=tz)
    return dt.strftime("%Y-%m-%dT%H:%M:%S%z")


def _build_message(
    day: date,
    active_repos: set[str],
    changelog_messages: dict[str, dict[str, str]],
) -> str:
    """Build commit message from changelog YAMLs or fallback.

    Only includes repos that had actual commits on this day (not carried-forward).
    """
    date_str = day.isoformat()
    lines = [f"{date_str} pyvider ecosystem", ""]

    has_changelog = False
    for name in sorted(active_repos):
        if name in changelog_messages and date_str in changelog_messages[name]:
            msg = changelog_messages[name][date_str]
            lines.append(f"{name}: {msg}")
            has_changelog = True
        else:
            lines.append(f"{name}: [activity, no changelog]")

    if not has_changelog and len(active_repos) == 1:
        name = next(iter(active_repos))
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


def _collect_day_context(
    source_repos: dict[str, Path],
    active_repos: set[str],
    day: date,
    exclude_paths: list[str] | None,
) -> tuple[list[str], list[str], list[str]]:
    """Collect files changed, commit subjects, and bodies for all active repos on a day.

    Uses two separate git calls per repo: one for subjects/bodies, one for file names.

    Returns:
        Tuple of (sorted_files, subjects, bodies) for passing to MessageGenerator.
    """
    since = f"{day.isoformat()}T00:00:00"
    until = f"{day.isoformat()}T23:59:59"
    all_files: set[str] = set()
    subjects: list[str] = []
    bodies: list[str] = []

    for name in sorted(active_repos):
        path = source_repos.get(name)
        if path is None or not path.exists():
            continue
        try:
            # Subjects and bodies — one record separator (RS = \x1e) per commit
            msg_out = subprocess.run(  # noqa: S603
                ["git", "log", f"--since={since}", f"--until={until}", "--format=%s\x1f%b\x1e"],  # noqa: S607
                cwd=str(path),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            ).stdout
            # Files changed — empty format strips hash lines
            file_out = subprocess.run(  # noqa: S603
                ["git", "log", f"--since={since}", f"--until={until}", "--name-only", "--format="],  # noqa: S607
                cwd=str(path),
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            ).stdout
        except subprocess.SubprocessError:
            continue

        for record in msg_out.split("\x1e"):
            record = record.strip()
            if not record:
                continue
            parts = record.split("\x1f", 1)
            subject = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else ""
            if subject:  # pragma: no branch — git always produces non-empty subjects
                subjects.append(f"{name}: {subject}")
            if body:
                bodies.append(body)

        for line in file_out.splitlines():
            line = line.strip()
            if line:
                all_files.add(line)

    filtered = exclude_files(all_files, exclude_paths)
    return sorted(filtered), subjects, bodies
