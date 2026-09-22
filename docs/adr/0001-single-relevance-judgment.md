# One relevance judgment routes both Alerts and Reports

> **Status: Partially superseded** by the `keyword-alerts-channel-modes` feature.
> Alerts are no longer produced by the relevance judgment: the LLM verdict now routes
> only **Report** or **Drop** (`Route.ALERT` was removed; the former "Digest" route is
> now **Report** / `Route.REPORT` — see CONTEXT.md → Report queue), and instant Alerts
> are driven by deterministic, model-free **Keyword rules** matched on raw Items — the
> "two independent pipelines" option this ADR rejected. The core decision below still
> holds for the Report path: one cheap batched judgment per Item builds the Report (see
> ADR-0002), and adding a Source means implementing collection only. Read "Digest"
> below as the historical name for "Report".

Every collected Item is judged once against the user's effective (cascaded) Interests, producing a single routing decision — **Alert**, **Report**, or **Drop** — rather than running separate alert and report pipelines. We do this so the reasoning about an Item happens once, the two delivery modes stay consistent, and adding a new Source later means implementing collection only — the judgment and routing are shared.

## Considered Options

- **Two independent pipelines** — a cheap keyword alerter plus a separate report summarizer. Rejected: duplicated logic, inconsistent verdicts (a post could alert but vanish from the report, or vice versa), and every new Source would need wiring into both.
- **One judgment, three-way route** (chosen) — the relevance verdict itself decides the delivery mode.

## Consequences

- The judgment produces the Report verdict cheaply (see ADR-0002); the "interrupt now" path is no longer part of the verdict — instant Alerts are handled separately by Keyword rules (`CONTEXT.md` → Keyword rule, Alert).
- Report-routed Items must be persisted as they are found, so the scheduled Report composes from accumulated verdicts rather than re-judging a time window.
