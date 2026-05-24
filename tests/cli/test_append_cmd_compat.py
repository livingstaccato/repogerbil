# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Coverage tests for legacy CLI append command compatibility exports."""

from repogerbil.cli.commands import append_cmd as legacy_append_cmd, catch_up_cmd


def test_legacy_append_command_module_reexports() -> None:
    assert legacy_append_cmd.append_cmd is catch_up_cmd.catch_up_cmd
    assert legacy_append_cmd.append_alias_cmd is catch_up_cmd.legacy_append_alias_cmd
