# Follow-up: `context_incomplete` does not mean missing context

Found while building the transfer snapshot (`artifacts/reaction-subject/transfer/snapshot.json`).
Not fixed here: the adapter is not changed during the reaction-subject experiment. The experiment
uses per-example `missing_parent` and `nontext_parent` flags instead of this flag.

## What the code does

`src/astrafeed/adapters/source/telegram.py`:

- line 591: a media-only comment is recorded as `parent_issues[comment.external_id] = "nontext"`,
  keyed by the comment itself, whether or not anything replies to it;
- line 692: a fetched parent without text is also recorded as `"nontext"`;
- line 702: `missing_parent_ids` excludes `"nontext"`, as the docstring (lines 524-528) intends;
- line 715: `context_incomplete=interrupted or bool(parent_issues)` does not exclude it, so any
  media-only comment in a thread sets the flag.

The DB stores only the boolean, not `parent_issues`, so the reason cannot be recovered afterwards.

## Probe on the transfer snapshot

`sqlite3 -readonly astrafeed-transfer.db < docs/research/context_incomplete_probe.sql`
(db md5 `1c714bad0d7dd7e07d1f2c5032fd8dce`):

| check | value |
|---|---|
| fetched threads | 183 |
| threads with `context_incomplete` | 79 |
| of them with a media-only comment | 79 |
| flagged threads without a media-only comment | 0 |
| replies with a parent id | 745 |
| replies whose parent is not stored in the same thread | 20 |
| threads with such replies | 11 |
| of those threads, not flagged | 6 |

So the flag marks exactly the threads with a media-only comment and misses 6 of the 11 threads
where a parent is really absent. Parent lookup is by (source, post, comment id); numeric ids from
other threads are not matched.

## Proposed fix (separate change)

Compute `context_incomplete` from `interrupted or missing_parent_ids`, keep `nontext` as a separate
signal (for example, a count of media-only comments), and add a test with a media-only comment
and no missing parent. Existing rows stay as they are until a rescan.
