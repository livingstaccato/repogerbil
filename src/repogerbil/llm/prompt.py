# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Prompt builder for commit message refinement (Iteration 1 — no retrieval)."""

from __future__ import annotations

PROMPT_VERSION: str = "1.0.0"

_VERB_HINTS: dict[str, str] = {
    "instantiate": "introducing new code, types, or modules",
    "interface": "wiring two subsystems together",
    "remediate": "fixing a bug or incorrect behaviour",
    "harden": "adding defensive handling, error hierarchy, or boundary checks",
    "margin": "adding buffer, tolerances, or safety margins",
    "decouple": "restructuring without behaviour change (refactor)",
    "qualify": "adding or extending test coverage",
    "streamline": "improving performance or reducing overhead",
    "specify": "adding documentation, comments, or reference material",
    "baseline": "maintenance, config, dependency, or build changes",
    "deprecate": "removing or marking functionality for removal",
}


def build_prompt(
    date_str: str,
    files: list[str],
    commit_count: int,
    original_subjects: list[str],
    allowed_verbs: list[str],
) -> str:
    """Build a refinement prompt for a commit group (no retrieval context).

    Args:
        date_str: YYYY-MM-DD string for the group's period start.
        files: Sorted list of file paths touched by commits in this group.
        commit_count: Total number of source commits in this group.
        original_subjects: Raw commit subjects from source (may be empty or inaccurate).
        allowed_verbs: Vocabulary verbs the LLM must choose from.

    Returns:
        Prompt string to send to the LLM.
    """
    verb_block = "\n".join(f"  - {v}: {_VERB_HINTS.get(v, '')}" for v in sorted(allowed_verbs))
    file_block = "\n".join(f"  - {f}" for f in sorted(files))
    if original_subjects:
        subject_block = "\n".join(f"  - {s}" for s in original_subjects)
    else:
        subject_block = "  (none available)"

    return f"""You are writing a commit message for a reconstructed git history.
The commit represents {commit_count} source commit(s) from {date_str}.

## Allowed verbs (use ONLY these — no others)
{verb_block}

## Files changed in this group
{file_block}

## Original commit subjects (may be absent, inaccurate, or terse)
{subject_block}

## Instructions
- Choose 1-4 header lines: each must be `verb(scope): description`
- Only use multiple lines when files span genuinely distinct concerns
- scope: short kebab-case label derived from file paths (e.g. core, cli, tests, types)
- description: precise phrase describing what changed (not what the file is named)
- summary: 2-5 sentences describing what happened and its significance
- Use only allowed verbs — any other word in the verb position is invalid
- Respond only with valid JSON matching the provided schema
"""
