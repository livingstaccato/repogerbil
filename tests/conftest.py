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
import os
from pathlib import Path
import subprocess

import pytest


@pytest.fixture(scope="session", autouse=True)
def _isolated_git_global_config(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Provide a sandboxed git global config for the whole test session.

    Several tests (and the production snapshot pipeline they exercise) call
    ``git commit-tree`` / ``git commit`` without setting per-repo identity
    first. Modern git refuses to auto-detect ``user.email``/``user.name``,
    so on CI runners or containers without a global identity these tests
    fail with ``fatal: unable to auto-detect email address``.

    We point git at a session-scoped ``GIT_CONFIG_GLOBAL`` file with a
    test identity so:
    - Tests run identically on developer machines, GitHub-hosted runners,
      and act containers — no workflow-side ``git config --global`` needed.
    - The developer's real ``~/.gitconfig`` is never touched (signing keys,
      aliases, user identity all preserved).

    Requires git >= 2.32 for ``GIT_CONFIG_GLOBAL`` support.
    """
    gitconfig_dir = tmp_path_factory.mktemp("git_global")
    gitconfig_file = gitconfig_dir / ".gitconfig"
    gitconfig_file.write_text(
        "[user]\n"
        "\temail = tests@repogerbil.test\n"
        "\tname = repogerbil tests\n"
        "[init]\n"
        "\tdefaultBranch = main\n"
        "[commit]\n"
        "\tgpgsign = false\n",
        encoding="utf-8",
    )
    previous = os.environ.get("GIT_CONFIG_GLOBAL")
    os.environ["GIT_CONFIG_GLOBAL"] = str(gitconfig_file)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GIT_CONFIG_GLOBAL", None)
        else:
            os.environ["GIT_CONFIG_GLOBAL"] = previous


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
