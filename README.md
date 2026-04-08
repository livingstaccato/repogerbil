# repogerbil

Git history documentation and consolidation tool.

Turns messy git histories into clean, documented daily commits by combining changelog generation with commit consolidation.

## Install

```bash
pip install repogerbil
# or
uv add repogerbil

# Optional: vector database for semantic search
pip install repogerbil[vectordb]
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

# Enrich changelogs with per-section stats + impact
repogerbil enrich /path/to/changelogs /path/to/repo --depth package

# Generate weekly summary
repogerbil summary /path/to/changelogs --year 2026 --week 15

# Show missing changelog dates across all tracked repos
repogerbil missing /path/to/changelogs --config .repogerbil.toml

# Backfill all missing changelogs
repogerbil backfill /path/to/changelogs --config .repogerbil.toml

# Preview a squash
repogerbil squash /path/to/repo --dry-run

# Squash with changelog-based commit messages
repogerbil squash /path/to/repo --changelog-dir /path/to/changelogs

# Index changelogs for semantic search (requires vectordb extra)
repogerbil index /path/to/changelogs

# Semantic search across all changelogs
repogerbil search "security hardening" --top 5

# Find related cross-repo work
repogerbil related provide-telemetry --date 2026-04-07
```

## Commands

| Command | What it does |
|---------|-------------|
| `status` | Show repo info: active dates, date range |
| `changelog` | Generate changelog YAML (draft, analyze, or prompt mode) |
| `fix-stats` | Correct changelog stats to match git truth |
| `verify` | Check stats accuracy + file coverage |
| `enrich` | Add per-section stats + import impact to changelogs |
| `squash` | Consolidate commits into daily/weekly groups |
| `audit` | Report commit message prefix adoption |
| `summary` | Generate weekly cross-repo summary |
| `missing` | Show missing changelog dates across tracked repos |
| `backfill` | Batch generate changelogs for all missing dates |
| `index` | Index changelogs into vector database (requires `[vectordb]`) |
| `search` | Semantic search across changelogs (requires `[vectordb]`) |
| `related` | Find related work in other repos (requires `[vectordb]`) |

## Changelog Modes

- **Draft** (default): Skeleton with TODO placeholders, commit subjects as points
- **Analyze** (`--analyze`): Complete changelog with real titles, summaries, grouped sections
- **Prompt** (`--prompt`): LLM-ready markdown with diffs for external analysis

## Vector Database

With `pip install repogerbil[vectordb]`, changelogs are indexed with 7 data dimensions:

| Dimension | What it enables |
|-----------|-----------------|
| Title + summary | Semantic search across repos |
| Change sections | Per-section search, category filtering |
| File paths | "What else changed when login.py was modified?" |
| Diff content (opt-in) | Code-level semantic search |
| Category distribution | Work pattern matching |
| Scopes | `search --scope parity` across all repos |
| Quality metrics | Surface changelogs needing the most work |

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

[tracked]
uwarp-space = "/path/to/uwarp-space"
provide-telemetry = "/path/to/provide-telemetry"
```

**Resolution order**: CLI flags > env vars (`REPOGERBIL_*`) > `.repogerbil.toml` > defaults

## Vocabulary

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
