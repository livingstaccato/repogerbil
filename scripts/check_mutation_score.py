#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Enforce a minimum mutmut kill-rate threshold.

Reads ``mutants/mutmut-cicd-stats.json`` (written by ``mutmut export-cicd-stats``,
which ``make mutation-ci`` invokes via ``scripts/run_mutation_test.py``) and
exits non-zero if ``killed / (total - no_tests - skipped)`` falls below the
threshold given as the first CLI argument (percent, 0-100).

Usage:
    python scripts/check_mutation_score.py 90

Designed for the nightly mutation workflow. Excluded mutants (no_tests,
skipped) are removed from the denominator so the rate reflects only the
mutants that actually got a verdict.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

_STATS_PATH = Path("mutants/mutmut-cicd-stats.json")


def main() -> int:
    """Return 0 if kill rate >= threshold, 1 otherwise (or 2 on input errors)."""
    if len(sys.argv) != 2:
        sys.stderr.write("usage: check_mutation_score.py <min_percent>\n")
        return 2
    try:
        threshold = float(sys.argv[1])
    except ValueError:
        sys.stderr.write(f"invalid threshold (not a number): {sys.argv[1]!r}\n")
        return 2
    if not 0.0 <= threshold <= 100.0:
        sys.stderr.write(f"threshold must be in [0, 100], got {threshold}\n")
        return 2

    if not _STATS_PATH.exists():
        sys.stderr.write(f"{_STATS_PATH}: not found — run `make mutation-ci` first to produce it.\n")
        return 2

    stats = json.loads(_STATS_PATH.read_text(encoding="utf-8"))
    total = int(stats.get("total", 0))
    killed = int(stats.get("killed", 0))
    no_tests = int(stats.get("no_tests", 0))
    skipped = int(stats.get("skipped", 0))
    judged = total - no_tests - skipped

    if judged <= 0:
        sys.stderr.write(f"no judged mutants in {_STATS_PATH}: {stats}\n")
        return 2

    rate = (killed / judged) * 100.0
    sys.stderr.write(f"mutation kill rate: {killed}/{judged} = {rate:.2f}% (threshold {threshold:.2f}%)\n")
    return 0 if rate >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
