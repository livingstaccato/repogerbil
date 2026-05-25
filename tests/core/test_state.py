# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for state management."""

from __future__ import annotations

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


def test_state_store_save_is_atomic(tmp_path: Path) -> None:
    """StateStore.save should write via a temp file and rename atomically.

    Asserts the final file is present with correct content and that no
    leftover .tmp file remains after a successful save.
    """
    import json

    store = StateStore(tmp_path)
    test_file = tmp_path / "atomic.yaml"
    test_file.write_text("content")
    store.update(test_file)
    store.save()

    assert store.path.exists()
    leftover = store.path.with_suffix(store.path.suffix + ".tmp")
    assert not leftover.exists()

    # Round-trip the persisted JSON to confirm it's valid and complete.
    loaded = json.loads(store.path.read_text())
    assert "indexed_files" in loaded
    assert "atomic.yaml" in loaded["indexed_files"]


def test_state_store_save_overwrites_existing(tmp_path: Path) -> None:
    """A second save should atomically replace the previous file."""
    store = StateStore(tmp_path)
    f1 = tmp_path / "first.yaml"
    f1.write_text("a")
    store.update(f1)
    store.save()

    f2 = tmp_path / "second.yaml"
    f2.write_text("b")
    store.update(f2)
    store.save()

    reloaded = StateStore(tmp_path)
    assert "first.yaml" in reloaded.state.indexed_files
    assert "second.yaml" in reloaded.state.indexed_files


def test_state_store_save_two_writers_no_tmp_leak(tmp_path: Path) -> None:
    """Two sequential saves succeed and leave no ``.tmp`` files behind.

    Stand-in for true concurrency: previously both writers shared a fixed
    ``.tmp`` path; with unique mkstemp temp files neither writer collides and
    no temp file remains in the directory after either save completes.
    """
    store_a = StateStore(tmp_path)
    f1 = tmp_path / "first.yaml"
    f1.write_text("a")
    store_a.update(f1)
    store_a.save()

    store_b = StateStore(tmp_path)
    f2 = tmp_path / "second.yaml"
    f2.write_text("b")
    store_b.update(f2)
    store_b.save()

    # Final file is present and the directory contains no stray .tmp files.
    assert store_a.path.exists()
    leftovers = sorted(tmp_path.glob(".repogerbil-state-*.tmp"))
    assert leftovers == []


def test_state_store_save_cleans_tmp_when_replace_fails(tmp_path: Path) -> None:
    """If ``Path.replace`` raises, the unique tmp file is still cleaned up."""
    import contextlib
    from unittest.mock import patch

    store = StateStore(tmp_path)
    test_file = tmp_path / "x.yaml"
    test_file.write_text("c")
    store.update(test_file)

    with (
        patch.object(Path, "replace", side_effect=OSError("replace failed")),
        contextlib.suppress(OSError),
    ):
        store.save()

    leftovers = sorted(tmp_path.glob(".repogerbil-state-*.tmp"))
    assert leftovers == []


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
