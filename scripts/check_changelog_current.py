#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Verify CHANGELOG.md is current relative to VERSION and recent commits.

Checks performed:

1. Parse the most recent version header from ``CHANGELOG.md``. The header
   format is ``## <version> (YYYY-MM-DD)`` or ``## Unreleased``.
2. Compare against the ``VERSION`` file. If the head entry is ``Unreleased``
   the check passes (work in progress). Otherwise the versions must match.
3. As a soft warning, count commits in ``git log`` since the date of the
   most recent CHANGELOG entry. If above ``COMMIT_DRIFT_WARN`` the script
   emits a warning to stderr but does not fail.

Exit codes:
    0 — checks passed (warnings may be present).
    1 — checks failed (mismatch, missing files, or unparseable changelog).
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

CHANGELOG_PATH = Path("CHANGELOG.md")
VERSION_PATH = Path("VERSION")
# Threshold (commits since last CHANGELOG entry date) above which we warn.
COMMIT_DRIFT_WARN = 30

# Matches "## 0.1.1 (2026-05-24)" or "## Unreleased".
_HEADER_RE = re.compile(r"^##\s+(?P<version>\S+)(?:\s+\((?P<date>\d{4}-\d{2}-\d{2})\))?\s*$")


def _parse_latest_entry(changelog_text: str) -> tuple[str, str | None] | None:
    """Return (version, date) for the first ``## ...`` header, or None."""
    for line in changelog_text.splitlines():
        m = _HEADER_RE.match(line)
        if m:
            return m.group("version"), m.group("date")
    return None


def _commits_since(date: str) -> int | None:
    """Return number of commits authored since ``date`` (YYYY-MM-DD).

    Returns None if git is unavailable or the repo has no commits.
    """
    try:
        proc = subprocess.run(
            ["git", "log", f"--since={date}", "--pretty=%H"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return sum(1 for line in proc.stdout.splitlines() if line.strip())


def main() -> int:
    """Run checks and return 0 on success, 1 on failure."""
    if not CHANGELOG_PATH.is_file():
        sys.stderr.write(f"error: {CHANGELOG_PATH} not found\n")
        return 1
    if not VERSION_PATH.is_file():
        sys.stderr.write(f"error: {VERSION_PATH} not found\n")
        return 1

    changelog_text = CHANGELOG_PATH.read_text()
    version_text = VERSION_PATH.read_text().strip()

    if not version_text:
        sys.stderr.write(f"error: {VERSION_PATH} is empty\n")
        return 1

    latest = _parse_latest_entry(changelog_text)
    if latest is None:
        sys.stderr.write(f"error: no version entries found in {CHANGELOG_PATH}\n")
        sys.stderr.write("  expected at least one '## <version> (YYYY-MM-DD)' header\n")
        return 1

    head_version, head_date = latest

    if head_version.lower() == "unreleased":
        sys.stderr.write("ok: CHANGELOG head is 'Unreleased' (work in progress)\n")
        return 0

    if head_version != version_text:
        sys.stderr.write(f"error: VERSION ({version_text}) does not match CHANGELOG head ({head_version})\n")
        sys.stderr.write("  update CHANGELOG.md or VERSION so they agree, or add an '## Unreleased' section\n")
        return 1

    if head_date is not None:
        commits = _commits_since(head_date)
        if commits is not None and commits > COMMIT_DRIFT_WARN:
            sys.stderr.write(
                f"warning: {commits} commits since {head_date} (threshold {COMMIT_DRIFT_WARN}); "
                f"consider updating CHANGELOG.md\n"
            )

    sys.stderr.write(f"ok: CHANGELOG head {head_version} matches VERSION\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
