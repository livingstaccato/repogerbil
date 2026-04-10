# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for new classification logic."""

from __future__ import annotations

from repogerbil.core.classify import classify_commit, classify_files
from repogerbil.core.config import FileRule


def test_classify_verb_heuristics() -> None:
    """classify_commit should use leading-verb heuristics."""
    # instantiate
    assert classify_commit("Add new feature").category == "instantiate"
    assert classify_commit("Added new feature").category == "instantiate"
    assert classify_commit("Adds new feature").category == "instantiate"

    # remediate -> harden
    assert classify_commit("Fix security vulnerability").category == "harden"

    # remediate -> margin
    assert classify_commit("Fix timeout issue").category == "margin"

    # remediate (plain)
    assert classify_commit("Fix small bug").category == "remediate"

    # deprecate
    assert classify_commit("Remove old code").category == "deprecate"

    # decouple
    assert classify_commit("Refactor some module").category == "decouple"

    # baseline
    assert classify_commit("Update dependencies").category == "baseline"


def test_classify_special_heuristics() -> None:
    """classify_commit should handle special heuristics for security/timeout/etc."""
    # fix + security -> harden
    assert classify_commit("fix: secur stuff").category == "harden"

    # fix + timeout -> margin
    assert classify_commit("fix: timeout issue").category == "margin"

    # fix (plain)
    assert classify_commit("fix: just a bug").category == "remediate"

    # feat + API -> interface
    assert classify_commit("feat: API endpoint").category == "interface"


def test_classify_conventional_edge_cases() -> None:
    """_try_conventional_prefix edge cases."""
    from repogerbil.core.classify import _try_conventional_prefix

    # 1. regex doesn't match at all (missing colon)
    assert _try_conventional_prefix("feat(scope) no-colon", "", True) is None
    assert _try_conventional_prefix("!!!: test", "", True) is None

    # 2. regex matches but category unknown
    assert _try_conventional_prefix("unknown: message", "", True) is None

    # 3. prefix in _PREFIX_SEVERITY (maps severity)
    res3 = _try_conventional_prefix("docs: update", "", True)
    assert res3 is not None
    assert res3.category == "specify"
    assert res3.severity is None  # errata maps to None

    # 4. prefix NOT in _PREFIX_SEVERITY
    res4 = _try_conventional_prefix("feat: message", "", True)
    assert res4 is not None
    assert res4.category == "instantiate"
    assert res4.severity == "minor"  # behavioral maps to minor

    # 5. Breaking change
    res5 = _try_conventional_prefix("feat!: message", "", True)
    assert res5 is not None
    assert res5.severity == "major"

    # 6. Breaking change but auto_breaking=False
    res6 = _try_conventional_prefix("feat!: message", "", False)
    assert res6 is not None
    assert res6.severity == "minor"


def test_classify_commit_body_breaking() -> None:
    """classify_commit with breaking change in body."""
    res = classify_commit("feat: message", body="BREAKING CHANGE: logic")
    assert res.severity == "major"


def test_classify_commit_no_match() -> None:
    """classify_commit with no prefix and no verb match."""
    res = classify_commit("random message with no verb")
    assert res.needs_review is True


def test_merge_commit() -> None:
    """classify_commit should identify merge commits."""
    res = classify_commit("Merge branch 'main' into dev")
    assert res.category == "baseline"
    assert res.severity is None


def test_classify_files_actions() -> None:
    """classify_files should handle skip, bulk, and classify actions."""
    rules = [
        FileRule(pattern="*.pyc", action="skip"),
        FileRule(pattern="*.lock", action="bulk", category="baseline", reason="Locks"),
        FileRule(pattern="docs/*.md", action="classify", category="specify"),
    ]

    files = ["src/main.py", "src/main.pyc", "uv.lock", "docs/README.md"]
    res = classify_files(files, rules)

    assert "src/main.py" in res.meaningful
    assert "src/main.pyc" not in res.meaningful
    assert "uv.lock" not in res.meaningful
    assert "docs/README.md" in res.meaningful

    assert res.forced_categories["docs/README.md"] == "specify"
    assert len(res.bulk_entries) == 1
    assert res.bulk_entries[0]["files"] == 1
    assert res.bulk_entries[0]["reason"] == "Locks"

    # Default bulk category/reason
    rules2 = [FileRule(pattern="*", action="bulk")]
    res2 = classify_files(["test.txt"], rules2)
    assert res2.bulk_entries[0]["category"] == "baseline"
    assert res2.bulk_entries[0]["reason"] == "Files matching *"

    # Classify with no category rule
    rules3 = [FileRule(pattern="*", action="classify")]
    res3 = classify_files(["test.txt"], rules3)
    assert res3.forced_categories == {}

    # No match
    res4 = classify_files(["other.txt"], [])
    assert "other.txt" in res4.meaningful
