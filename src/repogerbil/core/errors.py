# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Custom exceptions for repogerbil."""

from __future__ import annotations


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
