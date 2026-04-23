# SPDX-FileCopyrightText: Copyright (C) 2026 provide.io llc
# SPDX-License-Identifier: Apache-2.0

.PHONY: help install lint type-check test test-cov security complexity dead-code mutation max-loc quality check

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

max-loc: ## Enforce 500-line per-file cap
	python scripts/check_max_loc.py

quality: lint type-check security complexity dead-code max-loc test ## Run all quality gates

check: quality ## Alias for quality
