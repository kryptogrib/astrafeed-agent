# Lean Hexagonal modular monolith — no pluggy, no CQRS

astrafeed is a modular monolith with a **thin** Hexagonal core: a pure `domain/` (Interests, Relevance routing, no I/O), a small set of **ports for what actually varies** (`Source`, `LLMClient`, `Notifier`, `Repository`), thin adapters, and a single pipeline orchestrator. We deliberately reject the heavier architecture proposed in the planning chats: **no `pluggy` plugin system and no CQRS** in the MVP.

This is the deviation a future reader will question, so: `pluggy` solves third-party *plugin ecosystems* (pytest's problem), but we are one developer adding Sources ourselves — a `Source` port plus a dict registry does the same job with far less indirection. CQRS pays off when reads and writes scale independently; at single-user MVP there is no such pressure, and both source chats themselves called it "избыточен для MVP / stage 2-3."

## Consequences

- **Definitions live in the DB, not `config.yaml`.** Channels, Groups, and Interests are runtime-editable through application **use-cases** (`AddChannel`, `EditInterests`, `TriggerReport`, `GetStatus`). `config.yaml` shrinks to system settings/secrets. This is because the stated end-goal is a web UI, and a UI editing a YAML file would force a later migration.
- **Bot and HTTP API are both driving adapters** over the same use-cases. The Telegram bot (delivery + a few commands) ships in MVP; a thin FastAPI layer exposes the same use-cases as a ready API (with OpenAPI docs) for the future web UI. "Развить бота до API" = add a second thin adapter, not a rewrite — provided logic never leaks into the bot.
- Adding a Source (RSS, X, …) later means: implement the `Source` port + register it. The domain and pipeline are untouched.
- If a real third-party plugin ecosystem or independent read/write scaling ever materializes, revisit `pluggy`/CQRS then — this ADR records that their absence is a choice, not an oversight.
