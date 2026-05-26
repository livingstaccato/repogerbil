# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for git error handling."""

from __future__ import annotations

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


# ----------------------------------------------------------------------
# Mutant-killers: pin exact strings, attribute storage, and propagation
# in the RepogerbilError / preflight hierarchy.
# ----------------------------------------------------------------------

from repogerbil.core.errors import (  # noqa: E402
    PreflightGitLogCommandFailedError,
    PreflightGitLogError,
    PreflightInvalidRevisionOrDateError,
    PreflightNotAGitRepositoryError,
    _build_preflight_git_message,
)


class TestNotAGitRepositoryError:
    def test_path_attribute_stores_str_of_input(self) -> None:
        """`self.path = str(path)` — must equal stringified input, not None or 'None'."""
        err = NotAGitRepositoryError("/some/repo")
        assert err.path == "/some/repo"

    def test_path_attribute_strs_non_string_input(self) -> None:
        """Path-like objects must be stringified via str(), not stored as None."""
        from pathlib import Path

        p = Path("/some/repo")
        err = NotAGitRepositoryError(p)
        assert err.path == str(p)
        assert err.path != "None"


class TestBuildPreflightGitMessage:
    """Exact-string assertions for _build_preflight_git_message output."""

    def _kwargs(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "repo_path": "/r",
            "operation": "op",
            "category": "cat",
            "command": ("git", "log", "--oneline"),
            "returncode": 1,
            "stderr": "boom",
        }
        base.update(overrides)
        return base

    def test_rendered_cmd_uses_single_space_separator(self) -> None:
        """`' '.join(command)` — must use a single ASCII space, not 'XX XX' or None."""
        msg = _build_preflight_git_message(**self._kwargs())  # type: ignore[arg-type]
        assert "command: git log --oneline" in msg

    def test_exit_code_from_int_returncode(self) -> None:
        """str(returncode) — must be the stringified int, not 'None' or 'unknown'."""
        msg = _build_preflight_git_message(**self._kwargs(returncode=42))  # type: ignore[arg-type]
        assert "exit code: 42" in msg

    def test_exit_code_unknown_when_returncode_none(self) -> None:
        """When returncode is None, exit_code is exactly 'unknown' (lowercase, not 'UNKNOWN')."""
        msg = _build_preflight_git_message(**self._kwargs(returncode=None))  # type: ignore[arg-type]
        assert "exit code: unknown" in msg
        assert "UNKNOWN" not in msg
        # And it must not be 'None'.
        assert "exit code: None" not in msg

    def test_stderr_fallback_when_none(self) -> None:
        """When stderr is None, detail is exactly 'no stderr output provided'."""
        msg = _build_preflight_git_message(**self._kwargs(stderr=None))  # type: ignore[arg-type]
        assert msg.endswith(": no stderr output provided")
        assert "NO STDERR OUTPUT PROVIDED" not in msg

    def test_stderr_fallback_when_empty_after_strip(self) -> None:
        """When stderr is only whitespace, the strip()-then-fallback path is used.

        Mutmut changes the `or ""` to `or "XX XX"`; with stderr=None, the
        result of `(stderr or "")` becomes "XX XX" instead of "", and
        `.strip()` on "XX XX" yields "XX" — failing this assertion.
        """
        msg = _build_preflight_git_message(**self._kwargs(stderr="   "))  # type: ignore[arg-type]
        assert msg.endswith(": no stderr output provided")

    def test_full_message_format(self) -> None:
        """Pin the full expected message template for a representative call."""
        msg = _build_preflight_git_message(
            repo_path="/r",
            operation="op",
            category="cat",
            command=("git", "log"),
            returncode=2,
            stderr="oops",
        )
        assert msg == (
            "Preflight failed during op for '/r' (category: cat; command: git log; exit code: 2): oops"
        )


