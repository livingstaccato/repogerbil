# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for vocabulary definitions and mappings."""

from repogerbil.core.config import CategoryDefinition
from repogerbil.core.vocabulary import (
    CATEGORIES,
    PREFIX_TO_CATEGORY,
    SEVERITIES,
    VOCAB_VERSION,
    allowed_verbs,
    category_to_conventional,
    conventional_to_category,
)

_EXPECTED_CATEGORIES = {
    # conventional prefix categories
    "feat",
    "fix",
    "refactor",
    "test",
    "perf",
    "docs",
    "chore",
    # semantic categories
    "instantiate",
    "remediate",
    "decouple",
    "deprecate",
    "interface",
    "specify",
    "qualify",
    "margin",
    "harden",
    "streamline",
    "baseline",
}


class TestCategories:
    def test_all_categories_have_conventional_equivalent(self) -> None:
        for cat, defn in CATEGORIES.items():
            assert isinstance(cat, str)
            assert isinstance(defn, CategoryDefinition)
            assert len(defn.conventional) > 0

    def test_expected_categories_present(self) -> None:
        assert set(CATEGORIES.keys()) >= _EXPECTED_CATEGORIES


class TestSeverities:
    def test_all_severities_present(self) -> None:
        expected = {"architectural", "behavioral", "internal", "errata"}
        assert set(SEVERITIES.keys()) == expected

    def test_errata_has_no_semver(self) -> None:
        assert SEVERITIES["errata"] is None

    def test_architectural_is_major(self) -> None:
        assert SEVERITIES["architectural"] == "major"

    def test_behavioral_is_minor(self) -> None:
        assert SEVERITIES["behavioral"] == "minor"

    def test_internal_is_patch(self) -> None:
        assert SEVERITIES["internal"] == "patch"


class TestPrefixToCategory:
    def test_feat_maps_to_instantiate(self) -> None:
        assert PREFIX_TO_CATEGORY["feat"] == "instantiate"

    def test_fix_maps_to_remediate(self) -> None:
        assert PREFIX_TO_CATEGORY["fix"] == "remediate"

    def test_all_prefixes_map_to_valid_categories(self) -> None:
        for prefix, cat in PREFIX_TO_CATEGORY.items():
            assert cat in CATEGORIES, f"{prefix} maps to unknown category {cat}"


class TestCategoryToConventional:
    def test_instantiate_to_feat(self) -> None:
        assert category_to_conventional("instantiate") == "feat"

    def test_unknown_returns_chore(self) -> None:
        assert category_to_conventional("nonexistent") == "chore"

    def test_all_categories_roundtrip(self) -> None:
        for cat in CATEGORIES:
            result = category_to_conventional(cat)
            assert isinstance(result, str)


class TestConventionalToCategory:
    def test_feat_to_instantiate(self) -> None:
        assert conventional_to_category("feat") == "instantiate"

    def test_case_insensitive(self) -> None:
        assert conventional_to_category("FEAT") == "instantiate"
        assert conventional_to_category("Fix") == "remediate"

    def test_unknown_returns_none(self) -> None:
        assert conventional_to_category("nonexistent") is None


class TestVocabVersion:
    def test_vocab_version_is_string(self) -> None:
        assert isinstance(VOCAB_VERSION, str)
        assert len(VOCAB_VERSION) > 0


class TestAllowedVerbs:
    def test_allowed_verbs_returns_semantic_verbs(self) -> None:
        verbs = allowed_verbs()
        assert "instantiate" in verbs
        assert "interface" in verbs
        assert "remediate" in verbs
        assert "harden" in verbs
        assert "margin" in verbs
        assert "decouple" in verbs
        assert "qualify" in verbs
        assert "streamline" in verbs
        assert "specify" in verbs
        assert "baseline" in verbs
        assert "deprecate" in verbs

    def test_allowed_verbs_excludes_conventional_prefixes(self) -> None:
        verbs = allowed_verbs()
        assert "feat" not in verbs
        assert "fix" not in verbs
        assert "refactor" not in verbs
        assert "test" not in verbs
        assert "perf" not in verbs
        assert "docs" not in verbs
        assert "chore" not in verbs

    def test_allowed_verbs_is_sorted(self) -> None:
        verbs = allowed_verbs()
        assert verbs == sorted(verbs)
