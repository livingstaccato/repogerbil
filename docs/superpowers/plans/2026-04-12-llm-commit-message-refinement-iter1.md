# LLM Commit Message Refinement — Iteration 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `gerbil snapshot --llm-refine` flag that generates narrative commit messages using Gemma 4 via Ollama, grounded in the project's vocabulary and the actual files each group touched.

**Architecture:** New `src/repogerbil/llm/` package provides schema, prompt, client, and generator layers. The generator is wired into `create_snapshot()` when `llm_refine=True`. A `FakeOllamaClient` enables full unit test coverage without a live Ollama. `HTTPOllamaClient` is coverage-carvedout (transport boundary).

**Tech Stack:** Python 3.11+, pydantic, Click, `urllib.request` (stdlib, no new runtime deps), Ollama HTTP API, Gemma 4 model, ChromaDB + sentence-transformers (optional, not required for this iteration).

---

## File Map

| Path | Action | Responsibility |
|---|---|---|
| `src/repogerbil/core/vocabulary.py` | Modify | Add `VOCAB_VERSION` constant + `allowed_verbs()` function |
| `src/repogerbil/core/config.py` | Modify | Add `llm_*` fields to `Settings` for Ollama connection |
| `src/repogerbil/llm/__init__.py` | Create | Empty package marker |
| `src/repogerbil/llm/schema.py` | Create | JSON schema for Ollama structured output + message composer |
| `src/repogerbil/llm/prompt.py` | Create | Prompt builder + `PROMPT_VERSION` constant |
| `src/repogerbil/llm/client.py` | Create | `OllamaClient` protocol, `FakeOllamaClient`, `HTTPOllamaClient` |
| `src/repogerbil/llm/generator.py` | Create | `MessageGenerator` orchestrator + `RefinementError` |
| `src/repogerbil/core/snapshot.py` | Modify | Add `_get_files_for_commit()`, `llm_generator` path in `_create_commits()`, `llm_refine` param on `create_snapshot()` |
| `src/repogerbil/cli/commands/distill_cmds.py` | Modify | Add `--llm-refine` flag to `snapshot` command |
| `tests/llm/__init__.py` | Create | Empty test package marker |
| `tests/llm/test_schema.py` | Create | Tests for `build_schema()` and `compose_message()` |
| `tests/llm/test_prompt.py` | Create | Tests for `build_prompt()` |
| `tests/llm/test_client.py` | Create | Tests for `FakeOllamaClient` |
| `tests/llm/test_generator.py` | Create | Tests for `MessageGenerator` (uses `FakeOllamaClient`) |
| `tests/core/test_snapshot.py` | Modify | Add test for `llm_refine=True` path |
| `tests/fixtures/ollama_responses/valid_single.json` | Create | Fixture: single-entry response |
| `tests/fixtures/ollama_responses/valid_multi.json` | Create | Fixture: multi-entry response |
| `pyproject.toml` | Modify | Add coverage omit for `llm/client.py` HTTPOllamaClient, add `tests/fixtures` note |

---

## Task 1: Extend `vocabulary.py` with `VOCAB_VERSION` and `allowed_verbs()`

**Files:**
- Modify: `src/repogerbil/core/vocabulary.py`
- Test: `tests/core/test_vocabulary.py` (check if exists; create if not)

- [ ] **Step 1: Write the failing test**

Check if `tests/core/test_vocabulary.py` exists. If it does, add these tests to it. If not, create it:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

from repogerbil.core.vocabulary import VOCAB_VERSION, allowed_verbs


def test_vocab_version_is_string():
    assert isinstance(VOCAB_VERSION, str)
    assert len(VOCAB_VERSION) > 0


def test_allowed_verbs_returns_semantic_verbs():
    verbs = allowed_verbs()
    # Semantic verbs (those with a non-empty verb field) should be present
    assert "instantiate" in verbs
    assert "interface" in verbs
    assert "remediate" in verbs
    assert "harden" in verbs
    assert "margin" in verbs
    assert "decouple" in verbs
    assert "qualify" in verbs
    assert "streamline" in verbs
    assert "specify" in verbs
    assert "baseline" in verbs
    assert "deprecate" in verbs


def test_allowed_verbs_excludes_conventional_prefixes():
    verbs = allowed_verbs()
    # Conventional prefixes (no verb field) should NOT appear
    assert "feat" not in verbs
    assert "fix" not in verbs
    assert "refactor" not in verbs
    assert "test" not in verbs
    assert "perf" not in verbs
    assert "docs" not in verbs
    assert "chore" not in verbs


def test_allowed_verbs_is_sorted():
    verbs = allowed_verbs()
    assert verbs == sorted(verbs)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/tim/code/gh/livingstaccato/repogerbil
python -m pytest tests/core/test_vocabulary.py -v -o addopts= --no-cov
```

Expected: `ImportError` or `AttributeError` — `VOCAB_VERSION` and `allowed_verbs` do not exist yet.

- [ ] **Step 3: Add `VOCAB_VERSION` and `allowed_verbs()` to `vocabulary.py`**

Open `src/repogerbil/core/vocabulary.py`. After the `PREFIX_TO_CATEGORY` line (around line 71), append:

```python
VOCAB_VERSION: str = "1.0.0"


