# ADR-0011: Comment findings are measured by entailment, not by taste

Status: Accepted
Date: 2026-09-11
Refines: [ADR-0002](0002-cost-aware-funnel.md) (bounded, cost-aware LLM stages),
[ADR-0010](0010-report-level-quality-metrics.md) (metric discipline)

## Context

The research module publishes claims attributed to other people ("Участник
пишет: …"). A wrong claim here is not a bad summary — it is a fabricated
quotation attached to a real discussion. ADR-0010 fixed the metric discipline
for Report-level quality, but its unit is a *story*; here the unit is a
*finding with evidence*, and the failure mode that matters is not "missed a
topic" but "said someone claimed something they did not".

ADR-0002 requires each LLM stage to be bounded and to fail closed. The research
module adds two paid stages (extract, verify) plus matching, and the question
this ADR answers is how we decide whether those stages earn their cost.

## Decision

1. **Two orthogonal axes.** Every published finding is labeled for
   *entailment* (does the cited comment actually support the attributed claim)
   and separately for *usefulness*. `publish_precision` requires both;
   `entailment_precision` isolates the honesty axis so a useful-but-fabricated
   finding can never be averaged away by useful-and-true ones. A claim that
   inverts its source is `severe_error` and is reported as `inversion_rate`.

2. **The gold standard is human, and says so.** `load_gold` rejects a label
   file without an `approved_by` attribution. The model under evaluation must
   not author its own exam, and an unattributed file is exactly what that would
   produce.

3. **Labels are bound to the rendered artifact.** `review.md` carries
   `rendered_sha256`; scoring refuses labels written against a different text.
   This mirrors ADR-0010's report-SHA binding, for the same reason: a label is
   a statement about a specific artifact, not about a pipeline version.

4. **Unknown is null, never a pass.** Each metric carries `numerator`,
   `denominator`, `pending`, and a `value` that is `None` when the denominator
   is zero or any dependent human label is still `не оценено`. Unknown cost and
   unmeasured latency are `null`, not `0` — a free-looking cost would make a
   paid stage look cheaper than it is.

5. **Recall is reported at two levels, and display caps stay in the
   denominator.** `recall_pre_display` measures what survived matching;
   `recall_final` measures what the reader saw. A gold finding hidden by the
   one-per-thread or two-per-channel cap remains in the denominator: that loss
   is the thing being measured, and excluding it would let a tighter cap
   improve the score.

6. **Misses are attributed structurally.** A missing gold finding is charged to
   the earliest stage that can be *shown* from the persisted run to have lost it
   (discovery / context / extraction / verifier / matching / display). While
   labels are incomplete, misses are listed as unattributed rather than guessed
   into a bucket.

7. **Timeouts and empty results are distinct outcomes.** Runtime timeouts are
   counted separately and never fold into "found nothing". `empty_result_
   precision` is taken before matching and excludes errored runs: correct
   silence is a success, a failure is not.

8. **Evaluation cannot publish.** The harness constructs a `ResearchService`
   and never a `ReportService`; no notifier exists in the eval path, so an
   evaluation run cannot send Telegram messages. Offline replay is the default;
   real model calls require `--live-llm` with explicit provider pins.

## Consequences

- A corpus with no labels scores nothing rather than scoring perfectly, so a
  green dashboard cannot be produced by not doing the work.
- Improving the display cap or the matching threshold shows up as a recall
  change rather than disappearing from the denominator.
- Cost per useful finding is only reported when every call reported its cost;
  partially-known spend is withheld instead of understated.
- Gold-vs-finding correspondence is quote-based (`quote_matches`), so it proves
  the material was still present at a stage — not that the claim is identical.
  Semantic equivalence stays a human judgment, recorded in `review.md`.
- Enabling the module in production (`shadow` → `on`) remains outside this ADR:
  it requires a separate, active deployment authorization.
