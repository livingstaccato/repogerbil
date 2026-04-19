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
    strip_fence_wrapper,
)


def test_strip_fence_wrapper_removes_outer_markdown_fence() -> None:
    wrapped = "```markdown\n## [v0.3.33]\n\n### Features\n- x\n```"
    assert strip_fence_wrapper(wrapped) == "## [v0.3.33]\n\n### Features\n- x"


def test_strip_fence_wrapper_no_fence_returns_as_is() -> None:
    plain = "## [v0.3.33]\n\n### Features\n- x\n"
    assert strip_fence_wrapper(plain) == plain


def test_strip_fence_wrapper_preserves_inner_fences() -> None:
    wrapped = "```markdown\n## Title\n\n```python\ncode\n```\n\n- bullet\n```"
    out = strip_fence_wrapper(wrapped)
    assert out.startswith("## Title")
    assert "```python" in out
    assert "code" in out
    # trailing outer fence removed
    assert not out.endswith("```\n```")


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
