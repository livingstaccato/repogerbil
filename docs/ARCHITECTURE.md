# Architecture

## Layers

```
repogerbil/
├── core/              Reusable library — no CLI or presentation dependencies
│   ├── git/               Subprocess git analysis helpers
│   ├── classify.py        Commit classification (prefix + verb + file rules)
│   ├── changelog.py       Changelog generation (draft, analyze, prompt)
│   ├── cadence.py         Time-based grouping (daily/hourly/weekly)
│   ├── consolidate.py     Cherry-pick distill with changelog messages
│   ├── diff.py            Diff reading with skip patterns
│   ├── verify.py          Stats accuracy + coverage checking
│   ├── enrich.py          Per-section stats + impact analysis
│   ├── audit.py           Missing changelog detection across tracked repos
│   ├── summary.py         Weekly summary generation
│   ├── config.py          pydantic-settings with TOML + env vars
│   ├── vocabulary.py      Category/severity definitions
│   ├── snapshot.py        Independent repo creation with distilled history
│   ├── artifact_patterns.py  Regex rules classifying known artifact file types
│   ├── preflight.py       Scan repo file history into PreflightReport
│   ├── embeddings.py      Embedding model wrapper (sentence-transformers or hash)
│   ├── vectordb.py        ChromaDB wrapper with 4 collections
│   ├── search.py          High-level semantic search + indexing
│   ├── append.py          Forward-only `.summaries.jsonl` sidecar append
│   ├── realign.py         Legacy sidecar hash realignment to current commits
│   └── llm_runner.py      Thin external LLM command runner for changelog-span
├── llm/               Ollama prompt/schema/client/generator for snapshot message refinement
├── cli/               Click CLI — thin wrappers around core
│   ├── main.py            CLI group and command registration
│   └── commands/
│       ├── distill_cmds/     snapshot, multi-snapshot, preview, export-cadence
│       ├── preflight_cmd.py  preflight — repo inspection before distilling
│       ├── changelog_span_cmd.py  release-span prompt/synthesis workflow
│       ├── append_cmd.py     sidecar append CLI
│       ├── realign_cmd.py    sidecar realignment CLI
│       └── vectordb_cmds.py  Optional vector DB commands (index, search, related, similar, impact)
```

`core/git/` re-exports the stable git helper API from smaller internal files (`_commits.py`, `_stats.py`, `_trees.py`, `_runner.py`, and `_types.py`).

## Plugin Layout

```
plugins/
└── repogerbil/            Shared Claude Code + Codex plugin
    ├── .claude-plugin/    Claude Code manifest
    ├── .codex-plugin/     Codex manifest
    ├── skills/
    │   └── gerbil/        /gerbil skill
    └── agents/
        └── analyzer/      changelog analysis agent
```

## Design Principles

1. **Core is UI-free** — no Click, Rich, or presentation concerns in core modules. Core owns reusable git, filesystem, and data operations; the CLI layer handles argument parsing, terminal output, and process exit behavior.

2. **Git via subprocess** — no GitPython, no pygit2. Direct `git` CLI calls with timeout protection. Easier to debug, no version compatibility issues.

3. **Config via pydantic-settings** — layered resolution: CLI flags > env vars > project TOML > user TOML > defaults. Per-repo overrides. File rules with three actions (bulk/skip/classify).

4. **100% coverage from day one** — every function has tests. Defensive branches use `pragma: no cover` with explanatory comments. Integration test covers the full pipeline.

5. **Conventional commits as input** — the classifier maps `feat:`, `fix:`, `refactor:` etc. to the vocabulary. Verb heuristics handle unprefixed commits. Scope extraction indexes `(scope)` for search.

6. **Vector DB is optional** — all core commands work without chromadb. The `index`, `search`, `related`, `similar`, and `impact` commands require `pip install repogerbil[vectordb]`.

7. **No source Python file over 500 lines** — enforced for `src/` by `scripts/check_max_loc.py` via `make max-loc` / `make quality`.

## Data Flow

```
Source repo (git)
    │
    ├─ get_commits_for_date() ──→ CommitInfo[]
    ├─ get_commits_for_range() ─→ CommitInfo[]
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
    ├─ consolidate() ───────────→ distilled branch + backup
    ├─ create_snapshot() ───────→ independent distilled repo
    ├─ create_multi_snapshot() ─→ independent merged multi-repo snapshot
    │
    ├─ verify_changelog() ──────→ VerifyResult
    ├─ enrich_changelog() ──────→ modified YAML with stats/impact
    │
    ├─ find_missing() ──────────→ MissingDate[]
    ├─ collect_week_data() ─────→ WeekSummaryData
    │
    ├─ append_new_commits() ────→ forward-only JSONL sidecar records
    ├─ realign_jsonl() ─────────→ current-hash JSONL sidecar records
    │
    └─ index_changelogs() ──────→ VectorStore (4 collections, 7 search facets)
        ├─ search_changelogs()      semantic search
        ├─ search_by_scope()        scope-based filtering
        ├─ find_related_work()      cross-repo correlation
        ├─ find_low_quality()       quality-based ranking
        └─ search_diffs()           code-level search
```

## Key Types

- **CommitInfo** — frozen dataclass: hash, date, subject, files, body, refs
- **DiffStats** — frozen dataclass: commits, files_changed, insertions, deletions
- **Classification** — frozen dataclass: category, severity, needs_review
- **FileRule** — pydantic model: pattern, action (bulk/skip/classify), category, reason
- **Settings** — pydantic-settings: full config with TOML + env resolution
- **TimeGroup** — frozen dataclass: period_start, period_end, commits, files_affected
- **ConsolidationResult** — frozen dataclass: target_branch, backup_branch, backup_tag, counts
- **ArtifactRule** — frozen dataclass: label, pattern (regex), flag (exclude-path value); pre-compiled
- **FileRecord** — frozen dataclass: path, commit_count, rule (ArtifactRule | None)
- **PreflightReport** — frozen dataclass: artifacts, source, unknown (all tuples), suggested_flags
- **VectorStore** — ChromaDB wrapper: changelogs, changes, filepaths, diffs collections
- **Embedder** — Protocol: embed(text) → list[float], embed_batch(texts) → list[list[float]]
- **GeneratedMessage** — LLM-generated snapshot message plus body and file-level changes
- **AppendResult** — sidecar append counts and latest appended hash
- **RealignResult** — sidecar realignment counts, including exact and unalignable records

## Vector DB Collections

| Collection | Documents | Metadata |
|-----------|-----------|----------|
| changelogs | title + summary | repo, date, commits, files, dominant_category, scopes, quality_* |
| changes | section title + points | category, severity, repo, date, scopes |
| filepaths | space-joined file paths | repo, date |
| diffs | diff text per file | repo, date, filepath |
