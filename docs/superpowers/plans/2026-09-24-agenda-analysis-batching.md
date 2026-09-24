# Agenda Analysis Batching Implementation Plan

**Status:** deferred until after the OKX Dev Day submission. The live assignment context and queue reliability fixes landed separately before this plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` for native execution. Work task by task and keep the checkboxes current.

**Goal:** Reduce Agenda bootstrap latency and repeated paid calls by batching exact-text extraction and unique embedding misses, while preserving per-publication evidence and chronological story assignment.

**Architecture:** Prepare extraction and embedding results in bounded batches before assignment. Key every extraction response by stable analysis ID and every embedding by exact input/cache key; validate the whole mapping before persistence. Then assign each publication in chronological order, reusing an assignment only when its complete resolved inputs and candidate context match.

**Tech Stack:** Python 3.12, Pydantic, Instructor/OpenAI-compatible async client, SQLite, FastAPI, pytest, existing budget wrapper.

**Spec:** `docs/superpowers/specs/2026-09-24-agenda-analysis-batching-design.md`

## Global Constraints

- HTTP handlers do not call the LLM.
- The collection set remains the Telegram-ID-deduplicated union of `channels` and `news_channels`.
- Keep entity, story, event, and author position separate.
- A quote is usable only when `text[start:end] == quote`; boundary correction is allowed only for one exact occurrence.
- Similarity retrieves candidates; it never suppresses posts or proves a merge.
- Resolve relative dates per publication and assign stories in `(published_at, publication_id)` order using only earlier candidates.
- One channel gives one vote per story per window; incomplete or unprocessed windows never create zero activity or growth.
- All paid requests, retries, and embeddings continue through `BudgetedClient` and the existing `$5/day` budget.
- Budget/provider failure preserves queued work and the last published snapshot.

## Review Focus

1. Reordered, missing, repeated, or unknown extraction IDs and embedding indices must not be associated by response position; Task 1 and Task 3 pin mapping and cardinality.
2. An exact text reused across different publication dates must resolve “today/yesterday” separately; Task 2 pins per-publication resolution.
3. Similar but non-identical posts with different dates, values, or positions must remain separate inputs and retain distinct verified quotes; Tasks 2 and 5 pin this.
4. A failed batch or budget denial must leave affected work queued and keep the latest snapshot; Task 4 pins retry and snapshot behavior.
5. A channel with a queued item or incomplete collection cannot enter the comparable set; Task 7 reruns the snapshot/window regression checks and live smoke.

---

### Task 1: Add keyed batch extraction to the port and OpenRouter adapter

**Files:**
- Modify: `src/astrafeed/domain/agenda.py`
- Modify: `src/astrafeed/ports/agenda.py`
- Modify: `src/astrafeed/adapters/llm/agenda.py`
- Create: `tests/adapters/test_agenda_llm.py`
- Modify: extraction test doubles in `tests/application/test_agenda_cycle.py`, `tests/application/test_agenda_extract.py`, and `tests/application/test_agenda_assign.py`

**Interfaces:**
- Add immutable `ExtractionRequest(analysis_key: str, text: str)` in `domain/agenda.py`.
- Extend `OpenExtractor` with `async def extract_many(self, items: Sequence[ExtractionRequest]) -> dict[str, ExtractionResult]`.
- Keep `OpenRouterExtractor.extract(text)` as a one-item wrapper around `extract_many`, returning that item's result.
- Use `analysis_reuse_key(text_hash(text), CLASSIFIER_VERSION)` as the request ID.

- [ ] **Step 1: Write adapter tests for keyed batch responses.** Cover normal response order, reversed response order, duplicate response ID, unknown response ID, omitted response ID, and the single-item wrapper.

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrafeed.adapters.llm.agenda import ExtractionBatchSchema, OpenRouterExtractor, _BatchItemSchema
from astrafeed.domain.agenda import ExtractionRequest, analysis_reuse_key, text_hash

@pytest.mark.asyncio
async def test_extract_many_maps_results_by_analysis_key_even_if_response_is_reordered(monkeypatch):
    first = ExtractionRequest(analysis_reuse_key(text_hash("one")), "one")
    second = ExtractionRequest(analysis_reuse_key(text_hash("two")), "two")
    monkeypatch.setattr("astrafeed.adapters.llm.agenda._wrap_with_instructor", lambda client: client)
    response = ExtractionBatchSchema(items=[
        _BatchItemSchema(id=second.analysis_key),
        _BatchItemSchema(id=first.analysis_key),
    ])
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    extractor = OpenRouterExtractor(client, "model")

    result = await extractor.extract_many([first, second])

    assert set(result) == {first.analysis_key, second.analysis_key}
    assert result[first.analysis_key].text_hash == text_hash("one")
```

