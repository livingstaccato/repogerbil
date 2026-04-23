# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Realign legacy jsonl records to current local commit SHAs.

Legacy records in a ``.summaries.jsonl`` hold hashes from a prior snapshot
run that no longer exist in the current local repository (history has been
rewritten since the jsonl was written). Reports and tooling that want to
look up records by current git hash need those records re-keyed.

This module finds the best-matching current local commit for each legacy
record using a cascading strategy over (date, file-set) and rewrites the
record's ``hash`` and ``date`` fields in place. LLM-refined ``subjects``,
``body``, and ``changes`` content is preserved untouched.

Matching cascade:

1. ``hash`` already resolves in local git — no change.
2. Same date as legacy, file-set overlap > 0 — pick highest Jaccard,
   tiebreak earliest timestamp.
3. Within ±1 day, file-set overlap > 0 — same tiebreak.
4. Within ±7 days, file-set overlap > 0 — same tiebreak.
5. No candidate — leave record unchanged, count as unalignable.

The jsonl is rewritten atomically (temp file + rename).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date as date_type, timedelta
import json
from pathlib import Path
from typing import Any

from repogerbil.core.git import _run_git


@dataclass(frozen=True)
class _LocalCommit:
    hash: str
    date: str
    timestamp: int
    files: frozenset[str]


@dataclass(frozen=True)
class RealignResult:
    """Outcome of a realign pass."""

    jsonl_path: str
    total_records: int
    already_verified: int  # hash already in local git, unchanged
    realigned: int  # matched to a new local hash
    unalignable: int  # no candidate found, unchanged
    exact_matches: int  # of realigned, how many had exact (date, fileset)


def _scan_local_commits(repo_path: Path) -> list[_LocalCommit]:
    """Return every reachable commit with date, timestamp, and file set."""
    fmt = "%H%x00%as%x00%at"
    meta = _run_git(repo_path, "log", "--all", "--no-merges", f"--format={fmt}", timeout=120)
    timestamps: dict[str, tuple[str, int]] = {}
    for line in meta.splitlines():
        parts = line.split("\x00", 2)
        if len(parts) < 3:
            continue
        try:
            ts = int(parts[2])
        except ValueError:
            continue
        timestamps[parts[0]] = (parts[1], ts)

    files_raw = _run_git(repo_path, "log", "--all", "--no-merges", "--format=%H", "--name-only", timeout=120)
    files_map: dict[str, set[str]] = defaultdict(set)
    current: str | None = None
    for line in files_raw.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if len(stripped) == 40 and all(c in "0123456789abcdef" for c in stripped):
            current = stripped
        elif current is not None:
            files_map[current].add(stripped)

    commits: list[_LocalCommit] = []
    for h, (d, ts) in timestamps.items():
        commits.append(_LocalCommit(hash=h, date=d, timestamp=ts, files=frozenset(files_map.get(h, set()))))
    return commits


def _hash_exists(repo_path: Path, commit_hash: str) -> bool:
    """Return True if ``commit_hash`` resolves to a commit object locally."""
    import subprocess

    r = subprocess.run(  # noqa: S603  # git args are controlled (repo_path, hash from our own DB)
        ["git", "-C", str(repo_path), "cat-file", "-e", f"{commit_hash}^{{commit}}"],  # noqa: S607  # rely on PATH-resolved git
        capture_output=True,
    )
    return r.returncode == 0


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def _date_window(iso_date: str, days: int) -> set[str]:
    """Return the set of YYYY-MM-DD strings within ``±days`` of ``iso_date``."""
    try:
        anchor = date_type.fromisoformat(iso_date)
    except ValueError:
        return set()
    return {(anchor + timedelta(days=d)).isoformat() for d in range(-days, days + 1)}


def _pick_best(
    candidates: list[_LocalCommit],
    rec_files: frozenset[str],
    rec_date: str,
) -> _LocalCommit | None:
    """Pick highest Jaccard; tiebreak by closer date, then earlier timestamp."""
    if not candidates:
        return None
    scored: list[tuple[float, int, int, str, _LocalCommit]] = []
    for c in candidates:
        score = _jaccard(rec_files, c.files)
        if score == 0 and rec_files:
            continue
        try:
            date_distance = abs((date_type.fromisoformat(c.date) - date_type.fromisoformat(rec_date)).days)
        except ValueError:
            date_distance = 9999
        scored.append((-score, date_distance, c.timestamp, c.hash, c))
    if not scored:
        return None
    scored.sort()
    return scored[0][4]


def _find_match(
    commits_by_date: dict[str, list[_LocalCommit]],
    rec_date: str,
    rec_files: frozenset[str],
) -> tuple[_LocalCommit | None, bool]:
    """Return (best_match, is_exact_match) or (None, False)."""
    # Same date exact fileset first.
    same_day = commits_by_date.get(rec_date, [])
    for c in same_day:
        if c.files == rec_files:
            return c, True

    # Widening date windows with Jaccard.
    for radius in (0, 1, 7):
        dates = _date_window(rec_date, radius) if radius > 0 else {rec_date}
        candidates: list[_LocalCommit] = []
        for d in dates:
            candidates.extend(commits_by_date.get(d, []))
        best = _pick_best(candidates, rec_files, rec_date)
        if best is not None:
            return best, False

    return None, False


def realign_jsonl(
    repo_path: Path,
    jsonl_path: Path,
    dry_run: bool = False,
) -> RealignResult:
    """Realign legacy records in ``jsonl_path`` to current local commit hashes.

    Args:
        repo_path: Git repository whose HEAD history provides the alignment
            targets.
        jsonl_path: Path to the ``.summaries.jsonl`` to rewrite.
        dry_run: When ``True``, compute realignment without writing.
    """
    if not jsonl_path.exists():
        return RealignResult(str(jsonl_path), 0, 0, 0, 0, 0)

    commits = _scan_local_commits(repo_path)
    commits_by_date: dict[str, list[_LocalCommit]] = defaultdict(list)
    for c in commits:
        commits_by_date[c.date].append(c)

    rewritten: list[str] = []
    total = 0
    already = 0
    realigned = 0
    unalignable = 0
    exact_matches = 0

    with jsonl_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            total += 1
            rec: dict[str, Any] = json.loads(line)
            h = rec.get("hash", "")

            if isinstance(h, str) and len(h) == 40 and _hash_exists(repo_path, h):
                already += 1
                rewritten.append(json.dumps(rec))
                continue

            rec_date = rec.get("date", "")
            rec_files = frozenset(
                c.get("file", "") for c in rec.get("changes", []) if isinstance(c, dict) and c.get("file")
            )
            match, is_exact = _find_match(commits_by_date, rec_date, rec_files)
            if match is None:
                unalignable += 1
                rewritten.append(json.dumps(rec))
                continue

            rec["hash"] = match.hash
            rec["date"] = match.date
            realigned += 1
            if is_exact:
                exact_matches += 1
            rewritten.append(json.dumps(rec))

    if not dry_run:
        tmp = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
        tmp.write_text("\n".join(rewritten) + ("\n" if rewritten else ""), encoding="utf-8")
        tmp.replace(jsonl_path)

    return RealignResult(
        jsonl_path=str(jsonl_path),
        total_records=total,
        already_verified=already,
        realigned=realigned,
        unalignable=unalignable,
        exact_matches=exact_matches,
    )
