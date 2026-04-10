# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for git error handling."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from repogerbil.core.errors import GitCommandError, NotAGitRepositoryError
from repogerbil.core.git import _run_git


def test_run_git_success() -> None:
    """_run_git should return stdout on success."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="success\n")
        assert _run_git(".", "status") == "success\n"


def test_run_git_not_a_repo() -> None:
    """_run_git should raise NotAGitRepositoryError when not in a repo."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=128, stderr="fatal: not a git repository (or any of the parent directories): .git\n"
        )
        with pytest.raises(NotAGitRepositoryError) as excinfo:
            _run_git(".", "status")
        assert "." in str(excinfo.value)


def test_run_git_generic_error() -> None:
    """_run_git should raise GitCommandError on generic git failure."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: some error\n")
        with pytest.raises(GitCommandError) as excinfo:
            _run_git(".", "status")
        assert "some error" in str(excinfo.value)
        assert excinfo.value.returncode == 1
        assert excinfo.value.stderr == "fatal: some error"
