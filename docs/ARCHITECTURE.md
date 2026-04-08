# Architecture

## Layers

```
repogerbil/
├── core/         Pure library — no CLI, no I/O assumptions
│   ├── git.py        Subprocess git analysis
│   ├── classify.py   Commit classification (prefix + verb + file rules)
│   ├── changelog.py  Changelog generation (draft, analyze, prompt)
│   ├── cadence.py    Time-based grouping (daily/hourly/weekly)
│   ├── consolidate.py Cherry-pick squash with changelog messages
│   ├── diff.py       Diff reading with skip patterns
│   ├── verify.py     Stats accuracy + coverage checking
│   ├── enrich.py     Per-section stats + impact analysis
│   ├── audit.py      Missing changelog detection
│   ├── summary.py    Weekly summary generation
│   ├── config.py     pydantic-settings with TOML + env vars
│   └── vocabulary.py Category/severity definitions
├── cli/          Click CLI — thin wrappers around core
│   └── main.py   11 commands
└── plugin/       Claude Code integration
    ├── skills/   /repogerbil skill
    └── agents/   analyzer agent
```

## Design Principles

1. **Core is pure** — no Click, no Rich, no logging in core modules. Functions take data in, return data out. All I/O is in the CLI layer.

2. **Git via subprocess** — no GitPython, no pygit2. Direct `git` CLI calls with timeout protection. Easier to debug, no version compatibility issues.

3. **Config via pydantic-settings** — layered resolution: CLI flags > env vars > project TOML > user TOML > defaults. Per-repo overrides. File rules with three actions (bulk/skip/classify).

4. **100% coverage from day one** — every function has tests. Defensive branches use `pragma: no cover` with explanatory comments. Integration test covers the full pipeline.

5. **Conventional commits as input** — the classifier maps `feat:`, `fix:`, `refactor:` etc. to the vocabulary. Verb heuristics handle the 86% of history without prefixes.

## Data Flow

```
Source repo (git)
    │
    ├─ get_commits_for_date() ──→ CommitInfo[]
    ├─ get_diff_stats() ────────→ DiffStats
    ├─ get_diff_content() ──────→ {file: diff_text}
    │
    ├─ classify_commit() ───────→ Classification (category, severity)
    ├─ classify_files() ────────→ FileClassification (meaningful, bulk, forced)
    │
    ├─ generate_analyzed() ─────→ changelog YAML dict
    ├─ generate_prompt() ───────→ markdown for LLM
    │
    ├─ group_by_cadence() ──────→ TimeGroup[]
    ├─ consolidate() ───────────→ squashed branch + backup
    │
    ├─ verify_changelog() ──────→ VerifyResult
    ├─ enrich_changelog() ──────→ modified YAML with stats/impact
    │
    ├─ find_missing() ──────────→ MissingDate[]
    └─ collect_week_data() ─────→ WeekSummaryData
```

## Key Types

- **CommitInfo** — frozen dataclass: hash, date, subject, files, body, refs
- **DiffStats** — frozen dataclass: commits, files_changed, insertions, deletions
- **Classification** — frozen dataclass: category, severity, needs_review
- **FileRule** — pydantic model: pattern, action (bulk/skip/classify), category, reason
- **Settings** — pydantic-settings: full config with TOML + env resolution
- **TimeGroup** — frozen dataclass: period_start, period_end, commits, files_affected
- **ConsolidationResult** — frozen dataclass: target_branch, backup_branch, backup_tag, counts
