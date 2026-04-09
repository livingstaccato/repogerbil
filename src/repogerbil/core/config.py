# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Configuration via pydantic-settings with layered resolution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


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


class Settings(BaseSettings):
    """repogerbil configuration with layered resolution.

    Priority: CLI flags > env vars > walked .repogerbil.toml > ~/.config fallback > defaults.
    """

    model_config = SettingsConfigDict(
        env_prefix="REPOGERBIL_",
    )

    # Class-level override for config file path (set before instantiation)
    _toml_path: ClassVar[str | Path | None] = None

    cadence: Literal["hourly", "daily", "weekly"] = "daily"
    message_depth: Literal["subject", "refs", "full"] = "subject"
    auto_breaking: bool = True
    include_files: bool = True
    backfill_depth: Literal["heuristic", "thorough"] = "heuristic"
    enrich_depth: Literal["file", "package", "cross-repo"] = "package"
    tolerance: int = Field(default=20, ge=0, le=100)
    preserve_timestamps: bool = True
    create_backup: bool = True
    target_branch: str = "repogerbil-consolidated"
    output: Literal["data-repo", "source-repo"] = "data-repo"
    output_dir: str = ""
    standard_scopes: list[str] = Field(
        default_factory=lambda: ["go", "ts", "py", "ci", "freebsd", "deps", "docs"],
    )
    file_rules: list[FileRule] = Field(default_factory=list)
    repos: dict[str, RepoOverride] = Field(default_factory=dict)
    tracked: dict[str, str] = Field(default_factory=dict)  # {name: path} registry of tracked repos
    changelog_dir: str = ""  # root directory for changelog output

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
