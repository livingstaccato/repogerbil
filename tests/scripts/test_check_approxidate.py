# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for ``scripts/check_approxidate.py``.

The script is a CI regression gate, so we lock in the exact patterns it
recognizes as pinned versus unpinned. The bug we are guarding against is
silent — a regression here means flaky tests reappear days later — so the
test suite has to be strict about both directions: real violations must be
flagged, and the established-safe patterns must not produce false positives.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "check_approxidate.py"


def _load_module() -> types.ModuleType:
    """Load ``scripts/check_approxidate.py`` as an importable module.

    We mirror ``tests/scripts/test_run_mutation_test.py`` here: the
    ``scripts/`` directory is not on ``sys.path`` and we deliberately do
    not add it, so we load the file directly via ``importlib.util``.
    """
    spec = importlib.util.spec_from_file_location("check_approxidate_under_test", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_MOD = _load_module()


class TestScanFileFlagsViolations:
    """Synthetic bad files must be flagged."""

    def test_bare_fstring_since_is_flagged(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_text('args = [f"--since={day}"]\n')
        violations = _MOD._scan_file(bad)
        assert len(violations) == 1
        path, line_no, _ = violations[0]
        assert path == bad
        assert line_no == 1

    def test_bare_fstring_until_is_flagged(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.py"
        bad.write_text('args = [f"--until={day}"]\n')
        violations = _MOD._scan_file(bad)
        assert len(violations) == 1

    def test_unpinned_variable_assignment_is_flagged(self, tmp_path: Path) -> None:
        # ``since`` is assigned a bare ISO date, then used in a flag — the
        # check must trace the variable and flag the call site.
        bad = tmp_path / "bad.py"
        bad.write_text(
            'since = day.isoformat()\ncmd = [f"--since={since}"]\n',
        )
        violations = _MOD._scan_file(bad)
        assert len(violations) == 1


class TestScanFileAcceptsPinnedCode:
    """Established-safe patterns must not produce false positives."""

    def test_inline_pin_since_is_ok(self, tmp_path: Path) -> None:
        good = tmp_path / "good.py"
        good.write_text('cmd = [f"--since={day}T00:00:00"]\n')
        assert _MOD._scan_file(good) == []

    def test_inline_pin_until_is_ok(self, tmp_path: Path) -> None:
        good = tmp_path / "good.py"
        good.write_text('cmd = [f"--until={day}T23:59:59"]\n')
        assert _MOD._scan_file(good) == []

    def test_pin_iso_date_helper_is_ok(self, tmp_path: Path) -> None:
        good = tmp_path / "good.py"
        good.write_text('cmd = [f"--since={_pin_iso_date(value, end_of_day=False)}"]\n')
        assert _MOD._scan_file(good) == []

    def test_pinned_variable_assignment_is_ok(self, tmp_path: Path) -> None:
        # Distant assignment with pin evidence on the RHS — the call site
        # is many lines later, mirroring the multi_snapshot.py pattern.
        good = tmp_path / "good.py"
        good.write_text(
            'since = f"{day.isoformat()}T00:00:00"\n' + "\n" * 50 + 'cmd = [f"--since={since}"]\n',
        )
        assert _MOD._scan_file(good) == []

    def test_docstring_mention_is_ignored(self, tmp_path: Path) -> None:
        # Plain ``--since=`` references in prose (no f-string brace) cannot
        # affect git behavior and must not produce false positives.
        good = tmp_path / "good.py"
        good.write_text('"""Use git --since= to filter by date."""\n')
        assert _MOD._scan_file(good) == []


class TestMainExitCode:
    """End-to-end: main() against the real repo tree."""

    def test_repo_currently_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The repository tree under src/repogerbil/ must currently pass.
        # If a regression slips in, this test fails loudly alongside CI.
        repo_root = Path(__file__).resolve().parents[2]
        monkeypatch.chdir(repo_root)
        assert _MOD.main() == 0
