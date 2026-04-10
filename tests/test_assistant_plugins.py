# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for packaged assistant plugin helpers."""

import json
from pathlib import Path
from typing import cast

import pytest

from repogerbil import assistant_plugins


def test_bundled_paths_exist_in_dev_tree() -> None:
    paths = assistant_plugins.get_bundled_paths()

    assert paths.plugin_dir.name == "repogerbil"
    assert paths.plugin_dir.parent.name == "assistant_plugins"
    assert paths.codex_marketplace.name == "codex-marketplace.json"
    assert paths.claude_marketplace.name == "claude-marketplace.json"
    assert (paths.plugin_dir / ".codex-plugin" / "plugin.json").exists()
    assert (paths.plugin_dir / ".claude-plugin" / "plugin.json").exists()
    assert paths.codex_marketplace.exists()
    assert paths.claude_marketplace.exists()


def test_bundled_paths_prefer_packaged_assets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    packaged_root = tmp_path / "packaged"
    plugin_dir = packaged_root / "repogerbil"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / ".codex-plugin").mkdir()
    (plugin_dir / ".claude-plugin").mkdir()
    (packaged_root / "codex-marketplace.json").write_text("{}")
    (packaged_root / "claude-marketplace.json").write_text("{}")
    monkeypatch.setattr(assistant_plugins, "_packaged_root", lambda: packaged_root)

    paths = assistant_plugins.get_bundled_paths()

    assert paths.plugin_dir == plugin_dir
    assert paths.codex_marketplace == packaged_root / "codex-marketplace.json"
    assert paths.claude_marketplace == packaged_root / "claude-marketplace.json"


