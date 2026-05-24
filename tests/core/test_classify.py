# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for commit and file classification."""

from repogerbil.core.classify import (
    Classification,
    FileClassification,
    _try_conventional_prefix,
    classify_commit,
    classify_files,
)
from repogerbil.core.config import FileRule


class TestClassifyCommitConventional:
    def test_feat(self) -> None:
        r = classify_commit("feat: add new feature")
        assert r == Classification("instantiate", "minor", False)

    def test_fix(self) -> None:
        r = classify_commit("fix: resolve crash")
        assert r == Classification("remediate", "minor", False)

    def test_refactor(self) -> None:
        r = classify_commit("refactor: extract module")
        assert r == Classification("decouple", "patch", False)

    def test_test(self) -> None:
        r = classify_commit("test: add unit tests")
        assert r == Classification("qualify", "patch", False)

    def test_docs(self) -> None:
        r = classify_commit("docs: update readme")
        assert r == Classification("specify", None, False)

    def test_perf(self) -> None:
        r = classify_commit("perf: optimize hot path")
        assert r == Classification("streamline", "minor", False)

    def test_chore(self) -> None:
        r = classify_commit("chore: update deps")
        assert r == Classification("baseline", "patch", False)

    def test_ci(self) -> None:
        r = classify_commit("ci: fix workflow")
        assert r == Classification("baseline", "patch", False)

    def test_with_scope(self) -> None:
        r = classify_commit("feat(go): add sampling")
        assert r == Classification("instantiate", "minor", False)

    def test_scaffold_prefix(self) -> None:
        r = classify_commit("scaffold(cli): create command skeleton")
        assert r == Classification("scaffold", "minor", False)

    def test_fix_harden(self) -> None:
        r = classify_commit("fix: harden auth validation")
        assert r == Classification("harden", "minor", False)

    def test_fix_margin(self) -> None:
        r = classify_commit("fix: increase timeout for slow clients")
        assert r == Classification("margin", "minor", False)

    def test_feat_interface(self) -> None:
        r = classify_commit("feat: add websocket transport")
        assert r == Classification("interface", "minor", False)

    def test_unknown_prefix(self) -> None:
        r = classify_commit("xyz: something weird")
        assert r.needs_review is True


class TestClassifyCommitBreaking:
    def test_bang_in_subject(self) -> None:
        r = classify_commit("feat!: replace old API")
        assert r.severity == "major"

    def test_breaking_change_in_body(self) -> None:
        r = classify_commit("feat: new API", body="BREAKING CHANGE: old API removed")
        assert r.severity == "major"

    def test_auto_breaking_disabled(self) -> None:
        r = classify_commit("feat!: replace old API", auto_breaking=False)
        assert r.severity == "minor"

    def test_fix_bang(self) -> None:
        r = classify_commit("fix!: breaking fix")
        assert r.severity == "major"


class TestClassifyCommitMerge:
    def test_merge_commit(self) -> None:
        r = classify_commit("Merge pull request #42")
        assert r == Classification("baseline", None, False)

    def test_merge_branch(self) -> None:
        r = classify_commit("Merge branch 'feature'")
        assert r == Classification("baseline", None, False)


class TestClassifyCommitVerb:
    def test_add(self) -> None:
        r = classify_commit("Add planet harvest pipeline")
        assert r.category == "instantiate"
        assert r.needs_review is False

    def test_added(self) -> None:
        r = classify_commit("Added new module")
        assert r.category == "instantiate"

    def test_fixed(self) -> None:
        r = classify_commit("Fixed the broken thing")
        assert r.category == "remediate"

    def test_removed(self) -> None:
        r = classify_commit("Removed dead code")
        assert r.category == "deprecate"

    def test_updated(self) -> None:
        r = classify_commit("Updated dependencies")
        assert r.category == "baseline"

    def test_cleaned_up(self) -> None:
        r = classify_commit("Cleaned up imports")
        assert r.category == "deprecate"

    def test_split(self) -> None:
        r = classify_commit("Split build into separate jobs")
        assert r.category == "decouple"

    def test_improved(self) -> None:
        r = classify_commit("Improved error handling")
        assert r.category == "streamline"

    def test_version(self) -> None:
        r = classify_commit("v0.3.22")
        assert r.category == "baseline"
        assert r.severity is None  # errata → None

    def test_hardened_verb(self) -> None:
        r = classify_commit("Harden policy parsing")
        assert r.category == "harden"

    def test_limit_verb(self) -> None:
        r = classify_commit("Limit retry attempts to 5")
        assert r.category == "margin"

    def test_fix_harden_verb(self) -> None:
        r = classify_commit("Fixed security vulnerability in auth")
        assert r.category == "harden"

    def test_fix_margin_verb(self) -> None:
        r = classify_commit("Fixed timeout handling for rate limit")
        assert r.category == "margin"


