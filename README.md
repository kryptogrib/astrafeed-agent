# Crowd Pulse

**Live agenda of crypto Telegram channels for AI agents, published as an OKX.AI A2MCP service.**

Crowd Pulse reads public Telegram channels, groups posts into stories, and every cycle publishes a snapshot: which stories are new or growing over the last 24 hours compared with the previous 24 hours, what the channels claim, and links to the original posts. An agent calls one endpoint and gets a verifiable answer. It gets no sentiment score and no trading advice.

Submitted to **OKX Dev Day 2026, track "Build a Company" (OKX AI)**.

| | |
|---|---|
| Live endpoint | `POST https://cutememe.lol/a2mcp/crowd-pulse` |
| Health | `GET https://cutememe.lol/healthz` |
| OKX.AI listing | _pending review_ |
| Demo video | _link_ |

## Try it

```sh
# Agenda of the current snapshot (the empty body is also what the OKX review sends)
curl -X POST https://cutememe.lol/a2mcp/crowd-pulse

# Search stories, then open one card on the same snapshot
curl -X POST https://cutememe.lol/a2mcp/crowd-pulse \
  -H 'content-type: application/json' -d '{"query": "ETH"}'
curl -X POST https://cutememe.lol/a2mcp/crowd-pulse \
  -H 'content-type: application/json' \
  -d '{"story_id": "st-...", "snapshot_id": "snap-..."}'

# Human-readable Markdown brief instead of JSON
curl -X POST https://cutememe.lol/a2mcp/crowd-pulse \
  -H 'content-type: application/json' -d '{"format": "md"}'
```

Request fields, all optional:

| Field | Meaning |
|---|---|
| `query` | Search by story title, entity, alias or claim text |
| `story_id` | Open one story card with its claims and source posts |
| `snapshot_id` | Pin follow-up calls to the snapshot returned earlier |
| `limit` | Search results, 1–50 (default 10) |
| `format` | `json` (default) or `md` |

The response is `{"service": "crowd-pulse", "action": "agenda" | "search" | "story", "result": {...}}`. Before the first snapshot the service answers `503 {"status": "preparing"}`. Plain REST mirrors of the same data are `GET /agenda`, `GET /stories/search?q=` and `GET /stories/{id}`.

## How it works

```
Telegram channels ──collect──▶ SQLite queue ──LLM extract + assign──▶ stories
                                                                        │
                        snapshot (atomic, per cycle) ◀── growth vs previous 24h
                                  │
             /a2mcp/crowd-pulse · /agenda · /stories  (read-only, no LLM on request)
```

- **Verifiable output.** Every quoted claim is an exact substring of the stored post (`text[start:end]`), and every story links to its `t.me` sources. A quote shows that a channel said something. It does not show that the event happened. The channel count measures spread, not independent confirmation.
- **Honest coverage.** Growth is shown only for channels that were fully collected and processed in both windows. A failed or queued channel never counts as zero activity. If nothing is comparable, the agenda says so and does not invent a trend.
- **Cheap requests.** The LLM (via OpenRouter) runs only in the background cycle and has a daily budget cap. HTTP requests read the published snapshot.
- **Layout.** Hexagonal: `domain/`, `application/`, `ports/`, `adapters/` (Telegram, SQLite, OpenRouter, HTTP). The OKX endpoint lives in [`src/astrafeed/adapters/http/a2mcp.py`](src/astrafeed/adapters/http/a2mcp.py).

**Channel selection.** The live demo watches a small set of public crypto news channels whose recent posts overlap on the same events. Otherwise there would be nothing to group into stories. The exact list is in the snapshot's coverage block. The list is not a sample of "the market", and answers describe only these sources.

## Monetization on OKX.AI

The service is listed free first so that the review can call it. The next step is a paid tier through the OKX Payment SDK (`okxweb3-app-x402`): the same endpoint answers `402` with an x402 `PAYMENT-REQUIRED` header and is settled in USDT0 on X Layer. The agenda stays free, and search and story cards become paid calls.

## Run it yourself

```sh
cp .env.example .env            # TELEGRAM_API_ID/HASH, OPENROUTER_API_KEY
cp config.example.yaml config.yaml
make install && make login      # creates the Telegram reader session
docker compose up -d --build    # app on :8000, data in the astrafeed-data volume

# Optional public HTTPS through a named Cloudflare Tunnel
# (CLOUDFLARE_TUNNEL_TOKEN in .env, public hostname → http://app:8000)
docker compose -f docker-compose.yml -f docker-compose.tunnel.yml up -d
```

`make check` runs lint, type checks and tests.

## Built during the hackathon

The collection engine (Telegram ingestion, filtering, dedup) comes from the earlier AstraFeed Token Brief project; see [PROVENANCE.md](PROVENANCE.md). The work for this hackathon starts after commit `a84b6e3` and is visible in `git log a84b6e3..HEAD`:

- the live agenda cycle: story extraction and assignment, 24h-vs-24h growth, atomic snapshots;
- quote grounding and the coverage rules;
- the read API (`/agenda`, `/stories`), the live Docker deployment and the smoke logs in [`artifacts/agenda-eval/live-smoke.md`](artifacts/agenda-eval/live-smoke.md);
- the OKX.AI A2MCP endpoint and public tunnel.

Product scope: [docs/product.md](docs/product.md). Plan: [docs/plans/community-pulse-mvp.md](docs/plans/community-pulse-mvp.md).