- [ ] **Step 2: Run the focused adapter test and confirm it fails on the missing batch method/schema.**

Run: `pytest tests/adapters/test_agenda_llm.py -q`

Expected: FAIL because `OpenRouterExtractor.extract_many` and the keyed batch schema are not implemented.

- [ ] **Step 3: Implement the keyed structured batch schema and adapter.** Each response item contains `id`, `fragments`, and `no_substantive_claims`; map IDs to submitted requests, reject any duplicate/unknown/missing ID, convert each item with the existing `schema_to_extraction(text, item_schema)`, and return a dict keyed by ID. Do not zip results by array position.

```python
class _BatchItemSchema(BaseModel):
    id: str
    fragments: list[_FragmentSchema] = Field(default_factory=list)
    no_substantive_claims: bool = False

class ExtractionBatchSchema(BaseModel):
    items: list[_BatchItemSchema]
```

- [ ] **Step 4: Run adapter tests and the existing extraction tests.**

Run: `pytest tests/adapters/test_agenda_llm.py tests/application/test_agenda_extract.py -q`

Expected: PASS; reordered responses map correctly and malformed IDs raise a typed batch error.

### Task 2: Batch cache-miss extraction and preserve per-publication validation

**Files:**
- Modify: `src/astrafeed/application/agenda_extract.py`
- Modify: `src/astrafeed/config.py`
- Modify: `src/astrafeed/cli.py`
- Modify: `tests/application/test_agenda_extract.py`

**Interfaces:**
- Add `async def analyze_publications(store, extractor, publications, *, batch_size: int) -> dict[str, ExtractionResult]`, keyed by `publication_id`.
- Retain `analyze_publication` as a one-publication wrapper that calls the batch path with `batch_size=1`.
- Add validated `Settings.agenda_extraction_batch_size: int = Field(default=4, gt=0)`; allow YAML and `ASTRAFEED_AGENDA_EXTRACTION_BATCH_SIZE` configuration.

- [ ] **Step 1: Write application tests for unique-text grouping, cache hits, quote validation per publication, and relative-date resolution.** Include an exact duplicate at two publication dates and two similar non-identical posts.

```python
assert extractor.batch_calls == [[analysis_reuse_key(text_hash(shared_text))]]
assert result_by_publication["1:old"].fragments[0].claims[0].dates == ("2026-09-21",)
assert result_by_publication["2:new"].fragments[0].claims[0].dates == ("2026-09-22",)
assert similar_text_key in extractor.submitted_keys
```

- [ ] **Step 2: Run the extraction tests and confirm grouping/date/quote cases fail before implementation.**

Run: `pytest tests/application/test_agenda_extract.py -q`

Expected: FAIL because the application currently extracts one publication at a time.

- [ ] **Step 3: Implement `analyze_publications`.** Sort publications by `(published_at, publication_id)`, group cache misses by analysis key, send bounded chunks through `extract_many`, validate/verify each result against its exact source text, persist valid extraction results, then resolve time-relative dates separately for every publication. Keep provider/validation failures as `status="error"`, enqueue affected publication IDs, and never convert them to `empty`.

```python
requests = [ExtractionRequest(key, publication.text) for key, publication in unique_cache_misses]
batch_result = await extractor.extract_many(requests)
```

- [ ] **Step 4: Verify cache behavior and error semantics.** Re-running an exact text must issue no extraction request; a malformed batch must leave those publications queued with an error reason; a successful no-content result must be cached as `empty`.

Run: `pytest tests/application/test_agenda_extract.py -q`

Expected: PASS.

### Task 3: Batch unique embedding misses and validate provider alignment

**Files:**
- Modify: `src/astrafeed/adapters/llm/agenda.py`
- Modify: `src/astrafeed/application/agenda_assign.py`
- Modify: `src/astrafeed/config.py`
- Modify: `src/astrafeed/cli.py`
- Modify: `tests/application/test_agenda_assign.py`
- Modify: `tests/adapters/test_budgeted_embeddings.py`