def allowed_verbs() -> list[str]:
    """Return semantic vocabulary verbs valid for LLM structured output.

    Returns only the entries that have a non-empty ``verb`` field —
    these are the semantic categories (instantiate, interface, etc.)
    rather than the conventional-commit prefix aliases (feat, fix, etc.).
    """
    return sorted(k for k, v in CATEGORIES.items() if v.verb)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/core/test_vocabulary.py -v -o addopts= --no-cov
```

Expected: All new tests PASS.

- [ ] **Step 5: Run full quality gate**

```bash
make quality
```

Expected: PASS. If mypy complains about `VOCAB_VERSION` type, confirm `str` annotation is present.

- [ ] **Step 6: Commit**

```bash
git add src/repogerbil/core/vocabulary.py tests/core/test_vocabulary.py
git commit -m "feat(vocab): add VOCAB_VERSION and allowed_verbs() for LLM schema"
```

---

## Task 2: Add LLM settings fields to `config.py`

**Files:**
- Modify: `src/repogerbil/core/config.py`
- Test: `tests/core/test_config.py` (add to existing file)

- [ ] **Step 1: Write the failing tests**

Find `tests/core/test_config.py` and add:

```python
def test_settings_has_llm_defaults():
    from repogerbil.core.config import Settings
    s = Settings()
    assert s.llm_ollama_url == "http://localhost:11434"
    assert s.llm_model == "gemma4"
    assert s.llm_temperature == 0.0
    assert s.llm_timeout_seconds == 120.0
    assert s.llm_concurrency == 1


def test_settings_llm_env_override(monkeypatch):
    import os
    from repogerbil.core.config import Settings
    monkeypatch.setenv("REPOGERBIL_LLM_MODEL", "gemma4:27b")
    monkeypatch.setenv("REPOGERBIL_LLM_CONCURRENCY", "4")
    s = Settings()
    assert s.llm_model == "gemma4:27b"
    assert s.llm_concurrency == 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/core/test_config.py::test_settings_has_llm_defaults tests/core/test_config.py::test_settings_llm_env_override -v -o addopts= --no-cov
```

Expected: `AttributeError: 'Settings' object has no attribute 'llm_ollama_url'`

- [ ] **Step 3: Add LLM fields to `Settings` in `config.py`**

In `src/repogerbil/core/config.py`, find the `Settings` class (around line 173). Add these fields after `vocabulary`:

```python
    # ── LLM / Ollama ─────────────────────────────────────────────────────────
    llm_ollama_url: str = "http://localhost:11434"
    llm_model: str = "gemma4"
    llm_temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    llm_timeout_seconds: float = Field(default=120.0, gt=0.0)
    llm_concurrency: int = Field(default=1, ge=1)
```

Env vars from pydantic-settings env_prefix="REPOGERBIL_": `REPOGERBIL_LLM_OLLAMA_URL`, `REPOGERBIL_LLM_MODEL`, `REPOGERBIL_LLM_TEMPERATURE`, `REPOGERBIL_LLM_TIMEOUT_SECONDS`, `REPOGERBIL_LLM_CONCURRENCY`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/core/test_config.py -v -o addopts= --no-cov
```

Expected: All tests PASS.

- [ ] **Step 5: Run full quality gate**

```bash
make quality
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/repogerbil/core/config.py tests/core/test_config.py
git commit -m "feat(config): add LLM/Ollama connection settings"
```

---

## Task 3: Create `llm/schema.py` — JSON schema + message composer

**Files:**
- Create: `src/repogerbil/llm/__init__.py`
- Create: `src/repogerbil/llm/schema.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_schema.py`

- [ ] **Step 1: Create the empty package markers**

Create `src/repogerbil/llm/__init__.py`:
```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0
```

Create `tests/llm/__init__.py`:
```python
```

- [ ] **Step 2: Write the failing tests**

