# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

.PHONY: help install lint type-check test test-cov security complexity dead-code mutation mutation-ci max-loc plugin-sync plugin-sync-copy changelog-check approxidate-check quality check act-dry act-ci

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

install: ## Install dependencies
	uv sync --all-extras

lint: ## Run ruff format + lint
	uv run ruff format --check .
	uv run ruff check .

type-check: ## Run mypy strict
	uv run mypy src tests

test: ## Run tests with 100% coverage enforcement
	uv run pytest

test-cov: ## Run tests with HTML coverage report
	uv run pytest --cov-report=html

security: ## Run bandit security scan
	uv run bandit -r src -ll

complexity: ## Run xenon complexity check
	uv run xenon --max-absolute C --max-modules B --max-average A src/

dead-code: ## Run vulture dead code detection
	uv run vulture src/ tests/ vulture_whitelist.py --exclude src/repogerbil/core/config.py --min-confidence 80

mutation: ## Run mutmut mutation testing
	uv run mutmut run --max-children 8

mutation-ci: ## Run mutmut for CI with summary artifacts (mutation-summary.txt, mutation-results.json)
	uv run python scripts/run_mutation_test.py

max-loc: ## Enforce 500-line per-file cap
	python scripts/check_max_loc.py

plugin-sync: ## Verify plugins/ matches packaged assistant_plugins/ mirror
	python scripts/check_plugin_sync.py

# Mirror plugins/ -> src/repogerbil/assistant_plugins/repogerbil/ byte-for-byte
# (including deletions). Manual convenience — not wired into `quality`.
plugin-sync-copy: ## Copy plugins/ -> packaged assistant_plugins/ mirror (manual)
	rsync -a --delete plugins/repogerbil/ src/repogerbil/assistant_plugins/repogerbil/

changelog-check: ## Verify CHANGELOG.md head matches VERSION and warn on commit drift
	python scripts/check_changelog_current.py

approxidate-check: ## Guard against unpinned git --since=/--until= approxidate usage
	python scripts/check_approxidate.py

quality: lint type-check security complexity dead-code max-loc plugin-sync changelog-check approxidate-check test ## Run all quality gates

check: quality ## Alias for quality

act-dry: ## List CI jobs without running them (validates workflow + .actrc)
	env -u DOCKER_HOST act --list

act-ci: ## Run the CI quality job locally via act (slow; pulls images on first run)
	env -u DOCKER_HOST act -j quality --matrix python-version:3.13 --rm
