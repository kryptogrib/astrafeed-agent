# Snapshot changes for agent polling

An agent owns its comparison cursor. AstraFeed does not infer whether a response
was read. After successfully processing a response, the agent stores its
`snapshot_id` and sends it as `since_snapshot_id` on a later agenda request.

## Requests

- `GET /agenda?since_snapshot_id=snap-A`
- `POST /a2mcp/astrafeed` with `{"since_snapshot_id":"snap-A"}`
- Both parameters may be used together: `snapshot_id` pins the target, while
  `since_snapshot_id` chooses the baseline.
- The baseline parameter applies to agenda calls. A2MCP rejects its combination
  with `query` or `story_id` with HTTP 422.
- JSON, Markdown and the REST HTML response describe the same comparison.

## Responses

Without a baseline the existing full response is retained.

With an available baseline the response has `response_mode: "delta"`,
`comparison_status: "ok"`, `compared_to`, and the target `snapshot_id`.
`stories` and `upcoming` contain only new or updated cards. Complete current
membership is given by `agenda_story_ids` and `upcoming_story_ids` in display order.
The comparison covers these two lists, not every searchable story in the database.
The repeated `lead_channels` ranking is omitted from delta content (an empty list).

`changes` contains:

| Field | Meaning |
| --- | --- |
| `new_stories` | Newly listed stories, each with ID, title, section and `previously_known`. True means the story was searchable in the baseline but not in its displayed lists. |
| `updated_stories` | Previously listed stories whose source evidence, sourcing labels or section changed. |
| `removed_stories` | Stories no longer in either displayed list; their ID, previous title and previous section. |

Each updated story contains:

- `added_publications`: stable ID, channel, link, original quote and publication
  time. `published_since_baseline` compares that time with baseline publication
  time. False can indicate a late arrival, newly analyzed post or changed grouping.
- `removed_publication_ids`: references no longer included, including those that
  aged out of the rolling window.
- `added_channels` / `removed_channels`: set differences of publication channels,
  rather than subtraction of counts calculated on potentially different coverage.
- `added_echo_channels`: newly added channels already marked as copies by stored
  signals; null if those signals are unavailable.
- `changed_quotes`: publication ID, source link/channel and before/after excerpts.
  A changed excerpt can reflect extraction or selection; it is not proof of a
  Telegram edit.
- `added_claims` / `removed_claims`: original displayed quotes with source links,
  claim kind and speaker. They describe evidence selection, not semantic novelty.
- `sourcing`: before/after stored confirmation label and attributed source names,
  or null when unchanged. A null side means the labels were unavailable.
- `caveat_drop`: before/after evidence pair when the narrowly detected qualifier
  loss appears, disappears or changes; null when unchanged. This tracks report
  wording evidence, not confirmation of the underlying event.
- `section` / `previous_section`: `agenda` or `upcoming`.

If a shared story lacks detailed publication references in either snapshot,
publication/channel differences and `changed_quotes` are null. Original displayed
claims and sourcing remain comparable. `comparison_limitations` includes
`publication_details_unavailable`; missing references never become invented IDs
or reported additions/removals.

Case and whitespace changes in quotes are ignored. Order, translated titles,
paraphrases, translations, freshness timestamps, price ticks, discussion summaries,
figure grouping and ranking changes alone do not resend a card. Retrieve a pinned
story card for its complete current context. Omissions do not imply a retraction or
the end of an event; new evidence does not imply that an event just happened.

Current coverage/limitations remain in the response, and `baseline_coverage` and
`baseline_limitations` expose the comparison's starting conditions. Collection or
analysis changes can affect report membership. This is a difference between stored
reports, not a claim of market activity growth.

The same snapshot returns empty change lists and no cards. If the baseline cannot
be loaded, return HTTP 200 with `response_mode: "full"`,
`comparison_status: "baseline_unavailable"`, `compared_to: null` and `changes: null`.
The requested ID remains in `since_snapshot_id`. Agents can rebuild state from the
full response. No retention duration is promised.

A blank baseline or a baseline published later than the target returns HTTP 422.
An unknown explicitly pinned target returns 404; no published target returns 503.
The target is resolved once before loading the baseline, so concurrent publication
cannot mix two target snapshots in one response. All work reads existing snapshots;
no collection, model, price API or client-state writes occur on this path.
