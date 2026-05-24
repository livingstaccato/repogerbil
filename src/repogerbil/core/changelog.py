# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Changelog generation, enrichment, and stats management."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import re
from typing import Any

import yaml

from repogerbil.core.classify import classify_commit, classify_files
from repogerbil.core.config import FileRule, Settings
from repogerbil.core.git import CommitInfo, DiffStats

yaml.representer.SafeRepresenter.add_representer(
    type(None),
    lambda dumper, _: dumper.represent_scalar("tag:yaml.org,2002:null", "null"),
)


def generate_draft(
    repo: str,
    date_str: str,
    commits: list[CommitInfo],
    stats: DiffStats,
    settings: Settings,
) -> dict[str, Any]:
    """Generate a skeleton changelog with draft placeholders."""
    groups, review = _group_commits(commits, settings)
    changes = _build_changes(groups, settings)

    result: dict[str, Any] = {
        "date": date_str,
        "repo": repo,
        "title": f"Draft: summarize {len(commits)} commits",
        "summary": f"Draft: write summary ({stats.files_changed} files, "
        f"+{stats.insertions}/-{stats.deletions})",
        "stats": _stats_dict(stats, len(commits)),
    }
    if review:
        result["review"] = review
    result["changes"] = changes
    return result


def generate_analyzed(
    repo: str,
    date_str: str,
    commits: list[CommitInfo],
    stats: DiffStats,
    settings: Settings,
) -> dict[str, Any]:
    """Generate a complete changelog using heuristic analysis."""
    auto_bulk, commits, forced_categories = _apply_file_rules(commits, settings.file_rules)
    groups, review = _group_commits(commits, settings, forced_categories)
    changes = _build_changes(groups, settings, forced_categories)

    result: dict[str, Any] = {
        "date": date_str,
        "repo": repo,
        "title": _generate_title(commits, groups),
        "summary": _generate_summary(stats, groups, settings),
        "stats": _stats_dict(stats, len(commits)),
    }
    if auto_bulk:
        result["bulk"] = auto_bulk
    if review:
        result["review"] = review
    result["changes"] = changes
    return result


def generate_prompt(
    repo: str,
    date_str: str,
    commits: list[CommitInfo],
    stats: DiffStats,
    diff_content: dict[str, str],
) -> str:
    """Generate a prompt for an external LLM to write the changelog."""
    parts = [
        f"# Generate a changelog for {repo} on {date_str}\n",
        f"## Stats\n- {len(commits)} commits, {stats.files_changed} files changed, "
        f"+{stats.insertions}/-{stats.deletions}\n",
        "## Commits\n",
    ]
    for c in commits:
        files = ", ".join(c.files[:5])
        parts.append(f"- `{c.subject}`")
        if files:
            parts.append(f"  files: {files}")
        parts.append("")

    if diff_content:
        parts.append("## Diffs (key files)\n")
        for filepath, diff_text in list(diff_content.items())[:30]:
            parts.append(f"### {filepath}\n```diff\n{diff_text}\n```\n")

    parts.append(_prompt_instructions(repo, date_str, stats, len(commits)))
    return "\n".join(parts)


def generate_prompt_span(
    repo: str,
    from_ref: str,
    to_ref: str,
    commits: list[CommitInfo],
    stats: DiffStats,
    diff_content: dict[str, str],
) -> str:
    """Generate a prompt for an external LLM to write a release-span changelog.

    Parallel to ``generate_prompt`` but scoped to a commit range instead of
    a single date. Intended for release-note generation where the span
    corresponds to a version boundary.
    """
    parts = [
        f"# Generate a release changelog for {repo}",
        f"## Span\n- From: `{from_ref}`\n- To: `{to_ref}`\n",
        (
            f"## Stats\n- {len(commits)} commits, {stats.files_changed} files changed, "
            f"+{stats.insertions}/-{stats.deletions}\n"
        ),
        "## Commits (oldest → newest)\n",
    ]
    for c in commits:
        files = ", ".join(c.files[:5])
        parts.append(f"- `{c.subject}`")
        if files:
            parts.append(f"  files: {files}")
        parts.append("")

    if diff_content:
        parts.append("## Diffs (key files)\n")
        for filepath, diff_text in list(diff_content.items())[:30]:
            parts.append(f"### {filepath}\n```diff\n{diff_text}\n```\n")

    parts.append(_prompt_instructions_span(repo, from_ref, to_ref, stats, len(commits)))
    return "\n".join(parts)


