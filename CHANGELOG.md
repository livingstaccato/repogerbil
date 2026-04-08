# Changelog

## 0.1.0 (2026-04-07)

Initial release.

### Features
- **14 CLI commands**: status, changelog, fix-stats, verify, distill, audit, summary, missing, backfill, enrich, index, search, related
- **Changelog generation**: draft, analyze (heuristic), and prompt (LLM-ready) modes
- **Commit classification**: conventional prefix parser, 35+ verb heuristics, file rules (bulk/skip/classify)
- **Commit consolidation**: daily/hourly/weekly distill with changelog-based commit messages, backup branch + tag
- **Stats verification**: two-level checking (accuracy + file coverage via bulk entries)
- **Weekly summaries**: aggregate changelogs by ISO week, generate markdown or LLM prompts
- **Enrichment**: per-section diff stats + import impact analysis (file/package/cross-repo)
- **Audit**: commit message prefix adoption tracking with ambiguous message detection
- **Missing/backfill**: find gaps across tracked repos, batch generate changelogs
- **Vector database** (optional): ChromaDB-backed semantic search across changelogs with 7 data dimensions — titles, changes, file paths, diff content, category distributions, scopes, quality metrics
- **Claude Code plugin**: skill (/repogerbil) + analyzer agent

### Configuration
- `.repogerbil.toml` with pydantic-settings (env vars, per-repo overrides)
- File rules with three actions: bulk, skip, classify
- Tracked repo registry for multi-repo workflows

### Quality
- 284 tests, 100% branch coverage
- mypy strict, ruff lint+format, bandit security
- Pre-commit hooks (format on commit, full gates on push)
- Integration test (create repo → changelog → verify → distill)
- 500-line file limit enforced
