#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Verify that the source plugin tree and packaged mirror stay in sync.

`plugins/repogerbil/` is the canonical plugin tree used by Claude Code and
Codex when loaded from a checkout. `src/repogerbil/assistant_plugins/repogerbil/`
is the mirror shipped inside the installed wheel via package-data. If the two
drift, only the packaged copy is distributed and users see stale behavior.
"""

from __future__ import annotations

from pathlib import Path
import sys

SOURCE = Path("plugins/repogerbil")
MIRROR = Path("src/repogerbil/assistant_plugins/repogerbil")


def _collect(root: Path) -> dict[Path, bytes]:
    """Return a map of relative path -> file bytes for every file under root."""
    files: dict[Path, bytes] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        files[path.relative_to(root)] = path.read_bytes()
    return files


def main() -> int:
    """Return 1 if the trees differ, 0 if they match."""
    if not SOURCE.is_dir():
        print(f"error: source tree not found: {SOURCE}", file=sys.stderr)
        return 1
    if not MIRROR.is_dir():
        print(f"error: mirror tree not found: {MIRROR}", file=sys.stderr)
        return 1

    src_files = _collect(SOURCE)
    mir_files = _collect(MIRROR)

    src_only = sorted(src_files.keys() - mir_files.keys())
    mir_only = sorted(mir_files.keys() - src_files.keys())
    differing = sorted(p for p in src_files.keys() & mir_files.keys() if src_files[p] != mir_files[p])

    if not (src_only or mir_only or differing):
        return 0

    print("plugin trees are out of sync:", file=sys.stderr)
    print(f"  source: {SOURCE}", file=sys.stderr)
    print(f"  mirror: {MIRROR}", file=sys.stderr)
    if src_only:
        print("\nonly in source (missing from mirror):", file=sys.stderr)
        for p in src_only:
            print(f"  {p}", file=sys.stderr)
    if mir_only:
        print("\nonly in mirror (missing from source):", file=sys.stderr)
        for p in mir_only:
            print(f"  {p}", file=sys.stderr)
    if differing:
        print("\ncontent differs:", file=sys.stderr)
        for p in differing:
            print(f"  {p}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
