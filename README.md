# repogerbil

Git history documentation and consolidation tool.

Turns messy git histories into clean, documented daily commits by combining changelog generation with commit consolidation.

## Install

```bash
pip install repogerbil
# or
uv add repogerbil

# Run without a permanent install
uvx repogerbil --help

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

# Index changelogs for semantic search (requires vectordb extra)
gerbil index /path/to/changelogs

# Semantic search across all changelogs
gerbil search "security hardening" --top 5

# Find related cross-repo work
gerbil related provide-telemetry --date 2026-04-07
```

## Commands

| Command | What it does |
|---------|-------------|
| `status` | Show repo info: active dates, date range |
| `changelog` | Generate changelog YAML (draft, analyze, or prompt mode) |
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
| `lint` | Validate changelog YAML files against schema |
| `plugin` | Export or install bundled assistant plugin files |
| `index` | Index changelogs into vector database (requires `[vectordb]`) |
| `search` | Semantic search across changelogs (requires `[vectordb]`) |
| `related` | Find related work in other repos (requires `[vectordb]`) |

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
| `^\.claude(/\|$)` | `.claude/` directory at repo root |
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
# Codex: writes into ~/.agents/plugins/marketplace.json and ~/plugins/repogerbil
uvx repogerbil plugin install --target codex

# Claude Code: writes into ~/plugins/.claude-plugin/marketplace.json and ~/plugins/repogerbil
uvx repogerbil plugin install --target claude
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

Apache-2.0
