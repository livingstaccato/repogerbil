# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Snapshot engine — create independent repo with distilled daily commits via git read-tree."""

from __future__ import annotations

from collections import defaultdict
import contextlib
from dataclasses import dataclass
from datetime import date as date_type, datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import random
import sys
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from repogerbil.core._snapshot_git import _get_commit_body, _get_files_for_commit
from repogerbil.core.cadence import TimeGroup
from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import _run_git
from repogerbil.core.multi_snapshot import _make_timestamp
from repogerbil.core.tree_filter import exclude_files as _exclude_files, filter_tree as _filter_tree
from repogerbil.llm.prompt import WELL_FORMED_RE

if TYPE_CHECKING:
    from repogerbil.llm.generator import MessageGenerator


@dataclass(frozen=True)
class SnapshotResult:
    """Result of a snapshot operation."""

    dest_path: str
    groups_created: int
    commits_created: int
    groups_skipped: int = 0  # Duplicates removed during deduplication
    summaries_path: str | None = None  # Path to sidecar JSONL if LLM was used


def create_snapshot(
    source_path: Path,
    dest_path: Path,
    groups: list[TimeGroup],
    source_branch: str | None = None,
    changelog_messages: dict[str, str] | None = None,
    preserve_timestamps: bool = True,
    commit_time: str | None = None,
    timezone: str | None = None,
    extra_sources: list[Path] | None = None,
    source_subdir: str | None = None,
    llm_generator: MessageGenerator | None = None,
    progress: bool = False,
    exclude_paths: list[str] | None = None,
    time_window_start: str | None = None,
    time_window_end: str | None = None,
) -> SnapshotResult:
    r"""Create an independent repo with one commit per TimeGroup.
    Uses git read-tree for fast, working-directory-free operations, and writes only to destination.

    Args:
        source_branch: Compatibility hint only; select branch commits before calling,
                      because snapshot creation uses ``groups`` as-is.
        source_subdir: When set, filter primary source commits to this subdirectory
                      and use its tree state (for monorepo sources).
        exclude_paths: Regex patterns to strip matching paths from every committed tree
                      (e.g. [r"^\.claude(/|$)", r".*\.lock$"]). Uses re.search so patterns
                      match anywhere in the file path unless anchored. Deduplication also
                      uses the filtered tree so groups that differ only in excluded content
                      are correctly collapsed.
        time_window_start: Start of daily commit window as HH:MM (use with --timezone).
                          Commits are spread across [time_window_start, time_window_end]
                          with spacing weighted by group size plus random jitter.
        time_window_end: End of daily commit window as HH:MM. Supports midnight-crossing
                        windows (e.g. start="23:00", end="01:00").
    """
    if dest_path.exists() and any(dest_path.iterdir()):
        msg = f"Destination already exists and is not empty: {dest_path}"
        raise RuntimeError(msg)

    remote_names = _init_and_fetch(dest_path, source_path, extra_sources)

    # Deduplicate groups by tree state BEFORE creating commits
    dedup_groups, groups_skipped = _deduplicate_groups(dest_path, groups, source_subdir, exclude_paths)

    # Sidecar JSONL path — only used when LLM is active
    summaries_path = dest_path.parent / f"{dest_path.name}.summaries.jsonl" if llm_generator else None

    commits_created = _create_commits(
        dest_path,
        dedup_groups,
        changelog_messages,
        preserve_timestamps,
        commit_time,
        timezone,
        source_subdir,
        llm_generator,
        progress,
        summaries_path,
        exclude_paths,
        time_window_start,
        time_window_end,
    )

    for rname in remote_names:
        with contextlib.suppress(GitCommandError):
            _run_git(dest_path, "remote", "remove", rname)

    _run_git(dest_path, "checkout", "--force", "main", timeout=30)

    return SnapshotResult(
        dest_path=str(dest_path),
        groups_created=len(groups),
        commits_created=commits_created,
        groups_skipped=groups_skipped,
        summaries_path=str(summaries_path) if summaries_path else None,
    )


def _init_and_fetch(
    dest_path: Path,
    source_path: Path,
    extra_sources: list[Path] | None,
) -> list[str]:
    """Initialize destination repo and fetch all source remotes."""
    dest_path.mkdir(parents=True, exist_ok=True)
    _run_git(dest_path, "init")

    _fetch_source(dest_path, "source", source_path)
    remote_names = ["source"]
    for i, extra in enumerate(extra_sources or []):
        if extra.exists():  # pragma: no branch
            name = f"extra-{i}"
            _fetch_source(dest_path, name, extra)
            remote_names.append(name)
    return remote_names


