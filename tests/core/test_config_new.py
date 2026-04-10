# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for configuration logic."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from repogerbil.core.config import find_config_file, load_settings, RepoOverride, Settings


def test_load_settings_repo_override() -> None:
    """load_settings should apply per-repo overrides."""
    # Create settings with repo override
    s1_base = Settings()
    s1_base.repos["myrepo"] = RepoOverride(backfill_depth="thorough", message_depth="full")
    
    with patch("repogerbil.core.config.Settings", return_value=s1_base):
        s1 = load_settings(repo="myrepo")
        assert s1.backfill_depth == "thorough"
        assert s1.message_depth == "full"
        
    s2_base = Settings()
    s2_base.repos["other"] = RepoOverride(backfill_depth="heuristic")
    with patch("repogerbil.core.config.Settings", return_value=s2_base):
        s2 = load_settings(repo="other")
        assert s2.backfill_depth == "heuristic"
        assert s2.message_depth == "subject" # default


def test_find_config_file_fallback(tmp_path: Path) -> None:
    """find_config_file should fall back to home directory."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with patch("pathlib.Path.home", return_value=tmp_path / "home"):
            # Ensure home fallback exists
            config_dir = tmp_path / "home" / ".config" / "repogerbil"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "config.toml"
            config_file.write_text("")
            
            assert find_config_file() == config_file


def test_find_config_file_not_found(tmp_path: Path) -> None:
    """find_config_file should return None if not found."""
    with patch("pathlib.Path.cwd", return_value=tmp_path):
        with patch("pathlib.Path.home", return_value=tmp_path / "home"):
            assert find_config_file() is None


def test_find_config_file_parent(tmp_path: Path) -> None:
    """find_config_file should walk up to parent directories."""
    config_file = tmp_path / ".repogerbil.toml"
    config_file.write_text("")
    child = tmp_path / "child" / "grandchild"
    child.mkdir(parents=True)
    
    with patch("pathlib.Path.cwd", return_value=child):
        assert find_config_file() == config_file


def test_load_settings_explicit_config(tmp_path: Path) -> None:
    """load_settings should use explicit config path."""
    config = tmp_path / "custom.toml"
    config.write_text('cadence = "weekly"\n')
    
    # We must patch settings_customise_sources to actually load the file
    settings = load_settings(config_path=config)
    assert settings.cadence == "weekly"


def test_load_settings_nonexistent_config(tmp_path: Path) -> None:
    """load_settings should ignore nonexistent explicit config path."""
    config = tmp_path / "nonexistent.toml"
    settings = load_settings(config_path=config)
    assert settings.cadence == "daily"  # default


def test_load_settings_no_repo_match() -> None:
    """load_settings should skip overrides if repo is not found."""
    settings = load_settings(repo="nonexistent_repo")
    assert settings.backfill_depth == "heuristic" # default


def test_load_settings_repo_override_partial() -> None:
    """load_settings with repo having only one override."""
    s1_base = Settings()
    s1_base.repos["myrepo"] = RepoOverride(backfill_depth="thorough")
    with patch("repogerbil.core.config.Settings", return_value=s1_base):
        s1 = load_settings(repo="myrepo")
        assert s1.backfill_depth == "thorough"
        assert s1.message_depth == "subject"
        
    s2_base = Settings()
    s2_base.repos["other"] = RepoOverride(message_depth="full")
    with patch("repogerbil.core.config.Settings", return_value=s2_base):
        s2 = load_settings(repo="other")
        assert s2.backfill_depth == "heuristic"
        assert s2.message_depth == "full"
