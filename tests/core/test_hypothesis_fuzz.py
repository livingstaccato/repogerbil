# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Property, parameterized, and fuzz-style tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import random

from hypothesis import given, settings, strategies as st
import pytest

from repogerbil.core.cadence import group_by_cadence
from repogerbil.core.classify import classify_commit
from repogerbil.core.diff import parse_diff
from repogerbil.core.git import CommitInfo
from repogerbil.core.verify import _within_tolerance
from repogerbil.core.vocabulary import CATEGORIES, PREFIX_TO_CATEGORY, SEVERITIES


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


# ---------------------------------------------------------------------------
# Property tests — core/cadence.py:group_by_cadence
# ---------------------------------------------------------------------------

# Restrict to a small calendar window so date strings are always valid.
_MIN_TS = int(datetime(2020, 1, 1, tzinfo=UTC).timestamp())
_MAX_TS = int(datetime(2030, 12, 31, tzinfo=UTC).timestamp())

_SECONDS_PER_HOUR = 3600
_SECONDS_PER_DAY = 86400


@st.composite
def _commits_with_timestamps(
    draw: st.DrawFn,
    min_size: int = 0,
    max_size: int = 20,
) -> tuple[list[CommitInfo], dict[str, int]]:
    """Draw a list of CommitInfo plus a parallel {hash: ts} dict."""
    count = draw(st.integers(min_value=min_size, max_value=max_size))
    commits: list[CommitInfo] = []
    timestamps: dict[str, int] = {}
    for i in range(count):
        ts = draw(st.integers(min_value=_MIN_TS, max_value=_MAX_TS))
        h = f"c{i:04d}"
        date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
        commits.append(CommitInfo(hash=h, date=date, subject=f"s{i}"))
        timestamps[h] = ts
    return commits, timestamps


@settings(max_examples=100, deadline=None)
@given(payload=_commits_with_timestamps(min_size=0, max_size=15))
def test_group_by_cadence_partitions_every_commit_exactly_once(
    payload: tuple[list[CommitInfo], dict[str, int]],
) -> None:
    """Every input commit appears in exactly one output group, regardless of cadence."""
    commits, ts = payload
    for cadence in ("hourly", "daily", "weekly", "gap:30m"):
        groups = group_by_cadence(commits, cadence, timestamps=ts)
        flat = [c for g in groups for c in g.commits]
        assert len(flat) == len(commits)
        assert {c.hash for c in flat} == {c.hash for c in commits}


@settings(max_examples=100, deadline=None)
@given(payload=_commits_with_timestamps(min_size=0, max_size=15))
def test_group_by_cadence_groups_are_chronologically_ordered(
    payload: tuple[list[CommitInfo], dict[str, int]],
) -> None:
    """Group ``period_start`` values are monotonically non-decreasing."""
    commits, ts = payload
    for cadence in ("hourly", "daily", "weekly"):
        groups = group_by_cadence(commits, cadence, timestamps=ts)
        starts = [g.period_start for g in groups]
        assert starts == sorted(starts)


def test_group_by_cadence_empty_input_yields_empty_output() -> None:
    """An empty commit list yields an empty group list for every cadence."""
    for cadence in ("hourly", "daily", "weekly", "gap:30m", "gap:2h"):
        assert group_by_cadence([], cadence) == []


@settings(max_examples=100, deadline=None)
@given(ts=st.integers(min_value=_MIN_TS, max_value=_MAX_TS))
def test_group_by_cadence_single_commit_yields_single_group(ts: int) -> None:
    """A single commit always produces exactly one group containing that commit."""
    date = datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%d")
    commit = CommitInfo(hash="solo", date=date, subject="only")
    for cadence in ("hourly", "daily", "weekly", "gap:30m"):
        groups = group_by_cadence([commit], cadence, timestamps={"solo": ts})
        assert len(groups) == 1
        assert groups[0].commits == [commit]


