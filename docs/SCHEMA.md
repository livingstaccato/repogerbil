# Changelog YAML Schema

## File Naming

```
<repo-name>/YYYY-MM-DD-<repo-name>-changelog.yaml
```

## Full Schema

```yaml
date: YYYY-MM-DD                       # required
repo: <repo-name>                      # required
title: "One-line title"                # required — the day's most significant work
summary: "1-3 sentence summary"        # required — high-level impact

stats:                                 # required — from git diff --shortstat
  commits: N                           # number of commits on this date
  files_changed: N
  insertions: N
  deletions: N

bulk:                                  # optional — mechanical/mass changes
  - category: <category>              # vocabulary category
    files: N                          # file count for this bulk operation
    reason: "Why these files changed"

review:                                # optional — unclassifiable commit subjects
  - "ambiguous commit message"

changes:                               # required — grouped change sections
  - title: "Section title"
    category: <category>              # vocabulary category (null to derive)
    severity: <severity>              # vocabulary severity (null to derive)

    stats:                            # optional — per-section diff stats (from enrich)
      files_changed: N
      insertions: N
      deletions: N

    impact:                           # optional — dependency analysis (from enrich)
      files: [importing_file.py]      # files that import changed files
      packages: [src/module/]         # affected packages/directories
      repos: [other-repo]            # cross-repo dependents

    files:                            # files touched by this section
      - path: path/to/file.py
        summary: "What changed in this file"

    points:                           # specific changes within the section
      - text: "What changed and why"
        category: <category>
        severity: <severity>
        files: [path/to/file.py]
        refs: ["#42"]                 # optional — issue references
        body: "Full commit body"      # optional — when message_depth=full
```

## Field Rules

- `title` + `summary` are always first
- `stats` comes from `git diff --shortstat` (corrected by `gerbil fix-stats`)
- `bulk` declares mechanical changes that shouldn't render on the site
- `review` lists commits that couldn't be auto-classified (clear after manual review)
- `changes[].stats` and `changes[].impact` are added by `gerbil enrich`
- `changes[].category`/`severity` can be null (derived from points)

## Verification Formula

```
sum(bulk[].files) + count(unique files in changes) ≈ stats.files_changed
```

`gerbil verify` checks both stats accuracy and file coverage.
