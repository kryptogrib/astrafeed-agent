# ADR-0009: Instructor for cheap-model scoring, with a layered reliability split

## Status

Accepted (2026-06-14)

## Context

The cheap-model scoring call (ADR-0002's one batched call per tick) was the
least reliable seam in the pipeline. A single hand-parsed JSON reply had to
survive: unparseable/missing-field structure, field-value noise (a stray
`alert` route, `importance=0` ×422 in prod), and silent item loss (a 147-Item
batch collapsed; a hallucinated id looped 25×; `by_id.get(id) -> DROP` dropped
omitted items with no signal). These are *different* failure modes with
different correct responses, but they were tangled in one parse-and-pray block,
so hardening one risked the others.

## Decision

Adopt **Instructor** (JSON mode) to wrap the injected client on the scoring
path, parsing each batch through a Pydantic `response_model` instead of
hand-parsed JSON. On top of that, split reliability into **four layers with
explicit ownership**, each handling exactly one failure mode:

1. **Parse-reask — Instructor (`score_parse_retries`).** STRUCTURAL failures
   only (unparseable JSON / a verdict missing a required field) are re-asked,
   bounded by `score_parse_retries`. On persistent structural failure `score()`
   raises, so the orchestrator leaves the watermark unadvanced and the items
   re-score next tick rather than being silently dropped.

2. **Field-normalize — non-raising validators + aggregate logging.**
   Field-value issues (unknown/legacy route → `drop`; out-of-range importance →
   clamp; `matched_interests` whole-string-match-first, comma-split only as a
   recorded fallback) are normalized by non-raising Pydantic validators. They
   never consume the parse-reask budget. Each validator *records* into a fresh
   per-call `_Anomalies` collector threaded through validation context (no
   cross-batch leakage); the adapter emits ONE aggregate WARNING per anomaly
   type per chunk (count + capped id sample), never one line per verdict.

3. **Coverage subset-retry + first-wins merge — adapter
   (`score_coverage_retries`).** Coverage is adapter-owned, the core silent-loss
   fix. After each pass the adapter computes which input ids got no verdict and
   re-scores JUST that missing subset (re-chunked), merging **first-wins** (a
   degenerate later duplicate cannot flip an outcome). Hallucinated ids (not in
   the sub-batch input), looping duplicates, and empty arrays are discarded and
   recorded against a whole-call `_CoverageAnomalies` collector. Anything still
   missing after the budget defaults to `Route.DROP` with one aggregate residual
   WARNING — replacing the previous silent drop.

4. **Batch-by-count — `score_max_items_per_batch`.** The chunker closes a
   sub-batch on EITHER the char budget OR an Item-count cap, whichever binds
   first, because the cheap model produces incoherent replies on mega-batches.
   This is still **batched, not per-Item** — it preserves ADR-0002's
   batched-scoring rule rather than weakening it.

**Deferred token ceiling (this slice).** Two optional `openrouter` config
fields — `score_token_limit_param`
(`null | "max_tokens" | "max_completion_tokens"`, default `null`) and
`score_max_tokens` (`int | null`, default `null`) — add an opt-in token ceiling.
A token-limit kwarg is sent on the scoring request ONLY when BOTH are non-null,
keyed by the operator-named parameter (providers disagree: `max_tokens` vs
`max_completion_tokens`). With the v1 defaults (both `null`) no token-limit
kwarg is sent, so an unsupported provider parameter can never break scoring. The
Item-count cap (layer 4) remains the primary runaway guard; this is belt-and-
suspenders for a future cost ceiling (PRD M5), seamed but not switched on.

## Alternatives considered

- **Keep hand-parsed JSON + ad-hoc retry.** What we had. The four failure modes
  stay tangled; every fix risks regressing another. Rejected.
- **Make field-value issues raise + re-ask.** Burns the parse budget on noise
  the model will likely repeat, and can abort a whole tick over one odd token.
  Normalizing non-raising keeps signal flowing; anomalies surface in aggregate.
- **Last-wins / per-Item scoring on under-coverage.** Last-wins lets a looped
  degenerate reply overwrite a good verdict; per-Item scoring reintroduces the
  exact cost problem ADR-0002 records. First-wins subset-retry recovers coverage
  while staying batched.
- **Always send a `max_tokens` ceiling.** Hard-coding one parameter name breaks
  providers that expect the other, and a too-low ceiling truncates the JSON
  reply into a structural failure. Hence the opt-in, both-or-neither gate.

## Consequences

- Operators get four independent knobs (`score_parse_retries`,
  `score_coverage_retries`, `score_max_items_per_batch`, and the token-limit
  pair) and aggregate, sampled WARNINGs instead of per-verdict log floods.
- The token ceiling is off by default; turning it on requires the operator to
  know which parameter their `cheap_model` accepts — the both-or-neither gate
  makes a half-configured ceiling a no-op rather than a 400.
- Risk for future maintainers/agents: collapsing these layers back into one
  parse-and-pray block, or switching field-value normalization to raising,
  reintroduces the silent-loss and tick-abort failures this records. Don't.