@settings(max_examples=100, deadline=None)
@given(payload=_commits_with_timestamps(min_size=1, max_size=10))
def test_group_by_cadence_hourly_buckets_share_calendar_hour(
    payload: tuple[list[CommitInfo], dict[str, int]],
) -> None:
    """Within a single hourly group, all commit timestamps share the same UTC hour bucket."""
    commits, ts = payload
    groups = group_by_cadence(commits, "hourly", timestamps=ts)
    for g in groups:
        buckets = {ts[c.hash] // _SECONDS_PER_HOUR for c in g.commits}
        assert len(buckets) == 1


@settings(max_examples=100, deadline=None)
@given(payload=_commits_with_timestamps(min_size=1, max_size=10))
def test_group_by_cadence_daily_buckets_share_calendar_day(
    payload: tuple[list[CommitInfo], dict[str, int]],
) -> None:
    """Within a single daily group, all commit timestamps share the same UTC date."""
    commits, ts = payload
    groups = group_by_cadence(commits, "daily", timestamps=ts)
    for g in groups:
        dates = {datetime.fromtimestamp(ts[c.hash], tz=UTC).date() for c in g.commits}
        assert len(dates) == 1


# ---------------------------------------------------------------------------
# Property tests — core/classify.py:classify_commit
# ---------------------------------------------------------------------------

# Conventional prefixes we know the classifier recognizes.
_KNOWN_PREFIXES = tuple(PREFIX_TO_CATEGORY.keys())
_VALID_SEVERITY_VALUES = set(SEVERITIES.values())
_VALID_CATEGORY_KEYS = set(CATEGORIES.keys())


# Free-form subject text — alnum, punctuation, whitespace. Restrict to printable
# ASCII so the regex paths exercise but we don't fight encoding rabbit holes.
_subject_text = st.text(
    alphabet=st.characters(
        min_codepoint=32,
        max_codepoint=126,
    ),
    min_size=0,
    max_size=120,
)


@settings(max_examples=200, deadline=None)
@given(subject=_subject_text)
def test_classify_commit_category_is_known_or_none(subject: str) -> None:
    """Output category is always either ``None`` or a key in the vocabulary."""
    result = classify_commit(subject)
    assert result.category is None or result.category in _VALID_CATEGORY_KEYS


@settings(max_examples=200, deadline=None)
@given(subject=_subject_text)
def test_classify_commit_severity_is_known_or_none(subject: str) -> None:
    """Output severity is always either ``None`` or one of the configured values."""
    result = classify_commit(subject)
    assert result.severity is None or result.severity in _VALID_SEVERITY_VALUES


@settings(max_examples=200, deadline=None)
@given(
    prefix=st.sampled_from(_KNOWN_PREFIXES),
    tail=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=40,
    ),
)
def test_classify_commit_known_prefix_maps_to_prefix_category(prefix: str, tail: str) -> None:
    """A subject starting with a recognized conventional prefix classifies via that prefix.

    A handful of prefixes have refinement rules (``feat`` may become "interface",
    ``fix`` may become "harden"/"margin") when the description matches certain
    regexes — we drop those from the asserted base category by using only a
    purely lowercase-alpha tail, which cannot match the refinement regexes.
    """
    subject = f"{prefix}: {tail}"
    expected = PREFIX_TO_CATEGORY[prefix]
    result = classify_commit(subject)
    assert result.category == expected
    assert result.needs_review is False


@pytest.mark.parametrize("subject", ["", "   ", "\t", "\n", "    \n\t  "])
def test_classify_commit_whitespace_or_empty_subject_does_not_crash(subject: str) -> None:
    """Empty / whitespace subjects should classify cleanly (likely needs_review=True)."""
    result = classify_commit(subject)
    # Whichever the classifier picks, it must be a structurally valid result.
    assert result.category is None or result.category in _VALID_CATEGORY_KEYS
    assert result.severity is None or result.severity in _VALID_SEVERITY_VALUES
    assert isinstance(result.needs_review, bool)