def _deduplicate_groups(
    dest_path: Path,
    groups: list[TimeGroup],
    source_subdir: str | None = None,
    exclude_paths: list[str] | None = None,
) -> tuple[list[TimeGroup], int]:
    """Deduplicate groups by their tree state, keeping only unique code states.

    Returns tuple of (deduplicated_groups, number_skipped).

    Args:
        dest_path: Path to destination repo with all sources fetched.
        groups: Groups to deduplicate.
        source_subdir: Optional subdirectory for monorepo filtering.
        exclude_paths: Paths stripped before comparing tree states.
    """
    seen_trees: set[str] = set()
    unique_groups: list[TimeGroup] = []
    skipped = 0

    for group in groups:
        if not group.commits:
            continue  # pragma: no cover — empty group

        last_commit = group.commits[-1]
        try:
            if source_subdir:
                # Try subdir first (for monorepo sources)
                tree_sha = _run_git(
                    dest_path, "rev-parse", f"{last_commit.hash}:{source_subdir}", timeout=10
                ).strip()
            else:
                # Full tree (for standalone repos)
                tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()
        except GitCommandError:
            # Fall back to full tree if subdir doesn't exist
            tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()

        tree_sha = _filter_tree(dest_path, tree_sha, exclude_paths)

        # Skip if we've already seen this tree state
        if tree_sha in seen_trees:
            skipped += 1
            continue

        seen_trees.add(tree_sha)
        unique_groups.append(group)

    return unique_groups, skipped


def _create_commits(  # noqa: C901 — intentionally broad; each branch is simple
    dest_path: Path,
    groups: list[TimeGroup],
    changelog_messages: dict[str, str] | None,
    preserve_timestamps: bool,
    commit_time: str | None,
    timezone: str | None,
    source_subdir: str | None = None,
    llm_generator: MessageGenerator | None = None,
    progress: bool = False,
    summaries_path: Path | None = None,
    exclude_paths: list[str] | None = None,
    time_window_start: str | None = None,
    time_window_end: str | None = None,
) -> int:
    """Create one commit per TimeGroup in the destination repo.

    Args:
        source_subdir: When set, use the tree state of this subdirectory
                      within each commit (for monorepo sources).
        summaries_path: When set, append LLM summaries as JSONL records here.
        exclude_paths: Regex patterns stripped from every committed tree.
        time_window_start: Start of daily commit window (HH:MM).
        time_window_end: End of daily commit window (HH:MM).
    """
    commits_created = 0
    used_changelog_keys: set[str] = set()
    total = len(groups)
    width = len(str(total))

    window_timestamps: list[str] | None = None
    if time_window_start and time_window_end and timezone:
        window_timestamps = _compute_window_timestamps(groups, time_window_start, time_window_end, timezone)

    for idx, group in enumerate(groups, 1):
        if not group.commits:
            continue  # pragma: no cover — empty group

        last_commit = group.commits[-1]
        try:
            if source_subdir:
                # Try subdir first (for monorepo sources)
                tree_sha = _run_git(
                    dest_path, "rev-parse", f"{last_commit.hash}:{source_subdir}", timeout=10
                ).strip()
            else:
                # Full tree (for standalone repos)
                tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()
        except GitCommandError:
            # Fall back to full tree if subdir doesn't exist
            tree_sha = _run_git(dest_path, "rev-parse", f"{last_commit.hash}^{{tree}}", timeout=10).strip()

        tree_sha = _filter_tree(dest_path, tree_sha, exclude_paths)
        _run_git(dest_path, "read-tree", tree_sha)

        generated = None
        subjects = [c.subject for c in group.commits]
        if llm_generator is not None and not all(WELL_FORMED_RE.match(s) for s in subjects):
            all_files: set[str] = set()
            for commit in group.commits:
                all_files.update(_get_files_for_commit(dest_path, commit.hash))
            all_files = _exclude_files(all_files, exclude_paths)
            original_bodies = [_get_commit_body(dest_path, c.hash) for c in group.commits]
            try:
                generated = llm_generator.generate(
                    date_str=group.period_start.strftime("%Y-%m-%d"),
                    files=sorted(all_files),
                    commit_count=len(group.commits),
                    original_subjects=subjects,
                    original_bodies=original_bodies,
                )
                message = generated.message
            except Exception:
                message = _build_snapshot_message(group, changelog_messages, used_changelog_keys)
        else:
            message = _build_snapshot_message(group, changelog_messages, used_changelog_keys)
        if window_timestamps is not None:
            date_str = window_timestamps[idx - 1]
        else:
            date_str = _resolve_timestamp(group, commit_time, timezone)

        if progress:
            first_line = message.splitlines()[0][:72]
            ts = group.period_start.strftime("%Y-%m-%d %H:%M")
            print(f"[{idx:{width}}/{total}] {ts}  {first_line}", file=sys.stderr, flush=True)

        commit_hash = _commit_with_timestamp(dest_path, tree_sha, message, date_str, preserve_timestamps)

        if generated is not None and summaries_path is not None:
            record = {
                "hash": commit_hash,
                "date": group.period_start.strftime("%Y-%m-%d"),
                "subjects": message.splitlines(),
                "body": generated.body,
                "changes": generated.changes,
            }
            with summaries_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record) + "\n")
        commits_created += 1

    return commits_created


