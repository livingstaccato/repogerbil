# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Data types (dataclasses) for git analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

_REF_RE = re.compile(r"(?:Fix(?:es)?|Clos(?:e[ds]?|ing)|Ref(?:s)?)\s+#(\d+)", re.IGNORECASE)


@dataclass(frozen=True)
class CommitInfo:
    """Immutable representation of a single git commit."""

    hash: str
    date: str
    subject: str
    files: list[str] = field(default_factory=list)
    body: str = ""
    refs: list[str] = field(default_factory=list)
    timestamp: int = 0  # unix epoch; 0 means only date available


@dataclass(frozen=True)
class DiffStats:
    """Aggregate diff statistics for a commit range."""

    commits: int
    files_changed: int
    insertions: int
    deletions: int
