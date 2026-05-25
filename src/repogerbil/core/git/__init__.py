# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Git analysis via subprocess — no GitPython dependency.

This package re-exports the public API so that existing imports of the form
``from repogerbil.core.git import <symbol>`` continue to work unchanged.

Underscore-prefixed names (``_run_git``, ``_attach_file_lists``) remain
importable from this package for internal callers but are intentionally
omitted from ``__all__``: the leading underscore signals "internal" and
keeps them out of ``from ... import *`` and tooling that respects ``__all__``.
"""

from __future__ import annotations

from ._commits import (
    _attach_file_lists as _attach_file_lists,
    get_active_dates,
    get_commit_for_hash,
    get_commits_for_date,
    get_commits_for_hashes,
    get_commits_for_path,
    get_hidden_ref_dates,
    get_hidden_ref_hashes,
    resolve_head_branch,
)
from ._runner import (
    _run_git as _run_git,
    parse_shortstat,
)
from ._stats import get_diff_stats
from ._trees import deduplicate_by_tree, get_commits_for_range, resolve_commit_trees
from ._types import CommitInfo, DiffStats

# ``_run_git`` and ``_attach_file_lists`` are re-exported via the explicit
# ``as`` aliases above for internal callers and tests, but intentionally
# omitted from ``__all__`` so that the leading underscore keeps signalling
# "internal" (and so ``from ... import *`` does not expose them).
__all__ = [
    "CommitInfo",
    "DiffStats",
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