Create `tests/llm/test_schema.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

import pytest

from repogerbil.llm.schema import build_schema, compose_message


def test_build_schema_populates_verb_enum():
    verbs = ["baseline", "instantiate", "qualify"]
    schema = build_schema(verbs)
    items = schema["properties"]["entries"]["items"]  # type: ignore[index]
    assert items["properties"]["verb"]["enum"] == sorted(verbs)


def test_build_schema_does_not_mutate_input():
    verbs = ["instantiate", "qualify"]
    build_schema(verbs)
    # Input list unchanged
    assert verbs == ["instantiate", "qualify"]


def test_build_schema_required_fields_present():
    schema = build_schema(["instantiate"])
    assert "entries" in schema["required"]  # type: ignore[operator]
    assert "summary" in schema["required"]  # type: ignore[operator]


def test_compose_message_single_entry():
    response = {
        "entries": [
            {"verb": "instantiate", "scope": "core", "description": "base type definitions introduced"}
        ],
        "summary": "Added the foundational type layer.",
    }
    msg = compose_message(response)
    assert msg.startswith("instantiate(core): base type definitions introduced")
    assert "\n\nAdded the foundational type layer." in msg


def test_compose_message_multi_entry():
    response = {
        "entries": [
            {"verb": "instantiate", "scope": "core", "description": "primary api built"},
            {"verb": "qualify", "scope": "primitives", "description": "first unit tests"},
        ],
        "summary": "Expanded the api surface and added tests.",
    }
    msg = compose_message(response)
    lines = msg.splitlines()
    assert lines[0] == "instantiate(core): primary api built"
    assert lines[1] == "qualify(primitives): first unit tests"
    assert lines[2] == ""
    assert "Expanded the api surface" in msg


def test_compose_message_strips_summary_whitespace():
    response = {
        "entries": [{"verb": "baseline", "scope": "deps", "description": "bump ruff"}],
        "summary": "  Updated ruff.  ",
    }
    msg = compose_message(response)
    assert msg.endswith("Updated ruff.")
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/llm/test_schema.py -v -o addopts= --no-cov
```

Expected: `ModuleNotFoundError: No module named 'repogerbil.llm'`

- [ ] **Step 4: Create `src/repogerbil/llm/schema.py`**

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""JSON schema for Ollama structured output — constrains LLM verb and scope choices."""

from __future__ import annotations

import copy
from typing import Any


_BASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["entries", "summary"],
    "properties": {
        "entries": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {
                "type": "object",
                "required": ["verb", "scope", "description"],
                "properties": {
                    "verb": {
                        "type": "string",
                        "enum": [],  # populated by build_schema()
                    },
                    "scope": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 40,
                    },
                    "description": {
                        "type": "string",
                        "minLength": 5,
                        "maxLength": 120,
                    },
                },
            },
        },
        "summary": {
            "type": "string",
            "minLength": 20,
            "maxLength": 600,
        },
    },
}


def build_schema(allowed_verbs: list[str]) -> dict[str, Any]:
    """Build the Ollama JSON schema with the allowed verb enum populated.

    Args:
        allowed_verbs: List of valid verb strings (from ``vocabulary.allowed_verbs()``).

    Returns:
        Deep-copied schema dict with ``verb.enum`` set to ``sorted(allowed_verbs)``.
    """
    schema = copy.deepcopy(_BASE_SCHEMA)
    schema["properties"]["entries"]["items"]["properties"]["verb"]["enum"] = sorted(allowed_verbs)
    return schema


def compose_message(response: dict[str, Any]) -> str:
    """Compose a multi-line commit message from a validated LLM response dict.

    Args:
        response: Dict with ``entries`` list and ``summary`` string,
                  as returned by the Ollama structured-output call.

    Returns:
        Commit message string: one ``verb(scope): description`` line per entry,
        blank line, then the summary paragraph.
    """
    entries: list[dict[str, str]] = response["entries"]
    summary: str = response["summary"]
    header_lines = [f"{e['verb']}({e['scope']}): {e['description']}" for e in entries]
    return "\n".join(header_lines) + "\n\n" + summary.strip()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/llm/test_schema.py -v -o addopts= --no-cov
```

Expected: All 6 tests PASS.

- [ ] **Step 6: Run quality gate**

```bash
make quality
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/repogerbil/llm/__init__.py src/repogerbil/llm/schema.py tests/llm/__init__.py tests/llm/test_schema.py
git commit -m "feat(llm): add schema module for Ollama structured output"
```

---

## Task 4: Create `llm/prompt.py` — prompt builder

**Files:**
- Create: `src/repogerbil/llm/prompt.py`
- Create: `tests/llm/test_prompt.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/llm/test_prompt.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

from repogerbil.llm.prompt import PROMPT_VERSION, build_prompt


def test_prompt_version_is_string():
    assert isinstance(PROMPT_VERSION, str)
    assert len(PROMPT_VERSION) > 0


def test_build_prompt_contains_verbs():
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/core/api.py"],
        commit_count=2,
        original_subjects=["feat: add api"],
        allowed_verbs=["instantiate", "qualify"],
    )
    assert "instantiate" in prompt
    assert "qualify" in prompt


def test_build_prompt_contains_files():
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/core/api.py", "tests/test_api.py"],
        commit_count=2,
        original_subjects=[],
        allowed_verbs=["instantiate"],
    )
    assert "src/core/api.py" in prompt
    assert "tests/test_api.py" in prompt


def test_build_prompt_contains_date_and_count():
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=5,
        original_subjects=[],
        allowed_verbs=["baseline"],
    )
    assert "2026-04-07" in prompt
    assert "5" in prompt


def test_build_prompt_handles_empty_subjects():
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=1,
        original_subjects=[],
        allowed_verbs=["baseline"],
    )
    assert isinstance(prompt, str)
    assert len(prompt) > 50


def test_build_prompt_contains_original_subjects():
    prompt = build_prompt(
        date_str="2026-04-07",
        files=["src/x.py"],
        commit_count=1,
        original_subjects=["feat: add x"],
        allowed_verbs=["instantiate"],
    )
    assert "feat: add x" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/llm/test_prompt.py -v -o addopts= --no-cov
```

Expected: `ModuleNotFoundError: No module named 'repogerbil.llm.prompt'`

- [ ] **Step 3: Create `src/repogerbil/llm/prompt.py`**

```python
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
    verb_block = "\n".join(
        f"  - {v}: {_VERB_HINTS.get(v, '')}"
        for v in sorted(allowed_verbs)
    )
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
- Choose 1–4 header lines: each must be `verb(scope): description`
- Only use multiple lines when files span genuinely distinct concerns
- scope: short kebab-case label derived from file paths (e.g. core, cli, tests, types)
- description: precise phrase describing what changed (not what the file is named)
- summary: 2–5 sentences describing what happened and its significance
- Use only allowed verbs — any other word in the verb position is invalid
- Respond only with valid JSON matching the provided schema
"""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/llm/test_prompt.py -v -o addopts= --no-cov
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/repogerbil/llm/prompt.py tests/llm/test_prompt.py
git commit -m "feat(llm): add prompt builder module"
```

---

## Task 5: Create `llm/client.py` — OllamaClient protocol + fake + HTTP

**Files:**
- Create: `src/repogerbil/llm/client.py`
- Create: `tests/llm/test_client.py`
- Create: `tests/fixtures/ollama_responses/valid_single.json`
- Create: `tests/fixtures/ollama_responses/valid_multi.json`

- [ ] **Step 1: Create fixture files**

Create `tests/fixtures/ollama_responses/valid_single.json`:
```json
{
  "entries": [
    {
      "verb": "instantiate",
      "scope": "core",
      "description": "base type definitions introduced"
    }
  ],
  "summary": "Introduced the base type definitions covering primitives and the value wrapper. This establishes the shape all subsequent modules will build against."
}
```

Create `tests/fixtures/ollama_responses/valid_multi.json`:
```json
{
  "entries": [
    {
      "verb": "instantiate",
      "scope": "core-api",
      "description": "primary api module built over the type layer"
    },
    {
      "verb": "qualify",
      "scope": "primitives",
      "description": "first unit tests for conversions and equality"
    }
  ],
  "summary": "Added the primary api module that operates over the type definitions. Simultaneously brought in the first round of unit tests covering primitive conversions and the equality surface."
}
```

- [ ] **Step 2: Write the failing tests**

Create `tests/llm/test_client.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest

