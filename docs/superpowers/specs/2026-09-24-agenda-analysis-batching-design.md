# Agenda analysis batching and duplicate reuse

**Status:** design and written specification approved by the owner; implementation deferred until after the OKX Dev Day submission.
**Date:** 2026-09-24
**Scope:** reduce first-snapshot latency and repeat LLM work while preserving the Agenda data and evidence contract.

## Context and problem

The current Agenda cycle processes queued publications in chronological order. Extraction and assignment are awaited per publication, and assignment requests an embedding for one fragment at a time. The embedding adapter already accepts a list, and exact-text extraction caching already exists. Exact duplicate publications still go through story assignment independently. In the live bootstrap, the queue contains hundreds of publications and the first snapshot is not published until the cycle finishes, so this serial path delays the first usable response.

Live measurements on 2026-09-24 at 15:05 UTC: the bootstrap had 528 publications, 483 still queued, and no published snapshot after roughly 57 minutes. The database held 45 extraction cache entries, 49 embeddings, 143 settled budget reservations, and one unsettled `$0.50` reservation while `/healthz` reported `phase=analyze`. This does not identify which individual stage owns the open request, but confirms that a cycle can remain unavailable while serial analysis is underway. The exact-text inventory had four duplicate groups (24 redundant publication rows); one group was 22 empty-text posts, leaving only three redundant non-empty copies. Therefore exact-copy reuse alone cannot explain or eliminate the bootstrap delay; batching independent model stages and recording per-stage durations are needed to quantify the speedup.

Optimization must preserve the product's distinctions between entity, story, event, and author position. A vector similarity score is candidate discovery only: it cannot establish that two posts report the same event, contain the same date or amount, or express the same position. Every published claim still needs a quote verified against its own source text.

## Goals

- Reduce paid extraction and embedding calls by grouping cache misses and exact duplicate text.
- Improve throughput without making assignment depend on future posts or changing its chronological semantics.
- Keep each source publication, link, and channel vote distinct even when analysis is reused.
- Preserve strict quote, error, budget, queue, snapshot, and comparable-window guarantees.
- Make batching observable and bounded so failures can be retried without losing work.

## Non-goals

- Do not drop a post solely because it is close to another post in embedding space.
- Do not merge stories or events on similarity alone.
- Do not introduce a vector database, new embedding provider/model, parallel global story assignment, or a new product surface.
- Do not change the configured source set or weaken completeness rules for growth.

## Considered approaches

1. **Keep per-post processing.** This has the least implementation risk, but retains the observed serial latency and singleton embedding calls.
2. **Batch independent preparation; assign chronologically (recommended).** Extract unique exact texts in bounded batches and embed distinct cache misses in bounded batches. Then resolve dates and assign publications in chronological order, reusing assignment only under a strict context key. This improves independent expensive stages while preserving story-state order.
3. **Fully parallelize extraction, embedding, and assignment.** This may maximize throughput, but assignments could race to create or mutate stories and change which candidates later publications see. It also complicates deterministic replay and failure recovery.

The design uses approach 2. Similar, non-identical texts can share an extraction/embedding batch request, but each keeps its own keyed result and its own assignment decision.

## Proposed pipeline

### 1. Prepare a stable batch

For one cycle, gather the pending publication versions and sort by `(published_at, telegram_id, version_id)` using the existing stable chronological order. Retain every publication row. Compute its existing analysis key from publication identity, exact text hash, and classifier/preparation version. Group exact-text extraction cache misses by hash; never combine changed versions merely because they look similar.

Batch sizes are bounded configuration values. The implementation should choose conservative initial defaults based on provider request limits and the 60-post evaluation, and expose them in configuration rather than hard-coding an unchangeable large batch. A batch is chunked without changing input order.

### 2. Batch extraction with per-item validation

For each chunk, send unique exact texts to the structured extractor with stable item IDs. Require exactly one result per submitted ID, with no unknown or repeated IDs. A malformed batch is an error for the affected batch; do not silently map by response order or turn failures into empty analyses. Persist valid per-item results through the existing versioned extraction cache.

Run the existing quote verifier independently against each original publication text. A quote is usable only when it equals `text[start:end]`; apply the one-shot boundary correction only if the exact quote occurs once. Claims without a verified quote stay unpublished. Duplicate publications reuse the text-level extraction result, but each publication still receives validation against its own exact text and retains its own source link.

Time-relative values such as “today” and “yesterday” are resolved per publication after extraction. They must not be copied as absolute dates from another duplicate unless the source text explicitly provides that date.

### 3. Batch distinct embedding cache misses

Gather all distinct fragment-plus-entity embedding inputs produced by successful extraction items. Check the existing cache key `(model, preparation_version, exact_input)` and send only cache misses to the embedding adapter in bounded chunks. Validate result count, ordering/index mapping, dimensions, finiteness, and expected model metadata before persisting any vector from a response. Do not assume provider response order if explicit indices are available.

