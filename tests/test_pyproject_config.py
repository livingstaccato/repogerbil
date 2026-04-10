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


def test_build_backend_uses_setuptools_and_version_file() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text())

    build_system = data["build-system"]
    project = data["project"]
    setuptools = data["tool"]["setuptools"]
    dynamic = setuptools["dynamic"]["version"]

    assert build_system["build-backend"] == "setuptools.build_meta"
    assert "setuptools>=77" in build_system["requires"]
    assert "wheel>=0.43" in build_system["requires"]
    assert project["dynamic"] == ["version"]
    assert dynamic["file"] == ["VERSION"]
    assert setuptools["include-package-data"] is True


def test_version_file_exists() -> None:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"

    assert version_file.exists()
    assert version_file.read_text().strip() != ""


def test_license_file_is_mit() -> None:
    license_file = Path(__file__).resolve().parents[1] / "LICENSE"

    assert license_file.read_text().startswith("MIT License")
