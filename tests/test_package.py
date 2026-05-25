# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Package-level tests for :mod:`repogerbil`."""

from __future__ import annotations

import logging

import repogerbil  # noqa: F401 — imported to ensure side-effecting init runs


def test_package_logger_has_null_handler_attached() -> None:
    """The package root logger should carry a NullHandler so library callers
    that haven't configured logging don't see "No handlers could be found"
    warnings.
    """
    logger = logging.getLogger("repogerbil")
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers), (
        f"expected a NullHandler on the 'repogerbil' logger, got handlers={logger.handlers!r}"
    )
