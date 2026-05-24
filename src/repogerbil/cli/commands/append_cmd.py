# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Compatibility re-exports for legacy append command module names."""

from repogerbil.cli.commands.catch_up_cmd import catch_up_cmd, legacy_append_alias_cmd

append_cmd = catch_up_cmd
append_alias_cmd = legacy_append_alias_cmd
