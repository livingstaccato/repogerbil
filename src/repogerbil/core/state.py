# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""State management for incremental processing."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
import tempfile

from pydantic import BaseModel, Field


class State(BaseModel):
    """Persistent state for a changelog directory."""

    # mapping of relative path to last modified timestamp
    indexed_files: dict[str, float] = Field(default_factory=dict)


class StateStore:
    """Handles reading and writing state to a JSON file."""

    def __init__(self, changelog_dir: Path) -> None:
        self.path = changelog_dir / ".repogerbil-state.json"
        self.state = self._load()

    def _load(self) -> State:
        """Load state from disk, or return empty state if missing/corrupt."""
        if not self.path.exists():
            return State()
        try:
            data = json.loads(self.path.read_text())
            return State(**data)
        except (json.JSONDecodeError, ValueError):
            return State()

    def save(self) -> None:
        """Save current state to disk atomically (temp file + rename).

        Uses a unique temp file path so concurrent writers cannot collide on a
        deterministic ``.tmp`` name; the temp file is always cleaned up on
        failure so it never leaks alongside the final state file.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=self.path.parent, prefix=".repogerbil-state-", suffix=".tmp")
        tmp_path = Path(tmp_name)
        try:
            # Close the low-level fd immediately — we re-open via Path to keep
            # write semantics consistent with the rest of the codebase.
            os.close(fd)
            tmp_path.write_text(self.state.model_dump_json(indent=2) + "\n")
            tmp_path.replace(self.path)
        finally:
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()

    def is_changed(self, file_path: Path) -> bool:
        """Return True if the file has changed since it was last indexed."""
        # Use relative path as key if file is inside changelog_dir
        try:
            key = str(file_path.relative_to(self.path.parent))
        except ValueError:
            key = str(file_path)

        mtime = file_path.stat().st_mtime
        return self.state.indexed_files.get(key) != mtime

    def update(self, file_path: Path) -> None:
        """Update the state for a file with its current mtime."""
        try:
            key = str(file_path.relative_to(self.path.parent))
        except ValueError:
            key = str(file_path)

        self.state.indexed_files[key] = file_path.stat().st_mtime