def _resolve_timestamp(
    group: TimeGroup,
    commit_time: str | None,
    timezone: str | None,
) -> str:
    """Resolve the timestamp for a commit."""
    if commit_time and timezone:
        day = date_type(group.period_start.year, group.period_start.month, group.period_start.day)
        return _make_timestamp(day, commit_time, timezone)
    return group.period_end.strftime("%Y-%m-%dT%H:%M:%S")


def _commit_with_timestamp(
    dest_path: Path,
    tree_sha: str,
    message: str,
    date_str: str,
    preserve: bool,
) -> str:
    """Create a commit-tree with optional timestamp override.

    Returns:
        The new commit hash.
    """
    cmd = ["commit-tree", tree_sha, "-m", message]

    try:
        head = _run_git(dest_path, "rev-parse", "--verify", "HEAD", timeout=5).strip()
    except GitCommandError:
        head = ""
    if head:
        cmd.extend(["-p", head])

    if preserve:
        env = dict(os.environ)
        env["GIT_AUTHOR_DATE"] = date_str
        env["GIT_COMMITTER_DATE"] = date_str
        new_commit = _run_git(dest_path, *cmd, timeout=30, env=env).strip()
    else:
        new_commit = _run_git(dest_path, *cmd, timeout=30).strip()

    _run_git(dest_path, "update-ref", "refs/heads/main", new_commit)
    return new_commit


def _spread_timestamps_for_day(
    day_groups: list[TimeGroup],
    start_dt: datetime,
    end_dt: datetime,
    rng: random.Random,
) -> list[str]:
    """Spread N groups across [start_dt, end_dt] with weight-proportional spacing.

    Each group occupies a proportional slot sized by its ``files_affected`` count.
    A random position is chosen within the middle 80% of each slot, ensuring
    strictly increasing timestamps by construction.

    Args:
        day_groups: Groups to spread (all from the same calendar day).
        start_dt: Window start (timezone-aware).
        end_dt: Window end (timezone-aware, may be next day for midnight-crossing windows).
        rng: Random number generator for reproducible tests.

    Returns:
        List of ISO8601 timestamp strings, one per group, strictly increasing.
    """
    total_seconds = (end_dt - start_dt).total_seconds()
    if len(day_groups) == 1:
        offset = rng.uniform(0, total_seconds)
        return [(start_dt + timedelta(seconds=offset)).strftime("%Y-%m-%dT%H:%M:%S%z")]

    weights = [max(1, len(g.files_affected)) for g in day_groups]
    total_weight = sum(weights)
    cumulative = 0.0
    results = []
    for w in weights:
        slot_start = cumulative / total_weight
        slot_end = (cumulative + w) / total_weight
        # Random position in middle 80% of slot (10% margin each side)
        lo = slot_start + 0.1 * (slot_end - slot_start)
        hi = slot_end - 0.1 * (slot_end - slot_start)
        pos = rng.uniform(lo, hi)
        ts = start_dt + timedelta(seconds=pos * total_seconds)
        results.append(ts.strftime("%Y-%m-%dT%H:%M:%S%z"))
        cumulative += w
    return results


