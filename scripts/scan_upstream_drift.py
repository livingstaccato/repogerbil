#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Scan upstream-vs-local drift across a list of sibling repos.

For each repo, walks the upstream clone's main-branch log newest-first and
finds the first commit whose scrubbed message matches a commit in the local
clone. Every upstream commit newer than that fork-point is an integration
candidate.

Designed for workflows where a local set of clones had their history
rewritten (for secrets scrubbing, squashing, etc.) and the SHAs no longer
align with GitHub upstream, but commit messages still rhyme after the same
scrubbing transforms are applied.

Usage:
    python scan_upstream_drift.py \\
        --local-root /Volumes/data/pyv \\
        --upstream-root /Users/tim/code/gh/provide-io \\
        --repos wrknv pyvider provide-telemetry

Companion to sync_upstream.py (which actually cherry-picks the drift).
"""

from __future__ import annotations

import argparse
from collections import Counter
import datetime
from pathlib import Path
import re
import subprocess
import sys

CHERRY_TRAILER = re.compile(r"\n?\(cherry picked from commit [0-9a-f]{7,}\)\s*$")
INFRA_SUBJECT = re.compile(
    r"^(chore\(?(ci|deps|actions?|workflows?|release|licensing|gitignore|security)"
    r"|docs|chore:|build\(deps|style|ci:|license)",
    re.IGNORECASE,
)


def scrub(msg: str) -> str:
    """Normalize a commit message the way filter-repo did during scrubbing."""
    msg = re.sub(r"(?im)^\s*Co-Authored-By:.*$\n?", "", msg)
    msg = re.sub(r"[a-zA-Z0-9._+-]+@anthropic\.com", "code@tim.life", msg)
    msg = msg.replace("timothy.perkins@hmhco.com", "code@tim.life")
    msg = msg.replace("tim.perkins@nwea.org", "code@tim.life")
    msg = msg.replace("tim@neurotic.org", "code@tim.life")
    msg = msg.replace("tim@provide.io", "code@provide.io")
    msg = msg.replace("engineering@provide.io", "code@provide.io")
    msg = CHERRY_TRAILER.sub("", msg)
    msg = re.sub(r"\n{3,}", "\n\n", msg)
    return msg.rstrip()


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def log_newest_first(root: Path, repo: str, branch: str = "main") -> list[tuple[str, int, str]]:
    """Return [(sha, committer_ts, scrubbed_body), ...] newest-first."""
    result = git(
        root / repo,
        "log",
        branch,
        "--no-merges",
        "--format=%H%x1f%ct%x1f%B%x1e",
    )
    records: list[tuple[str, int, str]] = []
    for rec in result.stdout.split("\x1e"):
        rec = rec.strip()
        if rec.count("\x1f") < 2:
            continue
        sha, ts, body = rec.split("\x1f", 2)
        records.append((sha, int(ts), scrub(body)))
    return records


def classify(body: str) -> str:
    subject = body.split("\n", 1)[0]
    return "infra" if INFRA_SUBJECT.match(subject) else "substantive"


def scan_repo(local_root: Path, upstream_root: Path, repo: str) -> dict[str, object]:
    """Find the fork-point and count integration candidates."""
    local = log_newest_first(local_root, repo)
    if not local:
        return {"error": "local has no commits"}
    upstream = log_newest_first(upstream_root, repo)
    if not upstream:
        upstream = log_newest_first(upstream_root, repo, branch="master")
    if not upstream:
        return {"error": "no upstream history"}

    local_bodies = {body for _, _, body in local}
    local_subjects = {body.split("\n", 1)[0] for _, _, body in local}

    fork_idx: int | None = None
    for i, (_, _, body) in enumerate(upstream):
        if body in local_bodies or body.split("\n", 1)[0] in local_subjects:
            fork_idx = i
            break

    if fork_idx is None:
        return {"candidates": upstream, "fork_date": None, "no_fork": True}
    candidates = upstream[:fork_idx]
    fork_date = datetime.datetime.fromtimestamp(upstream[fork_idx][1]).strftime("%Y-%m-%d %H:%M")
    return {"candidates": candidates, "fork_date": fork_date, "no_fork": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-root",
        type=Path,
        required=True,
        help="Parent dir containing locally-scrubbed clones.",
    )
    parser.add_argument(
        "--upstream-root",
        type=Path,
        required=True,
        help="Parent dir containing the upstream clones (kept in sync with GitHub).",
    )
    parser.add_argument(
        "--repos",
        nargs="+",
        required=True,
        help="Repo names (must be subdirectories of both --local-root and --upstream-root).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    print(
        f"{'repo':<32} {'candidates':>11} {'subst':>6} {'infra':>6}"
        f"  {'fork-point':<18} {'newest-upstream':<18}"
    )
    print("-" * 100)

    totals: Counter[str] = Counter()
    for repo in args.repos:
        result = scan_repo(args.local_root, args.upstream_root, repo)
        if "error" in result:
            print(f"{repo:<32} ERROR: {result['error']}")
            continue

        candidates = result["candidates"]  # type: ignore[assignment]
        assert isinstance(candidates, list)
        fork_date = result["fork_date"] or "NO-FORK"
        subst = sum(1 for _, _, b in candidates if classify(b) == "substantive")
        infra = sum(1 for _, _, b in candidates if classify(b) == "infra")

        upstream_newest = log_newest_first(args.upstream_root, repo)
        newest = (
            datetime.datetime.fromtimestamp(upstream_newest[0][1]).strftime("%Y-%m-%d %H:%M")
            if upstream_newest
            else "-"
        )
        print(f"{repo:<32} {len(candidates):>11} {subst:>6} {infra:>6}  {fork_date:<18} {newest:<18}")
        totals["candidates"] += len(candidates)
        totals["subst"] += subst
        totals["infra"] += infra

    print("-" * 100)
    print(f"{'TOTAL':<32} {totals['candidates']:>11} {totals['subst']:>6} {totals['infra']:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