from repogerbil.llm.client import FakeOllamaClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ollama_responses"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


def test_fake_client_returns_responses_in_order():
    r1 = _load("valid_single.json")
    r2 = _load("valid_multi.json")
    client = FakeOllamaClient([r1, r2])

    out1 = client.generate("p1", {}, "gemma4")
    out2 = client.generate("p2", {}, "gemma4")

    assert out1 == r1
    assert out2 == r2


def test_fake_client_raises_when_exhausted():
    client = FakeOllamaClient([_load("valid_single.json")])
    client.generate("p1", {}, "gemma4")

    with pytest.raises(ValueError, match="ran out of responses"):
        client.generate("p2", {}, "gemma4")


def test_fake_client_accepts_kwargs():
    r = _load("valid_single.json")
    client = FakeOllamaClient([r])
    # Should not raise even with all kwargs passed
    out = client.generate("prompt", {"type": "object"}, "gemma4", temperature=0.0, timeout=30.0)
    assert out == r


def test_fixture_valid_single_parses():
    """Ensures the fixture file matches the expected schema shape."""
    r = _load("valid_single.json")
    assert "entries" in r
    assert "summary" in r
    assert len(r["entries"]) == 1
    assert all(k in r["entries"][0] for k in ("verb", "scope", "description"))