**Interfaces:**
- Add `async def prepare_embeddings(store, embedder, inputs: Sequence[str], *, batch_size: int) -> dict[str, list[float]]`; the returned map is keyed by exact embedding input text.
- Change `assign_publication` to consume a preloaded `Mapping[str, list[float]]`; it must not call `embedder.embed([text])` itself.
- Add `Settings.agenda_embedding_batch_size: int = Field(default=64, gt=0)` and `ASTRAFEED_AGENDA_EMBEDDING_BATCH_SIZE` support.

- [ ] **Step 1: Write tests for deduped inputs, cache hits, bounded chunks, response index ordering, wrong response count, wrong dimensions, non-finite values, and budget denial.** The fake embedding response must include explicit indices so a shuffled response tests index mapping.

```python
vectors = await prepare_embeddings(store, embedder, ["a", "b", "a"], batch_size=2)
assert embedder.calls == [["a", "b"]]
assert set(vectors) == {"a", "b"}
```

- [ ] **Step 2: Run embedding tests and confirm they fail because assignment embeds singleton inputs.**

Run: `pytest tests/application/test_agenda_assign.py tests/adapters/test_budgeted_embeddings.py -q`

Expected: FAIL on batch preparation/alignment behavior.

- [ ] **Step 3: Implement preparation over unique cache misses.** Resolve cache keys with the existing `(model, preparation_version, exact_input)` function, chunk only misses, sort provider items by explicit index, require a contiguous index set and exact result count, validate 1536 finite numeric values per vector, and persist a chunk only after all its vectors pass validation. Keep all requests on the existing `BudgetedClient`.

```python
unique = list(dict.fromkeys(inputs))
cached = {text: vector for text in unique if (vector := await store.get_embedding(embedding_cache_key(text))) is not None}
```

- [ ] **Step 4: Remove singleton embedding calls from `assign_publication`.** Look up its exact `embedding_input` in the prepared map; missing input raises an explicit processing error and leaves the publication queued.

- [ ] **Step 5: Run embedding and assignment tests.**

Run: `pytest tests/application/test_agenda_assign.py tests/adapters/test_budgeted_embeddings.py -q`

Expected: PASS; cache hits are not resubmitted, all output vectors map to exact inputs, and budget denial does not mark posts processed.

### Task 4: Orchestrate prepared batches, then assign chronologically

**Files:**
- Modify: `src/astrafeed/application/agenda_cycle.py`
- Modify: `src/astrafeed/application/agenda_assign.py`
- Modify: `tests/application/test_agenda_cycle.py`
- Modify: `tests/application/test_agenda_assign.py`

**Interfaces:**
- `run_cycle(..., extraction_batch_size: int = 4, embedding_batch_size: int = 64)` performs collect → extraction batches → embedding batches → chronological assignment → snapshot.
- `assign_publication(store, assigner, publication, extraction, embeddings)` handles one publication in existing `(published_at, publication_id)` order.

- [ ] **Step 1: Write a cycle test with several publications whose extraction and embedding inputs can be batched, but whose assignment fake records call order and candidate visibility.** Assert every assignment sees only candidates with an earlier `published_at`.

- [ ] **Step 2: Run the cycle test and confirm it fails because the current cycle awaits extraction/embedding per publication.**

Run: `pytest tests/application/test_agenda_cycle.py -q`

Expected: FAIL on batch-call grouping/order assertions.

- [ ] **Step 3: Change `run_cycle` to gather/sort pending publications once, call `analyze_publications`, collect embedding inputs from successful extractions, call `prepare_embeddings`, then run the existing publication loop chronologically with precomputed values.** The serial loop is retained only for assignment and story-state mutation.

```python
pending.sort(key=lambda pub: (pub.published_at, pub.publication_id))
extractions = await analyze_publications(store, extractor, pending, batch_size=extraction_batch_size)
embeddings = await prepare_embeddings(store, embedder, collect_embedding_inputs(pending, extractions), batch_size=embedding_batch_size)
for publication in pending:
    await assign_publication(store, assigner, publication, extractions[publication.publication_id], embeddings)
```

- [ ] **Step 4: Pin failure behavior.** Extraction errors remain queued and do not become empty; budget denial or embedding batch failure aborts publication of a new snapshot; valid extractions/vectors from completed prior chunks remain cached; the previous snapshot remains readable.

