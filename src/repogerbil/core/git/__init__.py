# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git analysis via subprocess — no GitPython dependency.

This package re-exports the full public API so that existing imports of the
form ``from repogerbil.core.git import <symbol>`` continue to work unchanged.
"""

from __future__ import annotations

from ._commits import (
    _attach_file_lists,
    get_active_dates,
    get_commit_for_hash,
    get_commits_for_date,
    get_commits_for_hashes,
    get_commits_for_path,
    get_hidden_ref_dates,
    get_hidden_ref_hashes,
    resolve_head_branch,
)
from ._runner import _run_git, parse_shortstat
from ._stats import get_diff_stats
from ._trees import deduplicate_by_tree, get_commits_for_range, resolve_commit_trees
from ._types import CommitInfo, DiffStats

__all__ = [
    "CommitInfo",
    "DiffStats",
    "_attach_file_lists",
    "_run_git",
    "deduplicate_by_tree",
    "get_active_dates",
    "get_commit_for_hash",
    "get_commits_for_date",
    "get_commits_for_hashes",
    "get_commits_for_path",
    "get_commits_for_range",
    "get_diff_stats",
    "get_hidden_ref_dates",
    "get_hidden_ref_hashes",
    "parse_shortstat",
    "resolve_commit_trees",
    "resolve_head_branch",
]
