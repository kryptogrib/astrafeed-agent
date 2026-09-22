# Project context

AstraFeed Token Brief is a single-service engine extracted from AstraFeed. Its core path is source ingestion, deterministic prefiltering and deduplication, LLM scoring, event grouping, report planning, and rendering.

## Boundaries

- `domain/` contains business models and pure rules.
- `ports/` defines source, repository, LLM, ingestion, and spend-budget interfaces.
- `adapters/` contains Telegram, OpenRouter, SQLite, and in-memory implementations.
- `application/` coordinates ingestion and brief generation.
- `pipeline/` runs collection through scoring and report queueing.
- `report/` deduplicates, groups, plans, and renders the output.

A brief request uses an in-memory per-request report repository while the SQLite ingestion store caches source posts and coverage. The spend reservation table applies one global daily ceiling using `BEGIN IMMEDIATE`; `principal_id` is an opaque service identifier rather than a user relation.
