# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for plugin export and install commands."""

from pathlib import Path

from click.testing import CliRunner

from repogerbil.cli.main import cli


class TestPluginExport:
    def test_export_codex_layout(self, tmp_path: Path) -> None:
        dest = tmp_path / "codex-home"
        result = CliRunner().invoke(cli, ["plugin", "export", "--target", "codex", "--dest", str(dest)])

        assert result.exit_code == 0
        assert (dest / "plugins" / "repogerbil" / ".codex-plugin" / "plugin.json").exists()
        assert (dest / "plugins" / "repogerbil" / "skills" / "gerbil" / "SKILL.md").exists()
        assert (dest / ".agents" / "plugins" / "marketplace.json").exists()

    def test_export_claude_layout(self, tmp_path: Path) -> None:
        dest = tmp_path / "claude-home"
        result = CliRunner().invoke(cli, ["plugin", "export", "--target", "claude", "--dest", str(dest)])

        assert result.exit_code == 0
        assert (dest / "plugins" / "repogerbil" / ".claude-plugin" / "plugin.json").exists()
        assert (dest / "plugins" / "repogerbil" / "agents" / "analyzer" / "AGENT.md").exists()
        assert (dest / "plugins" / ".claude-plugin" / "marketplace.json").exists()


class TestPluginInstall:
    def test_install_uses_root_flag(self, tmp_path: Path) -> None:
        root = tmp_path / "custom-home"
        result = CliRunner().invoke(cli, ["plugin", "install", "--target", "codex", "--root", str(root)])

        assert result.exit_code == 0
        assert (root / "plugins" / "repogerbil" / ".codex-plugin" / "plugin.json").exists()
        assert (root / ".agents" / "plugins" / "marketplace.json").exists()
