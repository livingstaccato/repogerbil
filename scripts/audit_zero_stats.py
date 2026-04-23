#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Audit changelog YAMLs for zero-stat records that shouldn't be zero.

Identifies the blast radius of the single-commit ``get_diff_stats`` bug that
returned ``files_changed=0, insertions=0, deletions=0`` whenever a date's
provenance resolution produced exactly one commit (``first_hash == last_hash``).

A changelog is suspicious when ``stats.commits > 0`` but all three of
``files_changed``, ``insertions``, and ``deletions`` are zero. Empty-diff
commits exist in the wild (merge commits, reverts, ``--allow-empty``), so this
is a heuristic — review the output before running ``repogerbil fix-stats``.

Usage:
    python scripts/audit_zero_stats.py <changelog_dir> [<changelog_dir> ...]

Exits 0 if no suspicious files found, 1 otherwise (so it can gate CI if wanted).
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import yaml


def _is_suspicious(stats: dict[str, Any]) -> bool:
    return (
        int(stats.get("commits", 0)) > 0
        and int(stats.get("files_changed", 0)) == 0
        and int(stats.get("insertions", 0)) == 0
        and int(stats.get("deletions", 0)) == 0
    )


def audit_dir(changelog_dir: Path) -> list[Path]:
    """Return the list of suspicious changelog YAMLs under ``changelog_dir``."""
    suspicious: list[Path] = []
    for yaml_file in sorted(changelog_dir.rglob("*-changelog.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text())
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict):
            continue
        stats = data.get("stats")
        if isinstance(stats, dict) and _is_suspicious(stats):
            suspicious.append(yaml_file)
    return suspicious


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    dirs = [Path(a) for a in argv[1:]]
    missing = [d for d in dirs if not d.is_dir()]
    if missing:
        for d in missing:
            print(f"error: not a directory: {d}", file=sys.stderr)
        return 2

    total = 0
    for d in dirs:
        hits = audit_dir(d)
        total += len(hits)
        if hits:
            print(f"\n{d} ({len(hits)} suspicious):")
            for p in hits:
                print(f"  {p.relative_to(d)}")

    if total == 0:
        print("No suspicious zero-stat changelogs found.")
        return 0

    print(
        f"\n{total} changelog(s) may have been affected by the single-commit stats bug.",
        file=sys.stderr,
    )
    print(
        "To repair: `repogerbil fix-stats <changelog_dir> <repo_path>` "
        "(re-runs get_diff_stats, which now handles single-commit ranges correctly).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
