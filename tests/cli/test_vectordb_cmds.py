# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for optional vector DB CLI commands."""

from __future__ import annotations

from click.testing import CliRunner
import pytest

from repogerbil.cli.main import cli


class TestVectordbCommands:
    def test_similar_command(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class DummyStore:
            pass

        def fake_get_store(_db_path: str | None) -> DummyStore:
            return DummyStore()

        def fake_find_similar_file_changes(
            store: object, filepaths: list[str], n: int
        ) -> list[dict[str, object]]:
            assert isinstance(store, DummyStore)
            assert filepaths == ["src/main.py", "src/lib.py"]
            assert n == 2
            return [
                {"id": "repo-a/2026-04-07/files", "distance": 0.123, "metadata": {"title": "Refactor main"}}
            ]

        monkeypatch.setattr("repogerbil.cli.commands.vectordb_cmds._get_store", fake_get_store)
        monkeypatch.setattr("repogerbil.core.search.find_similar_file_changes", fake_find_similar_file_changes)

        result = CliRunner().invoke(cli, ["similar", "src/main.py", "src/lib.py", "--top", "2"])
        assert result.exit_code == 0
        assert "repo-a/2026-04-07/files: Refactor main (distance: 0.123)" in result.output

    def test_impact_filepaths_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class DummyStore:
            pass

        def fake_get_store(_db_path: str | None) -> DummyStore:
            return DummyStore()

        def fake_search_filepaths(store: object, query: str, n: int) -> list[dict[str, object]]:
            assert isinstance(store, DummyStore)
            assert query == "src/auth.py"
            assert n == 3
            return [{"id": "repo-b/2026-04-08/files", "distance": 0.02, "metadata": {"title": "Auth updates"}}]

        def _unexpected_search_diffs(_store: object, _query: str, _n: int) -> list[dict[str, object]]:
            raise AssertionError("search_diffs should not be called when --source=filepaths")

        monkeypatch.setattr("repogerbil.cli.commands.vectordb_cmds._get_store", fake_get_store)
        monkeypatch.setattr("repogerbil.core.search.search_filepaths", fake_search_filepaths)
        monkeypatch.setattr("repogerbil.core.search.search_diffs", _unexpected_search_diffs)

        result = CliRunner().invoke(cli, ["impact", "src/auth.py", "--source", "filepaths", "--top", "3"])
        assert result.exit_code == 0
        assert "repo-b/2026-04-08/files: Auth updates (distance: 0.020)" in result.output

    def test_impact_diffs_source_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class DummyStore:
            pass

        def fake_get_store(_db_path: str | None) -> DummyStore:
            return DummyStore()

        def _unexpected_search_filepaths(_store: object, _query: str, _n: int) -> list[dict[str, object]]:
            raise AssertionError("search_filepaths should not be called when --source=diffs")

        def fake_search_diffs(store: object, query: str, n: int) -> list[dict[str, object]]:
            assert isinstance(store, DummyStore)
            assert query == "retry backoff"
            assert n == 2
            return []

        monkeypatch.setattr("repogerbil.cli.commands.vectordb_cmds._get_store", fake_get_store)
        monkeypatch.setattr("repogerbil.core.search.search_filepaths", _unexpected_search_filepaths)
        monkeypatch.setattr("repogerbil.core.search.search_diffs", fake_search_diffs)

        result = CliRunner().invoke(cli, ["impact", "retry backoff", "--source", "diffs", "--top", "2"])
        assert result.exit_code == 0
        assert "No impact context found." in result.output
