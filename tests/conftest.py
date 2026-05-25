# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Shared pytest fixtures for repogerbil tests.

``tests/core/test_provenance.py`` was migrated to ``make_git_repo`` as the
canonical multi-repo example, and ``tests/core/test_git.py`` renamed its
local fixture to ``repo_with_commits`` so it no longer shadows the shared
``git_repo`` below.

TODO: many test files still ship their own ``_init_repo`` / ``_init_*_repo``
helpers — see the list emitted by::

    grep -rln "_init.*repo" tests/

(roughly 8+ files at last count: ``tests/core/test_audit.py``,
``tests/core/test_catch_up.py``, ``tests/core/test_enrich.py``,
``tests/core/test_realign.py``, ``tests/core/test_snapshot.py``,
``tests/core/test_tree_filter.py``, ``tests/cli/test_catch_up_cmd.py``,
``tests/cli/test_distill_cmds.py``, ...). Each defines a subtly different
helper (e.g. some omit ``commit.gpgsign=false``, which has previously caused
signed-commit hooks to break tests on developer machines). The migration
strategy is to swap each for the ``git_repo`` / ``make_git_repo`` fixtures
below in follow-up passes. A future CI gate idea: a ``make`` target that
``grep``s for the ``_init.*repo`` pattern and fails if any new helper is
introduced after the migration completes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
import subprocess

import pytest


def _run_git(args: list[str], cwd: Path) -> None:
    """Run a git command, raising on failure with captured stderr for context."""
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


def _init_test_repo(parent: Path, name: str) -> Path:
    """Initialise ``parent/name`` as an empty repo with the canonical test defaults.

    Shared body between ``git_repo`` (single-repo) and ``make_git_repo``
    (factory) so they cannot drift apart.
    """
    repo = parent / name
    repo.mkdir()
    # init.defaultBranch is set on the local config *before* the initial ref is
    # written — pass it via -c so it actually applies to this ``git init``.
    subprocess.run(
        ["git", "-c", "init.defaultBranch=main", "init"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    _run_git(["config", "user.email", "test@example.com"], repo)
    _run_git(["config", "user.name", "Test User"], repo)
    _run_git(["config", "commit.gpgsign", "false"], repo)
    _run_git(["config", "init.defaultBranch", "main"], repo)
    return repo


@pytest.fixture
def git_repo(tmp_path: Path) -> Iterator[Path]:
    """Create an empty git repo with sensible test defaults and yield its path.

    Defaults applied to the repo's local config:

    - ``user.email`` / ``user.name`` — required for ``git commit``
    - ``commit.gpgsign=false`` — avoid prompting for signing keys in CI / dev
    - ``init.defaultBranch=main`` — stable default branch name across git versions

    The repo is initialised inside ``tmp_path/"repo"`` so callers retain
    ``tmp_path`` for other scratch files alongside the working tree.

    For tests that need *multiple* repos in the same ``tmp_path``, use the
    sibling ``make_git_repo`` factory fixture instead of (or in addition to)
    this one.
    """
    yield _init_test_repo(tmp_path, "repo")


@pytest.fixture
def make_git_repo(tmp_path: Path) -> Callable[[str], Path]:
    """Factory: return a callable that initialises additional named repos.

    Returns a callable ``(name: str = "repo") -> Path`` that creates a fresh
    git repo at ``tmp_path/<name>`` with the same defaults as ``git_repo``.
    Use this when a single test needs more than one repo side-by-side
    (e.g. provenance tests that pair a primary repo with a backup source).

    Note: if both ``git_repo`` and ``make_git_repo("repo")`` are requested in
    the same test, the second call will collide on ``tmp_path/"repo"`` — pass
    a distinct name to the factory in that case.
    """

    def _make(name: str = "repo") -> Path:
        return _init_test_repo(tmp_path, name)

    return _make
