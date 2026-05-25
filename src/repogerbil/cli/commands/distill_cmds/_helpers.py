# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Shared helpers for distill CLI commands."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import click
import yaml

from repogerbil.core.config import VocabularyConfig
from repogerbil.core.errors import GitCommandError
from repogerbil.core.git import get_active_dates, get_commits_for_date
from repogerbil.core.vocabulary import PREFIX_TO_CATEGORY

# Regex matching any conventional-commit prefix known to the vocabulary.
# Derived from PREFIX_TO_CATEGORY so adding a new prefix in vocabulary.py
# automatically prevents double-prefixing here without a code edit.
_KNOWN_PREFIX_RE = re.compile(r"^(" + "|".join(re.escape(p) for p in PREFIX_TO_CATEGORY) + r")\b")


def _build_prefix_re(vocabulary: VocabularyConfig | None) -> re.Pattern[str]:
    """Build a known-prefix regex from the merged default + user prefix map.

    When ``vocabulary`` is ``None``, returns the module-level snapshot regex
    (default behaviour). When provided, merges ``vocabulary.extra_prefix_map``
    over the defaults so user-declared prefixes (e.g. ``hotfix``) are honoured
    by the double-prefix guard in :func:`_changelog_to_message`.
    """
    if vocabulary is None:
        return _KNOWN_PREFIX_RE
    merged = {**PREFIX_TO_CATEGORY, **vocabulary.extra_prefix_map}
    return re.compile(r"^(" + "|".join(re.escape(p) for p in merged) + r")\b")


def _collect_commits(path: Path, since: str | None, branch: str | None = None) -> list[Any]:
    """Collect all commits, optionally filtered by date and branch."""
    from repogerbil.core.git import CommitInfo, _run_git

    if branch:
        # Get commits only from this branch (not --all)
        try:
            output = _run_git(path, "log", branch, "--format=%H\t%as\t%ct\t%s")
        except GitCommandError as e:
            click.echo(
                f"git log failed for branch {branch!r}: {e.stderr or e} — does the branch exist?",
                err=True,
            )
            return []
        all_commits: list[Any] = []
        for line in output.strip().splitlines():
            parts = line.split("\t", 3)
            if len(parts) >= 4:  # pragma: no branch — format is fixed
                date_str = parts[1]
                if since and date_str < since:
                    continue
                all_commits.append(
                    CommitInfo(hash=parts[0], date=date_str, timestamp=int(parts[2]), subject=parts[3])
                )
        # Reverse to chronological order
        all_commits.reverse()
        # Attach file lists
        if all_commits:  # pragma: no branch — branch implies commits exist
            from repogerbil.core.git import _attach_file_lists

            all_commits = _attach_file_lists(path, all_commits)
        return all_commits

    dates = sorted(get_active_dates(path))
    if since:
        dates = [d for d in dates if d >= since]
    all_commits_list: list[Any] = []
    for date_str in dates:
        all_commits_list.extend(get_commits_for_date(path, date_str, include_files=True))
    return all_commits_list


def _load_changelog_messages(
    changelog_dir: str,
    repo_name: str,
    vocabulary: VocabularyConfig | None = None,
) -> dict[str, str]:
    """Load full changelog content as commit messages.

    When ``vocabulary`` is provided, user-declared ``extra_prefix_map`` entries
    participate in the double-prefix guard inside :func:`_changelog_to_message`
    — preventing ``fix: hotfix: ...`` style smell when a user has registered
    ``hotfix`` as a known prefix in ``.repogerbil.toml``.
    """
    messages: dict[str, str] = {}
    cl_path = Path(changelog_dir)
    for yaml_file in cl_path.glob(f"*-{repo_name}-changelog.yaml"):
        data = yaml.safe_load(yaml_file.read_text())
        if isinstance(data, dict) and data.get("date") and data.get("title"):  # pragma: no branch
            date_key = str(data["date"])[:10]
            messages[date_key] = _changelog_to_message(data, vocabulary=vocabulary)
    return messages


def _derive_commit_type(data: dict[str, Any]) -> str:
    """Derive conventional commit type from changelog category vocabulary.

    Looks at the first change section's category and maps it to a conventional
    commit type (feat, fix, docs, etc.) using the default settings vocabulary.
    Returns empty string if no category found.
    """
    vocab = VocabularyConfig()
    changes = data.get("changes", [])
    if not changes:
        return ""

    for change in changes:
        if not isinstance(change, dict):
            continue
        category = change.get("category", "")
        if category in vocab.categories:
            return vocab.categories[category].conventional

    return ""


def _collect_change_points(changes: list[Any]) -> list[str]:
    """Collect all point text values from changelog change sections."""
    points: list[str] = []
    for section in changes:
        if not isinstance(section, dict) or not section.get("points"):
            continue  # pragma: no cover — changelogs always have points
        for point in section["points"]:
            if isinstance(point, dict) and point.get("text"):
                points.append(point["text"])
            elif isinstance(point, str):  # pragma: no branch
                points.append(point)
    return points


def _changelog_to_message(
    data: dict[str, Any],
    vocabulary: VocabularyConfig | None = None,
) -> str:
    """Build a commit message from full changelog YAML data.

    When ``vocabulary`` is provided, its ``extra_prefix_map`` is merged with
    the default vocabulary for the double-prefix guard. Default behaviour
    (``vocabulary=None``) is unchanged and uses the module-level snapshot.
    """
    commit_type = _derive_commit_type(data)
    title = data["title"]

    # Don't double-prefix if title already starts with a conventional type
    prefix_re = _build_prefix_re(vocabulary)
    subject = f"{commit_type}: {title}" if commit_type and not prefix_re.match(title) else title

    lines = [subject]

    if data.get("summary"):  # pragma: no branch — changelogs always have summaries
        lines += ["", data["summary"]]

    if data.get("changes"):  # pragma: no branch — changelogs always have changes
        points = _collect_change_points(data["changes"])
        if points:  # pragma: no branch
            lines.append("")
            for p in points:
                lines.append(f"- {p}")

    return "\n".join(lines)


def _find_source_repo(name: str, source_base: Path) -> Path | None:
    """Find source repo by checking source_base/name then source_base/repo-bak/name."""
    primary = source_base / name
    if primary.is_dir():
        return primary
    fallback = source_base / "repo-bak" / name
    if fallback.is_dir():
        return fallback
    return None
