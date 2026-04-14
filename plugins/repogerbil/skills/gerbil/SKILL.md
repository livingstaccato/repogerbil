---
name: gerbil
description: Git history documentation, consolidation, and snapshot distillation — generate changelogs, verify stats, distill commits, audit prefix adoption, preflight inspect repos before snapshot, and search changelog archives. Context-aware when invoked without arguments.
user-invocable: true
---

# gerbil

Use this skill when the user wants to work with git history documentation, changelog generation, commit consolidation, history verification, or semantic search across changelogs.

## Preamble: Config Discovery

Before running commands, find the config file:

1. Walk up from the current working directory looking for `.repogerbil.toml`
2. Extract `changelog_dir` and `[tracked]` repos from the config
3. Use these values to fill command arguments automatically; do not ask for paths if the config already provides them

If no config is found, ask for the missing paths as needed.

## Context-Aware Mode (no arguments)

When invoked without arguments:

1. Read `.repogerbil.toml` and extract `changelog_dir` and `tracked` repos
2. Run `gerbil status .` and report repo name, active dates, and date range
3. Run `gerbil audit .` and report prefix adoption percentage
4. If `changelog_dir` is configured, run `gerbil missing <changelog_dir> --config <config_path>` to show gaps
5. Suggest next actions based on state:
   - Missing dates: suggest a catch-up workflow
   - Low prefix adoption: suggest `gerbil audit . --show-bad`
   - Everything clean: suggest "document today" or `enrich`

## Command Reference

| Command | Args | Key Options | Description |
|---|---|---|---|
| `status` | `<repo>` | — | Repo info, active dates, date range |
| `changelog` | `<repo>` | `--date`, `--analyze`, `--prompt`, `--output-dir`, `--force`, `--message-depth` | Generate changelog YAML or LLM prompt |
| `fix-stats` | `<cl_dir> <repo>` | `--since` | Correct stats to match git truth |
| `verify` | `<cl_dir> <repo>` | `--since`, `--tolerance` | Check stats accuracy and file coverage |
| `enrich` | `<cl_dir> <repo>` | `--since`, `--depth {file\|package\|cross-repo}` | Add per-section stats and impact |
| `distill` | `<repo>` | `--dry-run`, `--cadence`, `--since`, `--target-branch`, `--changelog-dir` | Consolidate commits on a branch (destructive) |
| `preview` | `<repo>` | `--cadence`, `--since` | Rich table preview of distillation |
| `preflight` | `<source>` | `--since`, `--until`, `--emit-flags`, `--verbose` | Inspect source repo — classify files as artifact/source/unknown, suggest exclude flags |
| `snapshot` | `<source> <dest>` | `--cadence`, `--since`, `--exclude-path`, `--time-window-start`, `--time-window-end`, `--timezone`, `--commit-time`, `--source-branch`, `--changelog-dir` | Create an independent repo with distilled history |
| `export-cadence` | `<repo>` | `--cadence`, `--since`, `-o` | JSON export of time-grouped commits |
| `audit` | `<repo>` | `--since`, `--show-bad` | Commit message prefix adoption |
| `summary` | `<cl_dir>` | `--year`, `--week`, `--output-dir`, `--prompt`, `--force` | Weekly cross-repo summary |
| `missing` | `<cl_dir>` | `--config` | Show missing changelog dates across tracked repos |
| `backfill` | `<cl_dir>` | `--config`, `--since` | Batch generate missing changelogs |
| `index` | `<cl_dir>` | `--db-path` | Index changelogs into vector DB* |
| `search` | `<query>` | `--top`, `--repo`, `--db-path` | Semantic search across changelogs* |
| `related` | `<repo>` | `--date`, `--top`, `--db-path` | Find related cross-repo work* |

*Requires `pip install repogerbil[vectordb]`. Before running vector DB commands, check availability with `python -c "import chromadb"`. If unavailable, suggest the install command.

## Workflows

### Catch up

```bash
gerbil missing <cl_dir> --config <config>
gerbil backfill <cl_dir> --config <config>
gerbil verify <cl_dir> <repo>
```

### Document today

```bash
gerbil changelog <repo> --date $(date +%Y-%m-%d) --analyze --output-dir <cl_dir>
gerbil verify <cl_dir> <repo>
gerbil enrich <cl_dir> <repo>
```

### Clean up history (same-repo, destructive)

```bash
gerbil preview <repo> --cadence daily
gerbil distill <repo> --dry-run --changelog-dir <cl_dir>
# Ask the user before proceeding: distilling is destructive
gerbil distill <repo> --changelog-dir <cl_dir>
```

### Snapshot a repo (independent copy, non-destructive)

```bash
# Step 1: inspect first — classify every committed file path
gerbil preflight <source>
# Step 2: copy suggested flags and build the snapshot command
gerbil preflight <source> --emit-flags
# Step 3: create the distilled snapshot
gerbil snapshot <source> <dest> \
  --cadence gap:15m \
  --exclude-path '__pycache__' \
  --exclude-path '(poetry|yarn|Pipfile|Gemfile|Cargo|composer|packages|uv)\.lock$' \
  --time-window-start 20:00 \
  --time-window-end 00:00 \
  --timezone America/Los_Angeles
```

Key snapshot options:
- `--exclude-path` — full Python `re.search()` regex, repeatable; strips matching paths from every committed tree
- `--time-window-start` / `--time-window-end` — spread commits across a daily window (`HH:MM`), proportional to file count + jitter; requires `--timezone`; mutually exclusive with `--commit-time`
- `--commit-time` — pin all commits to a fixed `HH:MM` time instead

### Weekly report

```bash
gerbil summary <cl_dir> --year YYYY --week NN --output-dir <cl_dir>/summaries
```

### Search and discover

```bash
gerbil index <cl_dir>
gerbil search "query" --top 10
gerbil related <repo> --date YYYY-MM-DD
```

## Important

- Always run `preview` and then `distill --dry-run` before `distill`. Distilling is destructive.
- Backup branches and tags are created automatically before distill, but verify first.
- Use `--analyze` for complete changelogs and plain mode for draft skeletons.
- Config lives in `.repogerbil.toml`; check for per-repo overrides in `[repos.<name>]`.
