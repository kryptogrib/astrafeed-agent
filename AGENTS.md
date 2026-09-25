# AGENTS.md

AstraFeed turns public crypto Telegram, RSS, Reddit and X posts into a verifiable
24-hour agenda. Every displayed quote is a verbatim span of a linked post; every
aggregate is computed by code, not by the LLM.

## Map

```
collect ──► extract ──► assign ──► snapshot ──► localize ──► publish (immutable)
 source/     agenda_     agenda_     agenda_      agenda_         SQLite
 *_ingest    extract     assign      snapshot     localize
                                     + signals
                                                                   │
HTTP (read-only, no LLM) ◄─────────────────────────────────────────┘
  /agenda  /stories/search  /stories/{id}  /healthz  POST /a2mcp/astrafeed
```

| Layer | Path | Rule |
|---|---|---|
| Domain | `src/astrafeed/domain/agenda.py` | Pure rules: quote spans, windows, growth, number grounding. Imports nothing from adapters or application. |
| Ports | `src/astrafeed/ports/` | Protocols for stores, extractor, assigner, verifier, translator. |
| Application | `src/astrafeed/application/agenda_*.py` | The cycle, snapshot math, evidence signals, `since_snapshot_id` deltas. `agenda_query` builds JSON; `agenda_markdown` and `agenda_html` render only from that JSON, so every format shows the same snapshot. |
| Adapters | `src/astrafeed/adapters/` | Telethon/RSS/Reddit/Xpoz sources, OpenRouter LLM, SQLite, FastAPI, OKX prices. |

The layer rules are enforced by `.importlinter`; HTTP adapters cannot import the
cycle or any LLM adapter, so a read request never spends money.

`report/`, `pipeline/` and `prefilter/` are the earlier Token Brief engine
([PROVENANCE.md](PROVENANCE.md)); the agenda reuses only its source `Item` model.
`docs/research/` and `artifacts/` are frozen experiments, not imported by `src/`.

## Verify

```sh
make check    # ruff, ruff format, mypy, import-linter, pytest (seconds, no network)
```

Invariant → test table: [README.md#invariants-the-code-enforces](README.md#invariants-the-code-enforces).
Live state: `curl https://cutememe.lol/healthz` (commit, cycle phase, snapshot id, spend).

## Conventions

- Tests name the behaviour they protect; regressions from production cite the snapshot id.
- LLM output is never trusted as evidence: quotes are re-verified against post text,
  paraphrases and translations may not introduce numbers absent from their quotes.
- Missing data is reported as missing (`null`, `limitations`, `coverage`), never as zero.

## Product and plan (Russian)

Прочитай [продуктовый ориентир](docs/product.md) и сверяй с ним предложения и
изменения поведения. Технические контракты MVP — в [плане](docs/plans/community-pulse-mvp.md),
контекст унаследованного движка — в [CONTEXT.md](CONTEXT.md).