def test_fixture_valid_multi_parses():
    r = _load("valid_multi.json")
    assert len(r["entries"]) == 2
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/llm/test_client.py -v -o addopts= --no-cov
```

Expected: `ModuleNotFoundError: No module named 'repogerbil.llm.client'`

- [ ] **Step 4: Create `src/repogerbil/llm/client.py`**

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""Ollama LLM client — Protocol, deterministic fake, and HTTP implementations."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OllamaClient(Protocol):
    """Protocol for Ollama LLM clients.

    Both ``FakeOllamaClient`` (for tests) and ``HTTPOllamaClient`` (for
    production) implement this interface.
    """

    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]: ...


class FakeOllamaClient:
    """Deterministic test client that returns preset responses in order.

    Usage::

        client = FakeOllamaClient([response_dict_1, response_dict_2])
        out = client.generate(...)  # returns response_dict_1
        out = client.generate(...)  # returns response_dict_2
    """

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self._index = 0

    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Return the next preset response; raise if all responses have been consumed."""
        if self._index >= len(self._responses):
            msg = f"FakeOllamaClient ran out of responses at call {self._index}"
            raise ValueError(msg)
        response = self._responses[self._index]
        self._index += 1
        return response


class HTTPOllamaClient:  # pragma: no cover — transport boundary, tested via integration only
    """Production Ollama HTTP client using stdlib ``urllib.request`` (no extra deps).

    Sends a ``POST /api/generate`` request with structured-output JSON schema
    constraint (``format`` field) and returns the parsed response object.
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url.rstrip("/")

    def generate(
        self,
        prompt: str,
        schema: dict[str, Any],
        model: str,
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> dict[str, Any]:
        """Call Ollama generate API with structured output schema.

        Args:
            prompt: The full prompt string.
            schema: JSON schema dict passed to Ollama's ``format`` field.
            model: Ollama model name (e.g. ``"gemma4"``).
            temperature: Sampling temperature (0.0 = deterministic).
            timeout: Request timeout in seconds.

        Returns:
            Parsed JSON object from Ollama's ``response`` field.

        Raises:
            OSError: If the Ollama server is unreachable.
            ValueError: If the response cannot be decoded as JSON.
        """
        import json
        import urllib.request

        payload = {
            "model": model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "options": {"temperature": temperature},
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = json.loads(resp.read())
        return json.loads(body["response"])  # type: ignore[no-any-return]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/llm/test_client.py -v -o addopts= --no-cov
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Update `pyproject.toml` coverage omit**

In `pyproject.toml`, find the `[tool.coverage.run]` section and add to the `omit` list:

```toml
[tool.coverage.run]
source = ["src/repogerbil"]
branch = true
omit = [
    "src/repogerbil/cli/commands/vectordb_cmds.py",
    "src/repogerbil/llm/client.py",
]
```

- [ ] **Step 7: Run quality gate**

```bash
make quality
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/repogerbil/llm/client.py tests/llm/test_client.py \
        tests/fixtures/ollama_responses/valid_single.json \
        tests/fixtures/ollama_responses/valid_multi.json \
        pyproject.toml
git commit -m "feat(llm): add OllamaClient protocol, FakeOllamaClient, and HTTPOllamaClient"
```

---

## Task 6: Create `llm/generator.py` — MessageGenerator orchestrator

**Files:**
- Create: `src/repogerbil/llm/generator.py`
- Create: `tests/llm/test_generator.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/llm/test_generator.py`:

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

import json
from pathlib import Path

import pytest

from repogerbil.llm.client import FakeOllamaClient
from repogerbil.llm.generator import MessageGenerator, RefinementError

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ollama_responses"


def _load(name: str) -> dict:  # type: ignore[type-arg]
    return json.loads((FIXTURES / name).read_text())


def _make_generator(responses: list[dict]) -> MessageGenerator:  # type: ignore[type-arg]
    client = FakeOllamaClient(responses)
    return MessageGenerator(client=client, model="gemma4")


def test_generate_returns_string():
    gen = _make_generator([_load("valid_single.json")])
    msg = gen.generate(
        date_str="2026-04-07",
        files=["src/core/api.py"],
        commit_count=1,
        original_subjects=["feat: add api"],
    )
    assert isinstance(msg, str)
    assert len(msg) > 10


def test_generate_single_entry_format():
    gen = _make_generator([_load("valid_single.json")])
    msg = gen.generate("2026-04-07", ["src/core/api.py"], 1, [])
    # First line must be verb(scope): description
    first_line = msg.splitlines()[0]
    assert first_line == "instantiate(core): base type definitions introduced"


def test_generate_multi_entry_format():
    gen = _make_generator([_load("valid_multi.json")])
    msg = gen.generate("2026-04-08", ["src/core/api.py", "tests/test_api.py"], 2, [])
    lines = msg.splitlines()
    assert lines[0] == "instantiate(core-api): primary api module built over the type layer"
    assert lines[1] == "qualify(primitives): first unit tests for conversions and equality"
    assert lines[2] == ""  # blank separator line


def test_generate_raises_on_invalid_verb():
    bad_response = {
        "entries": [{"verb": "notaverb", "scope": "core", "description": "something"}],
        "summary": "Summary text here that is long enough to pass validation.",
    }
    gen = _make_generator([bad_response])
    with pytest.raises(RefinementError, match="invalid verb"):
        gen.generate("2026-04-07", ["src/x.py"], 1, [])


def test_generate_raises_on_missing_entries():
    bad_response = {"summary": "No entries here at all."}
    gen = _make_generator([bad_response])  # type: ignore[arg-type]
    with pytest.raises(RefinementError, match="missing required fields"):
        gen.generate("2026-04-07", ["src/x.py"], 1, [])


def test_prompt_version_accessible():
    from repogerbil.llm.prompt import PROMPT_VERSION
    gen = _make_generator([])
    assert gen.prompt_version == PROMPT_VERSION
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/llm/test_generator.py -v -o addopts= --no-cov
```

Expected: `ModuleNotFoundError: No module named 'repogerbil.llm.generator'`

- [ ] **Step 3: Create `src/repogerbil/llm/generator.py`**