class TestPreflightGitLogError:
    def _make(self, **overrides: object) -> PreflightGitLogError:
        kwargs: dict[str, object] = {
            "repo_path": "/repo",
            "operation": "snapshot",
            "category": "my-cat",
            "command": ("git", "log"),
            "returncode": 3,
            "stderr": "bad",
        }
        kwargs.update(overrides)
        return PreflightGitLogError(**kwargs)  # type: ignore[arg-type]

    def test_repo_path_attribute_stringifies_input(self) -> None:
        err = self._make(repo_path="/some/repo")
        assert err.repo_path == "/some/repo"

    def test_repo_path_attribute_not_none_or_str_none(self) -> None:
        err = self._make(repo_path="/x")
        assert err.repo_path is not None
        assert err.repo_path != "None"

    def test_operation_attribute_preserved(self) -> None:
        err = self._make(operation="my-op")
        assert err.operation == "my-op"

    def test_category_attribute_preserved(self) -> None:
        err = self._make(category="my-cat")
        assert err.category == "my-cat"

    def test_command_attribute_is_tuple_of_input(self) -> None:
        cmd = ["git", "log", "--all"]
        err = self._make(command=cmd)
        assert err.command == ("git", "log", "--all")
        assert isinstance(err.command, tuple)

    def test_message_includes_repo_path_not_none(self) -> None:
        """If mutmut passes repo_path=None into the builder, message would say 'None'."""
        err = self._make(repo_path="/distinctive/path")
        assert "/distinctive/path" in str(err)
        assert "'None'" not in str(err)

    def test_message_includes_actual_returncode(self) -> None:
        """If mutmut passes returncode=None into the builder, message would say 'unknown'."""
        err = self._make(returncode=7)
        assert "exit code: 7" in str(err)
        assert "exit code: unknown" not in str(err)

    def test_returncode_attribute_preserved_through_super(self) -> None:
        """super().__init__ must forward returncode=returncode (not None, not dropped)."""
        err = self._make(returncode=9)
        assert err.returncode == 9

    def test_stderr_attribute_preserved_through_super(self) -> None:
        """super().__init__ must forward stderr=stderr (not None, not dropped)."""
        err = self._make(stderr="distinctive-stderr")
        assert err.stderr == "distinctive-stderr"


class TestPreflightNotAGitRepositoryError:
    def _make(self, **overrides: object) -> PreflightNotAGitRepositoryError:
        kwargs: dict[str, object] = {
            "repo_path": "/repo",
            "operation": "snapshot",
            "command": ("git", "log"),
            "returncode": 128,
            "stderr": "fatal: not a git repository",
        }
        kwargs.update(overrides)
        return PreflightNotAGitRepositoryError(**kwargs)  # type: ignore[arg-type]

    def test_operation_attribute_preserved(self) -> None:
        err = self._make(operation="my-op")
        assert err.operation == "my-op"

    def test_command_attribute_is_tuple(self) -> None:
        err = self._make(command=["git", "log", "--all"])
        assert err.command == ("git", "log", "--all")
        assert isinstance(err.command, tuple)

    def test_returncode_attribute_preserved(self) -> None:
        err = self._make(returncode=128)
        assert err.returncode == 128

    def test_stderr_attribute_preserved(self) -> None:
        err = self._make(stderr="distinctive-stderr")
        assert err.stderr == "distinctive-stderr"

    def test_path_attribute_stringifies_input(self) -> None:
        err = self._make(repo_path="/distinctive/path")
        assert err.path == "/distinctive/path"
        assert err.path != "None"

    def test_message_includes_repo_path_not_none(self) -> None:
        err = self._make(repo_path="/distinctive/path")
        assert "/distinctive/path" in str(err)
        assert "'None'" not in str(err)

    def test_message_includes_actual_returncode(self) -> None:
        err = self._make(returncode=128)
        assert "exit code: 128" in str(err)
        assert "exit code: unknown" not in str(err)

    def test_category_is_fixed_string(self) -> None:
        err = self._make()
        assert err.category == "not-a-git-repository"


class TestPreflightInvalidRevisionOrDateError:
    def test_repo_path_propagated_to_message(self) -> None:
        err = PreflightInvalidRevisionOrDateError(
            repo_path="/distinctive/path",
            operation="snapshot",
            command=("git", "log"),
            returncode=128,
            stderr="bad rev",
        )
        assert "/distinctive/path" in str(err)
        assert err.repo_path == "/distinctive/path"
        assert err.category == "invalid-revision-or-date"

    def test_returncode_propagated_to_message(self) -> None:
        err = PreflightInvalidRevisionOrDateError(
            repo_path="/r",
            operation="snapshot",
            command=("git", "log"),
            returncode=129,
            stderr="bad rev",
        )
        assert "exit code: 129" in str(err)
        assert err.returncode == 129


class TestPreflightGitLogCommandFailedError:
    def test_repo_path_propagated_to_message(self) -> None:
        err = PreflightGitLogCommandFailedError(
            repo_path="/distinctive/path",
            operation="snapshot",
            command=("git", "log"),
            returncode=1,
            stderr="fail",
        )
        assert "/distinctive/path" in str(err)
        assert err.repo_path == "/distinctive/path"
        assert err.category == "git-command-failed"

    def test_returncode_propagated_to_message(self) -> None:
        err = PreflightGitLogCommandFailedError(
            repo_path="/r",
            operation="snapshot",
            command=("git", "log"),
            returncode=5,
            stderr="fail",
        )
        assert "exit code: 5" in str(err)
        assert err.returncode == 5
