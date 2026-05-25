# Changelog

## 0.1.1 (2026-05-24)

Six weeks of follow-up work on top of the 0.1.0 release. Headline additions:
LLM-backed commit-message refinement, the `snapshot` / `multi-snapshot` /
`preflight` / `append` / `realign` / `changelog-span` commands, a structured
sidecar format for LLM summaries, time-windowed commit spreading, regex-based
path exclusion, an artifact pattern table for preflight categorization, and a
hierarchical, configurable vocabulary.

### Features

- **`multi-snapshot --ecosystem-label`**: configurable label appended after
  the date on each multi-snapshot commit's first line, with matching
  `ecosystem_label` Settings field (env `REPOGERBIL_ECOSYSTEM_LABEL`).
- **Multi-snapshot author identity**: `snapshot_author_name` /
  `snapshot_author_email` Settings fields override the destination repo's
  commit identity; default `None` inherits the user's global git config.
- **TOML-extensible preflight patterns**: `extra_artifact_patterns` Settings
  field appends user-defined regex rules to the built-in preflight artifact
  table.
- **Snapshot engine**: tree-level snapshot consolidation with cadence export,
  rich preview, and `summary --force` (7045402).
- **Multi-snapshot command**: multi-repo daily distillation across an
  ecosystem, with hidden-ref support for batch ecosystem distillation
  (51310e7, 9b351b3).
- **Snapshot options**: `--commit-time` / `--timezone`, `--all-branches`,
  `--exclude-path`, `--llm-refine`, `--source-branch`, per-commit progress
  output, and time-window commit spreading (26e06ba, c7b8869, 7acad6e,
  3971edb, f5783dd, 329465f, 58135a5).
- **Preflight command**: pre-distill repo inspection with an artifact pattern
  table covering mutation-testing artifacts, backups, coverage XML, htmlcov,
  go.sum / go.mod, CODEOWNERS, generated stubs, zip / vendor / node_modules,
  image / video / BFG / binary patterns, and tool configs (1f226e2, c78538f,
  01d66f3, d2beff8, 5120747, f50a332, 516e64d, 583d8cb, f04cef8, 87da7de).
- **LLM commit-message refinement**: end-to-end pipeline with Ollama client,
  prompt builder, JSON schema, message composer, MessageGenerator
  orchestrator, and structured JSONL sidecar carrying body + changes array
  plus original commit bodies; bypasses the LLM when conventional messages
  are already well-formed (926cbb7, 600223f, d6d74c1, 3550294, 74b80b4,
  12ec4e9, 9954f5f, 8275efa, a31094f).
- **`changelog-span` CLI**: LLM-backed release notes spanning a window,
  with `--run` flag for automatic changelog synthesis (a3df2ad, 2fba76f).
- **`append` and `realign` commands**: JSONL maintenance for sidecar
  metadata (adc616b).
- **Walk-up config discovery**: `.repogerbil.toml` is located like `.git`
  (561f433).
- **Hierarchical vocabulary**: configurable taxonomy with DAG structure,
  `VOCAB_VERSION`, `allowed_verbs()` for LLM schema, scaffold verb, and
  full conventional + semantic verb suite (4dc6ee7, a322b1b, 2f8b2d4,
  4ba04bd, cb6dc74, f0618b2).
- **Incremental indexing and structured errors** (4dc6ee7, a322b1b).
- **Upstream drift scripts**: `scripts/scan_upstream_drift.py` and
  `scripts/sync_upstream.py` for tracking upstream changes (771ac4d).
- **`--verbose` group-level flag**: enables INFO-level logging from
  `repogerbil.*` loggers; pass before the subcommand
  (`gerbil --verbose snapshot ...`). No short form — `-v` is reserved for
  per-command use such as `preflight -v`.
- **`corrupt_lines` field in `RealignResult`**: counts preserved-but-unparsed
  JSONL records so realign reports surface corruption without dropping data.

### Fixes

- **Atomic state save**: `state.py` now writes via temp-file + replace to
  avoid partial writes if interrupted mid-save.
- **SHA-256-safe git parsing**: all four git-log parsers switched to a
  NUL-sentinel format (`--format=%x00%H`) so 64-character SHA-256 hashes
  parse cleanly alongside SHA-1.
- **`HTTPOllamaClient` URL required**: removed the inline default; callers
  must pass `base_url` (sourced from `Settings.llm_ollama_url`).
- **LLM error logging**: snapshot and multi-snapshot now log LLM refinement
  failures instead of swallowing them silently.
- **Snapshot module split**: extracted `_snapshot_timestamps.py` to keep
  `snapshot.py` under the 500-LOC cap.
- **Realign cleanup**: removed the dead radius-0 pass and added a JSON
  decode guard around sidecar records.
- **Preflight timeout**: 120s subprocess timeout on the `git log` call used
  for repo inspection.
- **Branch scoping and preflight error specificity** tightened (8ce0f53).
- **Reproducibility and branch-aware distill flows** hardened against
  non-deterministic ordering and stray branch state (faa19ec).
- **Append / verification review findings** resolved across the core
  modules (f491542, cefc2d5).
- **Snapshot subprocess calls** routed through `_run_git`; `CommitInfo`
  fields preserved (42fa0a7).
- **LLM timeout fallback**: snapshot falls back to the built-in message
  when the LLM times out; git helpers split for testability (f7c06af).
- **`llm_runner` markdown handling**: strips outer markdown fences from
  Claude output (d59d45e).
