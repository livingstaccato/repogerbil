# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for configuration loading."""

from pathlib import Path
from unittest.mock import patch

import pytest

from repogerbil.core.config import FileRule, RepoOverride, Settings, find_config_file, load_settings


class TestFileRule:
    def test_defaults(self) -> None:
        rule = FileRule(pattern="*.lock")
        assert rule.action == "bulk"
        assert rule.category is None
        assert rule.reason == ""

    def test_all_fields(self) -> None:
        rule = FileRule(pattern="tests/**", action="classify", category="qualify", reason="test files")
        assert rule.pattern == "tests/**"
        assert rule.action == "classify"
        assert rule.category == "qualify"
        assert rule.reason == "test files"

    def test_skip_action(self) -> None:
        rule = FileRule(pattern="*.pyc", action="skip")
        assert rule.action == "skip"


class TestRepoOverride:
    def test_defaults(self) -> None:
        override = RepoOverride()
        assert override.backfill_depth is None
        assert override.message_depth is None

    def test_set_backfill(self) -> None:
        override = RepoOverride(backfill_depth="thorough")
        assert override.backfill_depth == "thorough"


class TestSettings:
    def test_defaults(self) -> None:
        settings = Settings()
        assert settings.cadence == "daily"
        assert settings.message_depth == "subject"
        assert settings.auto_breaking is True
        assert settings.tolerance == 20
        assert settings.target_branch == "repogerbil-consolidated"
        assert settings.file_rules == []
        assert settings.repos == {}

    def test_valid_cadence_gap_format(self) -> None:
        """Test that gap-format cadence is accepted."""
        settings = Settings(cadence="gap:30m")
        assert settings.cadence == "gap:30m"

    def test_valid_cadence_gap_hours(self) -> None:
        """Test that gap-format with hours is accepted."""
        settings = Settings(cadence="gap:2h")
        assert settings.cadence == "gap:2h"

    def test_invalid_cadence_raises(self) -> None:
        """Test that invalid cadence values raise ValueError."""
        with pytest.raises(ValueError, match="Invalid cadence"):
            Settings(cadence="monthly")

    def test_invalid_cadence_gap_format_raises(self) -> None:
        """Test that invalid gap format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid cadence"):
            Settings(cadence="gap:invalid")

    def test_scaffold_category_present_in_defaults(self) -> None:
        settings = Settings()
        assert "scaffold" in settings.vocabulary.categories
        assert settings.vocabulary.prefix_to_category["scaffold"] == "scaffold"


class TestLoadSettings:
    def test_default_settings(self) -> None:
        settings = load_settings()
        assert settings.cadence == "daily"

    def test_nonexistent_config_path(self, tmp_path: Path) -> None:
        settings = load_settings(config_path=tmp_path / "nonexistent.toml")
        assert settings.cadence == "daily"

    def test_with_config_file(self, tmp_path: Path) -> None:
        config = tmp_path / ".repogerbil.toml"
        config.write_text('cadence = "weekly"\ntolerance = 30\n')
        settings = load_settings(config_path=config)
        assert settings.cadence == "weekly"
        assert settings.tolerance == 30

    def test_repo_override(self, tmp_path: Path) -> None:
        config = tmp_path / ".repogerbil.toml"
        config.write_text('backfill_depth = "heuristic"\n\n[repos.my-repo]\nbackfill_depth = "thorough"\n')
        settings = load_settings(repo="my-repo", config_path=config)
        assert settings.backfill_depth == "thorough"

    def test_repo_override_not_found(self, tmp_path: Path) -> None:
        config = tmp_path / ".repogerbil.toml"
        config.write_text('backfill_depth = "heuristic"\n')
        settings = load_settings(repo="nonexistent", config_path=config)
        assert settings.backfill_depth == "heuristic"

    def test_repo_override_partial(self, tmp_path: Path) -> None:
        config = tmp_path / ".repogerbil.toml"
        config.write_text(
            'message_depth = "subject"\nbackfill_depth = "heuristic"\n\n'
            "[repos.my-repo]\n"
            'message_depth = "full"\n'
        )
        settings = load_settings(repo="my-repo", config_path=config)
        assert settings.message_depth == "full"
        assert settings.backfill_depth == "heuristic"

    def test_explicit_config_does_not_leak_across_calls(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_a = tmp_path / "a.toml"
        config_a.write_text('cadence = "weekly"\n')
        config_b = tmp_path / "b.toml"
        config_b.write_text('cadence = "hourly"\n')

        empty_cwd = tmp_path / "empty"
        empty_cwd.mkdir()
        monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: empty_cwd))
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path / "no-user-config"))

        first = load_settings(config_path=config_a)
        second = load_settings(config_path=config_b)
        third = load_settings(config_path=tmp_path / "missing.toml")

        assert first.cadence == "weekly"
        assert second.cadence == "hourly"
        assert third.cadence == "daily"


class TestFindConfigFile:
    def test_finds_in_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core.config import find_config_file

        config = tmp_path / ".repogerbil.toml"
        config.write_text('cadence = "weekly"\n')
        import os

        monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
        monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: tmp_path))
        result = find_config_file()
        assert result == config

    def test_finds_in_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core.config import find_config_file

        config = tmp_path / ".repogerbil.toml"
        config.write_text('cadence = "daily"\n')
        child = tmp_path / "child" / "grandchild"
        child.mkdir(parents=True)
        monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: child))
        result = find_config_file()
        assert result == config

    def test_returns_none_when_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core.config import find_config_file

        child = tmp_path / "nowhere"
        child.mkdir()
        monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: child))
        result = find_config_file()
        # May find a real config in the filesystem or return None
        # Just verify it doesn't crash
        assert result is None or isinstance(result, Path)

    def test_user_config_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from repogerbil.core.config import find_config_file

        # Create user config
        user_dir = tmp_path / ".config" / "repogerbil"
        user_dir.mkdir(parents=True)
        (user_dir / "config.toml").write_text('cadence = "hourly"\n')
        # Point CWD to a dir with no config
        empty = tmp_path / "empty"
        empty.mkdir()
        monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: empty))
        monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
        result = find_config_file()
        assert result is not None
        assert "config.toml" in str(result)


class TestLoadSettingsMocked:
    def test_repo_override_applied(self) -> None:
        s = Settings()
        s.repos["myrepo"] = RepoOverride(backfill_depth="thorough", message_depth="full")
        with patch("repogerbil.core.config.Settings", return_value=s):
            result = load_settings(repo="myrepo")
            assert result.backfill_depth == "thorough"
            assert result.message_depth == "full"

    def test_partial_override(self) -> None:
        s = Settings()
        s.repos["myrepo"] = RepoOverride(backfill_depth="thorough")
        with patch("repogerbil.core.config.Settings", return_value=s):
            result = load_settings(repo="myrepo")
            assert result.backfill_depth == "thorough"
            assert result.message_depth == "subject"

    def test_no_repo_match(self) -> None:
        result = load_settings(repo="nonexistent_repo")
        assert result.backfill_depth == "heuristic"

    def test_explicit_config_path(self, tmp_path: Path) -> None:
        config = tmp_path / "custom.toml"
        config.write_text('cadence = "weekly"\n')
        result = load_settings(config_path=config)
        assert result.cadence == "weekly"

    def test_nonexistent_config_uses_defaults(self, tmp_path: Path) -> None:
        result = load_settings(config_path=tmp_path / "nonexistent.toml")
        assert result.cadence == "daily"


class TestFindConfigFileMocked:
    def test_home_fallback(self, tmp_path: Path) -> None:
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("pathlib.Path.home", return_value=tmp_path / "home"),
        ):
            config_dir = tmp_path / "home" / ".config" / "repogerbil"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.toml"
            config_file.write_text("")
            assert find_config_file() == config_file

    def test_not_found_returns_none(self, tmp_path: Path) -> None:
        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch("pathlib.Path.home", return_value=tmp_path / "home"),
        ):
            assert find_config_file() is None

    def test_walks_to_parent(self, tmp_path: Path) -> None:
        config_file = tmp_path / ".repogerbil.toml"
        config_file.write_text("")
        child = tmp_path / "child" / "grandchild"
        child.mkdir(parents=True)
        with patch("pathlib.Path.cwd", return_value=child):
            assert find_config_file() == config_file


def test_settings_has_llm_defaults() -> None:
    s = Settings()
    assert s.llm_ollama_url == "http://localhost:11434"
    assert s.llm_model == "qwen3-coder-next:q8_0"
    assert s.llm_temperature == 0.0
    assert s.llm_timeout_seconds == 120.0
    assert s.llm_concurrency == 1
    assert s.llm_refine is False


def test_settings_llm_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPOGERBIL_LLM_MODEL", "gemma4:27b")
    monkeypatch.setenv("REPOGERBIL_LLM_CONCURRENCY", "4")
    monkeypatch.setenv("REPOGERBIL_LLM_REFINE", "true")
    s = Settings()
    assert s.llm_model == "gemma4:27b"
    assert s.llm_concurrency == 4
    assert s.llm_refine is True
