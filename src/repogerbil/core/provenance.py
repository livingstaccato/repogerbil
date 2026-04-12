# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Source provenance resolution for changelog dates."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast

from repogerbil.core.git import (
    CommitInfo,
    DiffStats,
    get_commit_for_hash,
    get_commits_for_date,
    get_diff_stats,
    get_hidden_ref_dates,
    get_hidden_ref_hashes,
)

ResolutionMode = Literal["visible", "hidden_ref", "backup", "unresolved"]


@dataclass(frozen=True)
class SourceCandidate:
    """A candidate source inspected during provenance resolution."""

    input_path: str
    resolved_path: str
    mode: Literal["visible", "hidden_ref", "backup"]
    reason: str
    commit_count: int = 0


@dataclass(frozen=True)
class ProvenanceResolution:
    """Resolution result for a repo/date pair."""

    repo: str
    date: str
    source_path: str | None
    mode: ResolutionMode
    commits: list[CommitInfo] = field(default_factory=list)
    stats: DiffStats | None = None
    candidates: list[SourceCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def resolve_provenance(
    repo: str,
    date_str: str,
    repo_path: Path,
    extra_sources: Sequence[Path] | None = None,
    message_depth: str = "subject",
    include_files: bool = False,
    include_hidden_refs: bool = True,
) -> ProvenanceResolution:
    """Resolve a source and commit range for a repo/date pair."""
    candidates: list[SourceCandidate] = []
    candidate_roots = _candidate_pairs(repo_path, extra_sources or [])
    primary_root = _resolve_git_root(repo_path)
    if not candidate_roots:
        return ProvenanceResolution(
            repo=repo,
            date=date_str,
            source_path=None,
            mode="unresolved",
            candidates=candidates,
            notes=[f"no git root found for {repo_path}"],
        )

    for input_hint, candidate_root in candidate_roots:
        is_primary = primary_root is not None and candidate_root == primary_root and input_hint == repo_path
        mode = "visible" if is_primary else "backup"

        visible = get_commits_for_date(
            candidate_root,
            date_str,
            message_depth=message_depth,
            include_files=include_files,
        )
        candidates.append(
            SourceCandidate(
                input_path=str(input_hint),
                resolved_path=str(candidate_root),
                mode=cast(Literal["visible", "hidden_ref", "backup"], mode),
                reason="visible history contains commits" if visible else "no visible commits for date",
                commit_count=len(visible),
            )
        )
        if visible:
            return _finalize_resolution(
                repo=repo,
                date_str=date_str,
                source_path=candidate_root,
                mode=cast(ResolutionMode, mode),
                candidates=candidates,
                commits=visible,
            )

        if not include_hidden_refs:
            continue

        hidden = _get_hidden_commits_for_date(
            candidate_root,
            date_str,
            message_depth=message_depth,
            include_files=include_files,
        )
        candidates.append(
            SourceCandidate(
                input_path=str(input_hint),
                resolved_path=str(candidate_root),
                mode="hidden_ref" if is_primary else "backup",
                reason="hidden unreachable commit contains date" if hidden else "no hidden commits for date",
                commit_count=len(hidden),
            )
        )
        if hidden:
            return _finalize_resolution(
                repo=repo,
                date_str=date_str,
                source_path=candidate_root,
                mode="hidden_ref" if is_primary else "backup",
                candidates=candidates,
                commits=hidden,
            )

    return ProvenanceResolution(
        repo=repo,
        date=date_str,
        source_path=None,
        mode="unresolved",
        candidates=candidates,
        notes=["no candidate source contained commits for the requested date"],
    )


def collect_effective_dates(
    repo_path: Path,
    extra_sources: Sequence[Path] | None = None,
    include_hidden_refs: bool = True,
) -> set[str]:
    """Collect dates from visible history, hidden refs, and any extra sources."""
    dates = set()
    for _, root in _candidate_pairs(repo_path, extra_sources or []):
        dates |= _visible_dates(root)
        if include_hidden_refs:
            dates |= get_hidden_ref_dates(root)
    return dates


def describe_resolution(resolution: ProvenanceResolution) -> list[str]:
    """Return human-readable lines for a provenance resolution."""
    lines = [
        f"{resolution.repo}/{resolution.date}: {resolution.mode}",
    ]
    if resolution.source_path:
        lines.append(f"  source: {resolution.source_path}")
    if resolution.commits:
        lines.append(f"  commits: {len(resolution.commits)}")
    if resolution.stats:
        lines.append(
            f"  stats: {resolution.stats.files_changed} files, "
            f"+{resolution.stats.insertions}/-{resolution.stats.deletions}"
        )
    for candidate in resolution.candidates:
        lines.append(
            f"  candidate[{candidate.mode}]: {candidate.resolved_path} "
            f"({candidate.commit_count} commits) - {candidate.reason}"
        )
    for note in resolution.notes:
        lines.append(f"  note: {note}")
    return lines


def _finalize_resolution(
    repo: str,
    date_str: str,
    source_path: Path,
    mode: ResolutionMode,
    candidates: list[SourceCandidate],
    commits: list[CommitInfo],
) -> ProvenanceResolution:
    """Attach diff stats to a resolved commit set."""
    stats = get_diff_stats(source_path, commits[0].hash, commits[-1].hash)
    stats = DiffStats(
        commits=len(commits),
        files_changed=stats.files_changed,
        insertions=stats.insertions,
        deletions=stats.deletions,
    )
    return ProvenanceResolution(
        repo=repo,
        date=date_str,
        source_path=str(source_path),
        mode=mode,
        commits=commits,
        stats=stats,
        candidates=candidates,
    )


def _candidate_pairs(repo_path: Path, extra_sources: Sequence[Path]) -> list[tuple[Path, Path]]:
    """Return (input hint, git root) pairs for the primary repo and any extra sources."""
    roots: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for path in [repo_path, *extra_sources]:
        root = _resolve_git_root(path)
        if root is None:
            continue
        key = str(root.resolve())
        if key in seen:
            continue
        seen.add(key)
        roots.append((path, root))
    return roots


def _visible_dates(repo_path: Path) -> set[str]:
    """Return visible active dates for a repository root."""
    from repogerbil.core.git import get_active_dates

    return get_active_dates(repo_path)


def _resolve_git_root(path: Path) -> Path | None:
    """Resolve a path to its nearest enclosing git repository root."""
    current = path if path.exists() else path.parent
    if current.is_file():
        current = current.parent
    while True:
        if (current / ".git").exists():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _get_hidden_commits_for_date(
    repo_path: Path,
    date_str: str,
    message_depth: str,
    include_files: bool,
) -> list[CommitInfo]:
    """Return unreachable commits matching the requested date."""
    commits: list[CommitInfo] = []
    for commit_hash in get_hidden_ref_hashes(repo_path):
        commit = get_commit_for_hash(
            repo_path,
            commit_hash,
            message_depth=message_depth,
            include_files=include_files,
        )
        if commit.date == date_str:
            commits.append(commit)

    commits.sort(key=lambda c: (c.date, c.hash))
    return commits
