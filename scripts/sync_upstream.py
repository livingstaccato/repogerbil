#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Cherry-pick upstream commits into a locally-scrubbed clone.

For each upstream commit newer than the fork-point (see scan_upstream_drift.py),
runs `git cherry-pick -x --empty=drop` and attempts to auto-resolve common
conflict patterns. Falls through to manual review only for conflicts that don't
match any known pattern.

Auto-resolution patterns handled:
  - `--empty=drop`: upstream commit already represented in local via squash
  - never-track paths: uv.lock, .claude/, .superpowers/, docs/superpowers/
  - SPDX-header-only conflicts: keep local's SPDX header, accept upstream content
  - README / CHANGELOG / CONTRIBUTING conflicts: accept upstream (docs authority)
  - .gitignore union merge

Usage:
    python sync_upstream.py \\
        --local-root /Volumes/data/pyv \\
        --upstream-root /Users/tim/code/gh/provide-io \\
        --repo wrknv

Companion to scan_upstream_drift.py. Run the scanner first to see what's pending.
"""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path
import re
import subprocess
import sys

CHERRY_TRAILER = re.compile(r"\n?\(cherry picked from commit [0-9a-f]{7,}\)\s*$")

NEVER_TRACK_PREFIXES = (
    "uv.lock",
    ".claude/",
    ".superpowers/",
    "docs/superpowers/",
)
DOC_ACCEPT_THEIRS_SUFFIXES = (
    "README.md",
    "README.rst",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
)


def scrub(msg: str) -> str:
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


def run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(args), cwd=str(cwd), capture_output=True, text=True)


def log_newest_first(root: Path, branch: str = "main") -> list[tuple[str, int, str]]:
    r = run(root, "git", "log", branch, "--no-merges", "--format=%H%x1f%ct%x1f%B%x1e")
    recs = []
    for rec in r.stdout.split("\x1e"):
        rec = rec.strip()
        if rec.count("\x1f") < 2:
            continue
        sha, ts, body = rec.split("\x1f", 2)
        recs.append((sha, int(ts), scrub(body)))
    return recs


def conflicted_files(cwd: Path) -> list[str]:
    lines = run(cwd, "git", "status", "--porcelain").stdout.splitlines()
    conflict_codes = ("DU", "UD", "AA", "DD", "UU", "AU", "UA")
    return [line[3:] for line in lines if line[:2] in conflict_codes]


def tracked_files(cwd: Path) -> set[str]:
    return set(run(cwd, "git", "ls-files").stdout.splitlines())


def stage_blob(cwd: Path, stage: int, path: str) -> str | None:
    r = run(cwd, "git", "show", f":{stage}:{path}")
    return r.stdout if r.returncode == 0 else None


def is_never_track(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in NEVER_TRACK_PREFIXES)


def resolve_never_track(cwd: Path, path: str) -> bool:
    if not is_never_track(path):
        return False
    run(cwd, "git", "update-index", "--remove", path)
    with contextlib.suppress(OSError, FileNotFoundError):
        (cwd / path).unlink()
    return True


def resolve_doc_accept_theirs(cwd: Path, path: str) -> bool:
    if not any(path.endswith(s) for s in DOC_ACCEPT_THEIRS_SUFFIXES):
        return False
    run(cwd, "git", "checkout", "--theirs", path)
    run(cwd, "git", "add", path)
    return True


def resolve_union_gitignore(cwd: Path, path: str) -> bool:
    if path != ".gitignore" and not path.endswith("/.gitignore"):
        return False
    ours = stage_blob(cwd, 2, path)
    theirs = stage_blob(cwd, 3, path)
    if ours is None or theirs is None:
        return False
    seen = set(ours.splitlines())
    extra = [line for line in theirs.splitlines() if line not in seen]
    merged = ours + ("\n" + "\n".join(extra) + "\n" if extra else "")
    (cwd / path).write_text(merged)
    run(cwd, "git", "add", path)
    return True


def resolve_spdx_prefix(cwd: Path, path: str) -> bool:
    """Preserve local SPDX header; accept upstream's content below it."""
    ours = stage_blob(cwd, 2, path)
    theirs = stage_blob(cwd, 3, path)
    if ours is None or theirs is None:
        return False
    ours_lines = ours.splitlines(keepends=True)
    theirs_lines = theirs.splitlines(keepends=True)
    prefix: list[str] = []
    seen_spdx = False
    for i, line in enumerate(ours_lines[:10]):
        if "SPDX-FileCopyrightText" in line or "SPDX-License-Identifier" in line:
            seen_spdx = True
            prefix.append(line)
        elif seen_spdx:
            prefix.append(line)
            if line.strip() == "":
                break
        else:
            prefix.append(line)
            if i > 2:
                return False
    if not seen_spdx:
        return False
    if any("SPDX-" in line for line in theirs_lines[:10]):
        (cwd / path).write_text(theirs)
        run(cwd, "git", "add", path)
        return True
    result = prefix + theirs_lines
    (cwd / path).write_text("".join(result))
    run(cwd, "git", "add", path)
    return True


