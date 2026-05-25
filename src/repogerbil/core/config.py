# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Configuration via pydantic-settings with layered resolution."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource

# Re-exported from vocabulary.py so ``from repogerbil.core.config import
# CategoryDefinition`` keeps working. Vocabulary is the single source of truth
# for default categories / severities / prefix mappings — see vocabulary.py.
from repogerbil.core.vocabulary import (
    CategoryDefinition as CategoryDefinition,
    _default_categories,
    _default_prefix_map,
    _default_severities,
)

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


class ArtifactPatternConfig(BaseModel):
    """User-supplied artifact pattern, merged with the built-in ``ARTIFACT_RULES``.

    ``pattern`` is a regex passed to ``re.search`` against repo-relative file
    paths (same semantics as the built-in rules). ``flag`` defaults to
    ``pattern`` and is the ready-to-paste ``--exclude-path`` value.

    Example ``.repogerbil.toml``:

    .. code-block:: toml

        [[extra_artifact_patterns]]
        label = "snapshot tarball"
        pattern = "snapshots/.*\\\\.tar\\\\.gz$"
    """

    label: str
    pattern: str
    flag: str = ""

    @field_validator("pattern")
    @classmethod
    def _validate_pattern_compiles(cls, v: str) -> str:
        """Reject patterns that fail to compile as a regex at config load time."""
        try:
            re.compile(v)
        except re.error as exc:
            msg = f"Invalid artifact pattern regex {v!r}: {exc}"
            raise ValueError(msg) from exc
        return v


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

    **Environment variable convention.** Every top-level field is settable via an
    env var named ``REPOGERBIL_<FIELD>`` (uppercased). For example,
    ``llm_model`` is overridden by ``REPOGERBIL_LLM_MODEL``. Nested fields on
    ``vocabulary`` use the pydantic-settings double-underscore convention:
    ``REPOGERBIL_VOCABULARY__<NESTED_FIELD>`` (e.g.
    ``REPOGERBIL_VOCABULARY__EXTRA_CATEGORIES`` — note **two** underscores
    between the parent and the nested field name).

    **Field organization.** Fields are grouped into sections (General / LLM /
    Multi-snapshot / Vocabulary / Per-repo) below for readability. The grouping
    is purely a comment convention — there is no nested sub-model, because
    introducing one would silently break the existing env-var names that ship
    with deployed configs.

    **Cross-field validation.** Grouped settings that must be all-set-or-all-None
    (e.g. ``snapshot_author_name`` / ``snapshot_author_email``) are validated
    via a ``model_validator(mode="after")`` here in this class — see
    ``_validate_snapshot_author_pair``. CLI-only group constraints
    (e.g. ``--time-window-start`` / ``--time-window-end`` on the distill
    commands) are *not* validated here; they live in the CLI layer because
    the underlying ``Settings`` fields are independently meaningful and only
    the CLI surface needs to enforce both-or-neither.
    """

    model_config = SettingsConfigDict(
        env_prefix="REPOGERBIL_",
    )
    # Backward-compatibility shim for older tests/callers that set this attribute directly.
    # It is intentionally not consulted by source resolution to avoid global mutable state races.
    _toml_path: ClassVar[str | Path | None] = None

    # ── General — cadence, depths, file rules, registries ────────────────────
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
    extra_artifact_patterns: list[ArtifactPatternConfig] = Field(default_factory=list)

    # ── Per-repo overrides and tracked-repo registry ─────────────────────────
    repos: dict[str, RepoOverride] = Field(default_factory=dict)
    tracked: dict[str, str] = Field(default_factory=dict)  # {name: path} registry of tracked repos

    # ── Vocabulary — categories, severities, prefix → category mapping ───────
    vocabulary: VocabularyConfig = Field(default_factory=VocabularyConfig)

    # ── LLM / Ollama ─────────────────────────────────────────────────────────
    llm_ollama_url: str = "http://localhost:11434"
    llm_model: str = "qwen3-coder-next:q8_0"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=120.0, gt=0.0)
    llm_concurrency: int = Field(default=1, ge=1)
    llm_refine: bool = False

    # ── Multi-snapshot — ecosystem label and dest-repo git identity ──────────
    # Label used in the first line of every multi-snapshot daily commit message,
    # e.g. "2026-05-24 <label>". Kept generic by default — projects can override
    # via .repogerbil.toml, the REPOGERBIL_ECOSYSTEM_LABEL env var, or the
    # CLI --ecosystem-label flag.
    ecosystem_label: str = "ecosystem"
    # Git identity for multi-snapshot commits. When both are ``None`` (the
    # default), the destination repo inherits the user's global git config —
    # matching the single-snapshot path. Set both to override.
    snapshot_author_name: str | None = None
    snapshot_author_email: str | None = None

    @model_validator(mode="after")
    def _validate_snapshot_author_pair(self) -> Settings:
        """Reject half-set ``snapshot_author_name`` / ``snapshot_author_email``.

        Both must be provided together so the multi-snapshot destination repo
        gets a complete git identity — otherwise the partial value was being
        silently dropped by ``_init_dest_repo``.

        This is the canonical example of the both-or-neither convention noted
        in the class docstring: pairs of settings that are only meaningful as
        a unit get a ``model_validator(mode="after")`` here in the Settings
        model. CLI-only pairings (e.g. ``--time-window-start`` /
        ``--time-window-end``) instead validate at the CLI layer because the
        underlying Settings fields are not paired in the same way.
        """
        name_set = self.snapshot_author_name is not None
        email_set = self.snapshot_author_email is not None
        if name_set != email_set:
            # Message intentionally lists both config sources — the half-set
            # value can come from .repogerbil.toml or the
            # REPOGERBIL_SNAPSHOT_AUTHOR_NAME/EMAIL environment variables.
            msg = (
                "snapshot_author_name and snapshot_author_email must be set together "
                "(both or neither). Check your .repogerbil.toml or "
                "REPOGERBIL_SNAPSHOT_AUTHOR_NAME/REPOGERBIL_SNAPSHOT_AUTHOR_EMAIL env vars — got "
                f"snapshot_author_name={self.snapshot_author_name!r}, "
                f"snapshot_author_email={self.snapshot_author_email!r}"
            )
            raise ValueError(msg)
        return self

    @field_validator("cadence")
    @classmethod
    def _validate_cadence(cls, v: str) -> str:
        """Validate cadence value: hourly, daily, weekly, or gap:NNm/gap:NNh."""
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
        return (
            init_settings,
            env_settings,
            TomlConfigSettingsSource(settings_cls, toml_file=find_config_file() or ".repogerbil.toml"),
        )


def _settings_with_explicit_toml(config_path: Path) -> type[Settings]:
    """Build a settings class that loads from one fixed TOML path.

    This avoids cross-call contamination from mutable class state.
    """

    class ExplicitTomlSettings(Settings):
        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: Any,
            env_settings: Any,
            dotenv_settings: Any,
            file_secret_settings: Any,
        ) -> tuple[Any, ...]:
            return (
                init_settings,
                env_settings,
                TomlConfigSettingsSource(settings_cls, toml_file=str(config_path)),
            )

    return ExplicitTomlSettings


def load_settings(repo: str | None = None, config_path: Path | None = None) -> Settings:
    """Load settings, optionally applying per-repo overrides.

    Args:
        repo: Repository name for per-repo overrides.
        config_path: Explicit config file path (overrides default search).
    """
    settings_cls: type[Settings]
    if config_path and config_path.exists():
        settings_cls = _settings_with_explicit_toml(config_path)
    else:
        settings_cls = Settings

    settings = settings_cls()

    if repo and repo in settings.repos:
        override = settings.repos[repo]
        if override.backfill_depth is not None:
            settings.backfill_depth = override.backfill_depth
        if override.message_depth is not None:
            settings.message_depth = override.message_depth

    return settings
