# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for custom vocabulary extensibility."""

from __future__ import annotations

from repogerbil.core.classify import classify_commit
from repogerbil.core.config import CategoryDefinition, Settings, VocabularyConfig
from repogerbil.core.vocabulary import (
    category_to_conventional,
    conventional_to_category,
    get_root_categories,
)


def test_custom_prefix_classification() -> None:
    """Classify commit should use custom prefix mapping from settings."""
    vocab = VocabularyConfig(
        prefix_to_category={"hotfix": "remediate"},
    )
    settings = Settings(vocabulary=vocab)

    # Custom prefix
    res = classify_commit("hotfix: urgent security patch", settings=settings)
    assert res.category == "remediate"
    assert res.needs_review is False

    # Standard prefix (not in custom list)
    res = classify_commit("feat: new feature", settings=settings)
    assert res.needs_review is True


def test_custom_severity_classification() -> None:
    """Classify commit should use custom severity mapping from settings."""
    vocab = VocabularyConfig(
        prefix_to_category={"feat": "instantiate"},
        severities={"architectural": "breaking", "behavioral": "feature"},
    )
    settings = Settings(vocabulary=vocab)

    # Conventional feat -> behavioral -> custom "feature"
    res = classify_commit("feat: some change", settings=settings)
    assert res.severity == "feature"

    # Breaking change -> architectural -> custom "breaking"
    res = classify_commit("feat!: breaking change", settings=settings)
    assert res.severity == "breaking"


def test_vocabulary_hierarchy() -> None:
    """Vocabulary should support hierarchical category associations (DAG)."""
    vocab = VocabularyConfig(
        categories={
            "standard": CategoryDefinition(label="std", conventional="feat"),
            "custom": CategoryDefinition(label="cust", conventional="fix", parents=["standard"]),
        }
    )

    assert get_root_categories("custom", vocab=vocab) == {"standard"}
    assert get_root_categories("standard", vocab=vocab) == {"standard"}
    assert get_root_categories("nonexistent", vocab=vocab) == {"nonexistent"}


def test_vocabulary_dag_multi_parent() -> None:
    """A category with multiple parents resolves to multiple roots."""
    vocab = VocabularyConfig(
        categories={
            "root_a": CategoryDefinition(label="a", conventional="feat"),
            "root_b": CategoryDefinition(label="b", conventional="docs"),
            "child": CategoryDefinition(label="c", conventional="feat", parents=["root_a", "root_b"]),
        }
    )

    assert get_root_categories("child", vocab=vocab) == {"root_a", "root_b"}


def test_extra_categories_are_additive() -> None:
    """extra_categories merges with defaults rather than replacing them."""
    vocab = VocabularyConfig(
        extra_categories={
            "hotfix": CategoryDefinition(label="hotfix", conventional="fix", parents=["remediate"]),
        },
        extra_prefix_map={"hotfix": "hotfix"},
    )

    # Default categories still present
    assert "instantiate" in vocab.categories
    assert "remediate" in vocab.categories
    # Extra category was added
    assert "hotfix" in vocab.categories
    assert vocab.prefix_to_category.get("hotfix") == "hotfix"
    # Original prefix map still intact
    assert vocab.prefix_to_category.get("feat") == "instantiate"


def test_vocabulary_mapping_with_vocab() -> None:
    """Category and prefix mapping should use provided vocab when available."""
    vocab = VocabularyConfig(
        categories={"mycat": CategoryDefinition(label="my", conventional="mypre")},
        prefix_to_category={"mypre": "mycat"},
    )

    assert category_to_conventional("mycat", vocab=vocab) == "mypre"
    assert category_to_conventional("other", vocab=vocab) == "chore"

    assert conventional_to_category("mypre", vocab=vocab) == "mycat"
    assert conventional_to_category("other", vocab=vocab) is None
