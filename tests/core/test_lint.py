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


class TestMutantKillers:
    """Targeted tests pinning exact strings, boundaries, and propagation.

    These exist to kill mutation-test survivors. They assert on exact
    error/warning message contents and on the exact propagation of the
    ``loc`` location string into nested checker errors.
    """

    # ------------------------------------------------------------------
    # lint_file: default errors_only=False and UTF-8 decoding
    # ------------------------------------------------------------------

    def test_lint_file_default_errors_only_emits_warnings(self, tmp_path: Path) -> None:
        """Default `errors_only=False` must surface warnings (mutmut: default flipped to True)."""
        data = _valid_changelog()
        del data["changes"][0]["category"]
        del data["changes"][0]["severity"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        # Call without errors_only kwarg so default value is exercised.
        result = lint_file(f)
        assert result.warnings, "default must produce warnings"

    def test_lint_directory_default_errors_only_emits_warnings(self, tmp_path: Path) -> None:
        """Default `errors_only=False` for lint_directory must surface warning-only files."""
        warning_only = _valid_changelog()
        del warning_only["changes"][0]["category"]
        _write_yaml(
            tmp_path / "repo-a" / "2026-04-08-repo-a-changelog.yaml",
            warning_only,
        )
        # Call without errors_only kwarg so default value is exercised.
        results = lint_directory(tmp_path)
        assert len(results) == 1
        assert results[0].warnings

    def test_lint_file_uses_utf8_encoding_for_non_ascii(self, tmp_path: Path) -> None:
        """UTF-8 decoding must succeed for non-ASCII content (mutmut: encoding=None)."""
        f = tmp_path / "utf8.yaml"
        # Hand-write with explicit UTF-8 bytes so a None / non-UTF8 default
        # could fail or misinterpret.
        data = _valid_changelog()
        data["title"] = "naïve café — résumé"
        f.write_bytes(yaml.dump(data, allow_unicode=True).encode("utf-8"))
        result = lint_file(f)
        assert result.ok, result.errors

    # ------------------------------------------------------------------
    # Exact error/warning message strings
    # ------------------------------------------------------------------

    def test_invalid_stats_block_exact_message(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["stats"] = "not a dict"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert "missing or invalid 'stats' block" in result.errors

    def test_bulk_must_be_list_exact_message(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert "'bulk' must be a list" in result.errors

    def test_changes_must_be_list_exact_message(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert "'changes' must be a list" in result.errors

    def test_empty_changes_warning_exact_message(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"] = []
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert "'changes' list is empty" in result.warnings

    # ------------------------------------------------------------------
    # _check_bulk: boundary `bfiles < 0` (negative is an error; zero is allowed)
    # ------------------------------------------------------------------

    def test_bulk_files_zero_is_allowed(self, tmp_path: Path) -> None:
        """`bfiles < 0` means zero must pass; mutmut: `<=0` / `<1` would reject zero."""
        data = _valid_changelog()
        data["bulk"] = [{"category": "baseline", "files": 0, "reason": "Empty"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert not any("positive integer" in e for e in result.errors), result.errors

    def test_bulk_files_negative_is_error(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["bulk"] = [{"category": "baseline", "files": -1, "reason": "Bad"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("positive integer" in e for e in result.errors)

    # ------------------------------------------------------------------
    # bloc / loc / floc / ploc propagation: errors must mention correct index
    # ------------------------------------------------------------------

    def test_bulk_bloc_includes_index_in_error(self, tmp_path: Path) -> None:
        """Mutmut sets `bloc = None`; error msg should contain `bulk[0]`."""
        data = _valid_changelog()
        data["bulk"] = ["not a dict"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("bulk[0]" in e for e in result.errors)

    def test_bulk_continue_processes_remaining_entries(self, tmp_path: Path) -> None:
        """Mutmut swaps `continue` -> `break`; the second bulk entry's error must still appear."""
        data = _valid_changelog()
        data["bulk"] = ["not a dict", {"files": 1, "reason": "ok"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        # First entry's "must be a mapping" error AND second's "missing 'category'".
        assert any("bulk[0]" in e and "must be a mapping" in e for e in result.errors)
        assert any("bulk[1]" in e and "missing 'category'" in e for e in result.errors)

    def test_changes_loc_includes_index_in_error(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"] = ["not a dict"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0]" in e for e in result.errors)

    def test_changes_continue_processes_remaining_entries(self, tmp_path: Path) -> None:
        """Mutmut swaps `continue` -> `break`; second change's missing title must still appear."""
        data = _valid_changelog()
        data["changes"] = ["not a dict", {"category": "instantiate"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0]" in e and "must be a mapping" in e for e in result.errors)
        assert any("changes[1]" in e and "missing 'title'" in e for e in result.errors)

    def test_section_stats_error_includes_loc_prefix(self, tmp_path: Path) -> None:
        """_check_changes must pass loc to _check_section_stats (mutmut: loc=None)."""
        data = _valid_changelog()
        data["changes"][0]["stats"] = "not a dict"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].stats: must be a mapping" in e for e in result.errors)

    def test_impact_error_includes_loc_prefix(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["impact"] = "not a dict"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].impact: must be a mapping" in e for e in result.errors)

    def test_category_severity_error_includes_loc_prefix(self, tmp_path: Path) -> None:
        """_check_changes must pass loc to _check_category_severity (mutmut: loc=None)."""
        data = _valid_changelog()
        data["changes"][0]["category"] = "bogus"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0]: unknown category 'bogus'" in e for e in result.errors)

    def test_files_error_includes_loc_prefix(self, tmp_path: Path) -> None:
        """_check_changes must pass loc to _check_files (mutmut: loc=None)."""
        data = _valid_changelog()
        data["changes"][0]["files"] = "not a list"
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0]: 'files' must be a list" in e for e in result.errors)

    def test_files_errors_only_propagates(self, tmp_path: Path) -> None:
        """_check_changes must pass errors_only to _check_files (mutmut: errors_only=None).

        With errors_only=True, the file-summary-missing warning must be suppressed.
        Note Python truthiness: None is falsy → `not None` is True so the warning
        would still be emitted by the mutant; we test errors_only=True path to pin
        the value rather than just truthiness.
        """
        data = _valid_changelog()
        data["changes"][0]["files"] = [{"path": "a.py"}]  # missing summary
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f, errors_only=True)
        assert not any("missing 'summary'" in w for w in result.warnings)

    def test_points_loc_passed_through(self, tmp_path: Path) -> None:
        """_check_changes must pass loc to _check_points (mutmut: loc=None)."""
        data = _valid_changelog()
        data["changes"][0]["points"] = [42]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].points[0]: must be a string or mapping" in e for e in result.errors)

    # ------------------------------------------------------------------
    # _check_section_stats: tuple identity, val-None semantics
    # ------------------------------------------------------------------

    def test_section_stats_all_three_fields_validated(self, tmp_path: Path) -> None:
        """Each of files_changed/insertions/deletions must be checked individually."""
        data = _valid_changelog()
        data["changes"][0]["stats"] = {
            "files_changed": "bad1",
            "insertions": "bad2",
            "deletions": "bad3",
        }
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        joined = "\n".join(result.errors)
        assert "changes[0].stats.files_changed: must be an integer" in joined
        assert "changes[0].stats.insertions: must be an integer" in joined
        assert "changes[0].stats.deletions: must be an integer" in joined

    def test_section_stats_missing_keys_do_not_error(self, tmp_path: Path) -> None:
        """When a stats field is absent (val is None), no error (mutmut: `is None` swap)."""
        data = _valid_changelog()
        data["changes"][0]["stats"] = {}  # all three keys absent
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert not any(".stats." in e for e in result.errors), result.errors

    # ------------------------------------------------------------------
    # _check_impact: all three field strings must be exact
    # ------------------------------------------------------------------

    def test_impact_all_three_fields_validated(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["impact"] = {
            "files": "x",
            "packages": "y",
            "repos": "z",
        }
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        joined = "\n".join(result.errors)
        assert "changes[0].impact.files: must be a list" in joined
        assert "changes[0].impact.packages: must be a list" in joined
        assert "changes[0].impact.repos: must be a list" in joined

    # ------------------------------------------------------------------
    # _check_files: floc includes filename index
    # ------------------------------------------------------------------

    def test_file_entry_floc_includes_index(self, tmp_path: Path) -> None:
        """floc must be `<loc>.files[<fi>]` (mutmut: floc=None)."""
        data = _valid_changelog()
        data["changes"][0]["files"] = [{"path": "a.py"}, {"summary": "no path"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].files[1]: missing 'path'" in e for e in result.errors)

    # ------------------------------------------------------------------
    # _check_points: ploc, continue→break, sub-call loc propagation
    # ------------------------------------------------------------------

    def test_points_ploc_includes_index(self, tmp_path: Path) -> None:
        data = _valid_changelog()
        data["changes"][0]["points"] = ["plain"]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].points[0]: plain string" in w for w in result.warnings)

    def test_points_after_string_continue_processes_rest(self, tmp_path: Path) -> None:
        """A string point must not stop processing of later bad points (mutmut: continue→break)."""
        data = _valid_changelog()
        data["changes"][0]["points"] = ["plain", 42]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        # Second point (42) must still produce its own error.
        assert any("changes[0].points[1]: must be a string or mapping" in e for e in result.errors)

    def test_points_after_invalid_type_continue_processes_rest(self, tmp_path: Path) -> None:
        """A non-dict non-str point must not stop processing (mutmut: continue→break)."""
        data = _valid_changelog()
        data["changes"][0]["points"] = [42, {"category": "bogus"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        # Both errors should appear: index 0 type error AND index 1 unknown category + missing text.
        assert any("changes[0].points[0]: must be a string or mapping" in e for e in result.errors)
        assert any("changes[0].points[1]: unknown category 'bogus'" in e for e in result.errors)

    def test_point_files_error_includes_ploc(self, tmp_path: Path) -> None:
        """_check_point_files receives ploc (mutmut: ploc=None)."""
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "files": "not a list"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].points[0]: 'files' must be a list" in e for e in result.errors)

    def test_point_category_severity_error_includes_ploc(self, tmp_path: Path) -> None:
        """_check_point_category_severity receives ploc (mutmut: ploc=None)."""
        data = _valid_changelog()
        data["changes"][0]["points"] = [{"text": "ok", "category": "bogus"}]
        f = _write_yaml(tmp_path / "test.yaml", data)
        result = lint_file(f)
        assert any("changes[0].points[0]: unknown category 'bogus'" in e for e in result.errors)

    # ------------------------------------------------------------------
    # lint_directory: continue→break in two distinct places
    # ------------------------------------------------------------------

    def test_lint_directory_continues_past_hidden_dir(self, tmp_path: Path) -> None:
        """A hidden dir must not stop processing of later dirs (mutmut: continue→break)."""
        bad = _valid_changelog()
        del bad["title"]
        # `.hidden` sorts before `repo-z`; original continues past hidden then
        # processes repo-z. Mutant break would exit the whole loop early.
        _write_yaml(
            tmp_path / ".hidden" / "2026-04-08-hidden-changelog.yaml",
            _valid_changelog(),
        )
        _write_yaml(
            tmp_path / "repo-z" / "2026-04-08-repo-z-changelog.yaml",
            bad,
        )
        results = lint_directory(tmp_path)
        assert len(results) == 1
        assert results[0].path.parent.name == "repo-z"

    def test_lint_directory_continues_past_filtered_repo(self, tmp_path: Path) -> None:
        """A filtered-out repo must not stop processing of later dirs (mutmut: continue→break)."""
        bad = _valid_changelog()
        del bad["title"]
        # `repo-a` (filtered out) sorts before `repo-b` (the one we want).
        _write_yaml(
            tmp_path / "repo-a" / "2026-04-08-repo-a-changelog.yaml",
            _valid_changelog(),
        )
        _write_yaml(
            tmp_path / "repo-b" / "2026-04-08-repo-b-changelog.yaml",
            bad,
        )
        results = lint_directory(tmp_path, repos=["repo-b"])
        assert len(results) == 1
        assert results[0].path.parent.name == "repo-b"
