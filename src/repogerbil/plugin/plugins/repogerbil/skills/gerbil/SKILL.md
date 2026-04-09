---
name: gerbil
description: Git history documentation and consolidation — generate changelogs, verify stats, distill commits, audit prefix adoption, semantic search. Context-aware when invoked without arguments.
user-invocable: true
---

# gerbil

Use this skill when the user wants to work with git history documentation, changelog generation, commit consolidation, history verification, or semantic search across changelogs.

## Preamble: Config Discovery

Before running commands, find the config file:

1. Walk up from the current working directory looking for `.repogerbil.toml`
2. Extract `changelog_dir` and `[tracked]` repos from the config
3. Use these values to fill command arguments automatically — don't ask the user for paths if the config has them

If no config is found, ask the user for paths as needed.

## Context-Aware Mode (no arguments)

When invoked without arguments:

1. Read `.repogerbil.toml` — extract `changelog_dir` and `tracked` repos
2. Run `gerbil status .` — report repo name, active dates, date range
3. Run `gerbil audit .` — report prefix adoption %
4. If `changelog_dir` is configured, run `gerbil missing <changelog_dir> --config <config_path>` — show gaps
5. Suggest next actions based on state:
   - Missing dates → suggest "catch up" workflow
   - Low prefix adoption → suggest `gerbil audit . --show-bad`
   - Everything clean → suggest "document today" or "enrich"

## Command Reference

| Command | Args | Key Options | Description |
|---|---|---|---|
| `status` | `<repo>` | — | Repo info, active dates, date range |
| `changelog` | `<repo>` | `--date`, `--analyze`, `--prompt`, `--output-dir`, `--force`, `--message-depth` | Generate changelog YAML or LLM prompt |
| `fix-stats` | `<cl_dir> <repo>` | `--since` | Correct stats to match git truth |
| `verify` | `<cl_dir> <repo>` | `--since`, `--tolerance` | Check stats accuracy + file coverage |
| `enrich` | `<cl_dir> <repo>` | `--since`, `--depth {file\|package\|cross-repo}` | Add per-section stats + impact |
| `distill` | `<repo>` | `--dry-run`, `--cadence`, `--since`, `--target-branch`, `--changelog-dir` | Consolidate commits on a branch |
| `preview` | `<repo>` | `--cadence`, `--since` | Rich table preview of distillation |
| `snapshot` | `<repo> <dest>` | `--cadence`, `--since`, `--source-branch`, `--changelog-dir` | Create independent repo with distilled history |
| `export-cadence` | `<repo>` | `--cadence`, `--since`, `-o` | JSON export of time-grouped commits |
| `audit` | `<repo>` | `--since`, `--show-bad` | Commit message prefix adoption |
| `summary` | `<cl_dir>` | `--year`, `--week`, `--output-dir`, `--prompt`, `--force` | Weekly cross-repo summary |
| `missing` | `<cl_dir>` | `--config` | Show missing changelog dates across tracked repos |
| `backfill` | `<cl_dir>` | `--config`, `--since` | Batch generate missing changelogs |
| `index` | `<cl_dir>` | `--db-path` | Index changelogs into vector DB* |
| `search` | `<query>` | `--top`, `--repo`, `--db-path` | Semantic search across changelogs* |
| `related` | `<repo>` | `--date`, `--top`, `--db-path` | Find related cross-repo work* |

*Requires `pip install repogerbil[vectordb]`. Before running vectordb commands, check availability: `python -c "import chromadb"`. If not installed, suggest the install command.

## Workflows

### Catch up — fill in missing changelogs

```bash
gerbil missing <cl_dir> --config <config>
gerbil backfill <cl_dir> --config <config>
gerbil verify <cl_dir> <repo>
```

### Document today — generate and verify today's changelog

```bash
gerbil changelog <repo> --date $(date +%Y-%m-%d) --analyze --output-dir <cl_dir>
gerbil verify <cl_dir> <repo>
gerbil enrich <cl_dir> <repo>
```

### Clean up history — consolidate commits

```bash
gerbil preview <repo> --cadence daily
gerbil distill <repo> --dry-run --changelog-dir <cl_dir>
# ASK THE USER before proceeding — distilling is destructive
gerbil distill <repo> --changelog-dir <cl_dir>
```

### Weekly report — generate summary

```bash
gerbil summary <cl_dir> --year YYYY --week NN --output-dir <cl_dir>/summaries
```

### Search & discover — semantic search (vectordb)

```bash
gerbil index <cl_dir>
gerbil search "query" --top 10
gerbil related <repo> --date YYYY-MM-DD
```

## Important

- Always run `preview` then `distill --dry-run` before `distill`. Distilling is destructive.
- Backup branches + tags are created automatically before distill — but verify first.
- Use `--analyze` for complete changelogs, plain mode for draft skeletons.
- Config lives in `.repogerbil.toml` — check for per-repo overrides in `[repos.<name>]`.
