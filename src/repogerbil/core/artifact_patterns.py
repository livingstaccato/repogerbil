from __future__ import annotations

from dataclasses import dataclass, field
import re


@dataclass(frozen=True)
class ArtifactRule:
    label: str  # e.g. "Python bytecode"
    pattern: str  # regex passed to re.search()
    flag: str  # ready-to-paste --exclude-path value
    _compiled: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", re.compile(self.pattern))

    def matches(self, path: str) -> bool:
        return bool(self._compiled.search(path))


ARTIFACT_RULES: list[ArtifactRule] = [
    # Python bytecode / caches
    ArtifactRule("Python bytecode", r"__pycache__", r"__pycache__"),
    ArtifactRule("Python bytecode", r"\.pyc$", r"\.pyc$"),
    ArtifactRule("Python bytecode", r"\.pyo$", r"\.pyo$"),
    ArtifactRule("pytest cache", r"\.pytest_cache", r"\.pytest_cache"),
    ArtifactRule("mypy cache", r"\.mypy_cache", r"\.mypy_cache"),
    ArtifactRule("coverage data", r"(^|/)\.coverage$", r"(^|/)\.coverage$"),
    ArtifactRule("coverage report", r"htmlcov/", r"^htmlcov/"),
    # Lock files
    ArtifactRule("lock file", r"\.lock$", r"\.lock$"),
    ArtifactRule("lock file", r"package-lock\.json$", r"package-lock\.json$"),
    # Build / dist artifacts
    ArtifactRule("build artifact", r"^dist/", r"^dist/"),
    ArtifactRule("build artifact", r"^build/", r"^build/"),
    ArtifactRule("build artifact", r"\.egg-info/", r"\.egg-info/"),
    ArtifactRule("build artifact", r"\.so$", r"\.so$"),
    ArtifactRule("build artifact", r"\.dylib$", r"\.dylib$"),
    # AI / IDE tool configs
    ArtifactRule("AI tool config", r"^\.claude(/|$)", r"^\.claude(/|$)"),
    ArtifactRule("AI tool config", r"^\.codex(/|$)", r"^\.codex(/|$)"),
    ArtifactRule("AI tool config", r"^\.cursor(/|$)", r"^\.cursor(/|$)"),
    ArtifactRule("AI tool config", r"^\.aider(/|$)", r"^\.aider(/|$)"),
    ArtifactRule("AI tool config", r"^\.continue(/|$)", r"^\.continue(/|$)"),
    ArtifactRule("IDE config", r"^\.idea(/|$)", r"^\.idea(/|$)"),
    ArtifactRule("IDE config", r"^\.vscode(/|$)", r"^\.vscode(/|$)"),
    # Stale / ephemeral docs
    ArtifactRule("ephemeral doc", r"(^|/)HANDOFF\.md$", r"(^|/)HANDOFF\.md$"),
    ArtifactRule("ephemeral doc", r"(^|/)SCRATCH\.md$", r"(^|/)SCRATCH\.md$"),
    ArtifactRule("ephemeral doc", r"(^|/)NOTES\.md$", r"(^|/)NOTES\.md$"),
    ArtifactRule("ephemeral doc", r"^\.provide(/|$)", r"^\.provide(/|$)"),
    # OS noise
    ArtifactRule("OS noise", r"\.DS_Store$", r"\.DS_Store$"),
    ArtifactRule("OS noise", r"^Thumbs\.db$", r"^Thumbs\.db$"),
]
