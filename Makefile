.DEFAULT_GOAL := help
.PHONY: help install test lint fmt typecheck check brief serve login channels backfill-posts backfill-comments up down

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

channels: ## List subscribed channels; ARGS=--write saves usable ones to config.yaml
	uv run python scripts/channels.py $(ARGS)

backfill-posts: ## Download 8 days of posts for configured channels
	uv run astrafeed-pulse backfill-posts $(ARGS)

backfill-comments: ## Read comment threads of stored posts (default 48h; resumable)
	uv run astrafeed-pulse backfill-comments $(ARGS)

up: ## Build and start the app container
	docker compose up --build

down: ## Stop the app container
	docker compose down