class TestClassifyCommitUnclassifiable:
    def test_wip(self) -> None:
        r = classify_commit("WIP checkpoint")
        assert r.needs_review is True
        assert r.category is None

    def test_misc(self) -> None:
        r = classify_commit("Miscellaneous changes")
        assert r.needs_review is True

    def test_empty(self) -> None:
        r = classify_commit("")
        assert r.needs_review is True


class TestClassifyFiles:
    def test_no_rules(self) -> None:
        files = ["src/main.py", "tests/test_main.py"]
        r = classify_files(files, [])
        assert r == FileClassification(
            meaningful=files,
            bulk_entries=[],
            forced_categories={},
        )

    def test_bulk_rule(self) -> None:
        rules = [FileRule(pattern="*.lock", action="bulk", category="baseline", reason="Lock file")]
        files = ["uv.lock", "go.lock", "src/main.py"]
        r = classify_files(files, rules)
        assert r.meaningful == ["src/main.py"]
        assert len(r.bulk_entries) == 1
        assert r.bulk_entries[0]["files"] == 2
        assert r.bulk_entries[0]["category"] == "baseline"

    def test_skip_rule(self) -> None:
        rules = [FileRule(pattern="*.pyc", action="skip")]
        files = ["src/main.py", "src/__pycache__/main.pyc"]
        r = classify_files(files, rules)
        assert r.meaningful == ["src/main.py"]
        assert r.bulk_entries == []

    def test_classify_rule(self) -> None:
        rules = [FileRule(pattern="tests/**", action="classify", category="qualify")]
        files = ["src/main.py", "tests/test_main.py"]
        r = classify_files(files, rules)
        assert "tests/test_main.py" in r.meaningful
        assert "src/main.py" in r.meaningful
        assert r.forced_categories == {"tests/test_main.py": "qualify"}

    def test_classify_rule_no_category(self) -> None:
        """classify action without category — file stays meaningful, no forced category."""
        rules = [FileRule(pattern="tests/*", action="classify")]
        files = ["tests/test_main.py"]
        r = classify_files(files, rules)
        assert r.meaningful == ["tests/test_main.py"]
        assert r.forced_categories == {}

    def test_first_matching_rule_wins(self) -> None:
        rules = [
            FileRule(pattern="*.lock", action="skip"),
            FileRule(pattern="*.lock", action="bulk", category="baseline"),
        ]
        files = ["uv.lock"]
        r = classify_files(files, rules)
        assert r.meaningful == []
        assert r.bulk_entries == []

    def test_bulk_default_category(self) -> None:
        rules = [FileRule(pattern="*.map", action="bulk")]
        files = ["main.js.map"]
        r = classify_files(files, rules)
        assert r.bulk_entries[0]["category"] == "baseline"

    def test_bulk_default_reason(self) -> None:
        rules = [FileRule(pattern="*.map", action="bulk")]
        files = ["main.js.map"]
        r = classify_files(files, rules)
        assert "*.map" in str(r.bulk_entries[0]["reason"])

    def test_multiple_bulk_rules(self) -> None:
        rules = [
            FileRule(pattern="*.lock", action="bulk", category="baseline", reason="Lock"),
            FileRule(pattern="mutants/**", action="bulk", category="deprecate", reason="Mutants"),
        ]
        files = ["uv.lock", "mutants/foo.py", "mutants/bar.py", "src/main.py"]
        r = classify_files(files, rules)
        assert r.meaningful == ["src/main.py"]
        assert len(r.bulk_entries) == 2
        assert r.bulk_entries[0]["files"] == 1  # lock
        assert r.bulk_entries[1]["files"] == 2  # mutants


class TestConventionalPrefixInternal:
    def test_regex_no_match(self) -> None:
        assert _try_conventional_prefix("feat(scope) no-colon", "", True) is None
        assert _try_conventional_prefix("!!!: test", "", True) is None

    def test_unknown_prefix(self) -> None:
        assert _try_conventional_prefix("unknown: message", "", True) is None

    def test_errata_severity(self) -> None:
        res = _try_conventional_prefix("docs: update", "", True)
        assert res is not None
        assert res.category == "specify"
        assert res.severity is None

    def test_behavioral_severity(self) -> None:
        res = _try_conventional_prefix("feat: message", "", True)
        assert res is not None
        assert res.severity == "minor"

    def test_breaking_flag(self) -> None:
        res = _try_conventional_prefix("feat!: message", "", True)
        assert res is not None
        assert res.severity == "major"

    def test_breaking_flag_ignored_when_disabled(self) -> None:
        res = _try_conventional_prefix("feat!: message", "", False)
        assert res is not None
        assert res.severity == "minor"
