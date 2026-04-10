# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the release workflow."""

from pathlib import Path


def test_release_workflow_uses_ci_tooling_reusable_workflow() -> None:
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text()

    assert "provide-io/ci-tooling/workflows/python-release.yml@v0" in text
    assert 'tags:\n      - "v*"' in text