def _prompt_instructions_span(
    repo: str, from_ref: str, to_ref: str, stats: DiffStats, commit_count: int
) -> str:
    return f"""## Instructions

Write a release changelog section in Markdown (Keep-a-Changelog flavor)
covering the span `{from_ref}..{to_ref}` for {repo}.

Structure:

```markdown
## [<version>] — <YYYY-MM-DD>

### Highlights
<1-3 bullets describing what a user actually notices about this release>

### Breaking Changes
<bullets, or omit if none>

### Features
<bullets>

### Fixes
<bullets>

### Security & Resilience
<bullets, or omit if none>

### Performance
<bullets, or omit if none>

### Refactors
<bullets, or omit if none>

### Documentation
<bullets, or omit if none>
```

Guidelines:
- Write as prose, not commit-subject echoes. Explain impact, not mechanics.
- Group related commits; collapse mechanical churn into one line.
- Use the existing provide.io vocabulary where accurate (instantiate, harden,
  qualify, baseline, specify, remediate, streamline, decouple).
- Skip `chore(ci|deps|build): bump X from Y to Z` entirely.
- Total commit count: {commit_count} ({stats.files_changed} files, +{stats.insertions}/-{stats.deletions}).

Output the markdown block only — no YAML wrapper, no frontmatter.
"""


def update_stats(yaml_path: Path, stats: DiffStats, commit_count: int) -> bool:
    """Update only the stats block in an existing changelog file.

    Returns True if the file was modified, False if unchanged or invalid.
    """
    content = yaml_path.read_text()
    data = yaml.safe_load(content)
    if not isinstance(data, dict) or not data.get("date") or not data.get("repo"):
        return False

    new_stats = _stats_dict(stats, commit_count)
    if data.get("stats") == new_stats:
        return False

    data["stats"] = new_stats
    new_content = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    if len(new_content) < len(content) * 0.5:  # pragma: no cover — safety net for yaml.dump corruption
        return False

    yaml_path.write_text(new_content)
    return True


def write_changelog(repo: str, date_str: str, data: dict[str, Any], output_dir: Path) -> Path:
    """Write changelog YAML file. Returns the output path."""
    repo_dir = output_dir / repo
    repo_dir.mkdir(parents=True, exist_ok=True)
    out_path = repo_dir / f"{date_str}-{repo}-changelog.yaml"
    out_path.write_text(yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False))
    return out_path


# ── Internal helpers ──────────────────────────────────────────────────────────


def _stats_dict(stats: DiffStats, commit_count: int) -> dict[str, int]:
    return {
        "commits": commit_count,
        "files_changed": stats.files_changed,
        "insertions": stats.insertions,
        "deletions": stats.deletions,
    }


def _group_commits(
    commits: list[CommitInfo],
    settings: Settings,
    forced_categories: dict[str, str] | None = None,
) -> tuple[dict[str, list[CommitInfo]], list[str]]:
    """Group commits by category. Returns (groups, review_subjects)."""
    groups: dict[str, list[CommitInfo]] = {}
    review: list[str] = []

    for commit in commits:
        result = classify_commit(
            commit.subject,
            body=commit.body,
            auto_breaking=settings.auto_breaking,
            settings=settings,
        )
        key = (forced_categories or {}).get(commit.hash) or result.category or "_unclassified"
        groups.setdefault(key, []).append(commit)
        if result.needs_review and not (forced_categories or {}).get(commit.hash):
            review.append(commit.subject)

    return groups, review


_STRIP_PREFIX_RE = re.compile(r"^(\w+)(?:\([^)]*\))?[!]?:\s*")


def _strip_prefix(subject: str) -> str:
    m = _STRIP_PREFIX_RE.match(subject)
    return m.string[m.end() :] if m else subject


