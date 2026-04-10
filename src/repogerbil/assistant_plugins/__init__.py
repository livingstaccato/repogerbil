# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Helpers for bundled assistant plugin assets."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
import json
from pathlib import Path
import shutil

PLUGIN_NAME = "repogerbil"


@dataclass(frozen=True)
class BundledPluginPaths:
    """Filesystem paths for the bundled plugin and marketplace metadata."""

    plugin_dir: Path
    codex_marketplace: Path
    claude_marketplace: Path


def get_bundled_paths() -> BundledPluginPaths:
    """Return the canonical package-local plugin paths."""
    packaged_root = _packaged_root()
    return BundledPluginPaths(
        plugin_dir=packaged_root / PLUGIN_NAME,
        codex_marketplace=packaged_root / "codex-marketplace.json",
        claude_marketplace=packaged_root / "claude-marketplace.json",
    )


def export_bundled_plugin(target: str, dest_root: Path) -> Path:
    """Export bundled plugin files for Codex or Claude into a destination root."""
    paths = get_bundled_paths()
    plugin_dest = dest_root / "plugins" / PLUGIN_NAME
    _copy_tree(paths.plugin_dir, plugin_dest)

    if target == "codex":
        marketplace_dest = dest_root / ".agents" / "plugins" / "marketplace.json"
        _merge_marketplace(paths.codex_marketplace, marketplace_dest)
    elif target == "claude":
        marketplace_dest = dest_root / "plugins" / ".claude-plugin" / "marketplace.json"
        _merge_marketplace(paths.claude_marketplace, marketplace_dest)
    else:  # pragma: no cover - click constrains this
        msg = f"Unsupported target: {target}"
        raise ValueError(msg)

    return plugin_dest


def install_bundled_plugin(target: str, root: Path | None = None) -> Path:
    """Install bundled plugin files into a home-like root."""
    if root is not None:
        return export_bundled_plugin(target, root)

    if target == "codex":
        return _install_codex_plugin()
    if target == "claude":
        return export_bundled_plugin(target, Path.cwd())

    msg = f"Unsupported target: {target}"
    raise ValueError(msg)


def sync_repo_plugin_tree(repo_root: Path) -> None:
    """Sync repo-root plugin files from the canonical package-local source."""
    paths = get_bundled_paths()
    _copy_tree(paths.plugin_dir, repo_root / "plugins" / PLUGIN_NAME)
    _write_json(paths.codex_marketplace, repo_root / ".agents" / "plugins" / "marketplace.json")
    _write_json(paths.claude_marketplace, repo_root / "plugins" / ".claude-plugin" / "marketplace.json")


def _install_codex_plugin() -> Path:
    """Install the Codex plugin into Codex home and pin marketplace to that absolute path."""
    paths = get_bundled_paths()
    codex_root = _default_codex_root()
    plugin_dest = codex_root / "plugins" / PLUGIN_NAME
    _copy_tree(paths.plugin_dir, plugin_dest)
    _merge_marketplace(
        paths.codex_marketplace,
        Path.home() / ".agents" / "plugins" / "marketplace.json",
        plugin_dest,
    )
    return plugin_dest


def _default_codex_root() -> Path:
    """Return the default Codex home directory."""
    return Path.home() / ".codex"


def _packaged_root() -> Path:
    """Return the package-local assistant plugin directory."""
    return Path(str(files("repogerbil.assistant_plugins")))


def _copy_tree(source: Path, dest: Path) -> None:
    """Copy a directory tree, replacing an existing destination."""
    if dest.is_symlink():
        dest.unlink()
    elif dest.exists():
        shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)


def _write_json(source: Path, dest: Path) -> None:
    """Copy a JSON file, replacing any existing file or symlink."""
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def _merge_marketplace(source: Path, dest: Path, installed_plugin_dir: Path | None = None) -> None:
    """Merge a bundled marketplace entry into an existing marketplace file."""
    bundled = json.loads(source.read_text())
    if installed_plugin_dir is not None:
        bundled = _rewrite_installed_marketplace_paths(bundled, installed_plugin_dir)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(bundled, indent=2) + "\n")
        return

    existing = json.loads(dest.read_text())
    merged = dict(existing)
    merged_plugins = _merge_plugin_lists(existing.get("plugins", []), bundled.get("plugins", []))
    merged["plugins"] = merged_plugins
    dest.write_text(json.dumps(merged, indent=2) + "\n")


def _merge_plugin_lists(existing: list[object], bundled: list[object]) -> list[object]:
    """Return existing plugins with bundled plugin entries inserted or replaced by name."""
    existing_by_name = {
        plugin["name"]: plugin for plugin in existing if isinstance(plugin, dict) and "name" in plugin
    }
    merged_names = [plugin["name"] for plugin in existing if isinstance(plugin, dict) and "name" in plugin]

    for plugin in bundled:
        if not isinstance(plugin, dict) or "name" not in plugin:  # pragma: no cover - bundled shape is fixed
            continue
        name = plugin["name"]
        existing_by_name[name] = plugin
        if name not in merged_names:
            merged_names.append(name)

    return [existing_by_name[name] for name in merged_names]


def _rewrite_installed_marketplace_paths(data: dict[str, object], plugin_dir: Path) -> dict[str, object]:
    """Rewrite bundled local plugin entries to the concrete installed plugin path."""
    rewritten = dict(data)
    plugins = []
    existing_plugins = data.get("plugins", [])
    if not isinstance(existing_plugins, list):  # pragma: no cover - bundled shape is fixed
        existing_plugins = []
    for plugin in existing_plugins:
        if isinstance(plugin, dict) and plugin.get("name") == PLUGIN_NAME:
            plugin_copy = dict(plugin)
            source = plugin_copy.get("source")
            if isinstance(source, dict):
                source_copy = dict(source)
                source_copy["path"] = str(plugin_dir)
                plugin_copy["source"] = source_copy
            plugins.append(plugin_copy)
        else:
            plugins.append(plugin)
    rewritten["plugins"] = plugins
    return rewritten
