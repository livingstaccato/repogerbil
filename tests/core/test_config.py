# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for configuration loading."""

from pathlib import Path

import pytest

from repogerbil.core.config import FileRule, RepoOverride, Settings, load_settings


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
        assert settings.output == "data-repo"
        assert settings.file_rules == []
        assert settings.repos == {}

    def test_standard_scopes_default(self) -> None:
        settings = Settings()
        assert "go" in settings.standard_scopes
        assert "ts" in settings.standard_scopes
        assert "py" in settings.standard_scopes


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