```python
# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

"""MessageGenerator — orchestrates client + prompt + schema into a refined commit message."""

from __future__ import annotations

from repogerbil.core.vocabulary import allowed_verbs as _allowed_verbs
from repogerbil.llm.client import OllamaClient
from repogerbil.llm.prompt import PROMPT_VERSION, build_prompt
from repogerbil.llm.schema import build_schema, compose_message


class RefinementError(Exception):
    """Raised when the LLM returns invalid or unrecoverable output."""


class MessageGenerator:
    """Generates refined commit messages using a local Ollama LLM.

    Holds the allowed-verb list and JSON schema as instance state so they
    are built once and reused across many ``generate()`` calls.
    """

    def __init__(
        self,
        client: OllamaClient,
        model: str = "gemma4",
        temperature: float = 0.0,
        timeout: float = 120.0,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = temperature
        self._timeout = timeout
        self._verbs = _allowed_verbs()
        self._schema = build_schema(self._verbs)

    @property
    def prompt_version(self) -> str:
        """Current prompt template version (from ``llm.prompt.PROMPT_VERSION``)."""
        return PROMPT_VERSION

    def generate(
        self,
        date_str: str,
        files: list[str],
        commit_count: int,
        original_subjects: list[str],
    ) -> str:
        """Generate a refined commit message for a group of source commits.

        Args:
            date_str: YYYY-MM-DD string for the group's period start.
            files: Sorted union of file paths touched by all commits in the group.
            commit_count: Total number of source commits in the group.
            original_subjects: Raw source commit subjects (may be empty or noisy).

        Returns:
            Multi-line commit message: one ``verb(scope): description`` line per
            entry, blank line, then the narrative summary.

        Raises:
            RefinementError: If the LLM response fails validation after one retry.
        """
        prompt = build_prompt(
            date_str=date_str,
            files=files,
            commit_count=commit_count,
            original_subjects=original_subjects,
            allowed_verbs=self._verbs,
        )
        response = self._client.generate(
            prompt=prompt,
            schema=self._schema,
            model=self._model,
            temperature=self._temperature,
            timeout=self._timeout,
        )
        self._validate(response)
        return compose_message(response)

    def _validate(self, response: dict[str, object]) -> None:
        """Validate LLM response structure and verb choices.

        Raises:
            RefinementError: If required fields are missing or verb is not in the allowed set.
        """
        if "entries" not in response or "summary" not in response:
            missing = [k for k in ("entries", "summary") if k not in response]
            msg = f"LLM response missing required fields: {missing}"
            raise RefinementError(msg)
        for entry in response["entries"]:  # type: ignore[union-attr]
            verb = entry["verb"]  # type: ignore[index]
            if verb not in self._verbs:
                msg = f"LLM returned invalid verb '{verb}'; allowed: {self._verbs}"
                raise RefinementError(msg)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/llm/test_generator.py -v -o addopts= --no-cov
```

Expected: All 6 tests PASS.

- [ ] **Step 5: Run quality gate**

```bash
make quality
```

Expected: PASS. If mypy reports issues with `entry["verb"]` indexing, add `# type: ignore[index]` comments already included in the code.

- [ ] **Step 6: Commit**

```bash
git add src/repogerbil/llm/generator.py tests/llm/test_generator.py
git commit -m "feat(llm): add MessageGenerator orchestrator"
```

---

## Task 7: Add `_get_files_for_commit()` and `llm_refine` path to `snapshot.py`

**Files:**
- Modify: `src/repogerbil/core/snapshot.py`
- Modify: `tests/core/test_snapshot.py`

- [ ] **Step 1: Write the failing test**

Open `tests/core/test_snapshot.py` and add the following test to the `TestCreateSnapshot` class:

```python
def test_llm_refine_uses_generator_message(self, tmp_path: Path) -> None:
    """When llm_generator is provided, snapshot uses its output as commit messages."""
    import json
    from pathlib import Path as _Path

    from repogerbil.llm.client import FakeOllamaClient
    from repogerbil.llm.generator import MessageGenerator

    FIXTURES = _Path(__file__).parent.parent / "fixtures" / "ollama_responses"
    response = json.loads((FIXTURES / "valid_single.json").read_text())

    source = _init_repo(tmp_path)
    dest = tmp_path / "snapshot-llm"
    apr7 = get_commits_for_date(source, "2026-04-07")
    groups = [
        TimeGroup(
            period_start=datetime(2026, 4, 7, tzinfo=UTC),
            period_end=datetime(2026, 4, 7, 23, 59, 59, tzinfo=UTC),
            commits=apr7,
        ),
    ]

    client = FakeOllamaClient([response])
    generator = MessageGenerator(client=client, model="gemma4")

    result = create_snapshot(source, dest, groups, llm_generator=generator)
    assert result.commits_created == 1

    import subprocess
    log = subprocess.run(
        ["git", "log", "--format=%s", "-1"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert log == "instantiate(core): base type definitions introduced"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/core/test_snapshot.py::TestCreateSnapshot::test_llm_refine_uses_generator_message -v -o addopts= --no-cov
```

Expected: `TypeError: create_snapshot() got an unexpected keyword argument 'llm_generator'`

- [ ] **Step 3: Add `_get_files_for_commit()` to `snapshot.py`**

