# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""repogerbil — Git history documentation and consolidation tool."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
import logging

# Library hygiene: attach a NullHandler so callers that do not configure
# logging do not see "No handlers could be found for logger ..." warnings.
logging.getLogger("repogerbil").addHandler(logging.NullHandler())

try:
    __version__ = version("repogerbil")
except PackageNotFoundError:  # pragma: no cover — only when running from an
    # uninstalled source tree.
    __version__ = "0.0.0+unknown"

__all__: list[str] = ["__version__"]
