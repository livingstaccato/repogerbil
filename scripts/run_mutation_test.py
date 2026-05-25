#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Run mutmut for CI with a JSON + text summary written to disk.

Designed for nightly / manual workflow runs — keeps stdout structured so the
GitHub Actions log stays readable, and emits ``mutation-summary.txt`` plus
``mutation-results.json`` artifacts for inspection.

Mutmut configuration (paths_to_mutate, do_not_mutate, runner, etc.) lives in
``[tool.mutmut]`` in ``pyproject.toml`` — this script only controls invocation
ergonomics and the post-run summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

DEFAULT_MAX_CHILDREN = 8
DEFAULT_TIMEOUT_FACTOR = 2.0
SUMMARY_TXT = Path("mutation-summary.txt")
SUMMARY_JSON = Path("mutation-results.json")


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` capturing stdout+stderr as text without raising on non-zero."""
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _parse_results(text: str) -> dict[str, int]:
    """Parse mutmut ``results`` output into a status -> count map.

    mutmut's ``results`` subcommand prints one section per status with mutant
    ids listed underneath. We only need the counts here, so we tally any line
    that looks like a mutant id under each header.
    """
    counts: dict[str, int] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            current = None
            continue
        # Status headers from mutmut look like "killed:", "survived:", etc.
        if line.endswith(":") and " " not in line[:-1]:
            current = line[:-1]
            counts.setdefault(current, 0)
            continue
        if current is not None:
            counts[current] = counts.get(current, 0) + 1
    return counts


def _write_summary(
    run_proc: subprocess.CompletedProcess[str], results_proc: subprocess.CompletedProcess[str]
) -> dict[str, int]:
    """Persist text + JSON summaries and return the parsed counts."""
    counts = _parse_results(results_proc.stdout)
    SUMMARY_JSON.write_text(json.dumps({"counts": counts, "run_returncode": run_proc.returncode}, indent=2))
    lines = [
        "mutmut summary",
        "==============",
        f"run exit code: {run_proc.returncode}",
        "",
        "results by status:",
    ]
    if counts:
        for status, count in sorted(counts.items()):
            lines.append(f"  {status}: {count}")
    else:
        lines.append("  (no results — check mutmut output below)")
    lines.extend(["", "raw `mutmut results` output:", "", results_proc.stdout.rstrip() or "(empty)"])
    SUMMARY_TXT.write_text("\n".join(lines) + "\n")
    return counts


def main(argv: list[str] | None = None) -> int:
    """Drive mutmut run + results and write CI artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-children", type=int, default=DEFAULT_MAX_CHILDREN)
    parser.add_argument(
        "--fail-on-survivors",
        action="store_true",
        help="Exit non-zero if any surviving mutants are reported.",
    )
    args = parser.parse_args(argv)

    run_cmd = [
        "uv",
        "run",
        "mutmut",
        "run",
        "--max-children",
        str(args.max_children),
    ]
    sys.stderr.write(f"running: {' '.join(run_cmd)}\n")
    run_proc = _run(run_cmd)
    sys.stdout.write(run_proc.stdout)
    sys.stderr.write(run_proc.stderr)

    results_proc = _run(["uv", "run", "mutmut", "results"])
    sys.stdout.write(results_proc.stdout)
    sys.stderr.write(results_proc.stderr)

    counts = _write_summary(run_proc, results_proc)
    sys.stderr.write(f"wrote {SUMMARY_TXT} and {SUMMARY_JSON}\n")

    survivors = counts.get("survived", 0) + counts.get("timeout", 0)
    if args.fail_on_survivors and survivors:
        sys.stderr.write(f"error: {survivors} surviving mutants\n")
        return 1
    # mutmut returns non-zero when survivors exist; without --fail-on-survivors
    # we only propagate genuine runner failures (e.g. crashes), not survivors.
    if run_proc.returncode not in (0, 2):
        return run_proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
