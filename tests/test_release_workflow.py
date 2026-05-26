# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for the release workflow."""

from pathlib import Path


def test_release_workflow_uses_ci_tooling_reusable_workflow() -> None:
    """Release workflow must delegate to the provide-io ci-tooling reusable.

    The pinned version is the canonical family standard (v0.4.2); bump in
    lockstep with sibling repos when ci-tooling cuts a new release.
    """
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text()

    assert "provide-io/ci-tooling/.github/workflows/python-release.yml@v0.4.2" in text


def test_release_workflow_triggers_on_release_published() -> None:
    """Trigger model: cut a GH release; the workflow handles the rest."""
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text()

    assert "release:\n    types: [published]" in text


def test_release_workflow_publishes_to_pypi_and_testpypi() -> None:
    """Pipeline must include TestPyPI publish + verify before PyPI publish.

    Mirrors the provide-io family flow so PyPI Trusted Publishing OIDC
    matches against this repo's release.yml (reusable workflows do not
    match by `job_workflow_ref`).
    """
    workflow = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"
    text = workflow.read_text()

    assert "publish-testpypi:" in text
    assert "verify-testpypi:" in text
    assert "publish-pypi:" in text
    assert "needs: verify-testpypi" in text
