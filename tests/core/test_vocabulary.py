# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for vocabulary definitions and mappings."""

from repogerbil.core.config import CategoryDefinition
from repogerbil.core.vocabulary import (
    CATEGORIES,
    PREFIX_TO_CATEGORY,
    SEVERITIES,
    category_to_conventional,
    conventional_to_category,
    get_root_categories,
    get_root_category,
)

# Standard conventional-prefix root nodes
_ROOTS = {"feat", "fix", "refactor", "test", "perf", "docs", "chore"}
# Semantic subcategories
_SUBCATEGORIES = {
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
        assert set(CATEGORIES.keys()) >= _ROOTS, "All conventional prefix roots must be present"
        assert set(CATEGORIES.keys()) >= _SUBCATEGORIES, "All semantic subcategories must be present"

    def test_roots_have_no_parents(self) -> None:
        for root in _ROOTS:
            assert CATEGORIES[root].parents == [], f"Root '{root}' must have no parents"

    def test_subcategories_have_parents(self) -> None:
        for sub in _SUBCATEGORIES:
            assert len(CATEGORIES[sub].parents) >= 1, f"Subcategory '{sub}' must have at least one parent"

    def test_interface_has_multiple_parents(self) -> None:
        """interface is a DAG node with parents from both feat and docs subtrees."""
        parents = CATEGORIES["interface"].parents
        assert len(parents) >= 2, "interface should have multiple parents"
        assert "instantiate" in parents
        assert "specify" in parents


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


class TestGetRootCategories:
    def test_root_node_returns_itself(self) -> None:
        assert get_root_categories("feat") == {"feat"}
        assert get_root_categories("fix") == {"fix"}

    def test_single_parent_chain(self) -> None:
        # instantiate → feat (root)
        assert get_root_categories("instantiate") == {"feat"}
        # harden → remediate → fix (root)
        assert get_root_categories("harden") == {"fix"}

    def test_dag_multiple_roots(self) -> None:
        # interface → [instantiate, specify] → [feat, docs]
        roots = get_root_categories("interface")
        assert roots == {"feat", "docs"}

    def test_unknown_category_returns_itself(self) -> None:
        assert get_root_categories("nonexistent") == {"nonexistent"}


class TestGetRootCategory:
    def test_shim_returns_string(self) -> None:
        result = get_root_category("instantiate")
        assert isinstance(result, str)
        assert result in {"feat"}

    def test_shim_dag_returns_one_root(self) -> None:
        result = get_root_category("interface")
        assert result in {"feat", "docs"}
