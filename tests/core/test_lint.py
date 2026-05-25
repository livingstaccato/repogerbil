# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for changelog YAML linting."""

from pathlib import Path
from typing import Any

import yaml

from repogerbil.core.lint import LintResult, lint_directory, lint_file


def _write_yaml(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data))
    return path


def _valid_changelog() -> dict[str, Any]:
    return {
        "date": "2026-04-08",
        "repo": "myrepo",
        "title": "Test changelog",
        "summary": "A test",
        "stats": {"files_changed": 3, "insertions": 10, "deletions": 5},
        "changes": [
            {
                "title": "Feature A",
                "category": "instantiate",
                "severity": "behavioral",
                "files": [{"path": "a.py", "summary": "Added feature"}],
                "points": [
                    {
                        "text": "Added new feature",
                        "category": "instantiate",
                        "severity": "behavioral",
                        "files": ["a.py"],
                    }
                ],
            }
        ],
    }


class TestLintFile:
    def test_valid_file(self, tmp_path: Path) -> None:
        f = _write_yaml(tmp_path / "test.yaml", _valid_changelog())
        result = lint_file(f)
        assert result.ok
        assert result.errors == []
        assert result.warnings == []

    def test_yaml_parse_error(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.yaml"
        f.write_text("  bad:\nyaml: [unclosed")
        result = lint_file(f)
        assert not result.ok
        assert any("YAML parse error" in e for e in result.errors)

    def test_not_a_mapping(self, tmp_path: Path) -> None:
        f = _write_yaml(tmp_path / "test.yaml", ["a", "list"])
        result = lint_file(f)
        assert not result.ok
        assert "top-level value is not a mapping" in result.errors

    def test_missing_required_fields(self, tmp_path: Path) -> None:
        f = _write_yaml(tmp_path / "test.yaml", {"stats": {}, "changes": []})
        result = lint_file(f)
        assert any("'date'" in e for e in result.errors)
        assert any("'repo'" in e for e in result.errors)
        assert any("'title'" in e for e in result.errors)
        assert any("'summary'" in e for e in result.errors)

    def test_missing_stats_fields(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["stats"] = {"files_changed": 3}
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'insertions'" in e for e in result.errors)
        assert any("'deletions'" in e for e in result.errors)

    def test_invalid_stats_block(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["stats"] = "not a dict"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("invalid 'stats'" in e for e in result.errors)

    def test_unknown_category(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["category"] = "bogus"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("unknown category 'bogus'" in e for e in result.errors)

    def test_unknown_severity(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["severity"] = "bogus"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("unknown severity 'bogus'" in e for e in result.errors)

    def test_missing_category_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        del data["changes"][0]["category"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok  # warning, not error
        assert any("'category' not set" in w for w in result.warnings)

    def test_missing_severity_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        del data["changes"][0]["severity"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok
        assert any("'severity' not set" in w for w in result.warnings)

    def test_errors_only_suppresses_warnings(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        del data["changes"][0]["category"]
        del data["changes"][0]["severity"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f, errors_only=True)
        assert result.ok
        assert result.warnings == []

    def test_change_not_a_mapping(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"] = ["not a dict"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be a mapping" in e for e in result.errors)

    def test_changes_not_a_list(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'changes' must be a list" in e for e in result.errors)

    def test_empty_changes_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"] = []
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("empty" in w for w in result.warnings)

    def test_missing_change_title(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        del data["changes"][0]["title"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("missing 'title'" in e for e in result.errors)

    def test_files_not_a_list(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["files"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'files' must be a list" in e for e in result.errors)

    def test_file_entry_not_mapping(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["files"] = ["just a string"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be a mapping" in e for e in result.errors)

    def test_file_entry_missing_path(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["files"] = [{"summary": "no path"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("missing 'path'" in e for e in result.errors)

    def test_file_entry_missing_summary_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["files"] = [{"path": "a.py"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("missing 'summary'" in w for w in result.warnings)

    def test_points_not_a_list(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'points' must be a list" in e for e in result.errors)

    def test_point_plain_string_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = ["just a string"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("plain string" in w for w in result.warnings)

    def test_point_not_string_or_mapping(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [42]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be a string or mapping" in e for e in result.errors)

    def test_point_missing_text(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"category": "instantiate"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("missing 'text'" in e for e in result.errors)

    def test_point_files_not_list(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "files": "not a list"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'files' must be a list" in e for e in result.errors)

    def test_point_file_not_string(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "files": [42]}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be a string" in e for e in result.errors)

    def test_point_unknown_category(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "category": "bogus"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("unknown category 'bogus'" in e for e in result.errors)

    def test_point_unknown_severity(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "severity": "bogus"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("unknown severity 'bogus'" in e for e in result.errors)

    def test_point_missing_category_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "severity": "internal"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'category' not set" in w for w in result.warnings)

    def test_point_missing_severity_warning(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "category": "instantiate"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'severity' not set" in w for w in result.warnings)

    def test_point_errors_only_suppresses_point_warnings(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = [
            "plain string point",
            {"text": "no cat or sev"},
        ]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f, errors_only=True)
        assert result.ok
        assert result.warnings == []

    def test_bulk_valid(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = [{"category": "baseline", "files": 5, "reason": "Lock files"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok

    def test_bulk_not_a_list(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("'bulk' must be a list" in e for e in result.errors)

    def test_bulk_entry_not_mapping(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = ["not a dict"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be a mapping" in e for e in result.errors)

    def test_bulk_missing_category(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = [{"files": 5, "reason": "test"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("missing 'category'" in e for e in result.errors)

    def test_bulk_unknown_category(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = [{"category": "bogus", "files": 5, "reason": "test"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("unknown category" in e for e in result.errors)

    def test_bulk_bad_files(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = [{"category": "baseline", "files": "not int", "reason": "test"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("positive integer" in e for e in result.errors)

    def test_bulk_missing_reason(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = [{"category": "baseline", "files": 5}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("missing 'reason'" in e for e in result.errors)

    def test_section_stats_valid(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["stats"] = {"files_changed": 2, "insertions": 5, "deletions": 3}
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok

    def test_section_stats_not_mapping(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["stats"] = "not a dict"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("stats: must be a mapping" in e for e in result.errors)

    def test_section_stats_bad_value(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["stats"] = {"files_changed": "bad"}
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be an integer" in e for e in result.errors)

    def test_impact_valid(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["impact"] = {"files": ["a.py"], "packages": ["pkg"]}
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok

    def test_impact_not_mapping(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["impact"] = "not a dict"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("impact: must be a mapping" in e for e in result.errors)

    def test_impact_bad_field(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["impact"] = {"files": "not a list"}
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("must be a list" in e for e in result.errors)

    def test_alt_label_categories_accepted(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["category"] = "rectify"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok

    def test_alt_label_severities_accepted(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["severity"] = "mechanical"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok


class TestLintDirectory:
    def test_finds_files_across_repos(self, tmp_path: Path) -> None:
        # Valid file
        _write_yaml(
            tmp_path / "repo-a" / "2026-04-08-repo-a-changelog.yaml",
            _valid_changelog(),
        )
        # Bad file
        bad = _valid_changelog()
        bad["repo"] = "repo-b"
        del bad["title"]
        _write_yaml(
            tmp_path / "repo-b" / "2026-04-08-repo-b-changelog.yaml",
            bad,
        )
        results = lint_directory(tmp_path)
        assert len(results) == 1
        assert results[0].path.parent.name == "repo-b"

    def test_filter_by_repo(self, tmp_path: Path) -> None:
        _write_yaml(
            tmp_path / "repo-a" / "2026-04-08-repo-a-changelog.yaml",
            _valid_changelog(),
        )
        bad = _valid_changelog()
        del bad["title"]
        _write_yaml(
            tmp_path / "repo-b" / "2026-04-08-repo-b-changelog.yaml",
            bad,
        )
        results = lint_directory(tmp_path, repos=["repo-a"])
        assert results == []

    def test_skips_hidden_dirs(self, tmp_path: Path) -> None:
        bad = _valid_changelog()
        del bad["title"]
        _write_yaml(
            tmp_path / ".hidden" / "2026-04-08-hidden-changelog.yaml",
            bad,
        )
        results = lint_directory(tmp_path)
        assert results == []

    def test_warning_only_files_are_returned_by_default(self, tmp_path: Path) -> None:
        warning_only = _valid_changelog()
        del warning_only["changes"][0]["category"]
        _write_yaml(
            tmp_path / "repo-a" / "2026-04-08-repo-a-changelog.yaml",
            warning_only,
        )

        results = lint_directory(tmp_path)

        assert len(results) == 1
        assert results[0].errors == []
        assert any("'category' not set" in warning for warning in results[0].warnings)

    def test_errors_only_excludes_warning_only_files(self, tmp_path: Path) -> None:
        warning_only = _valid_changelog()
        del warning_only["changes"][0]["category"]
        _write_yaml(
            tmp_path / "repo-a" / "2026-04-08-repo-a-changelog.yaml",
            warning_only,
        )

        results = lint_directory(tmp_path, errors_only=True)

        assert results == []


class TestLintResult:
    def test_ok_property(self) -> None:
        r = LintResult(path=Path("test.yaml"))
        assert r.ok
        r.errors.append("bad")
        assert not r.ok


class TestValidCategoriesDerivation:
    """``VALID_CATEGORIES`` must follow the vocabulary, not drift from it."""

    def test_module_attribute_includes_all_vocabulary_categories(self) -> None:
        from repogerbil.core.lint import VALID_CATEGORIES
        from repogerbil.core.vocabulary import CATEGORIES

        for key in CATEGORIES:
            assert key in VALID_CATEGORIES, key

    def test_module_attribute_includes_legacy_synonyms(self) -> None:
        from repogerbil.core.lint import _CATEGORY_SYNONYMS, VALID_CATEGORIES

        for synonym in _CATEGORY_SYNONYMS:
            assert synonym in VALID_CATEGORIES, synonym

    def test_new_vocabulary_category_picked_up_by_valid_categories(self, monkeypatch: "Any") -> None:
        """Adding a vocabulary entry at runtime appears in :func:`_valid_categories`.

        This pins the derivation: ``_valid_categories()`` reads vocabulary live,
        so adding a category in ``vocabulary._default_categories`` does not
        require a parallel edit in lint.py.
        """
        from repogerbil.core import lint, vocabulary as vocab_mod
        from repogerbil.core.vocabulary import CategoryDefinition

        custom = dict(vocab_mod.CATEGORIES)
        custom["choreograph"] = CategoryDefinition(label="choreograph", conventional="chore")
        monkeypatch.setattr(lint, "CATEGORIES", custom)

        assert "choreograph" in lint._valid_categories()

    def test_new_vocabulary_category_accepted_by_linter(self, monkeypatch: "Any", tmp_path: Path) -> None:
        """A custom category added to vocabulary lints cleanly without code edit."""
        from repogerbil.core import lint, vocabulary as vocab_mod
        from repogerbil.core.vocabulary import CategoryDefinition

        custom = dict(vocab_mod.CATEGORIES)
        custom["choreograph"] = CategoryDefinition(label="choreograph", conventional="chore")
        monkeypatch.setattr(lint, "CATEGORIES", custom)

        data = _valid_changelog()
        data["changes"][0]["category"] = "choreograph"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert result.ok, result.errors
