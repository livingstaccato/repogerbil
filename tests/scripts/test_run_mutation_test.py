# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Pin the mutmut-output parser in ``scripts/run_mutation_test.py``.

mutmut's ``results`` stdout format is not a stable public API: the parser at
``scripts/run_mutation_test.py:_parse_results`` assumes status headers end with
``:`` and contain no spaces, with mutant ids listed underneath. If mutmut bumps
and changes that shape, these tests break loudly so we know to update the
parser instead of silently shipping empty CI summaries.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types
from typing import cast

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_mutation_test.py"


def _load_module() -> types.ModuleType:
    """Load ``scripts/run_mutation_test.py`` as an importable module.

    The ``scripts/`` directory is not on ``sys.path`` and we deliberately do
    not add it (avoid leaking script-local helpers into the test namespace),
    so we load the file directly via ``importlib.util``.
    """
    spec = importlib.util.spec_from_file_location("rmt_under_test", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_RMT = _load_module()


class TestParseResultsCurrentFormat:
    """Lock in the mutmut output shape we currently rely on."""

    def test_typical_mutmut_results(self) -> None:
        # Representative mutmut `results` output: one header per status, blank
        # lines separating sections, mutant ids underneath.
        text = (
            "killed:\n"
            "src.foo.x_mutmut_1\n"
            "src.foo.x_mutmut_2\n"
            "src.foo.x_mutmut_3\n"
            "\n"
            "survived:\n"
            "src.foo.x_mutmut_4\n"
            "\n"
            "timeout:\n"
            "src.foo.x_mutmut_5\n"
            "src.foo.x_mutmut_6\n"
        )
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        assert counts == {"killed": 3, "survived": 1, "timeout": 2}

    def test_single_status_no_trailing_newline(self) -> None:
        text = "killed:\nm1\nm2"
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        assert counts == {"killed": 2}

    def test_status_with_zero_mutants_is_recorded(self) -> None:
        # A status header followed immediately by a blank line should still
        # register the status with a count of 0 — otherwise downstream summary
        # logic can't tell "absent" from "zero".
        text = "killed:\nm1\n\nsurvived:\n\nskipped:\nm2\nm3\n"
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        assert counts == {"killed": 1, "survived": 0, "skipped": 2}


class TestParseResultsEdgeCases:
    def test_empty_input(self) -> None:
        assert _RMT._parse_results("") == {}

    def test_only_whitespace(self) -> None:
        assert _RMT._parse_results("\n\n   \n") == {}

    def test_lines_before_first_header_ignored(self) -> None:
        # Stray preamble lines (mutmut sometimes prints a banner) must not be
        # silently tallied as a mutant.
        text = "stray preamble\nanother line\nkilled:\nm1\nm2\n"
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        assert counts == {"killed": 2}

    def test_header_with_internal_space_is_not_a_header(self) -> None:
        # The parser uses ``" " not in line[:-1]`` to reject lines that look
        # header-ish but have an embedded space. Such lines under an active
        # status are counted as mutant ids; outside any status they're ignored.
        text = "killed:\nnot a header:\nm1\n"
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        # "not a header:" counted as one mutant id, then "m1" as another.
        assert counts == {"killed": 2}

    def test_unexpected_status_names_are_passed_through(self) -> None:
        # Future mutmut versions could add new statuses (e.g. "skipped",
        # "no_tests"). The parser must surface them verbatim so the summary
        # JSON shows the new bucket instead of dropping data.
        text = "exotic_status:\nm1\nm2\nanother_new_one:\nm3\n"
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        assert counts == {"exotic_status": 2, "another_new_one": 1}

    def test_malformed_only_garbage(self) -> None:
        # No status header anywhere → no counts (no false positives).
        text = "foo\nbar\nbaz\n"
        assert _RMT._parse_results(text) == {}

    def test_duplicate_header_does_not_reset_count(self) -> None:
        # If mutmut ever emits the same status twice, totals should accumulate
        # (``setdefault`` + ``get(..., 0) + 1``), not reset.
        text = "killed:\nm1\n\nkilled:\nm2\nm3\n"
        counts = cast("dict[str, int]", _RMT._parse_results(text))
        assert counts == {"killed": 3}
