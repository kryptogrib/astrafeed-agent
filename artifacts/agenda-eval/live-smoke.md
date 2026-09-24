# Crowd Pulse — live Docker smoke

## Run 1: 2026-09-24 14:48 UTC

Status: **incomplete; first snapshot is still processing**. This run confirms that the local HTTP service is reachable and reports its preparing state. It does not pass the agenda, story-card, or source-link acceptance checks.

Container: `hakaton-app-1`, healthy, host port `8000`.

Runtime state at capture: 528 publications, 494 queued, 0 snapshots. `/healthz` reports phase `analyze`, no last error, no successful cycle, and no budget block. The worktree is uncommitted; the health commit is the repository `HEAD`, not a complete identity for the running source tree.

### Captured responses

`GET /healthz` — HTTP 200

```json
{"status":"preparing","commit":"a4ec4bd51e15492dc6420ef9ccb209310aed8f6e","cycle":{"phase":"analyze","last_error":"","last_success_at":null,"queue_depth":494},"last_snapshot":null,"budget_blocked":false}
```

`GET /agenda` — HTTP 503

```json
{"status":"preparing"}
```

`GET /agenda?format=md` — HTTP 503

```json
{"status":"preparing"}
```

`GET /stories/search?q=ETH` — HTTP 503

```json
{"status":"preparing"}
```

### Remaining live acceptance

- [ ] First snapshot is published from the full configured source union.
- [ ] At least two channels have complete collection and processing in both 24-hour windows before growth is shown.
- [ ] `/agenda` JSON and Markdown refer to the same `snapshot_id`.
- [ ] Search a returned story, open its card, and verify its source link.
- [ ] Check every displayed quote against `text[start:end]`; check every displayed number against its linked quote.
- [ ] Confirm incomplete channels and queued publications do not create zero activity or growth.
- [ ] Record the successful commands, status codes, snapshot ID, and reviewed commit below.

## Successful limited bootstrap: 2026-09-24 15:48 UTC

Runtime commit: `438b81e6b9b119add27e000618d20940d5a195bd`. Local ignored `config.yaml` temporarily contains only `@cryptonftded` and `@whitelist1`; the full 21-channel union was **not** accepted by this run.

- `GET /healthz`: HTTP 200, `status=ok`, no cycle error or budget block, last snapshot `snap-20260924T154858Z`.
- `GET /agenda`: HTTP 200, same snapshot ID, `agenda_mode=empty_no_growth`, `stories=[]`, `channels_ok=2`, `comparable_channels=2`, `publications_processed=10/10`, `publications_queued=0` for the configured set.
- `GET /agenda?format=md`: HTTP 200; Markdown contains the same snapshot ID and says there are no new or growing stories on the comparable set.
- `GET /stories/search?q=VAR`: HTTP 200, one result, `st-82aaef69c0fa8d7d`.
- `GET /stories/st-82aaef69c0fa8d7d`: HTTP 200, same snapshot ID; source `https://t.me/whitelist1/7157`. The displayed quote `У Variational появились новые детали по $VAR, и теперь вся картина стала еще более ясной.` occurs exactly once in the stored original text of publication `4:7157`.

This proves the first live publish and read path, including source linkage and one exact quote. The two-channel sample produced no agenda card, so growth/card acceptance and the 60-post human review remain open. The backlog from previously configured channels remains persisted but is excluded from this snapshot's coverage.

## Full news bootstrap: 2026-09-24 16:39 UTC

Configured local channels: `@cryptonftded`, `@whitelist1`, `@crypto_hd`, `@cryptoattack24`. The 48-hour backlog was processed in chronological order. A partial assignment failure exposed that extraction had been removing queue entries too early; fix `38d395a` retains them until assignment completes. Three partially assigned posts were restored to the queue before this run.

- `GET /healthz`: HTTP 200, `status=ok`, commit `1081a855b97a7556c320837fafade7e131340a8a`, last snapshot `snap-20260924T163926Z`, `stale=false`, no budget block.
- `GET /agenda`: HTTP 200, `agenda_mode=full`, 10 growing cards, 4 comparable channels, 102/102 configured publications processed, 0 queued in this snapshot. The global SQLite queue still contains publications from previously configured channels; it is excluded from these coverage figures.
- `GET /agenda?format=md`: same snapshot ID as JSON.
- Public `GET https://cutememe.lol/agenda`: HTTP 200, same snapshot ID.
- Public `GET /stories/search?q=Payy`, `GET /stories/st-73928c3e4a74afa4`, and `GET /agenda?format=md`: HTTP 200; all refer to `snap-20260924T163926Z`. The detail exposes four linked publications.
- Public `POST https://cutememe.lol/a2mcp/astrafeed` with `{}`: HTTP 200; `result.snapshot_id` matches and `result.stories` has 10 cards. The endpoint was renamed from `/a2mcp/crowd-pulse` in commit `1081a85`.
- Checked all 27 displayed claims in the 10 agenda cards against their linked original texts stored in SQLite: 0 missing quotes. Checked numbers in every card explanation and claim paraphrase with `numbers_are_grounded`: 0 failures. These are code checks, not an independent truth check of the posts.