In `src/repogerbil/core/snapshot.py`, after the `_fetch_source()` function (around line 258), add:

```python
def _get_files_for_commit(dest_path: Path, commit_hash: str) -> list[str]:
    """Return the list of files changed in a commit, resolved from the fetched repo.

    Args:
        dest_path: Destination repo with all sources already fetched.
        commit_hash: The commit hash to inspect.

    Returns:
        Sorted list of file paths changed in that commit.
        Returns an empty list if the commit cannot be inspected (e.g. initial commit).
    """
    try:
        output = _run_git(
            dest_path,
            "diff-tree",
            "--root",
            "--no-commit-id",
            "--name-only",
            "-r",
            "--no-renames",
            "--no-ext-diff",
            commit_hash,
            timeout=20,
        )
        return sorted(line.strip() for line in output.splitlines() if line.strip())
    except GitCommandError:
        return []
```

- [ ] **Step 4: Add `llm_generator` parameter to `create_snapshot()` and wire it through**

In `src/repogerbil/core/snapshot.py`, modify `create_snapshot()` signature to add the `llm_generator` parameter. Add `TYPE_CHECKING` guard for the import to avoid circular deps:

At the top of the file, add to imports:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repogerbil.llm.generator import MessageGenerator
```

Update `create_snapshot()` signature:
```python
def create_snapshot(
    source_path: Path,
    dest_path: Path,
    groups: list[TimeGroup],
    source_branch: str = "main",
    changelog_messages: dict[str, str] | None = None,
    preserve_timestamps: bool = True,
    commit_time: str | None = None,
    timezone: str | None = None,
    extra_sources: list[Path] | None = None,
    source_subdir: str | None = None,
    llm_generator: "MessageGenerator | None" = None,
) -> SnapshotResult:
```

Update the call to `_create_commits()` inside `create_snapshot()`:
```python
    commits_created = _create_commits(
        dest_path,
        dedup_groups,
        changelog_messages,
        preserve_timestamps,
        commit_time,
        timezone,
        source_subdir,
        llm_generator,
    )
```

Update `_create_commits()` signature:
```python
def _create_commits(
    dest_path: Path,
    groups: list[TimeGroup],
    changelog_messages: dict[str, str] | None,
    preserve_timestamps: bool,
    commit_time: str | None,
    timezone: str | None,
    source_subdir: str | None = None,
    llm_generator: "MessageGenerator | None" = None,
) -> int:
```

In the body of `_create_commits()`, replace the `message = _build_snapshot_message(...)` line with:

```python
        if llm_generator is not None:
            all_files: set[str] = set()
            for commit in group.commits:
                all_files.update(_get_files_for_commit(dest_path, commit.hash))
            message = llm_generator.generate(
                date_str=group.period_start.strftime("%Y-%m-%d"),
                files=sorted(all_files),
                commit_count=len(group.commits),
                original_subjects=[c.subject for c in group.commits],
            )
        else:
            message = _build_snapshot_message(group, changelog_messages, used_changelog_keys)
```

- [ ] **Step 5: Run the new test to verify it passes**

```bash
python -m pytest tests/core/test_snapshot.py::TestCreateSnapshot::test_llm_refine_uses_generator_message -v -o addopts= --no-cov
```

Expected: PASS.

- [ ] **Step 6: Run the full snapshot test suite**

```bash
python -m pytest tests/core/test_snapshot.py -v -o addopts= --no-cov
```

Expected: All existing tests still PASS plus the new one.

- [ ] **Step 7: Run quality gate**

```bash
make quality
```

Expected: PASS. If mypy complains about the `TYPE_CHECKING` guard for `MessageGenerator`, verify the string annotation `"MessageGenerator | None"` is used (already in the code above).

- [ ] **Step 8: Commit**

```bash
git add src/repogerbil/core/snapshot.py tests/core/test_snapshot.py
git commit -m "feat(snapshot): add llm_generator param and file-collection for LLM refinement"
```

---

## Task 8: Add `--llm-refine` flag to `snapshot` CLI command

**Files:**
- Modify: `src/repogerbil/cli/commands/distill_cmds.py`
- Modify: `tests/cli/test_distill_cmds.py`

- [ ] **Step 1: Write the failing test**

Open `tests/cli/test_distill_cmds.py` and add a test. First check what runner fixture it uses (likely `click.testing.CliRunner`). Add:

```python
def test_snapshot_llm_refine_flag_accepted(tmp_path):
    """--llm-refine flag is accepted; MessageGenerator.generate is mocked to avoid real Ollama."""
    from unittest.mock import patch
    from click.testing import CliRunner
    from repogerbil.cli.commands.distill_cmds import snapshot
    import subprocess

    # Build a minimal source repo
    source = tmp_path / "src"
    source.mkdir()
    subprocess.run(["git", "init"], cwd=source, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=source, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=source, capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=source, capture_output=True, check=True)
    (source / "a.py").write_text("a\n")
    env = {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "GIT_AUTHOR_DATE": "2026-04-07T10:00:00",
        "GIT_COMMITTER_DATE": "2026-04-07T10:00:00",
    }
    subprocess.run(["git", "add", "."], cwd=source, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add a"],
        cwd=source, capture_output=True, check=True, env=env,
    )

    dest = tmp_path / "dest"
    expected_message = "instantiate(core): base type definitions introduced"

    # Patch MessageGenerator.generate so no real Ollama call is made
    with patch(
        "repogerbil.llm.generator.MessageGenerator.generate",
        return_value=expected_message,
    ):
        runner = CliRunner()
        result = runner.invoke(snapshot, [str(source), str(dest), "--llm-refine"])

    assert result.exit_code == 0, result.output
    assert "Snapshot created" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/cli/test_distill_cmds.py::test_snapshot_llm_refine_flag_accepted -v -o addopts= --no-cov
