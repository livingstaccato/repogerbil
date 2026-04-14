# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Configuration via pydantic-settings with layered resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class CategoryDefinition(BaseModel):
    """Definition of a vocabulary category."""

    label: str
    conventional: str = "chore"
    verb: str = ""  # imperative verb used in multi-commit section titles, e.g. "Add", "Fix"
    description: str = ""


# ── Default vocabulary builders ───────────────────────────────────────────────
# Extracted to module-level functions so they are importable, testable, and
# readable — no logic buried inside Field(default_factory=lambda: {...}).


def _default_categories() -> dict[str, CategoryDefinition]:
    """Return the default category taxonomy."""
    return {
        # ── Conventional commit prefix categories ─────────────────────────
        "feat": CategoryDefinition(label="feat", conventional="feat"),
        "fix": CategoryDefinition(label="fix", conventional="fix"),
        "refactor": CategoryDefinition(label="refactor", conventional="refactor"),
        "test": CategoryDefinition(label="test", conventional="test"),
        "perf": CategoryDefinition(label="perf", conventional="perf"),
        "docs": CategoryDefinition(label="docs", conventional="docs"),
        "chore": CategoryDefinition(label="chore", conventional="chore"),
        # ── Semantic categories ────────────────────────────────────────────
        "instantiate": CategoryDefinition(label="feat", conventional="feat", verb="Add"),
        "interface": CategoryDefinition(label="feat", conventional="feat", verb="Wire"),
        "remediate": CategoryDefinition(label="fix", conventional="fix", verb="Fix"),
        "harden": CategoryDefinition(label="fix", conventional="fix", verb="Harden"),
        "margin": CategoryDefinition(label="fix", conventional="fix", verb="Buffer"),
        "decouple": CategoryDefinition(label="refactor", conventional="refactor", verb="Refactor"),
        "qualify": CategoryDefinition(label="test", conventional="test", verb="Test"),
        "streamline": CategoryDefinition(label="perf", conventional="perf", verb="Optimize"),
        "specify": CategoryDefinition(label="docs", conventional="docs", verb="Document"),
        "baseline": CategoryDefinition(label="chore", conventional="chore", verb="Update"),
        "deprecate": CategoryDefinition(label="remove", conventional="refactor", verb="Remove"),
    }


def _default_severities() -> dict[str, str | None]:
    return {
        "architectural": "major",
        "behavioral": "minor",
        "internal": "patch",
        "errata": None,
    }


def _default_prefix_map() -> dict[str, str]:
    return {
        "feat": "instantiate",
        "fix": "remediate",
        "refactor": "decouple",
        "test": "qualify",
        "perf": "streamline",
        "docs": "specify",
        "spec": "specify",
        "chore": "baseline",
        "ci": "baseline",
        "build": "baseline",
        "style": "baseline",
        "revert": "deprecate",
        "rename": "decouple",
        "config": "baseline",
        "release": "baseline",
    }


# ── Vocabulary config ─────────────────────────────────────────────────────────


class VocabularyConfig(BaseSettings):
    """Configuration for custom vocabulary categories and mappings.

    For additive customisation without replacing the full defaults, use
    ``extra_categories`` and ``extra_prefix_map``.  Full replacement is still
    possible by supplying ``categories`` / ``prefix_to_category`` directly.

    Example ``.repogerbil.toml`` (additive):

    .. code-block:: toml

        [vocabulary.extra_categories.hotfix]
        label = "hotfix"
        conventional = "fix"
        verb = "Patch"

        [vocabulary.extra_prefix_map]
        hotfix = "hotfix"
    """

    categories: dict[str, CategoryDefinition] = Field(default_factory=_default_categories)
    severities: dict[str, str | None] = Field(default_factory=_default_severities)
    prefix_to_category: dict[str, str] = Field(default_factory=_default_prefix_map)

    # Additive fields — merged on top of the defaults above.
    extra_categories: dict[str, CategoryDefinition] = Field(default_factory=dict)
    extra_prefix_map: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _merge_extras(self) -> VocabularyConfig:
        if self.extra_categories:
            self.categories = {**self.categories, **self.extra_categories}
        if self.extra_prefix_map:
            self.prefix_to_category = {**self.prefix_to_category, **self.extra_prefix_map}
        return self


