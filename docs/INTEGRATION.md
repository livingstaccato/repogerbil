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
gerbil missing /path/to/repo-reports --config .repogerbil.toml

# Backfill all gaps
gerbil backfill /path/to/repo-reports --config .repogerbil.toml

# Generate today's changelogs
gerbil changelog /path/to/repo --date $(date +%Y-%m-%d) --analyze --output-dir /path/to/repo-reports

# Fix any stats drift
gerbil fix-stats /path/to/repo-reports/uwarp-space /path/to/uwarp-space

# Verify everything
gerbil verify /path/to/repo-reports/uwarp-space /path/to/uwarp-space

# Generate weekly summary
gerbil summary /path/to/repo-reports --year 2026 --week 15 --output-dir /path/to/repo-reports/summaries
```

## With messometer

messometer was the predecessor for commit consolidation. repogerbil's `distill` command replaces messometer's `auto` and `apply` commands.

### Migration

| messometer | repogerbil |
|-----------|------------|
| `messometer extract --cadence daily` | `gerbil changelog --analyze` |
| `messometer auto ./snapshot --cadence daily` | `gerbil distill --changelog-dir` |
| `messometer apply --script consolidate.sh` | `gerbil distill` (no script step) |
| `messometer status` | `gerbil status` |

### Key Differences

- repogerbil uses changelog YAML as commit messages (messometer used generic "Snapshot for day" text)
- repogerbil creates backup tag + branch (messometer created branch only)
- repogerbil classifies commits by vocabulary (messometer had no classification)

## With Claude Code

### Plugin Installation

**Development / testing:**

```bash
claude --plugin-dir ./src/repogerbil/plugin
```

**Permanent install (via marketplace):**

```bash
# Add marketplace (once)
/plugin marketplace add livingstaccato/repogerbil

# Install
/plugin install repogerbil
```

### Usage

```
/gerbil                     # context-aware — detects repo, suggests work
/gerbil audit --show-bad    # direct command
/gerbil catch up            # conversational — asks what to do
```

## With Hugo (sight/staccato-hugo)

repogerbil generates YAML changelogs that `tools/generate_hugo_data.py` in repo-reports converts to Hugo-compatible JSON for the livingstaccato.com site. The pipeline:

```
gerbil changelog → YAML → generate_hugo_data.py → JSON → Hugo → site
```
