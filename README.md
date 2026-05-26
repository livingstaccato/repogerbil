# repogerbil

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/uv-package_manager-FF6B35.svg)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/livingstaccato/repogerbil/actions/workflows/ci.yml/badge.svg)](https://github.com/livingstaccato/repogerbil/actions/workflows/ci.yml)
[![Mutation](https://github.com/livingstaccato/repogerbil/actions/workflows/mutation.yml/badge.svg)](https://github.com/livingstaccato/repogerbil/actions/workflows/mutation.yml)

**Git history documentation and consolidation tool.**

Turns messy git histories into clean, documented daily commits by combining changelog generation with commit consolidation. Use it to produce per-day YAML changelog records, distill a noisy branch in place, or emit an entirely fresh repo with a clean derived history (private→public, monorepo→public, ecosystem→single timeline).

- **Source**: <https://github.com/livingstaccato/repogerbil>
- **Issues**: <https://github.com/livingstaccato/repogerbil/issues>
- **Releases**: <https://github.com/livingstaccato/repogerbil/releases>
- **Changelog**: [CHANGELOG.md](CHANGELOG.md)
- **Architecture**: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Configuration**: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- **Schema reference**: [docs/SCHEMA.md](docs/SCHEMA.md)
- **Vocabulary**: [docs/VOCABULARY.md](docs/VOCABULARY.md)
- **Vector DB design**: [docs/VECTOR-DB-DESIGN.md](docs/VECTOR-DB-DESIGN.md)
- **Assistant integration**: [docs/INTEGRATION.md](docs/INTEGRATION.md)

## Install

```bash
pip install repogerbil
# or
uv add repogerbil

# Run without a permanent install
uvx --from repogerbil gerbil --help

# Optional: vector database for semantic search
pip install repogerbil[vectordb]
```

## Quick Start

```bash
# See what's in a repo
gerbil status /path/to/repo

# Generate a changelog for today
gerbil changelog /path/to/repo --date 2026-04-07 --analyze

# Generate an LLM prompt with diffs
gerbil changelog /path/to/repo --date 2026-04-07 --prompt

# Generate a release-span changelog prompt
gerbil changelog-span /path/to/repo --from v0.3.21 --to v0.4.0 --output prompt.md

# Audit commit message quality
gerbil audit /path/to/repo --show-bad

# Verify changelog accuracy
gerbil verify /path/to/changelogs /path/to/repo

# Fix stats to match git truth
gerbil fix-stats /path/to/changelogs /path/to/repo

# Enrich changelogs with per-section stats + impact
gerbil enrich /path/to/changelogs /path/to/repo --depth package

# Generate weekly summary
gerbil summary /path/to/changelogs --year 2026 --week 15

# Show missing changelog dates across all tracked repos
gerbil missing /path/to/changelogs --config .repogerbil.toml

# Backfill all missing changelogs
gerbil backfill /path/to/changelogs --config .repogerbil.toml

# Preview a distill
gerbil distill /path/to/repo --dry-run

# Distill with changelog-based commit messages
gerbil distill /path/to/repo --changelog-dir /path/to/changelogs

# Inspect a source repo before distilling — surface artifacts to exclude
gerbil preflight /path/to/repo

# Emit ready-to-paste --exclude-path flags for gerbil snapshot
gerbil preflight /path/to/repo --emit-flags

# Create an independent distilled snapshot repo
gerbil snapshot /path/to/source /path/to/dest \
  --cadence gap:15m \
  --exclude-path '^\.claude(/|$)' \
  --exclude-path '\.lock$' \
  --time-window-start 20:00 \
  --time-window-end 00:00 \
  --timezone America/Los_Angeles

# Merge multiple repos into one ecosystem-labeled distilled snapshot
gerbil multi-snapshot /path/to/dest \
  --repo api:/path/to/api \
  --repo web:/path/to/web \
  --ecosystem-label my-platform \
  --timezone America/Los_Angeles

# Index changelogs for semantic search (requires vectordb extra)
gerbil index /path/to/changelogs

# Semantic search across all changelogs
gerbil search "security hardening" --top 5

# Find related cross-repo work
gerbil related provide-telemetry --date 2026-04-07

# Find similar file-change history from path signatures
gerbil similar src/repogerbil/cli/main.py tests/cli/test_main.py --top 5

# Search likely impact context from indexed path/diff history
gerbil impact "src/repogerbil/cli/main.py" --source filepaths --top 5
gerbil impact "retry backoff" --source diffs --top 5

# Record missing commit metadata in sidecar records after history changes
gerbil catch-up /path/to/repo /path/to/repo.summaries.jsonl
gerbil realign /path/to/repo /path/to/repo.summaries.jsonl
```

## Global Options

`--verbose` is a group-level flag (no short form — `-v` is reserved for per-command use such as `preflight -v`). Pass it at the group level, before the subcommand, to enable INFO-level logging from `repogerbil.*` loggers:

```bash
gerbil --verbose snapshot /path/to/source /path/to/dest --cadence daily
```

Without `--verbose`, logging defaults to WARNING level.

## Commands

| Command | What it does |
|---------|-------------|
| `status` | Show repo info: active dates, date range |
| `changelog` | Generate changelog YAML (draft, analyze, or prompt mode) |
| `changelog-span` | Generate a release-span prompt or synthesized changelog for `from..to` |
| `fix-stats` | Correct changelog stats to match git truth |
| `verify` | Check stats accuracy + file coverage |
| `enrich` | Add per-section stats + import impact to changelogs |
| `audit` | Report commit message prefix adoption |
| `preflight` | Scan a source repo — classify committed files as artifact/source/unknown, emit exclude flags |
| `snapshot` | Create an independent repo with distilled history |
| `multi-snapshot` | Merge multiple source repos into one distilled snapshot |
| `distill` | Consolidate commits into daily/weekly groups (same repo, destructive) |
| `distill-ecosystem` | Distill multiple repos in parallel with conventional commits |
| `preview` | Rich table preview of what distillation would produce |
| `export-cadence` | Export cadence-grouped commits as JSON |
| `probe` | Probe candidate commit sources for a repo/date pair |
| `summary` | Generate weekly cross-repo summary |
| `missing` | Show missing changelog dates across tracked repos |
| `backfill` | Batch generate changelogs for all missing dates |
| `catch-up` | Record missing HEAD commit metadata to a `.summaries.jsonl` sidecar |
| `append` | Legacy alias for `catch-up` |
| `realign` | Re-key legacy `.summaries.jsonl` records to current local commit SHAs |
| `lint` | Validate changelog YAML files against schema |
| `plugin` | Export or install bundled assistant plugin files |
| `index` | Index changelogs into vector database (requires `[vectordb]`) |
| `search` | Semantic search across changelogs (requires `[vectordb]`) |
| `related` | Find related work in other repos (requires `[vectordb]`) |
| `similar` | Find changelogs that touched similar file paths (requires `[vectordb]`) |
| `impact` | Search filepath/diff history for impact context (requires `[vectordb]`) |

## Snapshot Workflow

`snapshot` creates an entirely independent destination repo with a clean, distilled history derived from the source. The source is never modified.

```bash
# 1. Inspect the source repo — see what would be excluded
gerbil preflight /path/to/source
gerbil preflight /path/to/source --verbose   # also show source files
gerbil preflight /path/to/source --emit-flags  # print ready-to-paste flags

# 2. Create the snapshot
gerbil snapshot /path/to/source /path/to/dest \
  --cadence gap:15m \
  --exclude-path '__pycache__' \
  --exclude-path '(poetry|yarn|Pipfile|Gemfile|Cargo|composer|packages|uv)\.lock$' \
  --exclude-path '^\.claude(/|$)' \
  --time-window-start 20:00 \
  --time-window-end 00:00 \
  --timezone America/Los_Angeles
```

### `--exclude-path`

Full Python `re.search()` regex. Matched paths are stripped from every committed tree. Repeatable.

| Pattern | Excludes |
|---------|---------|
| `__pycache__` | All `__pycache__` dirs |
| `\.lock$` | All lock files |
| `^\.claude(/|$)` | `.claude/` directory at repo root |
| `^mutants/` | Mutation testing output |
| `\.bak$` | Stale backup files |

### `--time-window-start` / `--time-window-end`

Spread snapshot commits across a daily time window (`HH:MM` format). Commits are spaced proportionally by number of changed files with random jitter — makes reconstructed history look organic. Requires `--timezone`. Mutually exclusive with `--commit-time`.

```bash
--time-window-start 20:00 --time-window-end 00:00 --timezone America/Los_Angeles
# 3 commits on 2026-04-10 land at e.g. 20:14, 21:47, 23:22
```

Windows crossing midnight are supported (`23:00`–`01:00`).

### Preflight artifact categories

`preflight` classifies every committed file path against known artifact patterns:

| Category | Examples |
|----------|---------|
| Python bytecode | `__pycache__/`, `.pyc`, `.pyo`, `.pytest_cache`, `.mypy_cache` |
| Lock files | `poetry.lock`, `yarn.lock`, `go.sum`, `go.mod`, `package-lock.json` |
| Build artifacts | `dist/`, `build/`, `.egg-info/`, `.so`, `.zip` |
| Generated stubs | `.pyi` |
| Mutation testing | `mutants/`, `.meta` |
| Backup files | `.bak` |
| Coverage reports | `htmlcov/`, `.coverage`, `cov.xml`, `coverage.xml` |
| AI tool configs | `.claude/`, `.codex/`, `.cursor/`, `.aider/`, `.continue/` |
| IDE configs | `.idea/`, `.vscode/` |
| VCS meta | `CODEOWNERS` |
| Ephemeral docs | `HANDOFF.md`, `SCRATCH.md`, `NOTES.md`, `.provide/` |
| Tool configs | `.python-version`, `.actrc`, `.pyre_configuration` |
| Vendored deps | `vendor/`, `node_modules/` |
| Binary fixtures | `.msgpack` |
| OS noise | `.DS_Store`, `Thumbs.db` |

## Changelog Modes

- **Draft** (default): Skeleton with `Draft:` placeholders, commit subjects as points
- **Analyze** (`--analyze`): Complete changelog with real titles, summaries, grouped sections
- **Prompt** (`--prompt`): LLM-ready markdown with diffs for external analysis

## Reproducibility

- Non-LLM workflows are deterministic and reproducible for the same inputs/config.
- Snapshot time-window jitter is deterministic by default (stable seeded output).
- LLM-generated commit messages are the only intentionally non-deterministic surface.

## Vector Database

With `pip install repogerbil[vectordb]`, changelogs are indexed into 4 ChromaDB collections:

| Collection | What it stores |
|------------|----------------|
| `changelogs` | Title + summary embeddings with repo/date/stats/category/quality metadata |
| `changes` | Per-section title + point embeddings with category, severity, scope metadata |
| `filepaths` | Space-joined file paths per changelog |
| `diffs` | Optional per-file diff chunks when indexing with source repos |

Those collections support 7 practical search facets:

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

llm_ollama_url = "http://localhost:11434"
llm_model = "qwen3-coder-next:q8_0"
llm_temperature = 0.0
llm_timeout_seconds = 120.0
llm_concurrency = 1
llm_refine = false               # when true, snapshot/multi-snapshot auto-enable LLM refinement

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
message_depth = "refs"
skip_dates = ["2026-04-01"]

[tracked]
uwarp-space = "/path/to/uwarp-space"
provide-telemetry = "/path/to/provide-telemetry"
```

**Resolution order**: CLI flags > env vars (`REPOGERBIL_*`) > walked `.repogerbil.toml` > `~/.config/repogerbil/config.toml` > defaults

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

## AI Plugin Integration

repogerbil ships a shared plugin at `plugins/repogerbil/` with:
- **Skill** (`gerbil`): Context-aware changelog and history management
- **Agent** (`analyzer`): Deep diff analysis for thorough changelog generation
- **Claude manifest**: `plugins/repogerbil/.claude-plugin/plugin.json`
- **Codex manifest**: `plugins/repogerbil/.codex-plugin/plugin.json`

For Claude Code development and testing:

```bash
claude --plugin-dir ./plugins
```

Codex uses the same shared plugin directory, with local marketplace metadata in `.agents/plugins/marketplace.json`.

To install the bundled plugin files from an installed package:

```bash
# Codex: writes plugin files into ~/.codex/plugins/repogerbil and marketplace metadata into ~/.agents/plugins/marketplace.json
uvx --from repogerbil gerbil plugin install --target codex

# Claude Code: writes into ./plugins/repogerbil and ./plugins/.claude-plugin/marketplace.json from the current directory
uvx --from repogerbil gerbil plugin install --target claude
```

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

[Apache-2.0](LICENSE) — © 2026 provide.io llc. See [REUSE.toml](REUSE.toml) for SPDX metadata.
