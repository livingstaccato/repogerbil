# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for project configuration."""

from pathlib import Path
import tomllib


def test_mutmut_copies_assistant_plugins_package() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    mutmut = data["tool"]["mutmut"]

    assert "src/repogerbil/assistant_plugins/" in mutmut.get("also_copy", [])
    assert "src/repogerbil/core/" in mutmut.get("also_copy", [])
    assert "src/repogerbil/cli/commands/" in mutmut.get("also_copy", [])


def test_mutmut_only_mutates_covered_lines() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    mutmut = data["tool"]["mutmut"]

    assert mutmut.get("mutate_only_covered_lines") is True