def test_export_replaces_existing_plugin_tree(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    old_file = dest / "plugins" / "repogerbil" / "stale.txt"
    old_file.parent.mkdir(parents=True)
    old_file.write_text("stale")

    assistant_plugins.export_bundled_plugin("codex", dest)

    assert not old_file.exists()


def test_export_merges_existing_codex_marketplace(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    marketplace = dest / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps(
            {
                "name": "custom-market",
                "interface": {"displayName": "Custom Market"},
                "plugins": [
                    {
                        "name": "other-plugin",
                        "source": {"source": "local", "path": "./plugins/other-plugin"},
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_USE"},
                        "category": "Utilities",
                    }
                ],
            }
        )
    )

    assistant_plugins.export_bundled_plugin("codex", dest)

    data = json.loads(marketplace.read_text())
    assert data["name"] == "custom-market"
    assert data["interface"]["displayName"] == "Custom Market"
    assert [plugin["name"] for plugin in data["plugins"]] == ["other-plugin", "repogerbil"]


def test_export_replaces_existing_codex_plugin_entry(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    marketplace = dest / ".agents" / "plugins" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps(
            {
                "name": "custom-market",
                "plugins": [
                    {
                        "name": "repogerbil",
                        "source": {"source": "local", "path": "./plugins/old-path"},
                        "policy": {"installation": "NOT_AVAILABLE", "authentication": "ON_USE"},
                        "category": "Old",
                    }
                ],
            }
        )
    )

    assistant_plugins.export_bundled_plugin("codex", dest)

    data = json.loads(marketplace.read_text())
    assert len(data["plugins"]) == 1
    assert data["plugins"][0]["name"] == "repogerbil"
    assert data["plugins"][0]["source"]["path"] == "./plugins/repogerbil"
    assert data["plugins"][0]["policy"]["installation"] == "AVAILABLE"


def test_export_merges_existing_claude_marketplace(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    marketplace = dest / "plugins" / ".claude-plugin" / "marketplace.json"
    marketplace.parent.mkdir(parents=True)
    marketplace.write_text(
        json.dumps(
            {
                "$schema": "https://example.test/schema.json",
                "name": "custom-claude-market",
                "plugins": [
                    {
                        "name": "other-plugin",
                        "description": "Other plugin",
                        "version": "1.0.0",
                        "source": "./other-plugin",
                        "category": "development",
                    }
                ],
            }
        )
    )

    assistant_plugins.export_bundled_plugin("claude", dest)

    data = json.loads(marketplace.read_text())
    assert data["name"] == "custom-claude-market"
    assert data["$schema"] == "https://example.test/schema.json"
    assert [plugin["name"] for plugin in data["plugins"]] == ["other-plugin", "repogerbil"]


def test_sync_repo_plugin_tree_creates_real_files(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    assistant_plugins.sync_repo_plugin_tree(repo_root)

    plugin_dir = repo_root / "plugins" / "repogerbil"
    codex_market = repo_root / ".agents" / "plugins" / "marketplace.json"
    claude_market = repo_root / "plugins" / ".claude-plugin" / "marketplace.json"

    assert plugin_dir.exists()
    assert plugin_dir.is_dir()
    assert not plugin_dir.is_symlink()
    assert (plugin_dir / ".codex-plugin" / "plugin.json").exists()
    assert codex_market.exists()
    assert claude_market.exists()
    assert not codex_market.is_symlink()
    assert not claude_market.is_symlink()


def test_sync_repo_plugin_tree_replaces_symlinks(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    plugin_parent = repo_root / "plugins"
    plugin_parent.mkdir()
    (tmp_path / "target-dir").mkdir()
    (plugin_parent / "repogerbil").symlink_to(tmp_path / "target-dir", target_is_directory=True)

    claude_market_parent = repo_root / "plugins" / ".claude-plugin"
    claude_market_parent.mkdir(parents=True)
    (tmp_path / "old-claude.json").write_text("{}")
    (claude_market_parent / "marketplace.json").symlink_to(tmp_path / "old-claude.json")

    codex_market_parent = repo_root / ".agents" / "plugins"
    codex_market_parent.mkdir(parents=True)
    (tmp_path / "old-codex.json").write_text("{}")
    (codex_market_parent / "marketplace.json").symlink_to(tmp_path / "old-codex.json")

    assistant_plugins.sync_repo_plugin_tree(repo_root)

    assert not (repo_root / "plugins" / "repogerbil").is_symlink()
    assert not (repo_root / "plugins" / ".claude-plugin" / "marketplace.json").is_symlink()
    assert not (repo_root / ".agents" / "plugins" / "marketplace.json").is_symlink()


def test_install_codex_defaults_to_codex_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(assistant_plugins, "_default_codex_root", lambda: tmp_path / ".codex")
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    plugin_dest = assistant_plugins.install_bundled_plugin("codex")

    assert plugin_dest == tmp_path / ".codex" / "plugins" / "repogerbil"
    assert (plugin_dest / ".codex-plugin" / "plugin.json").exists()

    marketplace = tmp_path / ".agents" / "plugins" / "marketplace.json"
    assert marketplace.exists()

    data = json.loads(marketplace.read_text())
    assert data["plugins"][0]["name"] == "repogerbil"
    assert data["plugins"][0]["source"]["path"] == str(plugin_dest)


def test_install_claude_defaults_to_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "cwd", classmethod(lambda _cls: tmp_path))

    plugin_dest = assistant_plugins.install_bundled_plugin("claude")

    assert plugin_dest == tmp_path / "plugins" / "repogerbil"
    assert (tmp_path / "plugins" / ".claude-plugin" / "marketplace.json").exists()


def test_install_rejects_unknown_target() -> None:
    with pytest.raises(ValueError, match="Unsupported target: bogus"):
        assistant_plugins.install_bundled_plugin("bogus")


def test_default_codex_root_uses_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    assert assistant_plugins._default_codex_root() == tmp_path / ".codex"


def test_rewrite_installed_marketplace_paths_preserves_non_target_entries(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin"
    data: dict[str, object] = {
        "plugins": [
            {"name": "other-plugin", "source": {"source": "local", "path": "./other"}},
            {"name": "repogerbil", "source": "not-a-mapping"},
        ]
    }

    rewritten = assistant_plugins._rewrite_installed_marketplace_paths(data, plugin_dir)
    rewritten_plugins = cast(list[object], rewritten["plugins"])
    original_plugins = cast(list[object], data["plugins"])

    assert rewritten_plugins[0] == original_plugins[0]
    assert rewritten_plugins[1] == original_plugins[1]
