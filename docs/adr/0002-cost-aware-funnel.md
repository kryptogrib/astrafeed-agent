# Cost-aware funnel: the expensive model sees only survivors

The expensive LLM must never run per-Item. Each poll tick passes new Items through a cost-increasing funnel — **free deterministic Pre-filters → dedup (hash/URL/near-text) → one batched cheap-model scoring call → strong model only for scheduled Report composition, a bounded number of selected discussion researches, and (when enabled) urgency candidates**. The strong model therefore runs a handful of times per day, not once per post. (Alerts no longer use the model — see CONTEXT.md → Alert / Keyword rule; "Digest" was renamed "Report".)

This directly answers the project's core cost worry ("вызывать LLM на каждую новость дорого"): for a single user (~hundreds of posts/day) the dominant lever is **batching** (one scoring call per tick, not per post) plus free filters and dedup — not vector infrastructure.

## Considered Options

- **Naive: one LLM call per post** — simplest to write, but the cost the user explicitly wants to avoid.
- **Full `optimize.md` funnel now** — embeddings relevance gate + PostgreSQL/pgvector + semantic cache + LiteLLM gateway. Rejected for MVP: that doc's own priorities mark these P1–P3 ("when users and load appear"), and for one user they save cents while adding real infrastructure — against "просто и быстро".
- **Lean funnel** (chosen) — filters + dedup + batched cheap scoring + tiered strong model.

## Consequences

- **Deferred-but-seamed.** The embedding relevance gate, pgvector, semantic cache, and an LLM gateway are deliberately *not* built, but each sits behind a clean port so it can slot in under load without restructuring. The cheap/strong split is two methods on one `LLMClient` port; the first adapter targets **OpenRouter** (OpenAI-compatible, multi-model), so swapping to a gateway later is a new adapter, not a rewrite.
- A token/cost log table exists from day one — the only way to know where money actually burns.
- Risk for future maintainers/agents: "simplifying" the funnel back to LLM-per-post reintroduces the exact cost problem this records. Don't. The strong-model exception for selected comment research and semantic urgency is still bounded (default five threads per Report, two urgency sends per poll) and does not authorize per-Item scoring.
