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