@settings(max_examples=200, deadline=None)
@given(subject=_subject_text, body=st.text(max_size=80))
def test_classify_commit_is_idempotent(subject: str, body: str) -> None:
    """Classifying the same input twice yields equal results."""
    first = classify_commit(subject, body=body)
    second = classify_commit(subject, body=body)
    assert first == second


# ---------------------------------------------------------------------------
# Property tests — cli/commands/distill_cmds/_helpers.py:_KNOWN_PREFIX_RE
# ---------------------------------------------------------------------------
#
# This block is intentionally defensive about how it imports the regex —
# Agent A is in the process of changing ``_KNOWN_PREFIX_RE`` so it may take
# an "effective vocabulary" instead of being a module-level constant. We
# resolve the matcher lazily via ``_resolve_known_prefix_matcher`` so the
# property tests still work whether Agent A keeps a constant regex, renames
# it, or turns it into a factory function.


def _resolve_known_prefix_matcher() -> Callable[[str], object]:
    """Return a callable ``(subject: str) -> object`` that returns truthy on match.

    Tries, in order:
      1. Module-level compiled regex ``_KNOWN_PREFIX_RE`` (current shape).
      2. Module-level zero-arg factory ``_known_prefix_re()`` that returns a
         compiled regex (one possible refactor shape).
      3. A factory that takes the active vocabulary's prefix-to-category map
         (the shape Agent A is rumored to be heading toward).
    On match we return the regex's ``match`` bound method so tests can
    uniformly call ``matcher(subject)``.
    """
    from repogerbil.cli.commands.distill_cmds import _helpers
    from repogerbil.core.vocabulary import PREFIX_TO_CATEGORY

    # Shape 1: module-level compiled regex.
    regex = getattr(_helpers, "_KNOWN_PREFIX_RE", None)
    if regex is not None and hasattr(regex, "match"):
        # mypy can't see that this is a compiled re.Pattern at this point.
        return regex.match  # type: ignore[no-any-return]  # mypy: regex was Any-ish via getattr

    # Shape 2: a zero-arg factory.
    factory = getattr(_helpers, "_known_prefix_re", None)
    if callable(factory):
        try:
            built = factory()
        except TypeError:
            # Shape 3: takes the prefix map.
            built = factory(PREFIX_TO_CATEGORY)
        return built.match  # type: ignore[no-any-return]  # mypy: built came from getattr factory

    msg = "Cannot locate a _KNOWN_PREFIX_RE-compatible matcher on distill_cmds._helpers"
    raise AssertionError(msg)


@settings(max_examples=100, deadline=None)
@given(
    prefix=st.sampled_from(list(PREFIX_TO_CATEGORY)),
    tail=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=40,
    ),
)
def test_known_prefix_re_matches_plain_prefix(prefix: str, tail: str) -> None:
    """``_KNOWN_PREFIX_RE`` matches the bare ``prefix: subject`` shape."""
    matcher = _resolve_known_prefix_matcher()
    assert matcher(f"{prefix}: {tail}") is not None


@settings(max_examples=100, deadline=None)
@given(
    prefix=st.sampled_from(list(PREFIX_TO_CATEGORY)),
    scope=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=12,
    ),
    tail=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=40,
    ),
)
def test_known_prefix_re_matches_scoped_prefix(prefix: str, scope: str, tail: str) -> None:
    """``_KNOWN_PREFIX_RE`` matches ``prefix(scope): subject``."""
    matcher = _resolve_known_prefix_matcher()
    assert matcher(f"{prefix}({scope}): {tail}") is not None


@settings(max_examples=100, deadline=None)
@given(
    prefix=st.sampled_from(list(PREFIX_TO_CATEGORY)),
    tail=st.text(
        alphabet=st.characters(min_codepoint=97, max_codepoint=122),
        min_size=1,
        max_size=40,
    ),
)
def test_known_prefix_re_matches_breaking_prefix(prefix: str, tail: str) -> None:
    """``_KNOWN_PREFIX_RE`` matches ``prefix!: breaking-subject`` (breaking change)."""
    matcher = _resolve_known_prefix_matcher()
    assert matcher(f"{prefix}!: {tail}") is not None
