# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Property, parameterized, and fuzz-style tests."""

from __future__ import annotations

import random

from hypothesis import given, settings, strategies as st
import pytest

from repogerbil.core.diff import parse_diff
from repogerbil.core.verify import _within_tolerance


def _render_diff(blocks: list[tuple[str, list[str]]]) -> str:
    lines: list[str] = []
    for filename, chunk in blocks:
        lines.append(f"diff --git a/{filename} b/{filename}")
        lines.extend(chunk)
    return "\n".join(lines)


@settings(max_examples=80, deadline=None)
@given(
    max_files=st.integers(min_value=1, max_value=8),
    max_lines=st.integers(min_value=1, max_value=30),
    blocks=st.lists(
        st.tuples(
            st.from_regex(r"[a-z]{1,8}\.py", fullmatch=True),
            st.lists(st.from_regex(r"[+\-][a-z]{0,12}", fullmatch=True), min_size=0, max_size=40),
        ),
        min_size=0,
        max_size=20,
    ),
)
def test_parse_diff_respects_output_caps(
    max_files: int,
    max_lines: int,
    blocks: list[tuple[str, list[str]]],
) -> None:
    result = parse_diff(_render_diff(blocks), max_files=max_files, max_lines_per_file=max_lines)
    assert len(result) <= max_files
    for diff_body in result.values():
        assert len(diff_body.splitlines()) <= max_lines


@pytest.mark.parametrize(
    ("reported", "actual", "tolerance", "expected"),
    [
        (100, 100, 0, True),
        (90, 100, 10, True),
        (89, 100, 10, False),
        (0, 0, 20, True),
        (1, 0, 20, False),
    ],
)
def test_within_tolerance_parameterized(reported: int, actual: int, tolerance: int, expected: bool) -> None:
    assert _within_tolerance(reported, actual, tolerance) is expected


def test_parse_diff_fuzz_no_crash() -> None:
    rng = random.Random(1337)
    for _ in range(250):
        blocks: list[tuple[str, list[str]]] = []
        for _ in range(rng.randint(0, 20)):
            ext = rng.choice(["py", "txt", "lock", "pyc"])
            filename = f"f{rng.randint(0, 30)}.{ext}"
            chunk = [rng.choice(["+x", "-y", "+data", "-data"]) for _ in range(rng.randint(0, 35))]
            blocks.append((filename, chunk))
        result = parse_diff(
            _render_diff(blocks),
            max_files=rng.randint(1, 10),
            max_lines_per_file=rng.randint(1, 25),
        )
        assert isinstance(result, dict)
