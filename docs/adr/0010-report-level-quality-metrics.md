# ADR-0010: Measure Report quality on rendered points, not scoring precision

## Status

Accepted (2026-09-10)

## Context

The first interest-matching experiment (`runs/interest-experiment-20260909T181457Z`)
reported **precision 68%** on scoring verdicts. Re-checking labels against the
posts that actually reach a Report showed that figure measures the wrong thing:

- Five of six "false positives" on arm A were repeats of stories already selected
  (Navier-Stokes, Anthropic researcher departure). Collapsing those repeats is
  `report/events.py`, which is off by default (`event_merge_enabled=False`).
- Scoring is judged *before* Report assembly, so a duplicate that event-merge
  would fold still counts as a false positive.
- `render_report` can still change the delivered set after the service: an
  invalid `EventBlock` reverts to N member bullets, and `subfacts_max` drops
  extra facts that exist on the block.

Retrieval (arm B) is not in production. The quality target is the rendered
Report: 100% of important stories, ≥90% of useful stories, 0 duplicate points,
no lost additional facts.

## Decision

1. **Trace the renderer.** `ReportTrace` records service stages *and*
   `rendered_points` via a `RenderObserver` on `render_report` (same optional
   contract as `PrefilterObserver`). Hooks only in `ReportService` are not
   enough.
2. **Score stories, not items.** Union-find over the frozen `duplicate_of`
   field. Metrics: `story_recall`, `important_recall`,
   `duplicate_points_cross_channel` / `duplicate_points_same_channel`,
   `noise_points`, `wrong_merge`, plus conservative `subfact_loss_candidates`.
   Final `lost_subfacts` is a manual checklist (`subfact_review.md`).
3. **Version the scoring contract.** `ScoreContract` is the triple (system
   prompt, pydantic schema, validators). `score-v7` is byte-compatible with the
   current scorer; `score-v8` adds `new_fact`/`evidence` and coerces `report`
   without them to `drop`. The client holds the contract at construction —
   no `if version ==` inside a shared validator.
4. **Pin Report-assembly settings across arms.** `scripts/report_eval.py`
   writes `editorial_mode`, `narrative_enabled`, `discussion_enabled`, and
   `event_merge` into `protocol.json`. Default editorial is on when a live LLM
   is used, because that is the Report we ship.

## Consequences

- Intra-channel paraphrases are diagnosed (`duplicate_points_same_channel`) but
  not "fixed" in this change: `_is_candidate_edge` stays cross-channel-only.
- Production `score_prompt_version` stays `score-v7` until an ablation on a
  *new* day's snapshot confirms v8 (or rewritten I02, or the strong model).
- `new_fact` is persisted on the Report queue but is not yet rendered into the
  Report gist.

## Follow-up: evidence and event evaluation repairs (2026-09-10)

- v8 evidence matching normalizes whitespace only. Paraphrased or stitched
  quotations still fail closed. Invalid v8 REPORT outputs remain outstanding
  for the existing bounded `score_coverage_retries` subset loop; valid verdicts
  and semantic DROP decisions are not retried. Exhausted failures are logged.
  Production stays on v7 until independent validation supports a change.
- Event recall additionally compares gists and gist/source context, within the
  existing cross-channel time and cost caps. These edges only nominate
  candidates; the judge decides whether their concrete events match.
- `event-judge-v2` reads bounded originals as well as gists and importance.
  `event_judge_source_max_chars` defaults to 4000 (0 disables originals), separate
  from the 280-character gist budget. This increases the judge input cost.
  It may return additional source quotes, checked against their own original
  text before rendering. A quote does not replace a distinct member gist.
  The existing subfact render cap remains; preserved facts still require review.
  Standalone practical demonstrations remain separate from release news.
- Trace retains nested component membership, judgments and exception fallbacks.
  Live judge replies must cover exactly the input components and local IDs.
  Eval records fallback failures and exits unsuccessfully after writing artifacts.
- `subfact_review_required` includes every manually specified additional fact,
  even if its source never reaches the Report. `subfact_coverage` is unknown
  until all such facts have explicit assessments; partial and lost facts are
  listed separately. Renderer drop candidates are diagnostic, not proof of
  semantic coverage. Assessments bind to the exact report SHA256.
- Live eval requires explicit `--provider MODEL=PROVIDER` pins for the configured
  models. It no longer assumes that every model has a StreamLake endpoint.
  New arms use new directories so previous responses cannot pollute a rerun.
- Dedup is judged on three numbers, printed first by `scripts/report_eval.py`:
  `rewrite_recall` = cross-channel rewrite stories collapsed into one rendered
  point / such stories the report showed at all (stories never shown are a
  recall defect, not a dedup one, and are excluded); `wrong_merge` = rendered
  points spanning more than one labelled story; detail loss = `subfact_lost` +
  `subfact_partial`. Same-channel repetition stays in
  `duplicate_points_same_channel` and never enters `rewrite_recall`.
- Recall feeds the judge a pair when the scorer's `event_key`
  (`actor|action|object`, no dates or numbers) matches within the 24-hour
  proximity window. A rewrite shares no wording with its original, so no lexical
  route sees it. The key proposes; the judge still decides, and an absent or
  one-segment key is empty and costs the item nothing.

See `docs/report-evaluation.md` for local commands and assessment format.
