# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""repogerbil — Git history documentation and consolidation tool."""

from __future__ import annotations

import logging

# Library hygiene: attach a NullHandler so callers that do not configure
# logging do not see "No handlers could be found for logger ..." warnings.
logging.getLogger("repogerbil").addHandler(logging.NullHandler())

__all__: list[str] = []
