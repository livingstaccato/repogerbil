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

Pytest is configured in `pyproject.toml`. Name files `test_*.py`, classes `Test*`, and functions `test_*`. Mark git-heavy coverage with the `integration` marker; `--strict-markers` is enabled, so do not invent new markers. Run `make test` before pushing; use `make test-cov` if you need the HTML coverage report. New behavior should ship with tests, because the repo enforces 100% coverage.

## Commit & Pull Request Guidelines

Commits follow conventional prefixes such as `feat:`, `fix:`, `refactor:`, `docs:`, and `chore:`; `commitlint` enforces this in hooks. Keep subject lines specific, for example `feat: add walk-up config discovery`. Do not mention AI assistance or add co-author trailers. For pull requests, include a short problem/solution summary, note any config or CLI impact, and paste the verification you ran (typically `make quality`). Add sample output when changing user-facing CLI behavior.

## Destructive Operations

Commands that mutate the SOURCE repository (rewrite history, force-push, rewrite refs in place) must surface their destructive scope to the user before doing the damage. The convention is `--confirm-source-<verb>` flags whose name describes the scope (e.g. `--confirm-source-write`).

Existing destructive commands are grandfathered into a warn-and-proceed behavior — changing them would break user scripts that already depend on the current surface — and new destructive commands take the stricter refuse-by-default stance.

- **Existing destructive commands** (currently only `gerbil distill`) MUST emit a prominent stderr warning that names the source repository and recommends the read-only alternative. They are allowed to warn-and-proceed for backwards compatibility; do not tighten this without a deprecation cycle.
- **New destructive commands** SHOULD prefer refuse-by-default behavior, requiring `--confirm-source-<verb>` to proceed and printing a short acknowledgement-instructions message when the flag is absent.
- **Help text MUST point to the read-only alternative** where one exists (`gerbil snapshot` for `distill`), so users see the safe path before they invoke the destructive command.

## Global flags

- `--verbose` — group-level Click flag (no short form; `-v` is reserved for per-command use such as `preflight -v`). Enables INFO-level logging from `repogerbil.*` loggers; without it, log output is at WARNING. Always pass at the group level (e.g. `gerbil --verbose snapshot ...`), never after the subcommand.

## Plugin Editing Workflow

The plugin lives in two places that must remain byte-identical:

- `plugins/repogerbil/` is the canonical source. Edit here.
- `src/repogerbil/assistant_plugins/repogerbil/` is a packaged mirror shipped with the wheel so `gerbil plugin install` works from an installed package.

When changing any plugin file:

1. Edit the canonical copy under `plugins/repogerbil/`.
2. Copy the same change into the mirror under `src/repogerbil/assistant_plugins/repogerbil/` (or vice versa — whichever you edited first).
3. Run `python scripts/check_plugin_sync.py` to confirm the trees match. The script exits non-zero on any drift, including byte-level differences in `SKILL.md`.

`make plugin-sync-copy` mirrors `plugins/repogerbil/` to `src/repogerbil/assistant_plugins/repogerbil/` via `rsync -a --delete` (byte-for-byte including deletions). It is a manual convenience and is not wired into `make quality` — run it after editing the canonical tree, then `make plugin-sync` to verify.
