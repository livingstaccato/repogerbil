# CLAUDE.md

## Git Workflow
- Do not attempt git rollbacks. Changes are auto-committed and rollbacks will cause issues.
- Do not mention Claude or AI assistance in git commits. No Co-Authored-By lines.
- Use conventional commit prefixes (feat:, fix:, refactor:, test:, docs:, chore:, perf:, ci:).

## Code Quality
- 100% test coverage enforced. Every new function needs tests before commit.
- No file over 500 lines. If a file grows past 500, split into a module directory with `__init__.py` exports.
- mypy strict mode. No `type: ignore` without a comment explaining why.
- ruff lint + format must pass.
- All quality gates: `make quality` (lint, type-check, security, complexity, dead-code, test).

## Python Standards
- Use proper logging instead of print statements.
- PTH109: Replace `os.getcwd()` with `Path.cwd()`.
- Python >=3.11. Use modern typing (PEP 604 unions, PEP 585 generics).

## Architecture
- Core library in `src/repogerbil/core/` — pure functions, no CLI dependencies.
- CLI in `src/repogerbil/cli/` — Click commands, thin wrappers around core.
- Plugin in `plugins/repogerbil/` — shared skill + agent definitions for Claude Code and Codex. Load with `claude --plugin-dir ./plugins`.
- Config via pydantic-settings. File: `.repogerbil.toml`. Env prefix: `REPOGERBIL_`.

## Configuration & Environment
- No `os.environ` access scattered throughout code. All env vars go through pydantic-settings.
- No inline defaults for configurable values. Defaults live in the Settings model.
- No hardcoded paths. Use config or environment variables.
- No inline URLs/ports. Put them in config or at the top of the module.
- Pydantic models for public API surfaces (config, results, CLI-facing data).
- Dataclass/frozen dataclass for hot-path internals (cadence bucketing, git parsing).
