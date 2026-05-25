# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Pre-flight repo scanning and classification."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from repogerbil.core.artifact_patterns import ARTIFACT_RULES, ArtifactRule
from repogerbil.core.config import Settings
from repogerbil.core.errors import (
    PreflightGitLogCommandFailedError,
    PreflightInvalidRevisionOrDateError,
    PreflightNotAGitRepositoryError,
)

# Walks the entire commit graph for --name-only output; 120s matches the
# upper-bound used by other full-history git operations in this package.
_GIT_LOG_TIMEOUT_SECONDS = 120

# Matches a bare ISO date with nothing else (no time, no trailing tokens).
# Used to decide whether a user-supplied --since/--until value needs pinning
# so git's approxidate doesn't interpret it as "that day at current wall-clock
# time" — which would silently drop same-day commits earlier than "now".
_BARE_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _pin_iso_date(value: str, *, end_of_day: bool) -> str:
    """Pin a bare YYYY-MM-DD value to start- or end-of-day for git's approxidate.

    Returns the value unchanged when it doesn't match the bare-ISO-date shape
    (so relative strings like ``yesterday`` or full ISO timestamps pass through).
    ``end_of_day=True`` is appropriate for ``--until``; ``False`` for ``--since``.
    """
    if not _BARE_ISO_DATE_RE.match(value):
        return value
    return f"{value}T23:59:59" if end_of_day else f"{value}T00:00:00"


_NOT_A_REPO_HINTS = (
    "not a git repository",
    "outside repository",
)

_INVALID_REVISION_OR_DATE_HINTS = (
    "bad revision",
    "unknown revision",
    "ambiguous argument",
    "invalid date",
    "malformed object name",
    "invalid object name",
)

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
        # Cert/key files (test fixtures)
        ".pem",
        ".crt",
        ".csr",
        ".key",
        ".srl",
        ".conf",
        ".ini",
        ".feature",
        ".xml",
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
        cmd += [f"--since={_pin_iso_date(since, end_of_day=False)}"]
    if until:
        cmd += [f"--until={_pin_iso_date(until, end_of_day=True)}"]

    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=True,
            timeout=_GIT_LOG_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        operation = "collecting file history with git log"
        stderr = exc.stderr
        lowered = (stderr or "").lower()
        if any(hint in lowered for hint in _NOT_A_REPO_HINTS):
            raise PreflightNotAGitRepositoryError(
                repo_path=repo,
                operation=operation,
                command=cmd,
                returncode=exc.returncode,
                stderr=stderr,
            ) from exc
        if any(hint in lowered for hint in _INVALID_REVISION_OR_DATE_HINTS):
            raise PreflightInvalidRevisionOrDateError(
                repo_path=repo,
                operation=operation,
                command=cmd,
                returncode=exc.returncode,
                stderr=stderr,
            ) from exc
        raise PreflightGitLogCommandFailedError(
            repo_path=repo,
            operation=operation,
            command=cmd,
            returncode=exc.returncode,
            stderr=stderr,
        ) from exc

    counts: Counter[str] = Counter()
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        counts[stripped] += 1
    return counts


def _classify_files(
    file_counts: Counter[str],
    rules: tuple[ArtifactRule, ...],
) -> tuple[list[FileRecord], list[FileRecord], list[FileRecord], list[str]]:
    """Bucket file records into artifacts, source, unknown and collect suggested flags."""
    artifacts: list[FileRecord] = []
    source: list[FileRecord] = []
    unknown: list[FileRecord] = []
    seen_flags: dict[str, None] = {}  # ordered set via insertion order

    for file_path, count in sorted(file_counts.items()):
        matched_rule: ArtifactRule | None = next((rule for rule in rules if rule.matches(file_path)), None)
        record = FileRecord(path=file_path, commit_count=count, rule=matched_rule)
        if matched_rule is not None:
            artifacts.append(record)
            seen_flags[matched_rule.flag] = None
        elif _is_source(file_path):
            source.append(record)
        else:
            unknown.append(record)

    return artifacts, source, unknown, list(seen_flags)


def _resolve_artifact_rules(settings: Settings | None) -> tuple[ArtifactRule, ...]:
    """Return the active artifact rule list: built-ins first, user extras appended.

    Built-ins run first so existing behaviour is preserved for any path they
    already classify. User patterns only get a chance at paths the built-ins
    do not recognise.
    """
    if settings is None or not settings.extra_artifact_patterns:
        return tuple(ARTIFACT_RULES)
    extras = tuple(
        ArtifactRule(label=cfg.label, pattern=cfg.pattern, flag=cfg.flag)
        for cfg in settings.extra_artifact_patterns
    )
    return tuple(ARTIFACT_RULES) + extras


def scan_repo(
    path: Path | str,
    since: str | None = None,
    until: str | None = None,
    settings: Settings | None = None,
) -> PreflightReport:
    """Scan a git repo and classify files into artifacts, source, and unknown.

    ``settings.extra_artifact_patterns`` (if any) are appended to the built-in
    ``ARTIFACT_RULES`` — so the built-ins always win first, and user-supplied
    patterns only match paths the built-ins did not classify.
    """
    repo = Path(path)
    file_counts = _count_files(repo, since, until)
    rules = _resolve_artifact_rules(settings)
    artifacts, source, unknown, suggested_flags = _classify_files(file_counts, rules)
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
