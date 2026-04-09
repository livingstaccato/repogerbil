# Repository Guidelines

## Project Structure & Module Organization

`src/repogerbil/` contains the package. Keep core logic in `src/repogerbil/core/` as pure, reusable functions with no CLI dependencies. Keep Click entrypoints thin in `src/repogerbil/cli/`, and treat `plugins/repogerbil/` as the shared plugin directory for Claude Code and Codex (skill and agent definitions live there, not in `src/`). Tests live in `tests/`, split by area (`tests/core/`, `tests/cli/`, plus `tests/test_integration.py`). Reference docs live in `docs/`, and small maintenance scripts live in `scripts/`.

## Build, Test, and Development Commands

Use `uv` for local setup and execution.

- `make install` installs all dependencies, including dev extras.
- `make lint` runs `ruff format --check` and `ruff check`.
- `make type-check` runs strict `mypy` over `src` and `tests`.
- `make test` runs `pytest` with branch coverage and a 100% coverage gate.
- `make quality` runs the full local gate: lint, typing, security, complexity, dead-code, and tests.
- `uv run gerbil --help` shows the CLI surface during development.

## Coding Style & Naming Conventions

Target Python 3.11+ with 4-space indentation, double quotes, and a max line length of 111. Prefer modern typing (`list[str]`, `X | None`) and keep `mypy` clean; avoid `type: ignore` unless it is justified inline. Follow the architectural split: no Click, Rich, or UI concerns inside `core/`. File size is capped at 500 lines by `scripts/check_max_loc.py`; split modules before they grow past that limit. Use snake_case for modules, functions, and test files.

## Testing Guidelines

Pytest is configured in `pyproject.toml`. Name files `test_*.py`, classes `Test*`, and functions `test_*`. Put fast isolated cases under the `unit` marker and git-heavy coverage under `integration`. Run `make test` before pushing; use `make test-cov` if you need the HTML coverage report. New behavior should ship with tests, because the repo enforces 100% coverage.

## Commit & Pull Request Guidelines

Commits follow conventional prefixes such as `feat:`, `fix:`, `refactor:`, `docs:`, and `chore:`; `commitlint` enforces this in hooks. Keep subject lines specific, for example `feat: add walk-up config discovery`. Do not mention AI assistance or add co-author trailers. For pull requests, include a short problem/solution summary, note any config or CLI impact, and paste the verification you ran (typically `make quality`). Add sample output when changing user-facing CLI behavior.
