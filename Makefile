.DEFAULT_GOAL := help
.PHONY: help install test lint fmt typecheck check brief serve pulse-build pulse-check pulse-demo news-pulse news-pulse-tune news-pulse-eval news-pulse-ground news-pulse-serve login channels backfill-posts backfill-comments up down

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "} {printf "  %-12s %s\n", $$1, $$2}'

install: ## Sync dependencies
	uv sync

test: ## Run tests
	uv run pytest -q

lint: ## Check formatting, lint, and layer imports
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run lint-imports

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

PULSE_DB ?= astrafeed.db
PULSE_HOST ?= 127.0.0.1
PULSE_PORT ?= 8000

pulse-build: ## Rebuild Pulse briefs and the comparison from saved runs (no LLM)
	python3 docs/research/pulse_brief.py $(PULSE_DB) zec
	python3 docs/research/pulse_brief.py $(PULSE_DB) zec 2026-09-17..2026-09-19
	python3 docs/research/pulse_brief.py $(PULSE_DB) zec 2026-09-20..2026-09-22
	python3 docs/research/pulse_brief.py $(PULSE_DB) eth
	python3 docs/research/pulse_compare.py $(PULSE_DB) zec 2026-09-17..2026-09-19 2026-09-20..2026-09-22

pulse-check: ## Check database md5 and that saved Pulse files match a rebuild
	python3 docs/research/pulse_check.py $(PULSE_DB)

pulse-demo: pulse-check ## Check, then serve /pulse and /pulse/compare
	uv run python3 docs/research/pulse_service.py $(PULSE_DB) $(PULSE_HOST) $(PULSE_PORT)

TOPIC ?= zec
WINDOW ?= 2026-09-17..2026-09-19
ALIASES ?=
export ALIASES

news-pulse: ## News-first Pulse: artifacts/news-pulse/<topic>/<window>/{pulse.json,brief.md,decisions.json,manifest.json}
	python3 docs/research/news_pulse_build.py $(PULSE_DB) $(TOPIC) $(WINDOW)

news-pulse-tune: ## Настроечная оценка на artifacts/news-tune (не news-eval)
	python3 docs/research/news_pulse_eval.py --db $(PULSE_DB) --sample artifacts/news-tune --runs artifacts/news-pulse --out artifacts/news-pulse/tune-eval

news-pulse-eval: ## Итоговая оценка на замороженной выборке artifacts/news-eval (включает проверку подтверждённости)
	python3 docs/research/news_pulse_eval.py --db $(PULSE_DB) --out artifacts/news-pulse/eval

news-pulse-ground: ## Подтверждённость брифов: цитаты и числа сверяются с БД; artifacts/news-pulse/grounding
	python3 docs/research/news_pulse_ground.py --db $(PULSE_DB) artifacts/news-pulse/*/*/

news-pulse-serve: ## Serve /news-pulse from cache (no LLM network); also keeps /pulse
	PULSE_REUSE=1 uv run python3 docs/research/pulse_service.py $(PULSE_DB) $(PULSE_HOST) $(PULSE_PORT)

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