All embedding requests continue through the shared daily budget. On budget denial, timeout, or invalid response, leave the affected publications queued and do not publish a partial snapshot. Successfully persisted extractions and embeddings remain reusable on retry. Keep the last published snapshot available.

### 4. Assign in chronological order

After batch preparation, process publications in the existing chronological order. Resolve each publication's time-dependent facts, find candidates from eligible prior context, and assign stories/events/positions using only context available at that point. Do not allow a post in the same or later batch to become a candidate before its chronological turn.

#### Exact duplicate assignment reuse

Assignment may be reused only when all of these match:

- exact source text hash and extraction/classifier version;
- resolved time-dependent dates and relevant numeric/event attributes;
- the normalized fragment and entity inputs used for assignment;
- the ordered candidate/context fingerprint presented to the assigner;
- assignment prompt/schema/model version.

If any item differs, make a distinct assignment decision. Reused output is fanned out to each publication's own provenance/link records. It does not collapse publication rows or channel votes. This strict key means duplicates that occur in different temporal or story context may correctly receive different assignments.

#### Near duplicates

Non-identical, highly similar posts are not suppressed. They may be submitted in the same extraction or embedding batch, but receive per-item extraction output, quote verification, resolved metadata, and assignment. Similarity may prioritize a candidate for a model decision; it cannot itself cause a merge, skip, duplicate count, or independent-confirmation claim.

### 5. Candidate context size

Keep candidate retrieval bounded to the current semantic and lexical retrieval contract. The assignment prompt should include only selected candidates and the entity/story/event records needed to interpret those candidates, rather than the entire story corpus. The exact candidate limits remain the existing contract unless evaluation shows they need adjustment; any change must be measured for missed links and false merges.

## Failure handling and consistency

- Distinguish `processed_no_content` from extraction, embedding, validation, and assignment errors.
- Persist successful per-item work before proceeding where the repository transaction model permits, so a failed sibling in a batch does not cause already validated cache entries to be paid for again.
- If an item cannot complete the required analysis, it remains queued and coverage stays incomplete. Do not publish growth from incomplete windows.
- A cycle failure preserves the last complete snapshot. Restart/retry must be idempotent for caches, links, and source publication rows.
- A response-level batch error may be retried through the existing budget-aware retry rules; never retry without budget accounting.

## Observability

Expose structured cycle metrics in logs or health diagnostics:

- queued publications at start and end;
- unique exact texts and cache hits/misses;
- extraction batch count, item count, and failures;
- distinct embedding inputs and cache hits/misses;
- assignment decisions and exact-assignment reuse count;
- per-stage elapsed time and last error.

Do not include full post text, credentials, or user secrets in logs. These counters make it possible to distinguish provider slowness from low deduplication or a blocked queue.

## Acceptance criteria

1. Exact duplicate posts cause one extraction analysis per exact text/version while all publication/source records remain available.
2. Embedding cache misses are sent in multi-item requests where the provider supports them; cache hits are not resubmitted.
3. Every extraction response maps unambiguously to an input; missing, duplicate, or unknown IDs become explicit processing errors.
4. Every card quote passes the existing exact slice rule against its linked publication, including reused analyses.
5. Similar but non-identical posts are not discarded and can produce different events, dates, amounts, positions, or story assignments.
6. Assignment output is deterministic for a fixed input and context and observes chronological visibility of candidates.
7. Budget or provider failure leaves incomplete items queued and preserves the last snapshot; retries reuse valid completed stage results.
8. A new channel, failed fetch, or unprocessed publication cannot create growth or count as a zero window.
9. The 60-post human evaluation measures extraction/quote validity, event/date/amount preservation, story false merges, duplicate behavior, and runtime/call reduction against the current path.
10. Live Docker smoke confirms queue progress, first snapshot publication, API responses, quote links, and unchanged source coverage behavior.

## Validation plan

- Unit-level checks for keyed batch response mapping, chunk boundaries, cache key construction, vector response alignment, and context-fingerprint reuse.
- Regression checks for quote boundaries, date resolution, exact duplicate fan-out, near-duplicate distinction, chronological candidate visibility, budget denial, restart/resume, and snapshot preservation.
- Replay the frozen 60-post set and compare quality and provider-call counts with the current serial implementation. Human labels remain authoritative; do not accept a speedup that materially increases quote failures or story/event false merges.
- Run the live Docker cycle with the configured keys; inspect the top cards against linked posts and verify each source-window completeness state before treating the MVP as accepted.

## Open implementation choices

- Initial extraction and embedding chunk sizes, within provider request/token limits.
- Whether a batch-level structured-output failure is retried item-by-item or retried as a whole; choose based on budget accounting and reproducibility.
- Whether to add a configurable explicit request timeout if the current client timeout is too long for an operational cycle.

These are implementation choices for the plan and should be resolved with measured limits; they do not change the approved semantics above.