- [ ] **Step 5: Run cycle, extraction, and assignment tests.**

Run: `pytest tests/application/test_agenda_cycle.py tests/application/test_agenda_extract.py tests/application/test_agenda_assign.py -q`

Expected: PASS; assignment order is deterministic and the previous snapshot survives a failed embedding batch.

### Task 5: Cache exact duplicate assignments only under a full context fingerprint

**Files:**
- Modify: `src/astrafeed/domain/agenda.py`
- Modify: `src/astrafeed/ports/agenda.py`
- Modify: `src/astrafeed/adapters/llm/agenda.py`
- Modify: `src/astrafeed/adapters/repository/sqlite/agenda.py`
- Modify: `src/astrafeed/adapters/repository/memory_agenda.py`
- Modify: `src/astrafeed/application/agenda_assign.py`
- Modify: `tests/adapters/test_agenda_sqlite.py`
- Modify: `tests/application/test_agenda_assign.py`

**Interfaces:**
- Move the serializable assignment value object to the domain as `StoryAssignment`; keep `adapters.llm.agenda.Assignment` as an alias during migration of existing imports.
- Add `async def get_assignment(cache_key: str) -> StoryAssignment | None` and `async def save_assignment(cache_key: str, value: StoryAssignment) -> None` to `AgendaStore` and both stores.
- Add stable `ASSIGNMENT_VERSION = "story-assign/v1"`; `StoryAssigner.cache_identity` returns the model identity.

- [ ] **Step 1: Write tests for persistent assignment round-trip and for cache miss when any key component changes:** exact hash/version, resolved date or number, normalized fragment/entity input, ordered candidate fingerprint, relevant context fingerprint, or assignment/model version.

```python
key_a = assignment_reuse_key(text_hash=text_hash, resolved_claims=claims, context=context_a, assigner_id="model/v1")
key_b = assignment_reuse_key(text_hash=text_hash, resolved_claims=claims, context=context_b, assigner_id="model/v1")
assert key_a != key_b
```

- [ ] **Step 2: Run the new cache tests and confirm they fail because assignment results are not persisted.**

Run: `pytest tests/adapters/test_agenda_sqlite.py tests/application/test_agenda_assign.py -q`

Expected: FAIL on missing assignment cache operations/key helper.

- [ ] **Step 3: Implement the typed assignment value and repository cache.** Register the domain dataclass in SQLite JSON encode/decode, store by full fingerprint, and mirror the API in the in-memory store.

- [ ] **Step 4: Build deterministic fingerprints and use the cache.** Sort entities/stories/events by stable ID and preserve candidate order with stable tie-breaks. Include only selected candidates and their linked story/event/entity records in both the prompt and fingerprint. On a cache hit, still apply the assignment to the current publication and create its own `StoryLink`/source provenance; never collapse publication rows or channel votes.

- [ ] **Step 5: Add behavior tests.** Exact identical posts with identical context call the assigner once and create two source links; a different publication date, candidate list, event amount, or author position calls the assigner again. Similar but non-identical posts retain their separate verified quotes and decisions.

- [ ] **Step 6: Run assignment and SQLite persistence tests.**

Run: `pytest tests/application/test_agenda_assign.py tests/adapters/test_agenda_sqlite.py -q`

Expected: PASS; only full-context matches reuse decisions.

### Task 6: Add bounded request timeout and stage-level cycle telemetry

**Files:**
- Modify: `src/astrafeed/config.py`
- Modify: `src/astrafeed/cli.py`
- Modify: `src/astrafeed/domain/agenda.py`
- Modify: `src/astrafeed/application/agenda_cycle.py`
- Modify: `src/astrafeed/application/agenda_query.py`
- Modify: `tests/application/test_agenda_cycle.py`
- Modify: `tests/adapters/http/test_agenda.py`

- [ ] **Step 1: Write tests for stage counters/timings and for an explicit OpenAI transport timeout flowing through `BudgetedClient` with SDK retries disabled.** Metrics must contain counts and durations only, never post text or credentials.

- [ ] **Step 2: Run focused tests and confirm no stage metrics or explicit Agenda timeout is present.**

Run: `pytest tests/application/test_agenda_cycle.py tests/adapters/http/test_agenda.py -q`

Expected: FAIL on the new metrics/timeout assertions.

