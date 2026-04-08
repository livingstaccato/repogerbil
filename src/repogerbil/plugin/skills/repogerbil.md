---
name: repogerbil
description: Git history documentation and consolidation — generate changelogs, verify stats, squash commits, audit prefix adoption. Context-aware when invoked without arguments.
user-invocable: true
---

# repogerbil

Use this skill when the user wants to work with git history documentation, changelog generation, commit consolidation, or history verification.

## Context-Aware Mode (no arguments)

When invoked without arguments, detect the current working directory's repo and report:
1. Repository name and date range
2. Missing changelog dates (if a changelog directory is configured)
3. Commit message quality (prefix adoption %)
4. Suggest next actions

## Direct Commands

Map user requests to `repogerbil` CLI commands:

| User says | Run |
|-----------|-----|
| "generate changelog for today" | `repogerbil changelog . --date $(date +%Y-%m-%d) --analyze` |
| "what's missing?" | `repogerbil status .` then check for gaps |
| "verify the changelogs" | `repogerbil verify <changelog_dir> .` |
| "fix the stats" | `repogerbil fix-stats <changelog_dir> .` |
| "squash this repo" | `repogerbil squash . --dry-run` first, then confirm |
| "audit commit messages" | `repogerbil audit . --show-bad` |
| "generate a prompt for this" | `repogerbil changelog . --date DATE --prompt` |

## Important

- Always `--dry-run` before squash. Squashing is destructive.
- The tool creates backup branches and tags before squash — but verify first.
- Use `--analyze` for complete changelogs, plain mode for draft skeletons.
- Config lives in `.repogerbil.toml` — check for per-repo overrides.
