# repogerbil

Git history documentation and consolidation tool.

Turns messy git histories into clean, documented daily commits by combining changelog generation with commit consolidation.

## Install

```bash
pip install repogerbil
# or
uv add repogerbil
```

## Quick Start

```bash
# See what's in a repo
repogerbil status /path/to/repo

# Generate a changelog for today
repogerbil changelog /path/to/repo --date 2026-04-07 --analyze

# Generate an LLM prompt with diffs
repogerbil changelog /path/to/repo --date 2026-04-07 --prompt

# Audit commit message quality
repogerbil audit /path/to/repo --show-bad

# Verify changelog accuracy
repogerbil verify /path/to/changelogs /path/to/repo

# Fix stats to match git truth
repogerbil fix-stats /path/to/changelogs /path/to/repo

# Preview a squash
repogerbil squash /path/to/repo --dry-run

# Squash with changelog-based commit messages
repogerbil squash /path/to/repo --changelog-dir /path/to/changelogs
```

## Commands

| Command | What it does |
|---------|-------------|
| `status` | Show repo info: active dates, date range |
| `changelog` | Generate changelog YAML (draft, analyze, or prompt mode) |
| `fix-stats` | Correct changelog stats to match git truth |
| `verify` | Check stats accuracy + file coverage |
| `squash` | Consolidate commits into daily/weekly groups |
| `audit` | Report commit message prefix adoption |

## Changelog Modes

- **Draft** (default): Skeleton with TODO placeholders, commit subjects as points
- **Analyze** (`--analyze`): Complete changelog with real titles, summaries, grouped sections
- **Prompt** (`--prompt`): LLM-ready markdown with diffs for external analysis

## Configuration

Create `.repogerbil.toml` in your project root:

```toml
cadence = "daily"
message_depth = "subject"       # subject | refs | full
backfill_depth = "heuristic"    # heuristic | thorough
tolerance = 20                  # verify_stats % tolerance

[[file_rules]]
pattern = "*.lock"
action = "bulk"
category = "baseline"
reason = "Lock file update"

[[file_rules]]
pattern = "*.pyc"
action = "skip"

[repos.my-important-repo]
backfill_depth = "thorough"
```

**Resolution order**: CLI flags > env vars (`REPOGERBIL_*`) > `.repogerbil.toml` > defaults

## Vocabulary

Changelogs use a structured vocabulary for categories and severities:

| Category | Conventional | Description |
|----------|-------------|-------------|
| `instantiate` | feat | New capability or feature |
| `remediate` | fix | Bug fix |
| `decouple` | refactor | Reduce coupling, improve modularity |
| `deprecate` | remove | Retire dead/unused code |
| `interface` | feat | Define connections between subsystems |
| `specify` | docs | Documentation, specs |
| `qualify` | test | Tests, verification |
| `margin` | fix | Add buffer/slack (timeouts, limits) |
| `harden` | fix | Resist failure/attack (validation, retries) |
| `streamline` | perf | Performance optimization |
| `baseline` | chore | Dependencies, config, environment |

| Severity | Semver | Description |
|----------|--------|-------------|
| `architectural` | major | Breaking change or foundational redesign |
| `behavioral` | minor | Observable behavior change |
| `internal` | patch | Implementation detail only |
| `errata` | — | Cosmetic, near-invisible |

## File Rules

Control how files are handled during `--analyze`:

- **bulk**: Count toward bulk entries, remove from detailed changes
- **skip**: Ignore entirely (not in stats, bulk, or changes)
- **classify**: Keep in changes but force a specific category

## Claude Code Plugin

repogerbil includes a Claude Code plugin with:
- **Skill** (`/repogerbil`): Context-aware changelog and history management
- **Agent** (`analyzer`): Deep diff analysis for thorough changelog generation

Plugin files are in `src/repogerbil/plugin/`.

## Development

```bash
uv sync --all-extras
make quality          # Run all quality gates
make test             # Run tests (100% coverage required)
make lint             # ruff format + check
make type-check       # mypy strict
make security         # bandit
make complexity       # xenon
make dead-code        # vulture
make mutation         # mutmut
```

## License

Apache-2.0
