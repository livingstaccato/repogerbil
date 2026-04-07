# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for vocabulary definitions and mappings."""

from repogerbil.core.vocabulary import (
    CATEGORIES,
    PREFIX_TO_CATEGORY,
    SEVERITIES,
    category_to_conventional,
    conventional_to_category,
)


class TestCategories:
    def test_all_categories_have_conventional_equivalent(self) -> None:
        for cat, conv in CATEGORIES.items():
            assert isinstance(cat, str)
            assert isinstance(conv, str)
            assert len(cat) > 0
            assert len(conv) > 0

    def test_expected_categories_present(self) -> None:
        expected = {
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
        assert set(CATEGORIES.keys()) == expected


class TestSeverities:
    def test_all_severities_present(self) -> None:
        expected = {"architectural", "behavioral", "internal", "errata"}
        assert set(SEVERITIES.keys()) == expected

    def test_errata_has_no_semver(self) -> None:
        assert SEVERITIES["errata"] is None

    def test_architectural_is_major(self) -> None:
        assert SEVERITIES["architectural"] == "major"


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
