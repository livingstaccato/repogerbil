# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Changelog vocabulary definitions — categories, severities, and mappings."""

from __future__ import annotations

from repogerbil.core.config import CategoryDefinition, VocabularyConfig

_DEFAULT_VOCAB = VocabularyConfig()

CATEGORIES: dict[str, CategoryDefinition] = _DEFAULT_VOCAB.categories
SEVERITIES: dict[str, str | None] = _DEFAULT_VOCAB.severities
PREFIX_TO_CATEGORY: dict[str, str] = _DEFAULT_VOCAB.prefix_to_category


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
