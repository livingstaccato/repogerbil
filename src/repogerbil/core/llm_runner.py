# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Dispatch a prompt to one of the available LLM runners.

Two paths are supported:

- ``claude-cli``: shell out to the ``claude`` CLI with ``-p`` (print mode).
  Requires the Claude Code CLI to be installed and on PATH. Returns the raw
  stdout from Claude as the synthesized changelog.
- ``agent``: emit dispatch instructions for the repogerbil analyzer subagent
  (meant for invocation from inside Claude Code, where the user's agent tool
  can consume the prompt directly). This path does not itself invoke an LLM;
  it prints the instructions the outer agent / user should follow.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess


class LlmRunnerError(Exception):
    """Raised when an LLM runner cannot complete its task."""


# Matches a full-document fence wrapping: leading ```<lang>\n ... \n``` trailing.
_FENCE_WRAPPER = re.compile(r"^\s*```[a-zA-Z0-9_+-]*\n(.*)\n```\s*$", re.DOTALL)


def strip_fence_wrapper(text: str) -> str:
    """Strip a single outer ``` ``` fence if the whole output is wrapped.

    LLMs often wrap their final answer in a ```markdown fenced block for
    display purposes; when we save that output to a .md file, the fences
    become literal content and Marked / GitHub render the whole thing as a
    code block. Strip exactly one layer if it wraps the entire payload;
    leave inner fences alone.
    """
    match = _FENCE_WRAPPER.match(text)
    return match.group(1) if match else text


def run_claude_cli(prompt: str, *, timeout: int = 600) -> str:
    """Feed ``prompt`` to the ``claude`` CLI via ``-p`` and return stdout.

    Raises ``LlmRunnerError`` if the CLI isn't installed or exits non-zero.
    The returned string has any outer ``` ``` wrapper fence stripped.
    """
    if shutil.which("claude") is None:
        raise LlmRunnerError(
            "'claude' CLI not on PATH. Install from https://docs.claude.com/en/docs/claude-code "
            "or pick a different runner with --run."
        )
    # S603/S607: 'claude' is resolved via shutil.which above; invoking by name
    # is the point (users have the CLI on PATH).
    result = subprocess.run(  # noqa: S603
        ["claude", "-p", prompt],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        raise LlmRunnerError(f"claude CLI failed (rc={result.returncode}): {result.stderr.strip()[:500]}")
    return strip_fence_wrapper(result.stdout)


def agent_dispatch_instructions(prompt_path: Path) -> str:
    """Return the message the outer agent (in Claude Code) should see.

    The analyzer agent is already defined in plugins/repogerbil/agents/analyzer.
    When this flow is invoked inside Claude Code, the outer agent reads this
    message, spawns the analyzer subagent with the prompt file as input, and
    passes back the result.
    """
    return (
        f"Analyzer dispatch requested.\n"
        f"  prompt-file: {prompt_path}\n"
        f"  subagent:    repogerbil:analyzer:analyzer\n"
        f"\n"
        f"Instruction: read the prompt file above, follow its 'Instructions'\n"
        f"section to write a Keep-a-Changelog markdown section, and write the\n"
        f"result to the --output path (or print to stdout if no --output).\n"
    )