# ── File classification rules ─────────────────────────────────────────────────


class FileRule(BaseModel):
    """A rule for classifying files by glob pattern."""

    pattern: str
    action: Literal["bulk", "skip", "classify"] = "bulk"
    category: str | None = None
    reason: str = ""


class RepoOverride(BaseModel):
    """Per-repo configuration overrides."""

    backfill_depth: Literal["heuristic", "thorough"] | None = None
    message_depth: Literal["subject", "refs", "full"] | None = None
    skip_dates: list[str] = Field(default_factory=list)


# ── Settings discovery ────────────────────────────────────────────────────────


def find_config_file(name: str = ".repogerbil.toml") -> Path | None:
    """Walk from CWD up to filesystem root looking for config file.

    Falls back to ~/.config/repogerbil/config.toml if not found.
    """
    current = Path.cwd()
    while True:
        candidate = current / name
        if candidate.exists():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # User-level fallback
    user_config = Path.home() / ".config" / "repogerbil" / "config.toml"
    if user_config.exists():
        return user_config

    return None


# ── Main settings model ───────────────────────────────────────────────────────


class Settings(BaseSettings):
    """repogerbil configuration with layered resolution.

    Priority: CLI flags > env vars > walked .repogerbil.toml > ~/.config fallback > defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="REPOGERBIL_",
    )

    # Class-level override for config file path (set before instantiation)
    _toml_path: ClassVar[str | Path | None] = None

    cadence: str = "daily"
    message_depth: Literal["subject", "refs", "full"] = "subject"
    auto_breaking: bool = True
    backfill_depth: Literal["heuristic", "thorough"] = "heuristic"
    enrich_depth: Literal["file", "package", "cross-repo"] = "package"
    tolerance: int = Field(default=20, ge=0, le=100)
    preserve_timestamps: bool = True
    create_backup: bool = True
    target_branch: str = "repogerbil-consolidated"
    file_rules: list[FileRule] = Field(default_factory=list)
    repos: dict[str, RepoOverride] = Field(default_factory=dict)
    tracked: dict[str, str] = Field(default_factory=dict)  # {name: path} registry of tracked repos
    vocabulary: VocabularyConfig = Field(default_factory=VocabularyConfig)

    # ── LLM / Ollama ─────────────────────────────────────────────────────────
    llm_ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3-coder-next:q8_0"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=120.0, gt=0.0)
    llm_concurrency: int = Field(default=1, ge=1)

    @field_validator("cadence")
    @classmethod
    def _validate_cadence(cls, v: str) -> str:
        """Validate cadence value: hourly, daily, weekly, or gap:NNm/gap:NNh."""
        import re

        if v in ("hourly", "daily", "weekly"):
            return v
        if re.match(r"^gap:\d+[mh]$", v):
            return v
        msg = f"Invalid cadence: {v}. Use 'hourly', 'daily', 'weekly', or 'gap:Nm'/'gap:Nh' (e.g., 'gap:30m')"
        raise ValueError(msg)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """Add TOML config source to the settings resolution chain."""
        toml_path = cls._toml_path or find_config_file() or ".repogerbil.toml"
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=toml_path),
        )


def load_settings(repo: str | None = None, config_path: Path | None = None) -> Settings:
    """Load settings, optionally applying per-repo overrides.

    Args:
        repo: Repository name for per-repo overrides.
        config_path: Explicit config file path (overrides default search).
    """
    if config_path and config_path.exists():
        Settings._toml_path = str(config_path)
    else:
        Settings._toml_path = None

    try:
        settings = Settings()
    finally:
        Settings._toml_path = None

    if repo and repo in settings.repos:
        override = settings.repos[repo]
        if override.backfill_depth is not None:
            settings.backfill_depth = override.backfill_depth
        if override.message_depth is not None:
            settings.message_depth = override.message_depth

    return settings
