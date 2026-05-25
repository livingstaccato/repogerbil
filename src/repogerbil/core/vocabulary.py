# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Changelog vocabulary — single source of truth for categories, severities,
prefix mappings, and the ``CategoryDefinition`` schema.

This module is the canonical home for the default vocabulary. ``config.py``
imports the defaults and the ``CategoryDefinition`` model from here for its
``VocabularyConfig`` pydantic model, and ``classify.py`` uses the bare-module
constants for the "no settings" fast path. Adding a new category should
require editing exactly one file: this one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from repogerbil.core.config import VocabularyConfig


class CategoryDefinition(BaseModel):
    """Definition of a vocabulary category."""

    label: str
    conventional: str = "chore"
    verb: str = ""  # imperative verb used in multi-commit section titles, e.g. "Add", "Fix"
    description: str = ""


# ── Default vocabulary builders ───────────────────────────────────────────────
# Defined as module-level functions so pydantic can use them as
# ``default_factory=…`` (each Settings() gets a fresh dict, no shared mutable
# state) while also remaining importable for the bare-constants fast path
# below.


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
        "scaffold": CategoryDefinition(label="feat", conventional="feat", verb="Scaffold"),
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
    """Return the default severity → semver-bump mapping."""
    return {
        "architectural": "major",
        "behavioral": "minor",
        "internal": "patch",
        "errata": None,
    }


def _default_prefix_map() -> dict[str, str]:
    """Return the default conventional-prefix → semantic-category mapping."""
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
        "scaffold": "scaffold",
    }


# ── Bare-module fast-path constants ───────────────────────────────────────────
# Used by ``classify.py`` when no ``Settings`` instance is supplied. They are
# snapshots of the factory output above — never mutate them at runtime; mutate
# ``VocabularyConfig`` instances instead.
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


VOCAB_VERSION: str = "1.2.0"


def allowed_verbs() -> list[str]:
    """Return all verbs valid for LLM structured output.

    Returns every category key — both conventional prefixes (feat, fix,
    refactor, …) and semantic aliases (instantiate, remediate, …) — so
    the LLM can choose whichever term best describes the change.
    """
    return sorted(CATEGORIES.keys())
