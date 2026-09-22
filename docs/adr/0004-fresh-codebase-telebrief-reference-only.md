# Fresh codebase; Telebrief is reference-only; permissive license

astrafeed is written from scratch. **Telebrief (`refs/Telebrief-main`) is a reading reference only** — we study how its collector, summarizer, grouper, and sender work and re-implement equivalent behaviour in our own design. We do **not** fork it or copy its code verbatim, and astrafeed is released under a permissive license (MIT or Apache-2.0).

The hard constraint behind this: **Telebrief is AGPL-3.0**. Copying its code (or forking) would bind astrafeed — and any hosted/SaaS deployment of it — to AGPL's network copyleft, which conflicts with the planned open-core/SaaS future. Writing fresh keeps licensing freedom and a clean, multi-Source architecture instead of inheriting Telegram-specific structure.

## Consequences

- **For any contributor or AI agent:** treat `refs/Telebrief-main` like documentation. Read it for understanding; never paste its functions. Re-express logic in astrafeed's own types and structure.
- Give attribution generously (README credits Telebrief as inspiration) — ethical and community-friendly, and costs nothing under a clean-room re-implementation.
- Pick MIT vs Apache-2.0 before first public release (Apache-2.0 adds an explicit patent grant; MIT is simpler). Either is compatible with the SaaS plan.
