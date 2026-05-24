# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Coverage tests for legacy core append compatibility exports."""

from repogerbil.core import append as legacy_append, catch_up


def test_legacy_append_module_reexports_catch_up_symbols() -> None:
    assert legacy_append.record_missing_commits is catch_up.record_missing_commits
    assert legacy_append.append_new_commits is catch_up.append_new_commits
    assert legacy_append.CatchUpResult is catch_up.CatchUpResult
    assert legacy_append.AppendResult is catch_up.AppendResult
