# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the shared JSONL iteration helper."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from repogerbil.core._jsonl import iter_jsonl_records


class TestIterJsonlRecords:
    def test_missing_file_yields_nothing(self, tmp_path: Path) -> None:
        """A non-existent path yields no records (no exception)."""
        result = list(iter_jsonl_records(tmp_path / "nope.jsonl"))
        assert result == []

    def test_skips_blank_lines_silently(self, tmp_path: Path) -> None:
        """Blank-only lines never appear in the output stream."""
        path = tmp_path / "blanks.jsonl"
        path.write_text(
            "\n"
            + json.dumps({"hash": "a", "date": "2026-01-01"})
            + "\n"
            + "   \n"
            + json.dumps({"hash": "b", "date": "2026-01-02"})
            + "\n"
            + "\n"
        )
        result = list(iter_jsonl_records(path))
        # Two valid records, no blank rows yielded.
        assert len(result) == 2
        assert [rec for _, _, rec in result] == [
            {"hash": "a", "date": "2026-01-01"},
            {"hash": "b", "date": "2026-01-02"},
        ]

    def test_corrupt_line_yields_none_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A non-JSON line yields ``(lineno, raw, None)`` and logs at WARNING."""
        path = tmp_path / "corrupt.jsonl"
        path.write_text("this is not json\n")
        with caplog.at_level(logging.WARNING, logger="repogerbil.core._jsonl"):
            result = list(iter_jsonl_records(path))
        assert len(result) == 1
        lineno, raw, rec = result[0]
        assert lineno == 1
        assert raw == "this is not json"
        assert rec is None
        assert any("Skipping corrupt JSONL line" in r.message for r in caplog.records)

    def test_non_dict_record_yields_none_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A JSON value that isn't a dict (e.g. bare list) is treated as corrupt."""
        path = tmp_path / "nondict.jsonl"
        # Valid JSON, but a bare list — our callers expect record dicts.
        path.write_text("[1, 2, 3]\n")
        with caplog.at_level(logging.WARNING, logger="repogerbil.core._jsonl"):
            result = list(iter_jsonl_records(path))
        assert len(result) == 1
        lineno, raw, rec = result[0]
        assert lineno == 1
        assert raw == "[1, 2, 3]"
        assert rec is None
        assert any("non-dict JSONL record" in r.message for r in caplog.records)

    def test_line_numbers_are_one_based(self, tmp_path: Path) -> None:
        """Line numbers in yields match 1-based file-reader conventions."""
        path = tmp_path / "numbered.jsonl"
        path.write_text(
            json.dumps({"hash": "a"})
            + "\n"
            + json.dumps({"hash": "b"})
            + "\n"
            + json.dumps({"hash": "c"})
            + "\n"
        )
        result = list(iter_jsonl_records(path))
        line_numbers = [lineno for lineno, _, _ in result]
        assert line_numbers == [1, 2, 3]
