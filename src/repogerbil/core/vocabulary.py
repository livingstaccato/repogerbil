# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Changelog vocabulary definitions — categories, severities, and mappings."""

from __future__ import annotations

CATEGORIES: dict[str, str] = {
    "instantiate": "feat",
    "remediate": "fix",
    "decouple": "refactor",
    "deprecate": "remove",
    "interface": "feat",
    "specify": "docs",
    "qualify": "test",
    "margin": "fix",
    "harden": "fix",
    "streamline": "perf",
    "baseline": "chore",
}

SEVERITIES: dict[str, str | None] = {
    "architectural": "major",
    "behavioral": "minor",
    "internal": "patch",
    "errata": None,
}

PREFIX_TO_CATEGORY: dict[str, str] = {
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


def category_to_conventional(category: str) -> str:
    """Map a vocabulary category to its conventional commit prefix."""
    return CATEGORIES.get(category, "chore")


def conventional_to_category(prefix: str) -> str | None:
    """Map a conventional commit prefix to a vocabulary category."""
    return PREFIX_TO_CATEGORY.get(prefix.lower())