def _compute_window_timestamps(
    groups: list[TimeGroup],
    window_start_hm: str,
    window_end_hm: str,
    timezone: str,
    seed: int | None = None,
) -> list[str]:
    """Distribute groups across a daily time window, one timestamp per group.

    Groups are bucketed by calendar day. Each day's groups are spread across
    [window_start_hm, window_end_hm] using weighted random spacing. Timestamps
    are strictly increasing within each day's window.

    Args:
        groups: All groups to timestamp (may span multiple calendar days).
        window_start_hm: Window start as ``HH:MM``.
        window_end_hm: Window end as ``HH:MM``. If end <= start, the window
                      crosses midnight (end is on the next calendar day).
        timezone: IANA timezone name (e.g. ``"America/Los_Angeles"``).
        seed: Optional RNG seed for deterministic output (useful in tests).

    Returns:
        List of ISO8601 timestamp strings, one per input group, in input order.
    """
    if seed is None:
        seed = _default_window_seed(groups, window_start_hm, window_end_hm, timezone)
    rng = random.Random(seed)  # noqa: S311 — not security-sensitive, used for commit timestamp jitter
    tz = ZoneInfo(timezone)
    sh, sm = map(int, window_start_hm.split(":"))
    eh, em = map(int, window_end_hm.split(":"))

    day_to_indices: dict[date_type, list[int]] = defaultdict(list)
    for i, g in enumerate(groups):
        day_to_indices[g.period_start.date()].append(i)

    timestamps: list[str | None] = [None] * len(groups)

    for day, indices in sorted(day_to_indices.items()):
        start_dt = datetime(day.year, day.month, day.day, sh, sm, 0, tzinfo=tz)
        end_day = day
        if eh < sh or (eh == sh and em <= sm):
            # Window crosses midnight — end is on the following calendar day
            end_day = day + timedelta(days=1)
        end_dt = datetime(end_day.year, end_day.month, end_day.day, eh, em, 0, tzinfo=tz)

        day_groups = [groups[i] for i in indices]
        day_ts = _spread_timestamps_for_day(day_groups, start_dt, end_dt, rng)
        for idx, ts in zip(indices, day_ts, strict=True):
            timestamps[idx] = ts

    return timestamps  # type: ignore[return-value]  # all slots filled by construction


def _default_window_seed(
    groups: list[TimeGroup],
    window_start_hm: str,
    window_end_hm: str,
    timezone: str,
) -> int:
    """Build a deterministic RNG seed from stable snapshot inputs."""
    chunks = [window_start_hm, window_end_hm, timezone]
    for group in groups:
        chunks.append(group.period_start.isoformat())
        chunks.append(group.period_end.isoformat())
        chunks.append(str(len(group.files_affected)))
        for commit in group.commits:
            chunks.append(commit.hash)
    digest = hashlib.sha256("|".join(chunks).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _fetch_source(dest_path: Path, remote_name: str, source_path: Path) -> None:
    """Add a source repo as a remote and fetch all refs."""
    source_uri = source_path.resolve().as_uri()
    _run_git(dest_path, "remote", "add", remote_name, source_uri)
    _run_git(dest_path, "fetch", remote_name, f"+refs/*:refs/fetch-{remote_name}/*", timeout=300)


def _build_snapshot_message(
    group: TimeGroup,
    changelog_messages: dict[str, str] | None,
    used_keys: set[str] | None = None,
) -> str:
    """Build commit message from changelog or conventional commits only.

    For gap-based cadence, tracks which changelog keys have been used to avoid
    multiple same-day groups getting the same YAML message.
    """
    date_str = group.period_start.strftime("%Y-%m-%d")

    # Changelog is authoritative — use it directly if not already consumed
    if (
        changelog_messages
        and date_str in changelog_messages
        and (used_keys is None or date_str not in used_keys)
    ):
        if used_keys is not None:
            used_keys.add(date_str)
        return changelog_messages[date_str]

    # No changelog (or already used): only list well-formed commits, suppress garbage
    n = len(group.commits)
    conventional = [c.subject for c in group.commits if WELL_FORMED_RE.match(c.subject)]

    if len(conventional) == 1:
        return conventional[0]

    if conventional:
        lines = [f"{date_str}: {n} commits", ""]
        for s in conventional:
            lines.append(f"- {s}")
        other = n - len(conventional)
        if other:  # pragma: no cover — test repos use conventional commits
            lines.append(f"- ({other} commits)")
        return "\n".join(lines)

    return f"{date_str}: {n} commits"
