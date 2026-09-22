.DEFAULT_GOAL := help
.PHONY: help install test lint fmt typecheck check brief serve login up down

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  %-12s %s\n", $$1, $$2}'

install: ## Sync dependencies
	uv sync

test: ## Run tests
	uv run pytest -q

lint: ## Check formatting and lint
	uv run ruff check src tests
	uv run ruff format --check src tests

fmt: ## Format and fix lint
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck: ## Run mypy
	uv run mypy -p astrafeed

check: lint typecheck test ## Run all checks

brief: ## Build an offline brief (ARGS="--tokens SOL")
	uv run astrafeed-brief --stub-llm $(ARGS)

serve: ## Start ingestion polling and HTTP health service
	uv run astrafeed-serve

login: ## Create a Telegram reader session
	uv run python scripts/login.py

up: ## Build and start the app container
	docker compose up --build

down: ## Stop the app container
	docker compose down
