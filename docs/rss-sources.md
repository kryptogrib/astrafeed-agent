# RSS source integration

Configured RSS URLs use the same raw publication cache and agenda pipeline as
Telegram posts. Each publisher gets a stable source row keyed by `rss_url`.
Existing SQLite deployments have `source.telegram_id NOT NULL`, so RSS rows use
a stable negative internal surrogate; the domain model exposes `telegram_id=None`
for those rows. This avoids rebuilding a table referenced by raw items and
coverage during a live upgrade. Do not send that surrogate to Telegram.

Feed history is a rolling publisher-controlled tail. A successful fetch counts
as complete for an interval only when its oldest parsed entry reaches the
interval start. Missing history, malformed feeds, HTTP errors and timeouts are
recorded as incomplete coverage for that feed. Articles already returned are
kept, but incomplete history cannot contribute to comparable growth. The
original article URL remains the evidence link; summaries are inputs to story
extraction, not full-text copies of articles.

## Reddit

`reddit_feeds` contains individual subreddit RSS URLs. The collector combines
them into one `/new/.rss?limit=100` request per cycle because Reddit throttles
rapid requests for separate feeds. Each returned post is stored under its own
subreddit source row and displayed as `r/<subreddit>`; a story's source count
therefore does not collapse all of Reddit into one source. This feed is limited
to recent posts and does not include comments. If its oldest entry does not
reach the comparison window start, all Reddit sources report incomplete
coverage. A busy combined feed can omit posts beyond its 100-entry tail.
