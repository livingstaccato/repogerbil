# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for state management."""

from __future__ import annotations

import json
from pathlib import Path

from repogerbil.core.state import State, StateStore


def test_state_store_load_save(tmp_path: Path) -> None:
    """StateStore should load and save state correctly."""
    store = StateStore(tmp_path)
    assert store.state.indexed_files == {}

    test_file = tmp_path / "test.yaml"
    test_file.write_text("content")
    store.update(test_file)
    store.save()

    assert store.path.exists()
    
    # Reload
    new_store = StateStore(tmp_path)
    assert len(new_store.state.indexed_files) == 1
    assert not new_store.is_changed(test_file)


def test_state_store_is_changed(tmp_path: Path) -> None:
    """StateStore should detect changes in files."""
    store = StateStore(tmp_path)
    test_file = tmp_path / "test.yaml"
    test_file.write_text("content")
    
    # Not in state yet
    assert store.is_changed(test_file)
    
    store.update(test_file)
    assert not store.is_changed(test_file)
    
    # Change file mtime
    import os
    import time
    
    # Ensure mtime actually changes (filesystem resolution)
    new_mtime = test_file.stat().st_mtime + 10
    os.utime(test_file, (new_mtime, new_mtime))
    
    assert store.is_changed(test_file)


def test_state_store_corrupt_file(tmp_path: Path) -> None:
    """StateStore should handle corrupt state files gracefully."""
    state_file = tmp_path / ".repogerbil-state.json"
    state_file.write_text("invalid json")
    
    store = StateStore(tmp_path)
    assert isinstance(store.state, State)
    assert store.state.indexed_files == {}


def test_state_store_outside_dir(tmp_path: Path) -> None:
    """StateStore should handle files outside its base directory using absolute paths."""
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    
    store = StateStore(base_dir)
    outside_file = other_dir / "test.yaml"
    outside_file.write_text("content")
    
    store.update(outside_file)
    assert not store.is_changed(outside_file)
    assert str(outside_file) in store.state.indexed_files
