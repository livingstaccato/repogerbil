# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Artifact detection rules and classification."""

from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class ArtifactRule:
    label: str  # e.g. "Python bytecode"
    pattern: str  # regex passed to re.search()
    flag: str = ""  # ready-to-paste --exclude-path value; defaults to pattern
    _compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.flag:
            object.__setattr__(self, "flag", self.pattern)
        object.__setattr__(self, "_compiled", re.compile(self.pattern))

    def matches(self, path: str) -> bool:
        return bool(self._compiled.search(path))


ARTIFACT_RULES: list[ArtifactRule] = [
    # Python bytecode / caches
    ArtifactRule("Python bytecode", r"__pycache__"),
    ArtifactRule("Python bytecode", r"\.pyc$"),
    ArtifactRule("Python bytecode", r"\.pyo$"),
    ArtifactRule("pytest cache", r"\.pytest_cache"),
    ArtifactRule("mypy cache", r"\.mypy_cache"),
    ArtifactRule("coverage data", r"(^|/)\.coverage$"),
    ArtifactRule("coverage report", r"^htmlcov/"),
    # Lock files
    ArtifactRule("lock file", r"(poetry|yarn|Pipfile|Gemfile|Cargo|composer|packages|uv)\.lock$"),
    ArtifactRule("lock file", r"package-lock\.json$"),
    # Build / dist artifacts
    ArtifactRule("build artifact", r"^dist/"),
    ArtifactRule("build artifact", r"^build/"),
    ArtifactRule("build artifact", r"\.egg-info/"),
    ArtifactRule("build artifact", r"\.so$"),
    ArtifactRule("build artifact", r"\.dylib$"),
    # AI / IDE tool configs
    ArtifactRule("AI tool config", r"^\.claude(/|$)"),
    ArtifactRule("AI tool config", r"^\.codex(/|$)"),
    ArtifactRule("AI tool config", r"^\.cursor(/|$)"),
    ArtifactRule("AI tool config", r"^\.aider(/|$)"),
    ArtifactRule("AI tool config", r"^\.continue(/|$)"),
    ArtifactRule("IDE config", r"^\.idea(/|$)"),
    ArtifactRule("IDE config", r"^\.vscode(/|$)"),
    # Stale / ephemeral docs
    ArtifactRule("ephemeral doc", r"(^|/)HANDOFF\.md$"),
    ArtifactRule("ephemeral doc", r"(^|/)SCRATCH\.md$"),
    ArtifactRule("ephemeral doc", r"(^|/)NOTES\.md$"),
    ArtifactRule("ephemeral doc", r"^\.provide(/|$)"),
    # Mutation testing artifacts
    ArtifactRule("mutation testing", r"^mutants/"),
    ArtifactRule("mutation testing", r"\.meta$"),
    # Stale backup files
    ArtifactRule("backup file", r"\.bak$"),
    # Coverage reports
    ArtifactRule("coverage report", r"(^|/)cov\.xml$"),
    ArtifactRule("coverage report", r"(^|/)coverage\.xml$"),
    # Go module checksums (lock-file equivalent)
    ArtifactRule("lock file", r"go\.sum$"),
    # Developer tool configs
    ArtifactRule("tool config", r"^\.python-version$"),
    ArtifactRule("tool config", r"^\.actrc$"),
    ArtifactRule("tool config", r"^\.pyre_configuration$"),
    # OS noise
    ArtifactRule("OS noise", r"\.DS_Store$"),
    ArtifactRule("OS noise", r"^Thumbs\.db$"),
]