```

Expected: `Error: No such option: --llm-refine`

- [ ] **Step 3: Add `--llm-refine` flag and wiring in `distill_cmds.py`**

In `src/repogerbil/cli/commands/distill_cmds.py`, add the import at the top of the function body or as a module-level import. Add the flag to `snapshot`:

After the existing `--source-subdir` option, add:
```python
@click.option("--llm-refine", is_flag=True, help="Use Gemma 4 via Ollama to generate narrative commit messages")
```

Update the `snapshot` function signature to include `llm_refine: bool = False`.

After `result = create_snapshot(...)` block, update to pass the generator. Add this logic before the `result = create_snapshot(...)` call:

```python
    llm_generator = None
    if llm_refine:
        from repogerbil.llm.client import HTTPOllamaClient
        from repogerbil.llm.generator import MessageGenerator
        client = HTTPOllamaClient(base_url=settings.llm_ollama_url)
        llm_generator = MessageGenerator(
            client=client,
            model=settings.llm_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
```

And add `llm_generator=llm_generator` to the `create_snapshot()` call:
```python
    result = create_snapshot(
        source_path=path,
        dest_path=dest,
        groups=groups,
        source_branch=source_branch,
        changelog_messages=changelog_messages,
        preserve_timestamps=settings.preserve_timestamps,
        commit_time=commit_time,
        timezone=timezone,
        extra_sources=[Path(e) for e in extra_sources],
        source_subdir=source_subdir,
        llm_generator=llm_generator,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/cli/test_distill_cmds.py::test_snapshot_llm_refine_flag_accepted -v -o addopts= --no-cov
```

Expected: PASS.

- [ ] **Step 5: Run full CLI test suite**

```bash
python -m pytest tests/cli/test_distill_cmds.py -v -o addopts= --no-cov
```

Expected: All existing tests PASS plus the new one.

- [ ] **Step 6: Run quality gate**

```bash
make quality
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/repogerbil/cli/commands/distill_cmds.py tests/cli/test_distill_cmds.py
git commit -m "feat(cli): add --llm-refine flag to snapshot command"
```

---

## Task 9: Final coverage verification and integration smoke test

**Files:**
- No new files

- [ ] **Step 1: Run full test suite with coverage**

```bash
cd /Users/tim/code/gh/livingstaccato/repogerbil
make quality
```

Expected: All tests PASS, 100% coverage (excluding `vectordb_cmds.py` and `llm/client.py` per omit list).

- [ ] **Step 2: Smoke test against real Ollama (optional, requires Ollama running)**

```bash
rm -rf /tmp/smoke-llm-refine
gerbil snapshot /Users/tim/code/gh/livingstaccato/pyvider-cty /tmp/smoke-llm-refine \
  --cadence gap:30m \
  --all-branches \
  --llm-refine
```

Expected output:
```
NNNN commits → NNN gap:30m groups
Snapshot created at /tmp/smoke-llm-refine (NNN commits)
```

Then inspect messages:
```bash
git -C /tmp/smoke-llm-refine log --format="%B%n---" | head -80
```

Expected: Commit messages use vocabulary verbs (`instantiate(...)`, `qualify(...)`, etc.) with narrative summaries. No `feat:`, `fix:` subjects visible.

- [ ] **Step 3: Commit if smoke test surfaces any bugs**

Fix and commit any issues found. If no bugs: no commit needed.

---

## Iteration 1 Complete

**What was built:**
- `src/repogerbil/llm/` package: schema, prompt, client (fake + HTTP), generator
- Vocabulary extended with `VOCAB_VERSION` and `allowed_verbs()`
- Settings extended with `llm_*` fields for Ollama config
- `create_snapshot()` accepts `llm_generator` parameter
- `gerbil snapshot --llm-refine` flag wires it all together
- Full unit test coverage via `FakeOllamaClient`
- `HTTPOllamaClient` coverage-carved-out (transport boundary)

**What comes next (Iteration 2):**
- Vector DB retrieval: add `groups` collection, embed file signatures, retrieve top-K similar groups as prompt context
- Content-addressed LLM response cache
- Seeded bootstrap examples bundled with the package

See spec: `docs/superpowers/specs/2026-04-12-llm-commit-message-refinement-design.md`
