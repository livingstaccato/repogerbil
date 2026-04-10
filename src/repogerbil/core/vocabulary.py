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


def get_root_categories(category: str, vocab: VocabularyConfig | None = None) -> set[str]:
    """Return the set of root ancestor categories (those with no parents) via BFS.

    For a category that IS a root (parents=[]), returns {category} itself.
    For a DAG node with multiple parents, all root ancestors are returned.
    """
    c = vocab.categories if vocab else CATEGORIES
    if category not in c:
        return {category}

    visited: set[str] = set()
    queue: list[str] = [category]
    roots: set[str] = set()

    while queue:
        current = queue.pop()
        if current in visited:  # pragma: no cover — safety guard against cycles
            continue
        visited.add(current)

        defn = c.get(current)
        if defn is None or not defn.parents:
            roots.add(current)
        else:
            queue.extend(defn.parents)

    return roots


def get_root_category(category: str, vocab: VocabularyConfig | None = None) -> str:
    """Return a single root ancestor (first found).

    Deprecated: prefer ``get_root_categories`` for DAG vocabularies.
    For tree-shaped vocabularies the result is deterministic.
    """
    roots = get_root_categories(category, vocab=vocab)
    return next(iter(roots))
