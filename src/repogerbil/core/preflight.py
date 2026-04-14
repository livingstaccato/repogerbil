# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Pre-flight repo scanning and classification."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import subprocess

from repogerbil.core.artifact_patterns import ARTIFACT_RULES, ArtifactRule

_SOURCE_EXTENSIONS = frozenset(
    {
        ".py",
        ".go",
        ".rb",
        ".rs",
        ".ts",
        ".js",
        ".tsx",
        ".jsx",
        ".java",
        ".kt",
        ".scala",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".tf",
        ".tf.json",
        ".yaml",
        ".yml",
        ".toml",
        ".json",
        ".md",
        ".rst",
        ".txt",
        ".sh",
        ".bash",
        ".zsh",
        ".html",
        ".css",
        ".scss",
        ".proto",
        ".sql",
    }
)

_SOURCE_FILENAMES = frozenset(
    {
        "Makefile",
        "Dockerfile",
        "Gemfile",
        "Rakefile",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".env.example",
        ".env.sample",
    }
)


@dataclass(frozen=True)
class FileRecord:
    path: str
    commit_count: int  # how many commits touched this file
    rule: ArtifactRule | None  # matched rule, or None if unknown/source


@dataclass(frozen=True)
class PreflightReport:
    artifacts: tuple[FileRecord, ...]  # matched an ARTIFACT_RULES rule
    source: tuple[FileRecord, ...]  # .py/.go/.rb/.tf/etc — clearly source
    unknown: tuple[FileRecord, ...]  # everything else — needs human eval
    suggested_flags: tuple[str, ...]  # de-duped --exclude-path values, in order


def _count_files(repo: Path, since: str | None, until: str | None) -> Counter[str]:
    """Run git log and return per-file commit counts.

    git --format= emits blank lines between commits; rename tracking shows old and new names as separate paths.
    """
    cmd = ["git", "log", "--name-only", "--format="]
    if since:
        cmd += [f"--since={since}"]
    if until:
        cmd += [f"--until={until}"]

    result = subprocess.run(  # noqa: S603
        cmd,
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )

    counts: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        counts[stripped] += 1
    return counts


def _classify_files(
    file_counts: Counter[str],
) -> tuple[list[FileRecord], list[FileRecord], list[FileRecord], list[str]]:
    """Bucket file records into artifacts, source, unknown and collect suggested flags."""
    artifacts: list[FileRecord] = []
    source: list[FileRecord] = []
    unknown: list[FileRecord] = []
    seen_flags: dict[str, None] = {}  # ordered set via insertion order

    for file_path, count in sorted(file_counts.items()):
        matched_rule: ArtifactRule | None = next(
            (rule for rule in ARTIFACT_RULES if rule.matches(file_path)), None
        )
        record = FileRecord(path=file_path, commit_count=count, rule=matched_rule)
        if matched_rule is not None:
            artifacts.append(record)
            seen_flags[matched_rule.flag] = None
        elif _is_source(file_path):
            source.append(record)
        else:
            unknown.append(record)

    return artifacts, source, unknown, list(seen_flags)


def scan_repo(
    path: Path | str,
    since: str | None = None,
    until: str | None = None,
) -> PreflightReport:
    """Scan a git repo and classify files into artifacts, source, and unknown."""
    repo = Path(path)
    file_counts = _count_files(repo, since, until)
    artifacts, source, unknown, suggested_flags = _classify_files(file_counts)
    return PreflightReport(
        artifacts=tuple(artifacts),
        source=tuple(source),
        unknown=tuple(unknown),
        suggested_flags=tuple(suggested_flags),
    )


def _is_source(path: str) -> bool:
    """Return True if the path looks like a source file (not an artifact)."""
    p = Path(path)
    if p.name in _SOURCE_FILENAMES:
        return True
    return p.suffix in _SOURCE_EXTENSIONS
