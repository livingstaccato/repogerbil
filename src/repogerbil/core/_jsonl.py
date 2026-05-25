# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Shared JSONL iteration helper.

Both :mod:`repogerbil.core.catch_up` and :mod:`repogerbil.core.realign` walk
``.summaries.jsonl`` sidecars with nearly identical corrupt-line handling.
Their semantics differ in what to *do* with a corrupt line:

* ``catch_up`` — skip silently and continue (the record is unrecoverable, and
  no rewrite is happening so there is nothing to preserve).
* ``realign`` — preserve the raw text in the rewritten file so a single bad
  line cannot silently drop data, and bump a ``corrupt_lines`` counter.

To accommodate both, :func:`iter_jsonl_records` yields a tuple of
``(line_number, raw_line, record_or_None)`` so callers can branch on
``record is None`` to handle the corrupt case in whichever way their workflow
demands. Blank lines are filtered out entirely and never yielded.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def iter_jsonl_records(path: Path) -> Iterator[tuple[int, str, dict[str, Any] | None]]:
    """Yield ``(line_number, stripped_line, record_or_None)`` for each JSONL line.

    Blank lines are skipped silently and never yielded. Lines that fail to
    parse as JSON are yielded with ``record=None`` and a WARNING log; the
    caller decides whether to skip (catch_up) or preserve verbatim (realign).

    If ``path`` does not exist, the generator yields nothing.

    Args:
        path: Path to the JSONL sidecar.

    Yields:
        ``(line_number, stripped_line, parsed_record_or_None)`` triples.
        ``line_number`` is 1-based to match common file-reader conventions.
    """
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Skipping corrupt JSONL line %d in %s: %s",
                    lineno,
                    path,
                    exc,
                )
                yield lineno, line, None
                continue
            if not isinstance(rec, dict):
                # Treat non-dict JSON (e.g. a bare list/string) as corrupt for
                # our schema — callers expect a record dict.
                logger.warning(
                    "Skipping non-dict JSONL record on line %d in %s",
                    lineno,
                    path,
                )
                yield lineno, line, None
                continue
            yield lineno, line, rec
