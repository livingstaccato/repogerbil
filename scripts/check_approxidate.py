#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Guard against the recurring git approxidate bug.

Background
----------
Git accepts ``--since`` and ``--until`` as *approxidates* — fuzzy date
expressions that, for a bare ``YYYY-MM-DD``, are evaluated as the moment the
parser happens to start. That means two ``git log`` calls a few seconds apart
can return *different* commit sets near the day boundary, which has bitten
us repeatedly (most recently the long-running flaky test in catch_up and a
GS-byte body corruption in ``_multi_snapshot._collect_day_context``).

The fix is to always pin the boundary explicitly:

* ``--since=YYYY-MM-DDT00:00:00`` for inclusive start-of-day
* ``--until=YYYY-MM-DDT23:59:59`` for inclusive end-of-day

Reference fixes:

* ``src/repogerbil/core/catch_up.py`` — pins both ``--since`` constructions
  with ``T00:00:00``.
* ``src/repogerbil/core/_multi_snapshot_git.py`` — pins ``--until`` with
  ``T23:59:59`` for the end-of-day tree lookup.
* ``src/repogerbil/core/preflight.py`` — routes both bounds through the
  shared ``_pin_iso_date`` helper.

This script statically scans ``src/repogerbil/`` for argv-construction sites
that build ``--since=<value>`` or ``--until=<value>`` strings. A site is
flagged unless one of the following pin signals is visible:

1. The same line literally contains ``T00:00:00`` (``--since``) or
   ``T23:59:59`` (``--until``).
2. The same line routes the value through the shared ``_pin_iso_date``
   helper.
3. The interpolated variable is assigned within the same file with a
   right-hand side that itself shows pin evidence (literal ``T00:00:00`` /
   ``T23:59:59`` or a ``_pin_iso_date(...)`` call).

Exits non-zero with ``path:line`` violations so CI fails loudly.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys

# Roots scanned for violations. Tests intentionally exclude themselves: test
# fixtures legitimately use bare-date approxidates to *reproduce* the bug.
SCAN_ROOTS: tuple[str, ...] = ("src/repogerbil",)

# Argv-construction sites: ``--since=`` / ``--until=`` immediately followed
# by an f-string interpolation. Plain doc / help-text mentions are skipped
# (they cannot affect git behavior).
_FLAG_RE = re.compile(r"--(?P<flag>since|until)=\{(?P<var>[A-Za-z_][A-Za-z_0-9]*)")

# Same-line pin signals. ``_pin_iso_date(...)`` is the shared helper; the
# literal ``T..:..:..`` markers cover f-strings that pin inline.
_PIN_INLINE_SINCE = re.compile(r"T00:00:00|_pin_iso_date\s*\(")
_PIN_INLINE_UNTIL = re.compile(r"T23:59:59|_pin_iso_date\s*\(")

# Assignment target — ``name = <rhs>`` (also handles ``name: type = <rhs>``).
_ASSIGN_RE = re.compile(
    r"^\s*(?P<name>[A-Za-z_][A-Za-z_0-9]*)\s*(?::\s*[^=]+)?=\s*(?P<rhs>.+)$",
)


def _iter_python_files(root: Path) -> list[Path]:
    """Yield every ``.py`` file under ``root`` in deterministic order."""
    return sorted(root.rglob("*.py"))


def _collect_variable_pin_status(lines: list[str]) -> dict[str, bool]:
    """Return ``{var_name: pinned}`` from assignment-style lines in the file.

    A name is considered pinned if *any* assignment of it has pin evidence
    on the RHS. This is intentionally lenient — once a variable is shown to
    carry a pinned value somewhere in the file, downstream uses inherit
    that guarantee for guard purposes.
    """
    status: dict[str, bool] = {}
    pin_any = re.compile(r"T00:00:00|T23:59:59|_pin_iso_date\s*\(")
    for line in lines:
        m = _ASSIGN_RE.match(line)
        if m is None:
            continue
        name = m.group("name")
        rhs = m.group("rhs")
        if pin_any.search(rhs):
            status[name] = True
        else:
            status.setdefault(name, False)
    return status


def _scan_file(path: Path) -> list[tuple[Path, int, str]]:
    """Return ``(path, line_number, line_text)`` tuples for each violation."""
    violations: list[tuple[Path, int, str]] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    var_pinned = _collect_variable_pin_status(lines)

    for idx, line in enumerate(lines):
        for m in _FLAG_RE.finditer(line):
            flag = m.group("flag")
            var = m.group("var")
            inline_re = _PIN_INLINE_SINCE if flag == "since" else _PIN_INLINE_UNTIL
            if inline_re.search(line):
                continue
            if var_pinned.get(var, False):
                continue
            violations.append((path, idx + 1, line.rstrip()))
    return violations


def main() -> int:
    """Return 1 if any unpinned approxidate is detected, 0 otherwise."""
    all_violations: list[tuple[Path, int, str]] = []
    for root_name in SCAN_ROOTS:
        root = Path(root_name)
        if not root.is_dir():
            sys.stderr.write(f"error: scan root not found: {root}\n")
            return 1
        for py in _iter_python_files(root):
            all_violations.extend(_scan_file(py))

    if not all_violations:
        return 0

    sys.stderr.write(
        "approxidate guard: unpinned --since=/--until= usage detected.\n"
        "Pin bare YYYY-MM-DD values with T00:00:00 (since) or T23:59:59 (until),\n"
        "or route through the _pin_iso_date helper. See scripts/check_approxidate.py.\n\n",
    )
    for path, line_no, text in all_violations:
        sys.stderr.write(f"  {path}:{line_no}: {text}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