def resolve_untracked(cwd: Path, path: str, head_tracked: set[str]) -> bool:
    if path in head_tracked:
        return False
    run(cwd, "git", "update-index", "--remove", path)
    with contextlib.suppress(OSError, FileNotFoundError):
        (cwd / path).unlink()
    return True


def try_resolve_all_conflicts(cwd: Path) -> bool:
    head_tracked = tracked_files(cwd)
    files = conflicted_files(cwd)
    if not files:
        return True
    resolvers = (
        resolve_never_track,
        resolve_union_gitignore,
        resolve_doc_accept_theirs,
        resolve_spdx_prefix,
    )
    all_ok = True
    for f in files:
        if any(resolver(cwd, f) for resolver in resolvers):
            continue
        if resolve_untracked(cwd, f, head_tracked):
            continue
        all_ok = False
    return all_ok


PickOutcome = tuple[int, int, int, bool]  # (picked, dropped, resolved, stopped)


def _finalize_empty_cherry_pick(local_cwd: Path) -> None:
    run(
        local_cwd,
        "git",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "--allow-empty",
        "-C",
        "CHERRY_PICK_HEAD",
    )
    head_file = local_cwd / ".git" / "CHERRY_PICK_HEAD"
    if head_file.exists():
        head_file.unlink()


def _apply_one_commit(local_cwd: Path, sha: str, subj: str) -> PickOutcome:
    """Cherry-pick a single upstream commit, with auto-resolution."""
    r = run(local_cwd, "git", "cherry-pick", "-x", "--empty=drop", sha)
    if r.returncode == 0:
        head_subj = run(local_cwd, "git", "log", "-1", "--format=%s").stdout.strip()
        if head_subj.startswith(subj[:40]):
            print(f"  ✓ {sha[:8]} {subj}")
            return (1, 0, 0, False)
        return (0, 1, 0, False)

    if not try_resolve_all_conflicts(local_cwd):
        print(f"  ✗ {sha[:8]} {subj} (manual resolution needed)")
        print(f"     conflicted: {conflicted_files(local_cwd)[:5]}")
        return (0, 0, 0, True)

    if run(local_cwd, "git", "diff", "--cached", "--quiet").returncode == 0:
        _finalize_empty_cherry_pick(local_cwd)
        print(f"  ∅⇒ {sha[:8]} {subj} (auto-resolved, empty)")
        return (0, 0, 1, False)

    r2 = run(
        local_cwd,
        "git",
        "-c",
        "commit.gpgsign=false",
        "cherry-pick",
        "--continue",
        "--no-edit",
    )
    if r2.returncode == 0:
        print(f"  ⚒ {sha[:8]} {subj} (auto-resolved)")
        return (0, 0, 1, False)
    print(f"  ✗ {sha[:8]} {subj} (continue failed)")
    return (0, 0, 0, True)


def _find_fork_and_candidates(local_cwd: Path, upstream_path: Path) -> list[tuple[str, int, str]] | None:
    local = log_newest_first(local_cwd)
    local_bodies = {b for _, _, b in local}
    local_subjects = {b.split("\n", 1)[0] for _, _, b in local}
    upstream = log_newest_first(upstream_path)

    fork: int | None = None
    for i, (_, _, body) in enumerate(upstream):
        if body in local_bodies or body.split("\n", 1)[0] in local_subjects:
            fork = i
            break
    if fork is None:
        return None
    candidates = upstream[:fork]
    candidates.reverse()
    return candidates


def cherry_pick_repo(local_root: Path, upstream_root: Path, repo: str) -> int:
    local_cwd = local_root / repo
    upstream_path = upstream_root / repo
    if not local_cwd.is_dir() or not upstream_path.is_dir():
        print(f"SKIP {repo}: missing clone")
        return 0

    candidates = _find_fork_and_candidates(local_cwd, upstream_path)
    if candidates is None:
        print(f"{repo}: NO-FORK-FOUND — manual review required")
        return 1
    if not candidates:
        print(f"{repo}: up-to-date")
        return 0

    run(local_cwd, "git", "fetch", f"file://{upstream_path}", "main", "--no-tags")

    picked = dropped = resolved = 0
    for sha, _, body in candidates:
        subj = body.split("\n", 1)[0][:75]
        pick_n, drop_n, resolve_n, stopped = _apply_one_commit(local_cwd, sha, subj)
        picked += pick_n
        dropped += drop_n
        resolved += resolve_n
        if stopped:
            return 1

    print(f"\n{repo}: picked={picked} resolved={resolved} dropped={dropped}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-root", type=Path, required=True)
    parser.add_argument("--upstream-root", type=Path, required=True)
    parser.add_argument("--repo", required=True, help="Repo subdirectory name.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return cherry_pick_repo(args.local_root, args.upstream_root, args.repo)


if __name__ == "__main__":
    sys.exit(main())
