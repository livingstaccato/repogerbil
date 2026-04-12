# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Parallel ecosystem-wide snapshot distillation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import subprocess

from repogerbil.core.cadence import TimeGroup
from repogerbil.core.snapshot import SnapshotResult, create_snapshot


@dataclass
class EcosystemTarget:
    """One repo to distill."""

    name: str
    source_path: Path
    dest_path: Path
    groups: list[TimeGroup]
    changelog_messages: dict[str, str] | None = None
    source_branch: str = "main"


@dataclass
class EcosystemResult:
    """Result of one repo's distillation."""

    name: str
    success: bool
    commits_created: int = 0
    prefixed: int = 0
    error: str = ""


def _count_prefixed_commits(dest_path: Path) -> int:
    """Count commits with conventional prefix in dest repo."""
    try:
        result = subprocess.run(
            ["git", "log", "--format=%s"],  # noqa: S607
            cwd=dest_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return 0
        output = result.stdout
        lines = [line for line in output.split("\n") if line.strip()]
        prefixed = sum(
            1
            for line in lines
            if line[0:5].rstrip(":")
            in ("feat", "fix", "docs", "test", "chore", "perf", "refactor", "ci", "build", "style")
        )
        return prefixed
    except Exception:
        return 0


def _distill_one_target(
    target: EcosystemTarget, commit_time: str | None, timezone: str | None
) -> EcosystemResult:
    """Distill a single target repo."""
    try:
        snapshot_result: SnapshotResult = create_snapshot(
            source_path=target.source_path,
            dest_path=target.dest_path,
            groups=target.groups,
            source_branch=target.source_branch,
            changelog_messages=target.changelog_messages,
            preserve_timestamps=True,
            commit_time=commit_time,
            timezone=timezone,
        )
        prefixed = _count_prefixed_commits(Path(snapshot_result.dest_path))
        return EcosystemResult(
            name=target.name,
            success=True,
            commits_created=snapshot_result.commits_created,
            prefixed=prefixed,
        )
    except Exception as e:
        return EcosystemResult(
            name=target.name,
            success=False,
            error=str(e),
        )


def run_ecosystem_snapshot(
    targets: list[EcosystemTarget],
    parallel: int,
    commit_time: str | None = None,
    timezone: str | None = None,
) -> list[EcosystemResult]:
    """Distill multiple repos in parallel.

    Args:
        targets: list of EcosystemTarget specs
        parallel: max concurrent workers
        commit_time: HH:MM override for all commits
        timezone: IANA timezone for timestamps

    Returns:
        list of EcosystemResult (one per target, in order)
    """
    results_by_name: dict[str, EcosystemResult] = {}

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = {
            executor.submit(_distill_one_target, target, commit_time, timezone): target.name
            for target in targets
        }

        for _, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            result = future.result()
            results_by_name[name] = result

    # Return results in original target order
    return [results_by_name[target.name] for target in targets]
