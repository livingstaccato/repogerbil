# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for CLI entry point."""

from click.testing import CliRunner

from repogerbil.cli.main import cli


class TestCli:
    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "repogerbil" in result.output

    def test_status_with_valid_path(self, tmp_path: object) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["status", str(tmp_path)])
        assert result.exit_code == 0
        assert "Status for" in result.output

    def test_status_with_invalid_path(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "/nonexistent/path"])
        assert result.exit_code != 0