Examples of growth in the published snapshot: Payy, Binance HYPE listing, and CFTC crypto market rules each have two current channels, zero previous channels, and `growth=2`. Human judgment of story merging, quote usefulness, and the frozen 60-post evaluation is still pending.

## Progress recheck: 2026-09-24 14:52 UTC

The same container is still healthy and in `analyze`; no `last_error`, budget block, successful cycle, or snapshot is recorded. Queue depth is now 491 of 528 publications. `GET /agenda` and `GET /stories/search?q=ETH` still return HTTP 503 with `{"status":"preparing"}`. This confirms that the original bootstrap continues to make slow progress, but the live API acceptance remains incomplete.

## Progress recheck: 2026-09-24 15:00 UTC

The container remains healthy and the analysis loop is active with no reported error or budget block. Queue depth fell from 488 at 14:58 UTC to 486; the Agenda result table grew from 276 to 282 rows during the same observation window. There are still 0 snapshots, and `/agenda` returns HTTP 503 with `{"status":"preparing"}`. This is verified progress, but the first live snapshot and all card-level acceptance checks remain pending.

## Progress recheck: 2026-09-24 15:02 UTC

`/healthz` remains HTTP 200 with phase `analyze`, queue depth 485, no error, and no budget block. The database contains 528 publications and 0 snapshots; the queue fell by one since 15:00 UTC. Current bootstrap coverage has one incomplete source record among 21 sources. `/agenda` still returns HTTP 503. No growth claim can be accepted until the snapshot is published and both 24-hour windows are checked for completeness and processing.

At 15:03 UTC, the same cycle was still active and the queue had fallen to 483 (from 485 at 15:02); snapshots remain 0. Bootstrap coverage currently reports 20 of 21 source records complete. This is collection coverage only; processing of the remaining queue is still required before a comparable growth claim is valid.

## Processing cost evidence: 2026-09-24 15:05 UTC

The 528-publication bootstrap had 483 queued and no snapshot after roughly 57 minutes. The database had 45 extraction entries, 49 embedding entries, 143 settled budget reservations, and one unsettled `$0.50` reservation while the health endpoint remained in `analyze`. The current source set has four exact-text duplicate groups (24 extra publication rows), but one group is 22 empty texts; only three extra rows are non-empty exact duplicates. Thus exact-copy reuse can save little in this corpus. This capture does not attribute the unsettled reservation to a specific stage. Further instrumentation or batch processing is needed to identify and reduce the remaining serial cost.

## Stalled-item probe: 2026-09-24 15:09 UTC

Queue depth remained 483 between 15:05 and 15:09 UTC. The oldest queued item is publication `16:1043271`, 70 characters long, still reason `new`; its exact-text extraction cache entry is absent. There remains one unsettled `$0.50` budget reservation, the cycle remains in `analyze`, and there are 0 snapshots. This is consistent with a pending extraction request for that item, but the existing runtime exposes no stage-level in-flight identifier, so the attribution is not proven. The HTTP health check alone does not show useful agenda progress.

## Progress recheck: 2026-09-24 15:14 UTC

The queue advanced from 483 to 482: publication `16:1043271` now has a saved extraction result and the next oldest item is `16:1043272`. `/healthz` remains in `analyze`, `/agenda` still returns HTTP 503, one budget reservation remains unsettled, and there are still 0 snapshots. The previously slow item did eventually complete; observed cycle throughput remains far too low for acceptance without improvement, and stage-level request timing is still unavailable.

## Progress recheck: 2026-09-24 15:24 UTC

The healthy app remains in `analyze`. Queue depth is 476 of 528, with no snapshot and `/agenda` still preparing. Settled budget reservations total `$1.1761`; `$0.50` remains reserved in one unsettled request. No item-level timing or request stage is exposed by the current runtime.
