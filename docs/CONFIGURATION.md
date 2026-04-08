# Configuration Reference

## File Location

repogerbil looks for `.repogerbil.toml` in the current directory, then `~/.config/repogerbil/config.toml`.

CLI flags override config file values. Environment variables (`REPOGERBIL_*`) override the config file but are overridden by CLI flags.

## Full Example

```toml
# .repogerbil.toml

# Commit grouping cadence for squash
cadence = "daily"                    # hourly | daily | weekly

# How much of the commit message to capture
message_depth = "subject"            # subject | refs | full

# Auto-detect breaking changes (feat!: → architectural)
auto_breaking = true

# Attach per-commit file lists in changelog points
include_files = true

# Depth for backfilling changelogs
backfill_depth = "heuristic"         # heuristic | thorough

# Depth for enrichment impact analysis
enrich_depth = "package"             # file | package | cross-repo

# Tolerance for stats verification (%)
tolerance = 20

# Preserve original timestamps when squashing
preserve_timestamps = true

# Create backup branch + tag before squash
create_backup = true

# Target branch name for squash output
target_branch = "repogerbil-consolidated"

# Where to write changelogs
output = "data-repo"                 # data-repo | source-repo
output_dir = ""                      # path (absolute or relative)

# Root directory for changelog output
changelog_dir = ""

# Standard commit scopes (cross-repo convention)
standard_scopes = ["go", "ts", "py", "ci", "freebsd", "deps", "docs"]

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

# Per-repo overrides
[repos.uwarp-space]
backfill_depth = "thorough"

[repos.provide-telemetry]
backfill_depth = "thorough"
message_depth = "refs"

# Tracked repos for missing/backfill commands
[tracked]
uwarp-space = "/Users/tim/code/gh/undef-games/uwarp-space"
provide-telemetry = "/Users/tim/code/gh/provide-io/provide-telemetry"
bbsbot = "/Users/tim/code/gh/undef-games/bbsbot"
```

## Environment Variables

All settings can be overridden via environment variables with the `REPOGERBIL_` prefix:

```bash
REPOGERBIL_CADENCE=weekly
REPOGERBIL_TOLERANCE=30
REPOGERBIL_BACKFILL_DEPTH=thorough
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
3. Project config (`.repogerbil.toml`)
4. User config (`~/.config/repogerbil/config.toml`)
5. Defaults (lowest)