- **Snapshot uses changelog as commit message** and filters garbage
  subjects; fetches all refs and respects `--source-branch` (bea8019,
  f5783dd).
- **Commit-header scope**: omit when redundant or empty; restrict to
  top-level codebase sections per conventional commits; single-word scope
  enforced in the prompt (bb8ce0d, dff452a, d082077).
- **Commit prompt polish**: lowercase change descriptions, prevent
  "This commit" anti-patterns, improve summary prompt (bfa8ff3, 540893f).
- **Snapshot identity**: use global git identity instead of hardcoded
  repogerbil author (3c8f644).
- **Snapshot tree handling**: `--force` final checkout to populate working
  tree; preserve timestamps in `_attach_file_lists` (cb8bc65, bd7ae09).
- **Preflight regex**: anchored htmlcov / coverage patterns, lock-file
  whitelist, flag/pattern contracts aligned (807911e, 34da478).
- **Multi-repo listing**: only list repos with actual commit activity
  (0b1e423).
- **Backfill**: `--prompt` flag for batch LLM prompt generation (4bb0425).
- **Plugin install paths**: install Claude plugin to cwd; install Codex
  plugin under Codex home (5428b58, 9c788ac).
- **Snapshot docstring**: corrected raw-string regex examples (750614d).
- **Scrub helper**: cover `hmhco.com` and `tim@provide.io` (498010f).
- **`catch_up` `--since=<bare-date>` approxidate**: bare-date `--since`
  values are now pinned to `T00:00:00` so the git approxidate parser
  cannot drift across the day boundary — root cause of the long-running
  flaky test.
- **`multi_snapshot._collect_day_context` body corruption**: rewritten as
  a two-call parser (metadata + file names) so commit bodies containing
  the GS (`\x1d`) field-separator byte no longer corrupt the parsed
  output.
- **`realign.py` atomic JSONL write**: switched to unique `mkstemp` tmp
  names so concurrent realign runs over the same sidecar cannot collide.

### Refactors

- **Vocabulary single source of truth**: `vocabulary.py` is now the only
  place category/severity definitions live; previously duplicated tables
  removed.
- **Snapshot public API tightened**: `_run_git` and `_attach_file_lists`
  dropped from `snapshot.py`'s `__all__` — internal helpers only.
- **Catch-up workflow**: renamed `append` workflow to catch-up metadata
  recording; terminology / compatibility normalized (76b13a8, 360bfe7).
- **Module splits to honor 500-LOC cap**: `core/git`, `cli/main`,
  `distill_cmds`, and `multi_snapshot.py` split into packages; max-loc
  gate enforced (0a1b473, f5f804c).
- **Snapshot engine**: single-pass tree deduplication; deduplicate groups
  before creating snapshots (ac25186, c57ff30).
- **Tree handling**: fallback to full tree when subdir does not exist in
  commit (10df347).
- **`CategoryDefinition`**: verb moved into the definition; distill CLI
  commands tested (20d2927).
- **Pre-release cleanup** of dead code and pre-release scaffolding
  (3cf3ec9, 8a50bf9).
- **`_KNOWN_PREFIX_RE` derived from vocabulary**: `distill_cmds/_helpers`
  now builds the known-prefix regex from the vocabulary module instead of
  carrying a hardcoded prefix list.
- **`_cleanup_index_files` shared helper**: cross-imported by
  `_multi_snapshot_git.py` instead of duplicated in both call sites.

### Docs

- **README**: all 22 commands documented, with preflight, snapshot, and
  exclude-path regex features; ARCHITECTURE and skill aligned to current
  surface (1d655be, 49897fe, 9531399).
- **LLM commit-message refinement design spec** and implementation plan
  added under `docs/` (21ea99b).

### Build / CI / Chore

- **New maintenance scripts**: `scripts/check_plugin_sync.py` enforces
  byte-identical plugin mirrors, `scripts/check_changelog_current.py`
  guards CHANGELOG drift, and `scripts/run_mutation_test.py` drives
  mutation runs.
- **Nightly mutation CI**: `.github/workflows/mutation.yml` runs
  `mutmut` on a schedule.
- **Hypothesis property tests** added for `cadence.py` and `classify.py`.
- **Pytest markers**: dropped the `unit` marker (kept `integration`);
  `--strict-markers` stays enabled.
- **Coverage tightening**: removed `pragma: no cover` from two reachable
  branches now backed by tests.
- **Packaging**: switched to setuptools with a `VERSION` file (30cc9e2).
- **Assistant plugins**: packaged via package-data; changelogs linted
  (b008fdd).
- **Lint / mypy housekeeping**: pre-existing blockers cleaned up so
  `make quality` is green; ruff fixes across tests and helpers; mypy
  type-ignore comments restored or removed in line with chromadb stubs
  (7b2a908, 6205496, 95b0171, 4ba2e45, a51cb40, 603ec78, d5ced61).
- **Test fixtures**: `commit.gpgsign=false` and `check=True` added where
  missing (7d292bb, 354449e).
- **SPDX headers** added to preflight tests; boilerplate cleaned up
  (6f55d86).
- **`scripts/audit_zero_stats.py`** added to find changelogs affected by
  the diff-stats bug (65f9960). (Later moved to `scripts/forensics/audit_zero_stats.py`.)
- **Default LLM model**: switched to `qwen3-coder-next:q8_0` (80fbb51).

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
