# OKX Dev Day final fixes — implementation plan

**Goal:** Correct reviewer-facing claims, bound search input, and explain the build-period work and service economics before 25 Sep 2026, 23:59 UTC.

**Base:** `public/main` at `5f43f2b8`. The listed A2MCP service #13877 remains free. The live x402 payment flow and listing changes are outside this submission.

**Product constraint:** Keep exact linked quotes, code-computed aggregates, honest missing data, immutable snapshots, and read-only HTTP behavior. A search error must not silently become an agenda request. An empty A2MCP POST must return the agenda for the OKX self-check.

## Priority 1 — accuracy and request bounds (execute now)

- [x] Replace README's claim that every displayed claim is linked with the narrower quote guarantee; describe title language accurately. Lead with the buyer and the job the service performs.
- [x] Add HTTP tests for both A2MCP and REST: 200-character query accepted; 201 characters, empty string, and whitespace-only query return 422. Keep tests for `{}` and a POST with no body returning 200.
- [x] Apply the same 200-character and nonblank constraint to `AstraFeedRequest.query` and `/stories/search?q=`. Run focused tests, then `make check`.

## Priority 2 — working consumer and submission demo (next work)

- [ ] Add `examples/agent_poll.py`: save a successful `snapshot_id`, poll with `since_snapshot_id`, handle an unchanged snapshot and `baseline_unavailable`, and print only available confirmation and price fields. Do not describe a report change as a new market event.
- [ ] Record real output against a pinned earlier and later snapshot, then update README and the 2–4 minute video to show OKX.AI #13877, the callable service, and the consumer workflow. Verify every narrated claim against the recorded response.
- [ ] Publish an accessible video URL and put it in README and the submission form before the deadline.

## Priority 3 — provenance and economics (execute now)

- [x] Expand `PROVENANCE.md` with a baseline/build-period table: actual module paths, representative commit hashes, and `git diff --stat aa9a275..main -- src tests` as a reproducibility command. Link it from README.
- [x] Add a short README section naming the likely agent buyer, the unit of use, the read-path cost property, the shared background cost and its measured/limited status, OKX ecosystem value, and a clearly hypothetical monetization path. Do not claim revenue, demand, or a $9/day cost without measurements.
- [x] Add a one-page `docs/x402-plan.md` with a future separate paid service, illustrative price, 402/payment/retry flow, and why the listed free endpoint stays 200. Link it from README.
- [x] Add third-party attribution in `NOTICE`, keep `artifacts/README.md` as the frozen-research explanation, and explain why `/healthz` exposes spend.

## Priority 4 — release check (after priorities 1–3 and demo)

- [ ] Read `docs/ops.md`; do not start a local Telegram client. Run `make check`, deploy once, and verify commit, fresh snapshot, 200 for empty POST, 422 for invalid searches, and a real search hit.
- [ ] Verify README links on public GitHub and run a focused judge review of the changed criteria. Keep the listed endpoint free; a paid integration requires its own fully tested service and listing decision.

## Acceptance for this work session

The checked priority 1 and 3 items pass `make check`. Priority 2 and 4 remain explicit follow-up work; no payment or production deployment is claimed from this session.
