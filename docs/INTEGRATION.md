# Integration Guide

## With repo-reports

repo-reports is a data repository containing YAML changelogs and weekly summaries. repogerbil is the tool that generates, verifies, and maintains that data.

### Setup

```toml
# .repogerbil.toml (in repo-reports root or your home config)

changelog_dir = "/Users/tim/code/gh/livingstaccato/repo-reports"

[tracked]
uwarp-space = "/Users/tim/code/gh/undef-games/uwarp-space"
provide-telemetry = "/Users/tim/code/gh/provide-io/provide-telemetry"
bbsbot = "/Users/tim/code/gh/undef-games/bbsbot"
# ... all tracked repos
```

### Workflow

```bash
# Check what's missing
repogerbil missing /path/to/repo-reports --config .repogerbil.toml

# Backfill all gaps
repogerbil backfill /path/to/repo-reports --config .repogerbil.toml

# Generate today's changelogs
repogerbil changelog /path/to/repo --date $(date +%Y-%m-%d) --analyze --output-dir /path/to/repo-reports

# Fix any stats drift
repogerbil fix-stats /path/to/repo-reports/uwarp-space /path/to/uwarp-space

# Verify everything
repogerbil verify /path/to/repo-reports/uwarp-space /path/to/uwarp-space

# Generate weekly summary
repogerbil summary /path/to/repo-reports --year 2026 --week 15 --output-dir /path/to/repo-reports/summaries
```

## With messometer

messometer was the predecessor for commit consolidation. repogerbil's `distill` command replaces messometer's `auto` and `apply` commands.

### Migration

| messometer | repogerbil |
|-----------|------------|
| `messometer extract --cadence daily` | `repogerbil changelog --analyze` |
| `messometer auto ./snapshot --cadence daily` | `repogerbil distill --changelog-dir` |
| `messometer apply --script consolidate.sh` | `repogerbil distill` (no script step) |
| `messometer status` | `repogerbil status` |

### Key Differences

- repogerbil uses changelog YAML as commit messages (messometer used generic "Snapshot for day" text)
- repogerbil creates backup tag + branch (messometer created branch only)
- repogerbil classifies commits by vocabulary (messometer had no classification)

## With Claude Code

### Plugin Installation

```bash
# Copy plugin files to Claude Code plugins directory
cp -r src/repogerbil/plugin ~/.claude/plugins/repogerbil
```

### Usage

```
/repogerbil                     # context-aware — detects repo, suggests work
/repogerbil audit --show-bad    # direct command
/repogerbil catch up            # conversational — asks what to do
```

## With Hugo (sight/staccato-hugo)

repogerbil generates YAML changelogs that `tools/generate_hugo_data.py` in repo-reports converts to Hugo-compatible JSON for the livingstaccato.com site. The pipeline:

```
repogerbil changelog → YAML → generate_hugo_data.py → JSON → Hugo → site
```
