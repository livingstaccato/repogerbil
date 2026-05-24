# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Custom exceptions for repogerbil."""

from __future__ import annotations

from collections.abc import Sequence


class RepogerbilError(Exception):
    """Base exception for all repogerbil errors."""


class GitCommandError(RepogerbilError):
    """Raised when a git command fails."""

    def __init__(self, message: str, returncode: int | None = None, stderr: str | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


class NotAGitRepositoryError(RepogerbilError):
    """Raised when an operation is attempted outside a git repository."""

    def __init__(self, path: str | object) -> None:
        super().__init__(f"Not a git repository: {path}")
        self.path = str(path)


def _build_preflight_git_message(
    *,
    repo_path: str | object,
    operation: str,
    category: str,
    command: Sequence[str],
    returncode: int | None,
    stderr: str | None,
) -> str:
    rendered_cmd = " ".join(command)
    exit_code = str(returncode) if returncode is not None else "unknown"
    stderr_detail = (stderr or "").strip() or "no stderr output provided"
    return (
        f"Preflight failed during {operation} for '{repo_path}' "
        f"(category: {category}; command: {rendered_cmd}; exit code: {exit_code}): {stderr_detail}"
    )


class PreflightGitLogError(GitCommandError):
    """Raised when preflight cannot collect file history via git log."""

    def __init__(
        self,
        *,
        repo_path: str | object,
        operation: str,
        category: str,
        command: Sequence[str],
        returncode: int | None,
        stderr: str | None,
    ) -> None:
        self.repo_path = str(repo_path)
        self.operation = operation
        self.category = category
        self.command = tuple(command)
        message = _build_preflight_git_message(
            repo_path=repo_path,
            operation=operation,
            category=category,
            command=command,
            returncode=returncode,
            stderr=stderr,
        )
        super().__init__(message, returncode=returncode, stderr=stderr)


class PreflightNotAGitRepositoryError(NotAGitRepositoryError):
    """Raised when preflight runs against a path that is not a git repository."""

    def __init__(
        self,
        *,
        repo_path: str | object,
        operation: str,
        command: Sequence[str],
        returncode: int | None,
        stderr: str | None,
    ) -> None:
        self.operation = operation
        self.category = "not-a-git-repository"
        self.command = tuple(command)
        self.returncode = returncode
        self.stderr = stderr
        self.path = str(repo_path)
        message = _build_preflight_git_message(
            repo_path=repo_path,
            operation=operation,
            category=self.category,
            command=command,
            returncode=returncode,
            stderr=stderr,
        )
        Exception.__init__(self, message)


class PreflightInvalidRevisionOrDateError(PreflightGitLogError):
    """Raised when preflight receives an invalid revision or date range filter."""

    def __init__(
        self,
        *,
        repo_path: str | object,
        operation: str,
        command: Sequence[str],
        returncode: int | None,
        stderr: str | None,
    ) -> None:
        super().__init__(
            repo_path=repo_path,
            operation=operation,
            category="invalid-revision-or-date",
            command=command,
            returncode=returncode,
            stderr=stderr,
        )


class PreflightGitLogCommandFailedError(PreflightGitLogError):
    """Raised when git log fails in preflight for reasons other than known categories."""

    def __init__(
        self,
        *,
        repo_path: str | object,
        operation: str,
        command: Sequence[str],
        returncode: int | None,
        stderr: str | None,
    ) -> None:
        super().__init__(
            repo_path=repo_path,
            operation=operation,
            category="git-command-failed",
            command=command,
            returncode=returncode,
            stderr=stderr,
        )
