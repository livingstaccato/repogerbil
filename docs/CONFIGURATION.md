# Configuration Reference

## File Discovery

repogerbil finds `.repogerbil.toml` by walking up from the current directory to the filesystem root — same pattern as `.git` discovery. If not found, it falls back to `~/.config/repogerbil/config.toml`.

This means you can place `.repogerbil.toml` in a parent directory and it will be found from any subdirectory.

**Search order:**
1. `.repogerbil.toml` in CWD
2. `.repogerbil.toml` in parent directories (walking up)
3. `~/.config/repogerbil/config.toml` (user-level fallback)

CLI flags and environment variables (`REPOGERBIL_*`) override the config file.

## Full Example

```toml
# .repogerbil.toml

# Commit grouping cadence for distill/snapshot
cadence = "daily"                    # hourly | daily | weekly | gap:NNm | gap:NNh

# How much of the commit message to capture
message_depth = "subject"            # subject | refs | full

# Auto-detect breaking changes (feat!: → architectural)
auto_breaking = true

# Depth for backfilling changelogs
backfill_depth = "heuristic"         # heuristic | thorough

# Depth for enrichment impact analysis
enrich_depth = "package"             # file | package | cross-repo

# Tolerance for stats verification (%)
tolerance = 20

# Preserve original timestamps when distilling
preserve_timestamps = true

# Create backup branch + tag before distill
create_backup = true

# Target branch name for distill output
target_branch = "repogerbil-consolidated"

# Ollama-backed snapshot message refinement
llm_ollama_url = "http://localhost:11434"
llm_model = "qwen3-coder-next:q8_0"
llm_temperature = 0.0
llm_timeout_seconds = 120.0
llm_concurrency = 1
llm_refine = false                     # auto-enable snapshot LLM refinement when true

# Multi-snapshot — label appended after the date on each daily commit's
# first line, e.g. "2026-05-24 my-platform". Override via the CLI flag
# --ecosystem-label or REPOGERBIL_ECOSYSTEM_LABEL.
ecosystem_label = "ecosystem"

# Multi-snapshot commit identity. When both are unset (the default), the
# destination repo inherits the user's global git config. Set both to
# override the author on every multi-snapshot commit.
snapshot_author_name = "Distill Bot"
snapshot_author_email = "distill@example.com"

# File rules — control how files are handled during --analyze
[[file_rules]]
pattern = "*.lock"
action = "bulk"                      # bulk | skip | classify
category = "baseline"
reason = "Lock file update"

[[file_rules]]
pattern = "*.pyc"
action = "skip"                      # ignore entirely

[[file_rules]]
pattern = "tests/**"
action = "classify"                  # keep in changes, force category
category = "qualify"

# Extra artifact patterns — appended to the built-in ARTIFACT_RULES used by
# `gerbil preflight`. Patterns are regex (re.search) applied to repo-relative
# paths. Built-ins always run first, so user patterns only match paths the
# built-ins did not classify. Invalid regex is rejected at config load.
[[extra_artifact_patterns]]
label = "snapshot tarball"
pattern = "snapshots/.*\\.tar\\.gz$"
# flag defaults to `pattern` (the ready-to-paste --exclude-path value)

# Per-repo overrides
[repos.uwarp-space]
backfill_depth = "thorough"
skip_dates = ["2025-03-15"]           # known artifact dates to ignore

[repos.provide-telemetry]
backfill_depth = "thorough"
message_depth = "refs"

[repos.tw2002]
# Archived repo — no source path, gap detection uses existing changelog range

# Tracked repos for missing/backfill commands
[tracked]
uwarp-space = "/path/to/uwarp-space"
provide-telemetry = "/path/to/provide-telemetry"
bbsbot = "/path/to/bbsbot"
tw2002 = ""                           # empty string = archived, no source
```

## Environment Variables

All settings can be overridden via environment variables with the `REPOGERBIL_` prefix:

```bash
REPOGERBIL_CADENCE=weekly
REPOGERBIL_TOLERANCE=30
REPOGERBIL_BACKFILL_DEPTH=thorough
REPOGERBIL_LLM_REFINE=true
```

## File Rule Actions

| Action | Behavior |
|--------|----------|
| `bulk` | Count toward bulk entries, remove from detailed changes |
| `skip` | Ignore entirely — not in stats, bulk, or changes |
| `classify` | Keep in changes but force the specified category |

## Resolution Priority

1. CLI flags (highest)
2. Environment variables (`REPOGERBIL_*`)
3. `.repogerbil.toml` found by walking up from CWD
4. `~/.config/repogerbil/config.toml` (user-level fallback)
5. Defaults (lowest)
