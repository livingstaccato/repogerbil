# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Changelog vocabulary definitions — categories, severities, and mappings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repogerbil.core.config import CategoryDefinition

if TYPE_CHECKING:
    from repogerbil.core.config import VocabularyConfig


def _default_categories() -> dict[str, CategoryDefinition]:
    """Return the default category taxonomy."""
    return {
        "feat": CategoryDefinition(label="feat", conventional="feat"),
        "fix": CategoryDefinition(label="fix", conventional="fix"),
        "refactor": CategoryDefinition(label="refactor", conventional="refactor"),
        "test": CategoryDefinition(label="test", conventional="test"),
        "perf": CategoryDefinition(label="perf", conventional="perf"),
        "docs": CategoryDefinition(label="docs", conventional="docs"),
        "chore": CategoryDefinition(label="chore", conventional="chore"),
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


CATEGORIES: dict[str, CategoryDefinition] = _default_categories()
SEVERITIES: dict[str, str | None] = _default_severities()
PREFIX_TO_CATEGORY: dict[str, str] = _default_prefix_map()


def category_to_conventional(category: str, vocab: VocabularyConfig | None = None) -> str:
    """Map a vocabulary category to its conventional commit prefix."""
    c = vocab.categories if vocab else CATEGORIES
    if category in c:
        return c[category].conventional
    return "chore"


def conventional_to_category(prefix: str, vocab: VocabularyConfig | None = None) -> str | None:
    """Map a conventional commit prefix to a vocabulary category."""
    p = vocab.prefix_to_category if vocab else PREFIX_TO_CATEGORY
    return p.get(prefix.lower())
