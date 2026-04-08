# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

# Vulture whitelist — fields/functions used by frameworks but not called directly

# Click CLI commands (registered via @cli.command decorator)
from repogerbil.cli.main import (
    audit,
    backfill,
    changelog,
    enrich,
    fix_stats,
    missing,
    squash,
    status,
    summary,
    verify,
)

# pydantic-settings hook (called by pydantic, not user code)
from repogerbil.core.config import Settings

Settings.model_config
Settings.settings_customise_sources

# VerifyResult fields (used by consumers)
from repogerbil.core.verify import VerifyResult

VerifyResult.reported_deletions
VerifyResult.reported_insertions
VerifyResult.actual_insertions
VerifyResult.actual_deletions
VerifyResult.accounted_files

# Suppress unused variable warnings for pydantic-settings signature params
_ = audit, backfill, changelog, enrich, fix_stats, missing, squash, status, summary, verify