- [ ] **Step 3: Add `Settings.agenda_request_timeout_seconds: float = Field(default=180, gt=0)` and `ASTRAFEED_AGENDA_REQUEST_TIMEOUT_SECONDS`; construct the async OpenAI client with this explicit timeout.** `BudgetedClient` already sets SDK `max_retries=0`; preserve that behavior so hidden retries do not bypass spend reservations.

- [ ] **Step 4: Record per-stage elapsed seconds and item/call/cache/failure counts in cycle diagnostics and structured logs.** Include queue-at-start/end, extraction unique/cache-hit counts, embedding unique/cache-hit counts, assignment decisions/reuse counts, and last failed stage. Extend health diagnostics without changing `/agenda` response semantics or exposing message text.

- [ ] **Step 5: Run focused tests and inspect one captured log record for the absence of raw post text and secrets.**

Run: `pytest tests/application/test_agenda_cycle.py tests/adapters/http/test_agenda.py -q`

Expected: PASS; timeout remains budget-accounted, metrics are serializable, and current HTTP clients remain read-only with respect to LLM calls.

### Task 7: Verify full contract, replay evaluation, and live Docker snapshot

**Files:**
- Modify: `artifacts/agenda-eval/live-smoke.md`
- Modify: `artifacts/agenda-eval/protocol.md` only if measured batch/runtime metadata needs recording
- Review: `artifacts/agenda-eval/manual-review.md`
- Review: `docs/product.md`, `docs/plans/community-pulse-mvp.md`, and the approved design spec

- [ ] **Step 1: Run the targeted Agenda suite and then the full repository suite, including `test_comparable_channels_require_complete_processing_of_both_windows` and `test_new_channel_without_backfill_does_not_create_growth`.**

Run: `pytest tests/domain/test_agenda.py tests/application/test_agenda_cycle.py tests/application/test_agenda_extract.py tests/application/test_agenda_assign.py tests/adapters/test_agenda_sqlite.py tests/adapters/test_budgeted_embeddings.py tests/adapters/test_agenda_llm.py tests/adapters/http/test_agenda.py -q`

Then run: `pytest -q`

Expected: both commands exit 0; record actual totals, do not rely on the earlier 274-test report.

- [ ] **Step 2: Run the frozen sample verifier and capture before/after operation counts on the 60-post set.**

Run: `python3 artifacts/agenda-eval/sample.py`

Expected: `ok ids=60 prev=30 curr=30 search=10 inclusions=20`; replay reports call counts, wall time, extraction/quote errors, missed links, and false story/event merges for human review.

- [ ] **Step 3: Complete the human labels in `artifacts/agenda-eval/manual-review.md`.** Use the original Telegram text and links; keep preliminary model outputs separate from the labels and record adjudicated quote, date, amount, event, position, and story-group judgments.

- [ ] **Step 4: Rebuild and run the live Docker service with configured keys.**

Run: `docker compose up --build -d`

Poll `GET /healthz` until the cycle leaves `analyze`; capture `GET /agenda`, `GET /agenda?format=md`, `GET /stories/search?q=ETH`, and one `GET /stories/{id}`. If a budget/provider failure occurs, record the retained snapshot and queue state instead of calling it a pass.

- [ ] **Step 5: Verify source-window coverage, quote slices, numbers, and links from live output.** The check must prove every surfaced quote against its linked publication, every number against its quote, and no new/incomplete source or queued publication creates a growth claim. JSON and Markdown must use the same `snapshot_id`.

- [ ] **Step 6: Update `live-smoke.md` with command outputs, UTC timestamp, snapshot ID, exact build commit/source identity, reviewed cards, coverage limitation, batch sizes, settled budget cost, queue depth, and cycle duration.** Leave any failed acceptance box unchecked.

## Coverage Self-Review

- Keyed extraction result validation: Task 1.
- Per-source quote verification and date resolution: Task 2.
- Embedding cache/version/cardinality/dimension checks: Task 3.
- Chronological assignment and snapshot/budget handling: Task 4.
- Exact assignment reuse, near-duplicate distinctions, source fan-out, and bounded context: Task 5.
- Bounded request time and operational visibility: Task 6.
- Comparable windows, 60-post human evaluation, API, Docker, cards, and smoke evidence: Task 7.

The approved spec's requirements are covered. No implementation has been started in this plan-only step.