def _build_changes(
    groups: dict[str, list[CommitInfo]],
    settings: Settings,
    forced_categories: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Build the changes list from grouped commits."""
    changes: list[dict[str, Any]] = []
    # Use categories from config if available, otherwise fallback to default order
    cat_order = [*settings.vocabulary.categories.keys(), "_unclassified"]

    for cat in cat_order:
        group = groups.get(cat)
        if not group:
            continue

        if cat == "_unclassified":
            title = f"Unclassified: {len(group)} commit{'s' if len(group) > 1 else ''}"
            section_cat: str | None = None
            section_sev: str | None = None
        elif len(group) == 1:
            title = _strip_prefix(group[0].subject)
            section_cat = cat
            section_sev = classify_commit(group[0].subject, body=group[0].body, settings=settings).severity
        else:
            cat_defn = settings.vocabulary.categories.get(cat)
            verb = (cat_defn.verb if cat_defn and cat_defn.verb else None) or cat.title()
            top_dir = _top_directory(group)
            title = f"{verb} {top_dir}/ ({len(group)} commits)" if top_dir else f"{verb}: {len(group)} commits"
            section_cat = cat
            section_sev = classify_commit(group[0].subject, body=group[0].body, settings=settings).severity

        points = [
            _commit_to_point(c, settings, forced_category=(forced_categories or {}).get(c.hash)) for c in group
        ]

        section_files = _collect_section_files(group)

        changes.append(
            {
                "title": title,
                "category": section_cat,
                "severity": section_sev,
                "files": section_files,
                "points": points,
            }
        )

    return changes


def _commit_to_point(
    commit: CommitInfo,
    settings: Settings,
    forced_category: str | None = None,
) -> dict[str, Any]:
    result = classify_commit(commit.subject, body=commit.body, settings=settings)
    point: dict[str, Any] = {
        "text": commit.subject,
        "category": forced_category or result.category,
        "severity": result.severity,
        "files": commit.files,
    }
    if commit.refs:
        point["refs"] = commit.refs
    if commit.body:
        point["body"] = commit.body
    return point


def _collect_section_files(commits: list[CommitInfo]) -> list[dict[str, str]]:
    """Build section-level files list from commits, capped at 10."""
    seen: dict[str, str] = {}
    for c in commits:
        for f in c.files:
            if f not in seen:
                seen[f] = c.subject
    return [{"path": p, "summary": s} for p, s in list(seen.items())[:10]]


def _top_directory(commits: list[CommitInfo]) -> str:
    """Find the most common top-level directory across commits' files."""
    dirs: dict[str, int] = {}
    for c in commits:
        for f in c.files:
            top = f.split("/")[0] if "/" in f else ""
            if top:
                dirs[top] = dirs.get(top, 0) + 1
    return max(dirs, key=dirs.get) if dirs else ""  # type: ignore[arg-type]


def _generate_title(commits: list[CommitInfo], groups: dict[str, list[CommitInfo]]) -> str:
    """Generate a title from the dominant category."""
    non_unclass = {k: v for k, v in groups.items() if k != "_unclassified"}
    if not non_unclass:
        return f"{len(commits)} unclassified commits"

    biggest_cat = max(non_unclass, key=lambda k: len(non_unclass[k]))
    cat_commits = non_unclass[biggest_cat]

    if len(commits) == 1:
        return _strip_prefix(commits[0].subject)

    first_clean = _strip_prefix(cat_commits[0].subject)
    if len(first_clean) > 10:
        remaining = len(commits) - 1
        return f"{first_clean}, and {remaining} more change{'s' if remaining > 1 else ''}"

    return f"{len(commits)} changes across {len(set(f for c in commits for f in c.files))} files"


def _generate_summary(stats: DiffStats, groups: dict[str, list[CommitInfo]], settings: Settings) -> str:
    """Generate a 1-3 sentence summary."""
    parts: list[str] = []
    # Use categories from config if available, otherwise fallback to default order
    cat_order = list(settings.vocabulary.categories.keys())

    for cat in cat_order:
        group = groups.get(cat)
        if not group:
            continue
        n = len(group)
        label = settings.vocabulary.categories[cat].label
        if n > 1:
            plural = label + "es" if label.endswith("x") else label + "s"
            parts.append(f"{n} {plural}")
        else:
            parts.append(f"1 {label}")

    summary = ", ".join(parts[:3])
    if len(parts) > 3:
        summary += f", and {len(parts) - 3} more categories"

    return f"{summary}. {stats.files_changed} files changed, +{stats.insertions}/-{stats.deletions}."


def _apply_file_rules(
    commits: list[CommitInfo],
    file_rules: list[FileRule],
) -> tuple[list[dict[str, Any]], list[CommitInfo], dict[str, str]]:
    """Apply file rules to commits, returning (bulk_entries, modified_commits)."""
    if not file_rules:
        return [], commits, {}

    all_bulk: list[dict[str, Any]] = []
    modified: list[CommitInfo] = []
    forced_by_commit: dict[str, str] = {}

    for commit in commits:
        if not commit.files:
            modified.append(commit)
            continue
        result = classify_files(commit.files, file_rules)
        modified.append(replace(commit, files=result.meaningful))
        all_bulk.extend(result.bulk_entries)
        if result.forced_categories:
            cat_counts: dict[str, int] = {}
            for category in result.forced_categories.values():
                cat_counts[category] = cat_counts.get(category, 0) + 1
            forced_by_commit[commit.hash] = min(
                (cat for cat, count in cat_counts.items() if count == max(cat_counts.values())),
                key=str,
            )

    # Merge bulk entries by category+reason
    merged: dict[tuple[str, str], int] = {}
    for entry in all_bulk:
        key = (str(entry["category"]), str(entry["reason"]))
        merged[key] = merged.get(key, 0) + int(entry["files"])

    bulk_list = [
        {"category": cat, "files": count, "reason": reason} for (cat, reason), count in sorted(merged.items())
    ]

    return bulk_list, modified, forced_by_commit


def _prompt_instructions(repo: str, date_str: str, stats: DiffStats, commit_count: int) -> str:
    return f"""## Instructions

Write a changelog YAML file following this structure:

```yaml
date: {date_str}
repo: {repo}
title: "One-line title"
summary: "1-3 sentence summary"
stats:
  commits: {commit_count}
  files_changed: {stats.files_changed}
  insertions: {stats.insertions}
  deletions: {stats.deletions}
changes:
  - title: "Section title"
    category: <category>
    severity: <severity>
    files:
      - path: path/to/file
        summary: "What changed"
    points:
      - text: "What changed and why"
        category: <category>
        severity: <severity>
        files: [path/to/file]
```

Categories: scaffold, instantiate, remediate, decouple, deprecate, interface, specify, qualify, margin, harden, streamline, baseline
Severities: architectural, behavioral, internal, errata

Group related changes into sections. Write real summaries based on the diffs.
If a large number of files are mechanical changes, use a bulk entry:

```yaml
bulk:
  - category: <category>
    files: N
    reason: "Why these files changed"
```
"""
