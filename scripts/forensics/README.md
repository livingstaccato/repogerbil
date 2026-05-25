# scripts/forensics/

One-off forensic / diagnostic scripts, kept here for historical reference.

These scripts are **not** run by CI, pre-commit, or any Makefile target. They
were written to investigate specific bugs or do a one-time data audit, and are
retained so the methodology can be re-used or audited later.

If a script in this directory becomes part of a regular workflow, promote it
back up to `scripts/` and wire it into the Makefile + CI.

## Inventory

- `audit_zero_stats.py` — audits changelog YAMLs for the
  `files_changed=0 / insertions=0 / deletions=0` blast radius from the
  single-commit `get_diff_stats` bug (see `CHANGELOG.md` 0.1.1). Heuristic;
  review output before running `repogerbil fix-stats`.
