# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Tests for the LLM runner dispatch helpers."""

from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from repogerbil.core.llm_runner import (
    LlmRunnerError,
    agent_dispatch_instructions,
    run_claude_cli,
)


def test_run_claude_cli_happy_path() -> None:
    completed = subprocess.CompletedProcess(
        args=["claude", "-p", "prompt"], returncode=0, stdout="## Changelog\n", stderr=""
    )
    with (
        patch("repogerbil.core.llm_runner.shutil.which", return_value="/usr/bin/claude"),
        patch("repogerbil.core.llm_runner.subprocess.run", return_value=completed) as mock_run,
    ):
        out = run_claude_cli("# prompt text")
    assert out == "## Changelog\n"
    args, kwargs = mock_run.call_args
    assert args[0] == ["claude", "-p", "# prompt text"]
    assert kwargs["capture_output"] is True


def test_run_claude_cli_not_installed() -> None:
    with (
        patch("repogerbil.core.llm_runner.shutil.which", return_value=None),
        pytest.raises(LlmRunnerError, match="not on PATH"),
    ):
        run_claude_cli("anything")


def test_run_claude_cli_nonzero_exit() -> None:
    completed = subprocess.CompletedProcess(
        args=["claude", "-p", "x"], returncode=2, stdout="", stderr="api error: boom"
    )
    with (
        patch("repogerbil.core.llm_runner.shutil.which", return_value="/usr/bin/claude"),
        patch("repogerbil.core.llm_runner.subprocess.run", return_value=completed),
        pytest.raises(LlmRunnerError, match="rc=2"),
    ):
        run_claude_cli("anything")


def test_agent_dispatch_instructions_contains_key_fields() -> None:
    msg = agent_dispatch_instructions(Path("/tmp/prompt.md"))
    assert "/tmp/prompt.md" in msg
    assert "repogerbil:analyzer:analyzer" in msg
    assert "Instruction:" in msg
