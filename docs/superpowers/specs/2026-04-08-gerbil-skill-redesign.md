# /gerbil Skill Redesign

## Context

The `/gerbil` skill currently exposes 7 of 14 CLI commands and lacks config-aware behavior. It doesn't know about `.repogerbil.toml`, can't auto-detect `changelog_dir`, and misses powerful features like backfill, enrich, preview, snapshot, and vectordb search. All messometer features have been fully integrated into the CLI — the skill just hasn't caught up.

This redesign makes the skill comprehensive and intelligent: full command coverage, config auto-detection, and multi-step workflow patterns for common tasks.

## Design

### Structure

The SKILL.md has four sections:

1. **Preamble** — Config discovery and auto-detection
2. **Context-Aware Mode** — What to do when invoked without arguments
3. **Command Reference** — All 14 commands with key options
4. **Workflows** — Multi-step patterns for common tasks

### 1. Preamble: Config Discovery

When the skill is invoked, Claude should:

1. Walk up from cwd to find `.repogerbil.toml` (same walk-up logic the CLI uses)
2. Extract `changelog_dir` and `[tracked]` repos from config
3. Use these values to fill command arguments automatically instead of requiring the user to specify them

If no config is found, fall back to asking the user for paths.

### 2. Context-Aware Mode

When `/gerbil` is invoked without arguments:

1. Read `.repogerbil.toml` — extract `changelog_dir` and `tracked` repos
2. Run `gerbil status .` — repo name, active dates, date range
3. Run `gerbil audit .` — prefix adoption %
4. If `changelog_dir` exists, run `gerbil missing <changelog_dir> --config <config_path>` — show gaps
5. Suggest next actions based on state:
   - Missing dates exist → suggest "catch up" workflow
   - Low audit adoption → suggest `audit --show-bad`
   - No issues → suggest "document today" or "enrich"

### 3. Command Reference

All 14 CLI commands:

| Command | Args | Key Options | Description |
|---|---|---|---|
| `status` | `<repo>` | — | Repo info, active dates, date range |
| `changelog` | `<repo>` | `--date`, `--analyze`, `--prompt`, `--output-dir`, `--force`, `--message-depth` | Generate changelog YAML or LLM prompt |
| `fix-stats` | `<cl_dir> <repo>` | `--since` | Correct stats to match git |
| `verify` | `<cl_dir> <repo>` | `--since`, `--tolerance` | Check stats + file coverage |
| `enrich` | `<cl_dir> <repo>` | `--since`, `--depth` | Add per-section stats + impact |
| `distill` | `<repo>` | `--dry-run`, `--cadence`, `--since`, `--target-branch`, `--changelog-dir` | Consolidate commits on branch |
| `preview` | `<repo>` | `--cadence`, `--since` | Rich preview of distillation |
| `snapshot` | `<repo> <dest>` | `--cadence`, `--since`, `--source-branch`, `--changelog-dir` | Create independent distilled repo |
| `export-cadence` | `<repo>` | `--cadence`, `--since`, `-o` | JSON export of time-grouped commits |
| `audit` | `<repo>` | `--since`, `--show-bad` | Commit message prefix adoption |
| `summary` | `<cl_dir>` | `--year`, `--week`, `--output-dir`, `--prompt`, `--force` | Weekly cross-repo summary |
| `missing` | `<cl_dir>` | `--config` | Show missing changelog dates |
| `backfill` | `<cl_dir>` | `--config`, `--since` | Batch generate missing changelogs |
| `index` | `<cl_dir>` | `--db-path` | Index changelogs into vector DB* |
| `search` | `<query>` | `--top`, `--repo`, `--db-path` | Semantic search across changelogs* |
| `related` | `<repo>` | `--date`, `--top`, `--db-path` | Find related cross-repo work* |

*Requires `pip install repogerbil[vectordb]`. Check availability with `python -c "import chromadb"` before running. If not installed, suggest the install command.

### 4. Workflows

**"Catch up"** — Fill in missing changelogs:
```
gerbil missing <cl_dir> --config <config>
gerbil backfill <cl_dir> --config <config>
gerbil verify <cl_dir> <repo>
```

**"Document today"** — Generate and verify today's changelog:
```
gerbil changelog <repo> --date YYYY-MM-DD --analyze --output-dir <cl_dir>
gerbil verify <cl_dir> <repo>
gerbil enrich <cl_dir> <repo>
```

**"Clean up history"** — Consolidate commits:
```
gerbil preview <repo> --cadence daily
gerbil distill <repo> --dry-run --changelog-dir <cl_dir>
# confirm with user before proceeding
gerbil distill <repo> --changelog-dir <cl_dir>
```

**"Weekly report"** — Generate summary:
```
gerbil summary <cl_dir> --year YYYY --week NN --output-dir <cl_dir>/summaries
```

**"Search & discover"** (vectordb):
```
gerbil index <cl_dir>
gerbil search "query" --top 10
gerbil related <repo> --date YYYY-MM-DD
```

### 5. Important Notes

- Always `--dry-run` before `distill`. Distilling is destructive.
- Always `preview` before `distill` for a readable table view.
- Backup branches + tags are created automatically before distill.
- `--analyze` for complete changelogs, plain mode for draft skeletons.
- Config lives in `.repogerbil.toml` — check for per-repo overrides.

## Scope

Single file change: `src/repogerbil/plugin/plugins/repogerbil/skills/gerbil/SKILL.md`

No code changes — this is purely a skill documentation update.

## Verification

1. Load the plugin: `claude --plugin-dir ./src/repogerbil/plugin`
2. Invoke `/gerbil` with no arguments — verify it runs context-aware mode
3. Invoke `/gerbil catch up` — verify it chains the correct commands
4. Invoke `/gerbil search "test"` — verify it checks for vectordb extra first
