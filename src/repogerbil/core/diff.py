# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Diff reading and parsing for thorough changelog analysis."""

from __future__ import annotations

from pathlib import Path
import re

from repogerbil.core.git import _run_git

SKIP_PATTERNS = re.compile(
    r"(package-lock\.json|yarn\.lock|uv\.lock|go\.sum|Cargo\.lock"
    r"|\.pyc$|__pycache__|node_modules|\.min\.js$|\.map$"
    r"|\.DAT$|\.LOG$|\.dat$|\.log$)",
)


def get_diff_content(
    repo_path: str | Path,
    first_hash: str,
    last_hash: str,
    max_files: int = 50,
    max_lines_per_file: int = 200,
) -> dict[str, str]:
    """Read actual diff content grouped by file path.

    Returns {filepath: diff_text} with size limits applied.
    Skips lock files, generated code, and binary files.
    """
    raw = _run_git(
        repo_path,
        "diff",
        f"{first_hash}..{last_hash}",
        "--no-color",
        timeout=120,
    )

    return parse_diff(raw, max_files=max_files, max_lines_per_file=max_lines_per_file)


def parse_diff(
    raw: str,
    max_files: int = 50,
    max_lines_per_file: int = 200,
) -> dict[str, str]:
    """Parse raw git diff output into per-file chunks.

    Args:
        raw: Raw git diff output.
        max_files: Maximum number of files to include.
        max_lines_per_file: Maximum lines per file.

    Returns:
        {filepath: diff_text} with size limits applied.
    """
    diffs: dict[str, list[str]] = {}
    current_file: str | None = None
    line_count = 0

    for line in raw.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/", 1)
            current_file = parts[1] if len(parts) == 2 else None
            line_count = 0
            if current_file and SKIP_PATTERNS.search(current_file):
                current_file = None
            if current_file and len(diffs) >= max_files:
                current_file = None
            if current_file:
                diffs[current_file] = []
        elif current_file is not None:
            if line_count < max_lines_per_file:
                diffs[current_file].append(line)
                line_count += 1

    return {f: "\n".join(lines) for f, lines in diffs.items() if lines}
